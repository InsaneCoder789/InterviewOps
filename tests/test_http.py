from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User

from .base import PASSWORD, Factory

APP = "https://app.example.test"
ALLOW = "Access-Control-Allow-Origin"


@override_settings(CORS_ALLOWED_ORIGINS=[APP])
class CorsTests(Factory, TestCase):
    def preflight(self, origin, path="/api/bookings/"):
        return APIClient().options(
            path, HTTP_ORIGIN=origin, HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST"
        )

    def test_preflight_from_allowed_origin_needs_no_token(self):
        response = self.preflight(APP)
        self.assertEqual((response.status_code, response[ALLOW]), (204, APP))
        self.assertIn("Authorization", response["Access-Control-Allow-Headers"])
        self.assertNotIn("Access-Control-Allow-Credentials", response)

    def test_errors_and_throttled_responses_stay_readable(self):
        client = APIClient()
        refused = client.get("/api/slots/", HTTP_ORIGIN=APP)
        self.assertEqual((refused.status_code, refused[ALLOW]), (401, APP))
        for _ in range(11):
            last = client.post("/api/auth/login/", {}, HTTP_ORIGIN=APP)
        self.assertEqual((last.status_code, last[ALLOW]), (429, APP))
        self.assertIn("Retry-After", last["Access-Control-Expose-Headers"])
        self.assertIn("Origin", last["Vary"])

    def test_unlisted_origins_get_nothing(self):
        for origin in ("https://evil.example.test", APP + ".evil.test", "null"):
            self.assertNotIn(ALLOW, self.preflight(origin))
            self.assertNotIn(ALLOW, APIClient().get("/health/", HTTP_ORIGIN=origin))

    def test_only_api_and_health_paths_are_shared(self):
        self.assertIn(ALLOW, APIClient().get("/health/", HTTP_ORIGIN=APP))
        self.assertNotIn(ALLOW, APIClient().get("/admin/login/", HTTP_ORIGIN=APP))

    @override_settings(CORS_ALLOWED_ORIGINS=[])
    def test_nothing_is_shared_by_default(self):
        self.assertNotIn(ALLOW, APIClient().get("/health/", HTTP_ORIGIN=APP))


class RegistrationAndConfigTests(Factory, TestCase):
    body = {"username": "newbie", "email": "newbie@example.test", "password": PASSWORD}

    @override_settings(ALLOW_REGISTRATION=False)
    def test_closed_registration_creates_nothing(self):
        response = APIClient().post("/api/auth/register/", self.body)
        self.assertEqual(
            (response.status_code, response.data["code"]), (403, "registration_closed")
        )
        self.assertFalse(User.objects.exists())
        self.assertFalse(APIClient().get("/api/config/").json()["registration_open"])

    @override_settings(ALLOW_REGISTRATION=True)
    def test_open_registration(self):
        self.assertEqual(APIClient().post("/api/auth/register/", self.body).status_code, 201)

    def test_config_is_public_and_matches_the_rules(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token stale")
        response = client.get("/api/config/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            (
                data["student_cancellation_cutoff_hours"],
                data["slot_min_minutes"],
                data["slot_max_minutes"],
                data["reminder_lead_hours"],
            ),
            (2, 15, 180, 24),
        )
        self.assertEqual(client.post("/api/config/").status_code, 405)


class ErrorBodyTests(Factory, TestCase):
    def test_unknown_api_urls_answer_json(self):
        for url in ("/api/nope/", "/api/slots/abc/", "/api/users/x/role/"):
            response = APIClient().get(url)
            self.assertEqual(
                (response.status_code, response.json()), (404, {"detail": "Not found."}), url
            )
        self.assertIn("text/html", APIClient().get("/nope/")["Content-Type"])

    def test_crashes_answer_json_without_details(self):
        client = self.client_for(self.user("student"))
        client.raise_request_exception = False
        with mock.patch(
            "accounts.views.UserSerializer.to_representation",
            side_effect=RuntimeError("secret detail"),
        ):
            response = client.get("/api/auth/me/")
        self.assertEqual(
            (response.status_code, response.json()), (500, {"detail": "Server error."})
        )
        self.assertIn("X-Request-ID", response)
