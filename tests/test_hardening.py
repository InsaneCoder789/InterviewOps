"""One test for each defect found by reviewing the whole codebase."""

from datetime import timedelta
from smtplib import SMTPException
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import authenticate
from django.core import mail
from django.core.cache import caches
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import Invitation, User
from notifications import delivery
from notifications.models import Notification
from scheduling import services

from .base import PASSWORD, Factory

LINK = "https://meet.example.test/room"


class LoginRaceTests(Factory, TestCase):
    """A login that authenticated just before the account changed must not get a token."""

    def login_while(self, change):
        user = self.user("student")

        def authenticate_then_change(*args, **kwargs):
            found = authenticate(*args, **kwargs)
            change(user)  # commits between the password check and the token
            return found

        with patch(
            "rest_framework.authtoken.serializers.authenticate",
            side_effect=authenticate_then_change,
        ):
            response = APIClient().post(
                "/api/auth/login/", {"username": "student", "password": PASSWORD}
            )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Token.objects.filter(user=user).exists())

    def test_password_changed_mid_login(self):
        def change(user):
            fresh = User.objects.get(pk=user.pk)
            fresh.set_password(PASSWORD[::-1])
            fresh.save()

        self.login_while(change)

    def test_deactivated_mid_login(self):
        self.login_while(lambda user: User.objects.filter(pk=user.pk).update(is_active=False))


class EmailIdentityTests(Factory, TestCase):
    def test_database_refuses_addresses_differing_only_in_case(self):
        self.user("first")
        with self.assertRaisesMessage(IntegrityError, "user_email_ci_unique"), transaction.atomic():
            User.objects.create_user("second", "FIRST@example.test", PASSWORD)

    def test_invite_notices_an_account_created_while_it_waited(self):
        admin = self.user("boss", User.Role.ADMIN)
        real_update = Invitation.objects.filter

        def create_account_first(*args, **kwargs):
            if "revoked_at__isnull" in kwargs:
                self.user("late")  # appears while the old invitation was locked
            return real_update(*args, **kwargs)

        with patch.object(Invitation.objects, "filter", side_effect=create_account_first):
            response = self.client_for(admin).post(
                "/api/invitations/", {"email": "late@example.test", "role": "student"}
            )
        self.assertEqual(response.data.get("code"), "email_in_use", response.data)
        self.assertFalse(Invitation.objects.exists())


class SessionMessageTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.m, self.student = self.mentor(), self.user("student")
        self.booking = services.book_slot(student=self.student, slot_id=self.slot(self.m).pk)
        Notification.objects.all().delete()

    def test_link_added_during_the_session_is_still_sent(self):
        self.move(self.booking.slot_id, timezone.now() - timedelta(minutes=5))
        services.update_session(actor=self.m, booking_id=self.booking.pk, meeting_link=LINK)
        delivery.process_due()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(LINK, mail.outbox[0].body)

    def test_unusual_error_text_cannot_stop_the_queue(self):
        services.update_session(actor=self.m, booking_id=self.booking.pk, meeting_link=LINK)
        broken = SMTPException("bad \x00 byte " + "\ud800" + "x" * 2000)
        with patch("notifications.delivery.send_mail", side_effect=broken):
            self.assertEqual(delivery.process_due(), 1)
        row = Notification.objects.get()
        self.assertEqual((row.status, row.attempts), ("pending", 1))
        self.assertIn("SMTPException", row.last_error)


class ThrottleStorageTests(TestCase):
    def test_counters_are_not_evicted_by_a_flood_of_new_addresses(self):
        cache = caches["default"]
        cache.set("throttle_auth_victim", [1], 600)
        for number in range(600):
            cache.set(f"throttle_auth_{number}", [1], 600)
        self.assertEqual(cache.get("throttle_auth_victim"), [1])
        self.assertGreaterEqual(settings.CACHES["default"]["OPTIONS"]["MAX_ENTRIES"], 10_000)


class ProfilePrivacyTests(Factory, TestCase):
    def test_a_cancelled_booking_does_not_keep_a_profile_open(self):
        m, student = self.mentor(), self.user("student")
        booking = services.book_slot(student=student, slot_id=self.slot(m).pk)
        url = f"/api/users/{student.pk}/profile/"
        self.assertEqual(self.client_for(m).get(url).status_code, 200)
        services.cancel_booking(actor=student, booking_id=booking.pk)
        self.assertEqual(self.client_for(m).get(url).status_code, 404)
