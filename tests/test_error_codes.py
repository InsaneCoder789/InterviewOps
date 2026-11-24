from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from scheduling import services
from scheduling.exceptions import Conflict
from scheduling.models import Booking, Slot

from .base import Factory


class ErrorCodeTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.m = self.mentor("m1")
        self.student = self.user("student")
        self.admin = self.user("boss", User.Role.ADMIN)

    def assertCode(self, code, user, method, url, body=None):
        response = getattr(self.client_for(user), method)(url, body)
        self.assertEqual((response.status_code, response.data.get("code")), (409, code))
        self.assertTrue(response.data["detail"])

    def test_booking_and_cancellation_codes(self):
        slot = self.slot(self.m)
        clash = self.slot(self.mentor("m2"))
        booking = services.book_slot(student=self.student, slot_id=slot.pk)
        cancel = f"/api/bookings/{booking.pk}/cancel/"
        self.assertCode("slot_already_booked", self.user("other"), "post",
                        "/api/bookings/", {"slot": slot.pk})
        self.assertCode("student_overlap", self.student, "post",
                        "/api/bookings/", {"slot": clash.pk})
        self.client_for(self.student).post(cancel)
        self.assertCode("booking_already_cancelled", self.student, "post", cancel)

        soon = services.book_slot(student=self.student, slot_id=self.slot(self.m, hours=1).pk)
        self.assertCode("cancel_cutoff", self.student, "post", f"/api/bookings/{soon.pk}/cancel/")
        Booking.objects.filter(pk=soon.pk).update(
            starts_at=timezone.now() - timedelta(minutes=1))
        self.assertCode("session_started", self.admin, "post", f"/api/bookings/{soon.pk}/cancel/")

    def test_slot_codes(self):
        slot = self.slot(self.m)
        self.assertCode("slot_overlap", self.m, "post", "/api/slots/", {
            "topic": "x", "starts_at": slot.starts_at.isoformat(),
            "ends_at": slot.ends_at.isoformat()})
        cancel = f"/api/slots/{slot.pk}/cancel/"
        self.client_for(self.m).post(cancel)
        self.assertCode("slot_already_cancelled", self.m, "post", cancel)
        started = self.slot(self.m, hours=60)
        Slot.objects.filter(pk=started.pk).update(
            starts_at=timezone.now() - timedelta(minutes=1))
        self.assertCode("slot_started", self.m, "post", f"/api/slots/{started.pk}/cancel/")

    def test_role_codes(self):
        self.slot(self.m)
        self.assertCode("own_role", self.admin, "patch",
                        f"/api/users/{self.admin.pk}/role/", {"role": "student"})
        self.assertCode("role_has_commitments", self.admin, "patch",
                        f"/api/users/{self.m.pk}/role/", {"role": "student"})

    def test_publish_rules_the_serializer_normally_catches_first(self):
        now = timezone.now()
        hour = timedelta(hours=1)
        for code, mentor, start, end in (
            ("mentor_unavailable", self.student, now + hour, now + 2 * hour),
            ("slot_not_in_future", self.m, now - hour, now),
            ("slot_length", self.m, now + hour, now + 5 * hour),
        ):
            with self.assertRaises(Conflict) as caught:
                services.publish_slot(mentor_id=mentor.pk, topic="x",
                                      starts_at=start, ends_at=end)
            self.assertEqual(caught.exception.get_codes(), code)
