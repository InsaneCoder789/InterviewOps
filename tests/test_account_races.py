"""Simultaneous requests against accounts, invitations and the mail queue."""

import secrets
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts import invitations, passwords
from accounts.models import Invitation, User
from accounts.serializers import check_new_account
from feedback.models import Feedback
from feedback.services import save_feedback
from notifications.models import Notification
from scheduling import services

from .base import PASSWORD, Factory
from .test_concurrency import ROUNDS, race

NEW = secrets.token_urlsafe(16)


class AccountRaceTests(Factory, TransactionTestCase):
    def post(self, codes, path, body):
        codes.append(APIClient().post(path, body).status_code)

    @override_settings(ALLOW_REGISTRATION=True)
    def test_the_same_signup_sent_at_once_creates_one_account(self):
        for i in range(ROUNDS):
            cache.clear()  # this is about uniqueness, not the rate limit
            codes = []
            body = {"username": f"u{i}", "email": f"u{i}@example.test", "password": NEW}
            race(*[lambda b=body: self.post(codes, "/api/auth/register/", b)] * 3)
            self.assertEqual(sorted(codes), [201, 400, 400], f"round {i}")

    def test_inviting_one_address_at_once_leaves_one_open_invitation(self):
        admin = self.user("boss", "admin")
        for i in range(ROUNDS):
            email = f"p{i}@example.test"
            result = race(
                *[lambda e=email: invitations.invite(actor=admin, email=e, role="student")] * 4
            )
            self.assertTrue(set(result) <= {"ok", "Conflict"}, result)
            self.assertEqual(
                Invitation.objects.filter(email=email, revoked_at__isnull=True).count(), 1
            )

    def test_one_invitation_accepted_at_once_creates_one_account(self):
        admin = self.user("boss", "admin")
        for i in range(ROUNDS):
            invitation = invitations.invite(actor=admin, email=f"p{i}@example.test", role="student")
            token = invitations.make_token(invitation)
            result = race(
                *[
                    lambda t=token, n=n, i=i: invitations.accept(
                        token=t, username=f"r{i}-{n}", password=NEW, validate=check_new_account
                    )
                    for n in range(3)
                ]
            )
            self.assertEqual(result, {"ok": 1, "ValidationError": 2}, f"round {i}")

    def test_two_invitees_choosing_one_username_cannot_both_have_it(self):
        admin = self.user("boss", "admin")
        for i in range(ROUNDS):
            tokens = [
                invitations.make_token(
                    invitations.invite(actor=admin, email=f"{x}{i}@example.test", role="student")
                )
                for x in "ab"
            ]
            result = race(
                *[
                    lambda t=t, i=i: invitations.accept(
                        token=t, username=f"same{i}", password=NEW, validate=lambda *a: None
                    )
                    for t in tokens
                ]
            )
            self.assertEqual(result, {"ok": 1, "ValidationError": 1}, f"round {i}")

    def test_reset_requests_at_once_queue_one_message(self):
        user = self.user("student")
        race(*[lambda: passwords.request_reset(email=user.email)] * 6)
        self.assertEqual(Notification.objects.count(), 1)

    def test_login_racing_deactivation_never_leaves_a_usable_token(self):
        admin = self.user("boss", "admin")
        for i in range(ROUNDS):
            cache.clear()
            user = self.user(f"s{i}")
            codes = []
            body = {"username": user.username, "password": PASSWORD}
            race(
                lambda b=body: self.post(codes, "/api/auth/login/", b),
                lambda u=user: services.set_active(actor=admin, user_id=u.pk, is_active=False),
            )
            self.assertIn(codes[0], (200, 400))
            self.assertFalse(Token.objects.filter(user=user).exists(), f"round {i}")

    def test_login_with_the_old_password_racing_a_change_leaves_only_the_new_token(self):
        for i in range(ROUNDS):
            cache.clear()
            user = self.user(f"s{i}")
            codes, fresh = [], []
            body = {"username": user.username, "password": PASSWORD}
            race(
                lambda b=body: self.post(codes, "/api/auth/login/", b),
                lambda u=user: fresh.append(
                    passwords.change(user=u, current_password=PASSWORD, new_password=NEW).key
                ),
            )
            self.assertEqual(
                list(Token.objects.filter(user=user).values_list("key", flat=True)), fresh
            )

    def test_feedback_saved_at_once_is_one_row_and_one_email(self):
        mentor, student = self.mentor(), self.user("student")
        booking = services.book_slot(student=student, slot_id=self.slot(mentor).pk)
        self.move(booking.slot_id, timezone.now() - timedelta(hours=3))
        values = dict.fromkeys(("communication", "problem_solving", "technical"), 3)
        values |= {"strengths": "a", "improvements": "b", "next_steps": "c"}
        result = race(
            *[lambda: save_feedback(actor=mentor, booking_id=booking.pk, values=values)] * 4
        )
        self.assertEqual(result, {"ok": 4})
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(kind="feedback_ready").count(), 1)


class EdgeTests(Factory, TestCase):
    def test_revoking_what_does_not_exist_or_was_used(self):
        admin = self.client_for(self.user("boss", "admin"))
        self.assertEqual(admin.post("/api/invitations/999999/revoke/").status_code, 404)
        invitation = invitations.invite(
            actor=User.objects.get(username="boss"), email="p@example.test", role="student"
        )
        invitations.accept(
            token=invitations.make_token(invitation),
            username="p",
            password=NEW,
            validate=check_new_account,
        )
        used = admin.post(f"/api/invitations/{invitation.pk}/revoke/")
        self.assertEqual(used.data["code"], "invitation_accepted")

    def test_setting_the_current_status_changes_nothing(self):
        admin, student = self.user("boss", "admin"), self.user("student")
        token = Token.objects.create(user=student)
        services.set_active(actor=admin, user_id=student.pk, is_active=True)
        self.assertTrue(Token.objects.filter(pk=token.pk).exists())

    def test_cannot_reschedule_for_someone_who_is_no_longer_a_student(self):
        admin, student = self.user("boss", "admin"), self.user("student")
        mentor = self.mentor()
        booking = services.book_slot(student=student, slot_id=self.slot(mentor).pk)
        other = self.slot(mentor, hours=72)
        User.objects.filter(pk=student.pk).update(role="mentor")
        response = self.client_for(admin).post(
            f"/api/bookings/{booking.pk}/reschedule/", {"slot": other.pk}
        )
        self.assertEqual(response.data["code"], "student_unavailable")

    def test_an_unexpected_database_error_is_not_disguised_as_a_conflict(self):
        from django.db import IntegrityError

        mentor = self.mentor()
        with self.assertRaisesMessage(IntegrityError, "scheduling_slot"), transaction.atomic():
            self.slot(mentor, topic=None)
