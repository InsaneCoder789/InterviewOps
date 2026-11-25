from datetime import timedelta

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from notifications import delivery
from notifications.models import Notification
from scheduling import services
from scheduling.models import Booking

from .base import Factory

LINK = "https://meet.example.test/room-1"


class SessionCase(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.m, self.student = self.mentor("m1"), self.user("student")
        self.admin = self.user("boss", User.Role.ADMIN)
        self.slot_a = self.slot(self.m, hours=48)
        self.booking = services.book_slot(student=self.student, slot_id=self.slot_a.pk)
        self.url = f"/api/bookings/{self.booking.pk}/"


class RescheduleTests(SessionCase):
    def move_to(self, slot, user=None):
        return self.client_for(user or self.student).post(
            self.url + "reschedule/", {"slot": slot.pk})

    def test_moves_the_booking_and_frees_the_old_slot(self):
        services.update_session(actor=self.student, booking_id=self.booking.pk,
                                preparation_notes="caching")
        services.update_session(actor=self.m, booking_id=self.booking.pk, meeting_link=LINK)
        new = self.slot(self.m, hours=72)
        response = self.move_to(new)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            (response.data["slot"], response.data["rescheduled_from"],
             response.data["preparation_notes"], response.data["meeting_link"]),
            (new.pk, self.booking.pk, "caching", LINK))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "cancelled")
        services.book_slot(student=self.user("next"), slot_id=self.slot_a.pk)

    def test_may_move_to_a_time_overlapping_the_old_one(self):
        other = self.mentor("m2")
        overlap = services.publish_slot(
            mentor_id=other.pk, topic="x",
            starts_at=self.slot_a.starts_at + timedelta(minutes=30), ends_at=self.slot_a.ends_at)
        self.assertEqual(self.move_to(overlap).status_code, 201)
        # The old mentor is told; the new mentor's link is not carried over.
        delivery.process_due()
        self.assertIn(("m1@example.test", "Cancelled"),
                      [(m.to[0], m.subject.split(":")[0]) for m in mail.outbox])

    def test_failure_keeps_the_old_booking(self):
        taken = self.slot(self.m, hours=72)
        services.book_slot(student=self.user("other"), slot_id=taken.pk)
        self.assertEqual(self.move_to(taken).data["code"], "slot_already_booked")
        busy = self.slot(self.m, hours=96)
        services.book_slot(student=self.student, slot_id=busy.pk)
        clash = services.publish_slot(
            mentor_id=self.mentor("m2").pk, topic="x",
            starts_at=busy.starts_at, ends_at=busy.ends_at)
        self.assertEqual(self.move_to(clash).data["code"], "student_overlap")
        self.assertEqual(self.move_to(self.slot_a).data["code"], "same_slot")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "booked")

    def test_only_student_or_admin_and_students_respect_the_cutoff(self):
        new = self.slot(self.m, hours=72)
        self.assertEqual(self.move_to(new, self.m).status_code, 403)
        self.assertEqual(self.move_to(new, self.user("stranger")).status_code, 404)
        self.move(self.slot_a, timezone.now() + timedelta(hours=1))
        self.assertEqual(self.move_to(new).data["code"], "cancel_cutoff")
        self.assertEqual(self.move_to(new, self.admin).status_code, 201)


class SessionDetailTests(SessionCase):
    def patch(self, user, body):
        return self.client_for(user).patch(self.url, body, format="json")

    def test_each_person_edits_their_own_part(self):
        self.assertEqual(self.patch(self.m, {"meeting_link": LINK}).status_code, 200)
        self.assertEqual(
            self.patch(self.student, {"preparation_notes": "trees"}).data["meeting_link"], LINK)
        self.assertEqual(self.patch(self.student, {"meeting_link": LINK}).status_code, 403)
        self.assertEqual(self.patch(self.m, {"preparation_notes": "x"}).status_code, 403)
        self.assertEqual(
            self.patch(self.user("stranger"), {"meeting_link": LINK}).status_code, 404)

    def test_only_https_links(self):
        for link in ("http://meet.example.test/a", "javascript:alert(1)", "meet"):
            self.assertEqual(self.patch(self.m, {"meeting_link": link}).status_code, 400, link)
        self.assertEqual(self.patch(self.m, {}).status_code, 400)

    def test_new_link_emails_the_student_once(self):
        Notification.objects.all().delete()
        for link in ("https://meet.example.test/old", LINK, LINK):
            self.patch(self.m, {"meeting_link": link})
        delivery.process_due()
        self.assertEqual([m.to for m in mail.outbox], [["student@example.test"]])
        self.assertIn(LINK, mail.outbox[0].body)

    def test_attendance_after_the_start_only(self):
        client = self.client_for(self.m)
        url = self.url + "attendance/"
        early = client.post(url, {"attendance": "completed"})
        self.assertEqual(early.data["code"], "session_not_started")
        self.move(self.slot_a, timezone.now() - timedelta(hours=2))
        self.assertEqual(
            self.client_for(self.student).post(url, {"attendance": "completed"}).status_code, 403)
        done = client.post(url, {"attendance": "student_absent"})
        self.assertEqual(done.data["attendance"], "student_absent")
        self.assertEqual(client.post(url, {"attendance": "gone"}).status_code, 400)
        self.assertEqual(
            self.patch(self.m, {"meeting_link": LINK}).data["code"], "session_ended")
