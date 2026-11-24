from datetime import timedelta

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from notifications.models import Notification
from scheduling import services

from .base import Factory


class AdminToolTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.user("boss", User.Role.ADMIN)
        self.m, self.student = self.mentor(), self.user("student")
        self.booking = services.book_slot(student=self.student, slot_id=self.slot(self.m).pk)
        self.slot(self.m, hours=60)
        self.client = self.client_for(self.admin)

    def test_overview(self):
        data = self.client.get("/api/admin/overview/").data
        self.assertEqual(
            (data["active_users"], data["open_slots"], data["upcoming_sessions"],
             data["upcoming_without_link"], data["awaiting_feedback"]),
            ({"student": 1, "mentor": 1, "admin": 1}, 1, 1, 1, 0))
        self.move(self.booking.slot_id, timezone.now() - timedelta(hours=3))
        self.assertEqual(self.client.get("/api/admin/overview/").data["awaiting_feedback"], 1)

    def test_delivery_list_and_retry(self):
        failed = Notification.objects.filter(kind="reminder").first()
        Notification.objects.filter(pk=failed.pk).update(
            status="failed", attempts=10, last_error="SMTPException: down")
        rows = self.client.get("/api/notifications/?status=failed").data["results"]
        self.assertEqual([r["id"] for r in rows], [failed.pk])
        self.assertTrue(rows[0]["email"])
        url = f"/api/notifications/{failed.pk}/retry/"
        self.assertEqual(self.client.post(url).data["status"], "pending")
        self.assertEqual(self.client.post(url).data["code"], "not_failed")
        self.assertEqual(self.client.post("/api/notifications/999999/retry/").status_code, 404)

    def test_admins_only(self):
        for user in (self.m, self.student):
            client = self.client_for(user)
            self.assertEqual(client.get("/api/admin/overview/").status_code, 403)
            self.assertEqual(client.get("/api/notifications/").status_code, 403)
            self.assertEqual(client.post("/api/notifications/1/retry/").status_code, 403)

    def test_check_queue_command(self):
        call_command("check_queue", verbosity=0, stdout=open("/dev/null", "w"))
        Notification.objects.update(available_at=timezone.now() - timedelta(hours=1))
        with self.assertRaises(CommandError):
            call_command("check_queue")
