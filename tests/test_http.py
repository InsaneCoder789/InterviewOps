from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .base import Factory

APP = "https://app.example.test"
ALLOW = "Access-Control-Allow-Origin"


@override_settings(CORS_ALLOWED_ORIGINS=[APP])
class CorsTests(Factory, TestCase):
    def preflight(self, origin, path="/api/bookings/"):
        return APIClient().options(
            path, HTTP_ORIGIN=origin, HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")

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
