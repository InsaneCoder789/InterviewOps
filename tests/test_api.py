from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from scheduling import services
from scheduling.exceptions import Conflict
from scheduling.models import Booking, Slot

from .base import PASSWORD, Factory


@override_settings(ALLOW_REGISTRATION=True)
class AuthTests(Factory, TestCase):
    def test_register_login_logout(self):
        client = APIClient()
        response = client.post(
            "/api/auth/register/",
            {
                "username": "newbie",
                "email": "New@Example.Test",
                "password": PASSWORD,
                "role": "admin",
                "is_staff": True,
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username="newbie")
        self.assertEqual(
            (user.role, user.is_staff, user.email), ("student", False, "new@example.test")
        )
        self.assertNotIn("password", response.data)

        login = {"username": "newbie", "password": PASSWORD}
        token = client.post("/api/auth/login/", login).data["token"]
        client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(client.get("/api/auth/me/").data["role"], "student")
        self.assertEqual(client.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)

    def test_duplicate_email_and_weak_password_rejected(self):
        self.user("first")
        client = APIClient()
        for body in (
            {"username": "second", "email": "FIRST@example.test", "password": PASSWORD},
            {"username": "third", "email": "third@example.test", "password": "123"},
        ):
            self.assertEqual(client.post("/api/auth/register/", body).status_code, 400)

    def test_login_is_throttled(self):
        client = APIClient()
        codes = [
            client.post("/api/auth/login/", {"username": "x", "password": "y"}).status_code
            for _ in range(11)
        ]
        self.assertEqual(codes[-1], 429)

    def test_anonymous_requests_rejected(self):
        client = APIClient()
        for method, url in (
            ("get", "/api/slots/"),
            ("post", "/api/slots/"),
            ("get", "/api/bookings/"),
            ("post", "/api/bookings/"),
            ("post", "/api/bookings/1/cancel/"),
            ("post", "/api/slots/1/cancel/"),
            ("get", "/api/users/"),
        ):
            self.assertEqual(getattr(client, method)(url).status_code, 401, url)


class PermissionTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_mentor = self.mentor("m1")
        self.other_mentor = self.mentor("m2")
        self.student = self.user("s1")
        self.intruder = self.user("s2")
        self.admin = self.user("boss", User.Role.ADMIN)
        self.open_slot = self.slot(self.owner_mentor)
        self.booking = services.book_slot(student=self.student, slot_id=self.open_slot.pk)

    def test_students_cannot_publish_or_cancel_slots(self):
        client = self.client_for(self.student)
        self.assertEqual(client.post("/api/slots/", {}).status_code, 403)
        self.assertEqual(client.post(f"/api/slots/{self.open_slot.pk}/cancel/").status_code, 403)

    def test_mentors_and_admins_cannot_book(self):
        for user in (self.owner_mentor, self.admin):
            response = self.client_for(user).post("/api/bookings/", {"slot": self.open_slot.pk})
            self.assertEqual(response.status_code, 403)

    def test_strangers_cannot_see_or_cancel_a_booking(self):
        for user in (self.intruder, self.other_mentor):
            client = self.client_for(user)
            self.assertEqual(client.get(f"/api/bookings/{self.booking.pk}/").status_code, 404)
            self.assertEqual(
                client.post(f"/api/bookings/{self.booking.pk}/cancel/").status_code, 404
            )
            self.assertEqual(client.get("/api/bookings/").data["count"], 0)
        self.assertEqual(Booking.objects.get(pk=self.booking.pk).status, "booked")

    def test_participants_and_admin_can_see_a_booking(self):
        for user in (self.student, self.owner_mentor, self.admin):
            self.assertEqual(
                self.client_for(user).get(f"/api/bookings/{self.booking.pk}/").status_code, 200
            )

    def test_mentor_cannot_act_for_another_mentor(self):
        client = self.client_for(self.other_mentor)
        start = timezone.now() + timedelta(days=5)
        response = client.post(
            "/api/slots/",
            {
                "mentor": self.owner_mentor.pk,
                "topic": "x",
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=1)).isoformat(),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(client.post(f"/api/slots/{self.open_slot.pk}/cancel/").status_code, 404)

    def test_only_admin_changes_roles(self):
        url = f"/api/users/{self.intruder.pk}/role/"
        self.assertEqual(
            self.client_for(self.intruder).patch(url, {"role": "admin"}).status_code, 403
        )
        self.assertEqual(
            self.client_for(self.admin).patch(url, {"role": "mentor"}).data["role"], "mentor"
        )

    def test_role_change_blocked_by_upcoming_commitments(self):
        client = self.client_for(self.admin)
        for user in (self.student, self.owner_mentor):
            response = client.patch(f"/api/users/{user.pk}/role/", {"role": "admin"})
            self.assertEqual(response.status_code, 409)


class SlotAndBookingTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.m = self.mentor()
        self.student = self.user("student")
        self.client = self.client_for(self.student)

    def publish(self, user, start, end, **extra):
        return self.client_for(user).post(
            "/api/slots/",
            {"topic": "DSA", "starts_at": start.isoformat(), "ends_at": end.isoformat(), **extra},
        )

    def test_publish_validation_and_overlap(self):
        start = timezone.now() + timedelta(days=2)
        hour = timedelta(hours=1)
        self.assertEqual(self.publish(self.m, start, start + hour).status_code, 201)
        self.assertEqual(self.publish(self.m, start + hour / 2, start + 2 * hour).status_code, 409)
        # Back to back is allowed.
        self.assertEqual(self.publish(self.m, start + hour, start + 2 * hour).status_code, 201)
        self.assertEqual(self.publish(self.m, start - 5 * hour, start - 6 * hour).status_code, 400)
        past = timezone.now() - timedelta(days=1)
        self.assertEqual(self.publish(self.m, past, past + hour).status_code, 400)

    def test_admin_publishes_for_mentor(self):
        admin = self.user("boss", User.Role.ADMIN)
        start = timezone.now() + timedelta(days=2)
        end = start + timedelta(hours=1)
        self.assertEqual(self.publish(admin, start, end).status_code, 400)
        self.assertEqual(self.publish(admin, start, end, mentor=self.m.pk).status_code, 201)

    def test_book_then_conflict_then_rebook_after_cancel(self):
        slot = self.slot(self.m)
        first = self.client.post("/api/bookings/", {"slot": slot.pk})
        self.assertEqual(first.status_code, 201, first.data)
        other = self.client_for(self.user("other"))
        self.assertEqual(other.post("/api/bookings/", {"slot": slot.pk}).status_code, 409)
        cancelled = self.client.post(f"/api/bookings/{first.data['id']}/cancel/")
        self.assertEqual(cancelled.data["status"], "cancelled")
        self.assertEqual(cancelled.data["cancelled_by"], self.student.pk)
        self.assertEqual(other.post("/api/bookings/", {"slot": slot.pk}).status_code, 201)
        self.assertEqual(
            self.client.post(f"/api/bookings/{first.data['id']}/cancel/").status_code, 409
        )

    def test_student_overlap_rejected_but_back_to_back_allowed(self):
        a = self.slot(self.m, hours=48)
        other = self.mentor("m2")
        overlapping = services.publish_slot(
            mentor_id=other.pk,
            topic="x",
            starts_at=a.starts_at + timedelta(minutes=30),
            ends_at=a.ends_at,
        )
        adjacent = services.publish_slot(
            mentor_id=other.pk,
            topic="x",
            starts_at=a.ends_at,
            ends_at=a.ends_at + timedelta(minutes=20),
        )
        self.assertEqual(self.client.post("/api/bookings/", {"slot": a.pk}).status_code, 201)
        self.assertEqual(
            self.client.post("/api/bookings/", {"slot": overlapping.pk}).status_code, 409
        )
        self.assertEqual(self.client.post("/api/bookings/", {"slot": adjacent.pk}).status_code, 201)

    def test_unbookable_slots(self):
        self.assertEqual(self.client.post("/api/bookings/", {"slot": 999999}).status_code, 404)
        self.assertEqual(self.client.post("/api/bookings/", {"slot": "abc"}).status_code, 400)
        slot = self.slot(self.m)
        self.move(slot, timezone.now() - timedelta(minutes=5))
        started = self.client.post("/api/bookings/", {"slot": slot.pk})
        missing = self.client.post("/api/bookings/", {"slot": 999999})
        self.assertEqual((started.status_code, started.data), (404, missing.data))

    def test_cancellation_cutoff_applies_to_students_only(self):
        slot = self.slot(self.m, hours=1)
        booking = services.book_slot(student=self.student, slot_id=slot.pk)
        url = f"/api/bookings/{booking.pk}/cancel/"
        self.assertEqual(self.client.post(url).status_code, 409)
        self.assertEqual(self.client_for(self.m).post(url).status_code, 200)

    def test_started_session_cannot_be_cancelled(self):
        booking = services.book_slot(student=self.student, slot_id=self.slot(self.m).pk)
        self.move(booking.slot_id, timezone.now() - timedelta(minutes=1))
        admin = self.client_for(self.user("boss", User.Role.ADMIN))
        self.assertEqual(admin.post(f"/api/bookings/{booking.pk}/cancel/").status_code, 409)

    def test_cancelling_a_slot_cancels_its_booking(self):
        slot = self.slot(self.m)
        booking = services.book_slot(student=self.student, slot_id=slot.pk)
        mentor = self.client_for(self.m)
        self.assertEqual(mentor.post(f"/api/slots/{slot.pk}/cancel/").status_code, 204)
        booking.refresh_from_db()
        self.assertEqual((booking.status, booking.cancelled_by), ("cancelled", self.m))
        self.assertEqual(
            set(
                booking.notifications.exclude(kind="booking_cancelled").values_list(
                    "status", flat=True
                )
            ),
            {"skipped"},
        )
        self.assertEqual(self.client.get("/api/slots/").data["count"], 0)
        self.assertEqual(self.client.post("/api/bookings/", {"slot": slot.pk}).status_code, 404)
        self.assertEqual(mentor.post(f"/api/slots/{slot.pk}/cancel/").status_code, 409)
        # The mentor can publish over the withdrawn time again.
        services.publish_slot(
            mentor_id=self.m.pk, topic="x", starts_at=slot.starts_at, ends_at=slot.ends_at
        )

    def test_database_rejects_double_booking_without_the_service(self):
        slot = self.slot(self.m)
        services.book_slot(student=self.student, slot_id=slot.pk)
        with (
            self.assertRaisesMessage(IntegrityError, "booking_one_active_per_slot"),
            transaction.atomic(),
        ):
            Booking.objects.create(
                slot=slot,
                student=self.user("other"),
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
            )


class ConstraintTests(Factory, TestCase):
    """The overlap constraints hold for writes that skip the service."""

    def test_database_rejects_overlapping_slots_for_a_mentor(self):
        slot = self.slot(self.mentor())
        with (
            self.assertRaisesMessage(IntegrityError, "slot_no_mentor_overlap"),
            transaction.atomic(),
        ):
            Slot.objects.create(
                mentor=slot.mentor, topic="x", starts_at=slot.starts_at, ends_at=slot.ends_at
            )

    def test_database_rejects_overlapping_bookings_for_a_student(self):
        student = self.user("student")
        first, second = self.slot(self.mentor("m1")), self.slot(self.mentor("m2"))
        services.book_slot(student=student, slot_id=first.pk)
        with (
            self.assertRaisesMessage(IntegrityError, "booking_no_student_overlap"),
            transaction.atomic(),
        ):
            Booking.objects.create(
                slot=second, student=student, starts_at=first.starts_at, ends_at=first.ends_at
            )


class RegressionTests(Factory, TestCase):
    """One test per defect found in review."""

    def setUp(self):
        super().setUp()
        self.m = self.mentor()
        self.student = self.user("student")

    def deactivate(self, user):
        User.objects.filter(pk=user.pk).update(is_active=False)

    def test_inactive_mentor_is_hidden_and_unbookable(self):
        slot = self.slot(self.m)
        self.deactivate(self.m)
        client = self.client_for(self.student)
        self.assertEqual(client.get("/api/slots/").data["count"], 0)
        self.assertEqual(client.post("/api/bookings/", {"slot": slot.pk}).status_code, 404)

    def test_available_filter_excludes_cancelled_and_past_slots(self):
        open_slot, cancelled, past = (self.slot(self.m, hours=h) for h in (48, 52, 56))
        services.cancel_slot(actor=self.m, slot_id=cancelled.pk)
        self.move(past, timezone.now() - timedelta(hours=3))
        client = self.client_for(self.m)
        available = client.get("/api/slots/?available=true").data["results"]
        self.assertEqual([s["id"] for s in available], [open_slot.pk])
        self.assertEqual(client.get("/api/slots/?available=false").data["count"], 2)

    def test_slot_filter_does_not_reveal_ids(self):
        response = self.client_for(self.student).get("/api/bookings/?slot=999999")
        self.assertEqual((response.status_code, response.data["count"]), (200, 0))

    def test_demoted_admin_loses_django_admin_access(self):
        boss = self.user("boss", User.Role.ADMIN)
        old = User.objects.create_superuser("old", "old@example.test", PASSWORD)
        services.change_role(actor=boss, user_id=old.pk, role="student")
        old.refresh_from_db()
        self.assertFalse(old.is_staff or old.is_superuser)

    def test_service_enforces_slot_length(self):
        with self.assertRaisesMessage(Conflict, "15 minutes"):
            self.slot(self.m, length=4)


class ListingTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.m1, self.m2 = self.mentor("m1"), self.mentor("m2")
        self.student = self.user("student")
        self.client = self.client_for(self.student)
        self.slots = [self.slot(self.m1, hours=48 + 2 * i, topic="DSA") for i in range(15)]
        self.slots += [self.slot(self.m2, hours=48 + 2 * i, topic="Behavioural") for i in range(15)]

    def test_pagination(self):
        first = self.client.get("/api/slots/").data
        self.assertEqual((first["count"], len(first["results"])), (30, 20))
        second = self.client.get("/api/slots/?page=2").data
        ids = [s["id"] for s in first["results"] + second["results"]]
        self.assertEqual(len(set(ids)), 30)
        self.assertEqual(len(self.client.get("/api/slots/?page_size=5").data["results"]), 5)

    def test_filters(self):
        services.book_slot(student=self.student, slot_id=self.slots[0].pk)

        def count(**params):
            return self.client.get("/api/slots/", params).data["count"]

        self.assertEqual(count(mentor=self.m2.pk), 15)
        self.assertEqual(count(topic="dsa"), 15)
        self.assertEqual(count(available="true"), 29)
        self.assertEqual(count(available="false"), 1)
        self.assertEqual(count(starts_after=self.slots[14].starts_at.isoformat()), 2)
        self.assertEqual(self.client.get("/api/slots/?starts_after=nonsense").status_code, 400)

    def test_mentor_sees_only_own_slots(self):
        self.assertEqual(self.client_for(self.m1).get("/api/slots/").data["count"], 15)

    def test_query_count_does_not_grow_with_rows(self):
        for slot in self.slots[:15]:
            services.book_slot(student=self.student, slot_id=slot.pk)
        # token+user, count, page
        for url in ("/api/slots/", "/api/bookings/"):
            for size in (1, 15):
                with self.assertNumQueries(3):
                    self.client.get(url, {"page_size": size})
