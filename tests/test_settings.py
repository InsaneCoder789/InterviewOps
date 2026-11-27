"""Settings as a fresh process reads them, and the health check when the database is gone."""

import json
import os
import secrets
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from django.db import DatabaseError
from django.test import SimpleTestCase

from config.local_key import local_secret_key

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
        data = json.loads(load(DJANGO_SECRET_KEY=secrets.token_urlsafe(50)).stdout)
        self.assertEqual(
            (data["debug"], data["admin"], data["signup"], data["cors"]),
            (False, False, False, []),
        )
        self.assertTrue(data["ssl"])
        self.assertGreater(data["hsts"], 0)

    def test_values_are_parsed(self):
        password = secrets.token_urlsafe(8) + ":w/"
        result = load(
            DJANGO_SECRET_KEY=secrets.token_urlsafe(50),
            DJANGO_ALLOWED_HOSTS=" a.test , b.test,",
            RENDER_EXTERNAL_HOSTNAME="c.test",
            CORS_ALLOWED_ORIGINS="https://app.test/, ,http://localhost:5173",
            DATABASE_URL=f"postgresql://u%40x:{quote(password, safe='')}"
            "@db.test:6543/n?sslmode=require",
        )
        data = json.loads(result.stdout)
        self.assertEqual(data["hosts"], ["a.test", "b.test", "c.test"])
        self.assertEqual(data["cors"], ["https://app.test", "http://localhost:5173"])
        db = data["db"]
        self.assertEqual(
            (db["USER"], db["PASSWORD"], db["HOST"], db["PORT"], db["NAME"], db["OPTIONS"]),
            ("u@x", password, "db.test", 6543, "n", {"sslmode": "require"}),
        )


class LocalKeyTests(SimpleTestCase):
    def test_processes_starting_together_share_one_private_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".dev-secret-key"
            with ThreadPoolExecutor(8) as pool:
                keys = set(pool.map(local_secret_key, [path] * 40))
            self.assertEqual(keys, {local_secret_key(path)})
            self.assertGreaterEqual(len(keys.pop()), 50)
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            self.assertEqual(list(Path(folder).iterdir()), [path])


class HealthTests(SimpleTestCase):
    def test_reports_an_unreachable_database_without_details(self):
        with mock.patch("config.views.connection") as broken:
            broken.cursor.side_effect = DatabaseError("secret")
            response = self.client.get("/health/")
        self.assertEqual(
            (response.status_code, response.json()), (503, {"status": "database unavailable"})
        )
