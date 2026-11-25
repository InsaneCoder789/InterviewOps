from datetime import timedelta

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from feedback.models import Feedback
from notifications import delivery
from notifications.models import Notification
from scheduling import services

from .base import Factory

FORM = {
    "communication": 4, "problem_solving": 3, "technical": 2,
    "strengths": "Clear explanations", "improvements": "Test edge cases",
    "next_steps": "Practise graphs",
}


class FeedbackTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.m, self.student = self.mentor("m1"), self.user("student")
        self.admin = self.user("boss", User.Role.ADMIN)
        self.booking = self.session(48)
        self.url = f"/api/bookings/{self.booking.pk}/feedback/"

    def session(self, hours):
        return services.book_slot(
            student=self.student, slot_id=self.slot(self.m, hours=hours).pk)

    def happened(self, booking, ago=2):
        self.move(booking.slot_id, timezone.now() - timedelta(hours=ago))

    def put(self, user=None, **changes):
        return self.client_for(user or self.m).put(
            self.url, {**FORM, **changes}, format="json")

    def test_not_before_the_session_starts(self):
        self.assertEqual(self.put().data["code"], "session_not_started")

    def test_mentor_writes_student_reads_and_is_told_once(self):
        self.happened(self.booking)
        Notification.objects.all().delete()
        self.assertEqual(self.put().status_code, 201)
        self.assertEqual(self.put(technical=3).status_code, 200)
        data = self.client_for(self.student).get(self.url).data
        self.assertEqual((data["technical"], data["mentor"]), (3, self.m.pk))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.attendance, "completed")
        delivery.process_due()
        self.assertEqual([m.to for m in mail.outbox], [["student@example.test"]])
        # The comments stay in the app, not in email.
        self.assertNotIn("Practise graphs", mail.outbox[0].body)

    def test_only_the_sessions_mentor_writes(self):
        self.happened(self.booking)
        self.assertEqual(self.put(self.student).status_code, 403)
        self.assertEqual(self.put(self.admin).status_code, 403)
        self.assertEqual(self.put(self.mentor("m2")).status_code, 404)
        self.assertFalse(Feedback.objects.exists())

    def test_validation(self):
        self.happened(self.booking)
        for change in ({"technical": 0}, {"technical": 6}, {"strengths": ""}):
            self.assertEqual(self.put(**change).status_code, 400, change)

    def test_missed_cancelled_and_locked(self):
        self.happened(self.booking)
        self.client_for(self.m).post(
            f"/api/bookings/{self.booking.pk}/attendance/", {"attendance": "student_absent"})
        self.assertEqual(self.put().data["code"], "session_missed")
        self.client_for(self.m).post(
            f"/api/bookings/{self.booking.pk}/attendance/", {"attendance": "completed"})
        self.assertEqual(self.put().status_code, 201)
        undo = self.client_for(self.m).post(
            f"/api/bookings/{self.booking.pk}/attendance/", {"attendance": "mentor_absent"})
        self.assertEqual(undo.data["code"], "feedback_exists")
        Feedback.objects.update(created_at=timezone.now() - timedelta(days=8))
        self.assertEqual(self.put().data["code"], "feedback_locked")

    def test_strangers_see_nothing(self):
        self.happened(self.booking)
        self.put()
        for user in (self.user("other"), self.mentor("m2")):
            client = self.client_for(user)
            self.assertEqual(client.get(self.url).status_code, 404)
            self.assertEqual(client.get("/api/feedback/").data["count"], 0)
            self.assertEqual(
                client.get(f"/api/feedback/?student={self.student.pk}").data["count"], 0)

    def test_progress(self):
        second = self.session(60)
        self.happened(self.booking, ago=30)
        self.put()
        self.happened(second, ago=5)
        self.url = f"/api/bookings/{second.pk}/feedback/"
        self.put(communication=5, next_steps="Mock again")
        data = self.client_for(self.student).get("/api/feedback/progress/?student=999").data
        self.assertEqual(
            (data["student"], data["sessions"], data["averages"]["communication"]),
            (self.student.pk, 2, 4.5))
        self.assertEqual([h["booking"] for h in data["history"]], [self.booking.pk, second.pk])
        self.assertEqual(data["latest_next_steps"], "Mock again")
        admin = self.client_for(self.admin)
        self.assertEqual(admin.get("/api/feedback/progress/").status_code, 400)
        empty = admin.get(f"/api/feedback/progress/?student={self.admin.pk}").data
        self.assertEqual((empty["sessions"], empty["averages"]["technical"]), (0, None))
