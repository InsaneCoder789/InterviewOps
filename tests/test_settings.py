"""Settings as a fresh process reads them, and the health check when the database is gone."""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

from django.db import DatabaseError
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parent.parent
PRINT = """
import json
from django.conf import settings as s
print(json.dumps({
    "debug": s.DEBUG, "admin": s.ENABLE_ADMIN, "signup": s.ALLOW_REGISTRATION,
    "hosts": s.ALLOWED_HOSTS, "cors": s.CORS_ALLOWED_ORIGINS,
    "db": s.DATABASES["default"], "ssl": getattr(s, "SECURE_SSL_REDIRECT", False),
    "hsts": getattr(s, "SECURE_HSTS_SECONDS", 0),
}))
"""


def load(**env):
    clean = {"PATH": os.environ["PATH"], "DJANGO_SETTINGS_MODULE": "config.settings", **env}
    return subprocess.run(
        [sys.executable, "-c", f"import django; django.setup()\n{PRINT}"],
        cwd=ROOT,
        env=clean,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


class ProductionSettingsTests(SimpleTestCase):
    def test_will_not_start_without_a_secret_key(self):
        result = load()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_production_defaults_are_closed(self):
        data = json.loads(load(DJANGO_SECRET_KEY="k" * 60).stdout)
        self.assertEqual(
            (data["debug"], data["admin"], data["signup"], data["cors"]),
            (False, False, False, []),
        )
        self.assertTrue(data["ssl"])
        self.assertGreater(data["hsts"], 0)

    def test_values_are_parsed(self):
        result = load(
            DJANGO_SECRET_KEY="k" * 60,
            DJANGO_ALLOWED_HOSTS=" a.test , b.test,",
            RENDER_EXTERNAL_HOSTNAME="c.test",
            CORS_ALLOWED_ORIGINS="https://app.test/, ,http://localhost:5173",
            DATABASE_URL="postgresql://u%40x:p%3Aw%2F@db.test:6543/n?sslmode=require",
        )
        data = json.loads(result.stdout)
        self.assertEqual(data["hosts"], ["a.test", "b.test", "c.test"])
        self.assertEqual(data["cors"], ["https://app.test", "http://localhost:5173"])
        db = data["db"]
        self.assertEqual(
            (db["USER"], db["PASSWORD"], db["HOST"], db["PORT"], db["NAME"], db["OPTIONS"]),
            ("u@x", "p:w/", "db.test", 6543, "n", {"sslmode": "require"}),
        )


class HealthTests(SimpleTestCase):
    def test_reports_an_unreachable_database_without_details(self):
        with mock.patch("config.views.connection") as broken:
            broken.cursor.side_effect = DatabaseError("secret")
            response = self.client.get("/health/")
        self.assertEqual(
            (response.status_code, response.json()), (503, {"status": "database unavailable"})
        )
