from django.test import TestCase
from rest_framework.exceptions import PermissionDenied

from accounts.models import Profile, User
from scheduling import services
from scheduling.models import Booking, Slot

from .base import Factory


class ProfileTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.student, self.stranger = self.user("student"), self.user("stranger")
        self.m = self.mentor()

    def test_empty_profile_then_save(self):
        client = self.client_for(self.student)
        self.assertEqual(client.get("/api/profile/").data["topics"], [])
        response = client.patch(
            "/api/profile/",
            {
                "topics": [" System Design", "system design", "DSA"],
                "target_roles": ["Backend engineer"],
                "experience_level": "entry",
                "timezone": "Asia/Kolkata",
                "role": "admin",
                "user": self.m.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            (response.data["topics"], response.data["role"], response.data["user"]),
            (["system design", "dsa"], "student", self.student.pk),
        )
        self.assertNotIn("email", response.data)

    def test_invalid_values_are_refused(self):
        client = self.client_for(self.student)
        for body in (
            {"timezone": "Mars/Base"},
            {"experience_level": "wizard"},
            {"topics": [str(i) for i in range(16)]},
            {"bio": "x" * 2001},
        ):
            self.assertEqual(
                client.patch("/api/profile/", body, format="json").status_code, 400, body
            )
        self.assertFalse(Profile.objects.exists())

    def test_who_may_read_whose_profile(self):
        def code(viewer, subject):
            return self.client_for(viewer).get(f"/api/users/{subject.pk}/profile/").status_code

        self.assertEqual(code(self.student, self.m), 200)
        self.assertEqual(code(self.student, self.stranger), 404)
        self.assertEqual(code(self.m, self.student), 404)
        booking = services.book_slot(student=self.student, slot_id=self.slot(self.m).pk)
        self.assertEqual(code(self.m, self.student), 200)
        self.assertEqual(code(self.mentor("other"), self.student), 404)
        self.assertEqual(code(self.user("boss", User.Role.ADMIN), self.stranger), 200)
        self.assertTrue(booking.pk)

    def test_mentor_directory_filters_by_topic_and_name(self):
        other = self.mentor("omar")
        Profile.objects.create(user=self.m, topics=["dsa"], display_name="Priya N")
        client = self.client_for(self.student)

        def ids(query=""):
            return [r["user"] for r in client.get(f"/api/mentors/{query}").data["results"]]

        self.assertEqual(ids(), [self.m.pk, other.pk])
        self.assertEqual(ids("?topic=DSA"), [self.m.pk])
        self.assertEqual(ids("?search=priya"), [self.m.pk])
        User.objects.filter(pk=other.pk).update(is_active=False)
        self.assertEqual(ids(), [self.m.pk])


class AccountStatusTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.user("boss", User.Role.ADMIN)
        self.m, self.student = self.mentor(), self.user("student")
        self.booked = self.slot(self.m, hours=48)
        self.open = self.slot(self.m, hours=52)
        self.booking = services.book_slot(student=self.student, slot_id=self.booked.pk)

    def set_active(self, user, value, actor=None):
        return self.client_for(actor or self.admin).patch(
            f"/api/users/{user.pk}/status/", {"is_active": value}, format="json"
        )

    def test_deactivating_a_mentor_cancels_their_future_slots(self):
        client = self.client_for(self.m)
        self.assertEqual(self.set_active(self.m, False).data["is_active"], False)
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)
        self.assertEqual(Slot.objects.filter(cancelled_at__isnull=True).count(), 0)
        self.booking.refresh_from_db()
        self.assertEqual(
            (self.booking.status, self.booking.cancelled_by), ("cancelled", self.admin)
        )
        recipients = set(
            self.booking.notifications.filter(kind="booking_cancelled").values_list(
                "recipient_id", flat=True
            )
        )
        self.assertIn(self.student.pk, recipients)

    def test_deactivating_a_student_frees_the_slot(self):
        self.set_active(self.student, False)
        self.assertEqual(Booking.objects.get(pk=self.booking.pk).status, "cancelled")
        self.assertEqual(Slot.objects.filter(cancelled_at__isnull=True).count(), 2)

    def test_reactivating_restores_access_but_not_sessions(self):
        self.set_active(self.student, False)
        self.assertTrue(self.set_active(self.student, True).data["is_active"])
        self.assertEqual(Booking.objects.get(pk=self.booking.pk).status, "cancelled")

    def test_guards(self):
        self.assertEqual(self.set_active(self.admin, False).data["code"], "own_status")
        self.assertEqual(self.set_active(self.m, False, actor=self.student).status_code, 403)
        response = self.client_for(self.admin).patch(f"/api/users/{self.m.pk}/status/", {})
        self.assertEqual(response.status_code, 400)

    def test_a_request_already_in_flight_cannot_book_after_deactivation(self):
        stale = User.objects.get(pk=self.student.pk)  # authenticated before the change
        self.set_active(self.student, False)
        with self.assertRaisesMessage(PermissionDenied, "active students"):
            services.book_slot(student=stale, slot_id=self.open.pk)
