import re
from datetime import timedelta
from urllib.parse import parse_qs

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import Invitation, User
from notifications import delivery
from notifications.models import Notification

from .base import PASSWORD, Factory

NEW_PASSWORD = "another-test-passphrase-902"


def emailed_values():
    """Send queued mail and read the values after "#" in the last link."""
    delivery.process_due()
    fragment = re.search(r"#(\S+)", mail.outbox[-1].body).group(1)
    return {key: values[0] for key, values in parse_qs(fragment).items()}


@override_settings(APP_BASE_URL="https://app.example.test", ALLOW_REGISTRATION=False)
class InvitationTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.user("boss", User.Role.ADMIN)
        self.client = self.client_for(self.admin)

    def invite(self, email="Priya@Example.Test", role="mentor"):
        return self.client.post("/api/invitations/", {"email": email, "role": role})

    def accept(self, token, username="priya", password=NEW_PASSWORD):
        return APIClient().post(
            "/api/auth/accept-invitation/",
            {"token": token, "username": username, "password": password},
        )

    def test_invited_person_joins_with_that_role_while_signup_is_closed(self):
        self.assertEqual(self.invite().status_code, 201)
        token = emailed_values()["token"]
        self.assertEqual(mail.outbox[-1].to, ["priya@example.test"])
        self.assertIn("https://app.example.test/accept-invitation#token=", mail.outbox[-1].body)
        response = self.accept(token)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            (response.data["role"], response.data["email"]), ("mentor", "priya@example.test")
        )
        self.assertEqual(
            self.client.get("/api/invitations/").data["results"][0]["status"], "accepted"
        )
        again = self.accept(token, "second")
        self.assertEqual((again.status_code, str(again.data["code"])), (400, "invalid_invitation"))

    def test_no_usable_secret_is_stored(self):
        self.invite()
        token = emailed_values()["token"]
        stored = Invitation.objects.values().get()
        self.assertNotIn(token, str(stored) + str(Notification.objects.values().get()))

    def test_revoked_expired_replaced_and_forged_links_fail(self):
        first = self.invite().data["id"]
        old = emailed_values()["token"]
        second = self.invite().data["id"]  # replaces the first
        new = emailed_values()["token"]
        self.assertEqual(self.accept(old).status_code, 400)
        self.assertEqual(self.accept(new[:-2] + "xx").status_code, 400)
        Invitation.objects.filter(pk=second).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.accept(new).status_code, 400)
        Invitation.objects.filter(pk=second).update(expires_at=timezone.now() + timedelta(days=1))
        self.client.post(f"/api/invitations/{second}/revoke/")
        self.assertEqual(self.accept(new).status_code, 400)
        self.assertEqual(Invitation.objects.get(pk=first).status, "revoked")
        self.assertFalse(User.objects.filter(username="priya").exists())

    def test_revoked_invitation_is_not_emailed(self):
        pk = self.invite().data["id"]
        self.client.post(f"/api/invitations/{pk}/revoke/")
        delivery.process_due()
        self.assertEqual(mail.outbox, [])

    def test_weak_password_or_taken_username_leaves_the_invitation_open(self):
        self.invite()
        token = emailed_values()["token"]
        self.assertIn("password", self.accept(token, password="123").data)
        self.assertIn("username", self.accept(token, username="boss").data)
        self.assertEqual(self.accept(token).status_code, 201)

    def test_only_admins_invite_and_not_existing_accounts(self):
        self.assertEqual(self.invite("BOSS@example.test").data["code"], "email_in_use")
        student = self.client_for(self.user("s"))
        self.assertEqual(student.post("/api/invitations/", {}).status_code, 403)
        self.assertEqual(student.get("/api/invitations/").status_code, 403)
        self.assertEqual(self.invite(role="owner").status_code, 400)


class PasswordTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.student = self.user("student")
        self.client = self.client_for(self.student)

    def request_reset(self, email):
        return APIClient().post("/api/auth/password-reset/", {"email": email})

    def confirm(self, values, password=NEW_PASSWORD):
        return APIClient().post(
            "/api/auth/password-reset/confirm/", {**values, "password": password}
        )

    def login(self, password):
        return (
            APIClient()
            .post("/api/auth/login/", {"username": "student", "password": password})
            .status_code
        )

    def test_reset_changes_the_password_once_and_signs_out(self):
        self.assertEqual(self.request_reset("STUDENT@example.test").status_code, 202)
        values = emailed_values()
        self.assertEqual(self.confirm(values, "123").status_code, 400)
        self.assertEqual(self.confirm(values).status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.assertEqual((self.login(PASSWORD), self.login(NEW_PASSWORD)), (400, 200))
        self.assertEqual(self.confirm(values).status_code, 400)

    def test_unknown_and_inactive_addresses_answer_the_same_and_send_nothing(self):
        known = self.request_reset("student@example.test")
        Notification.objects.all().delete()
        User.objects.filter(pk=self.student.pk).update(is_active=False)
        for email in ("student@example.test", "nobody@example.test"):
            response = self.request_reset(email)
            self.assertEqual((response.status_code, response.data), (known.status_code, known.data))
        self.assertFalse(Notification.objects.exists())

    def test_repeated_requests_queue_one_message(self):
        for _ in range(3):
            self.request_reset("student@example.test")
        self.assertEqual(Notification.objects.count(), 1)

    def test_bad_links_are_refused(self):
        for values in ({"uid": "!!", "token": "x"}, {"uid": "OTk5OTk5", "token": "x"}):
            self.assertEqual(self.confirm(values).status_code, 400)

    def test_change_requires_the_current_password_and_rotates_the_token(self):
        old = Token.objects.get(user=self.student).key
        wrong = self.client.post(
            "/api/auth/password/", {"current_password": "nope", "new_password": NEW_PASSWORD}
        )
        self.assertEqual(wrong.status_code, 400)
        response = self.client.post(
            "/api/auth/password/", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["token"], old)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.assertEqual(self.login(NEW_PASSWORD), 200)
