import io

from django.core.cache import caches
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase, override_settings

from accounts.models import User
from feedback.models import Feedback

from .base import PASSWORD


class OperationsTests(TestCase):
    def test_throttle_counters_are_stored_in_the_database(self):
        caches["default"].set("probe", 1)
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM django_cache")
            self.assertGreaterEqual(cursor.fetchone()[0], 1)

    @override_settings(DEBUG=True)
    def test_seed_demo_creates_usable_data_once(self):
        out = io.StringIO()
        call_command("seed_demo", password=PASSWORD, stdout=out)
        self.assertEqual(User.objects.count(), 5)
        self.assertEqual(Feedback.objects.count(), 1)
        with self.assertRaises(CommandError):
            call_command("seed_demo")

    @override_settings(DEBUG=False)
    def test_seed_demo_refuses_outside_debug(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo")
        self.assertFalse(User.objects.exists())
