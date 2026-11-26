import threading
from datetime import timedelta

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .base import PASSWORD, Factory


def age(user, hours):
    Token.objects.filter(user=user).update(created=timezone.now() - timedelta(hours=hours))


def login(user):
    return APIClient().post("/api/auth/login/", {"username": user.username, "password": PASSWORD})


@override_settings(TOKEN_TTL_HOURS=12)
class TokenExpiryTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.student = self.user("student")
        self.client = self.client_for(self.student)

    def test_fresh_token_works_and_expired_token_is_refused(self):
        age(self.student, 11)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
        age(self.student, 12)
        response = self.client.get("/api/auth/me/")
        self.assertEqual(
            (response.status_code, response.data["detail"]), (401, "Token has expired.")
        )

    def test_login_keeps_a_live_token_and_replaces_an_expired_one(self):
        first = login(self.student).data
        self.assertEqual(login(self.student).data, first)
        age(self.student, 13)
        second = login(self.student).data
        self.assertNotEqual(second["token"], first["token"])
        self.assertGreater(second["expires_at"], timezone.now() + timedelta(hours=11))
        # The old key stays dead.
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_login_ignores_a_bad_token_header(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token no-such-token")
        body = {"username": "student", "password": PASSWORD}
        self.assertEqual(client.post("/api/auth/login/", body).status_code, 200)


class ConcurrentLoginTests(Factory, TransactionTestCase):
    def test_simultaneous_logins_after_expiry_share_one_new_token(self):
        student = self.user("student")
        Token.objects.create(user=student)
        age(student, 100)
        barrier, results = threading.Barrier(4), []

        def run():
            try:
                barrier.wait(timeout=10)
                response = login(student)
                results.append((response.status_code, response.data.get("token")))
            finally:
                connection.close()

        threads = [threading.Thread(target=run) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual([code for code, _ in results], [200] * 4)
        self.assertEqual(len({token for _, token in results}), 1)
