from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from scheduling import services
from scheduling.models import Slot

from .base import Factory


class CommitmentFilterTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.m1, self.m2 = self.mentor("m1"), self.mentor("m2")
        self.s1, self.s2 = self.user("s1"), self.user("s2")
        self.admin = self.user("boss", User.Role.ADMIN)
        self.a = self.slot(self.m1, hours=48)
        self.b = self.slot(self.m2, hours=52)
        self.first = services.book_slot(student=self.s1, slot_id=self.a.pk)
        self.second = services.book_slot(student=self.s2, slot_id=self.b.pk)

    def ids(self, user, path, **params):
        response = self.client_for(user).get(path, params)
        self.assertEqual(response.status_code, 200, response.data)
        return [row["id"] for row in response.data["results"]]

    def test_admin_finds_one_users_bookings(self):
        self.assertEqual(self.ids(self.admin, "/api/bookings/", student=self.s1.pk),
                         [self.first.pk])
        self.assertEqual(self.ids(self.admin, "/api/bookings/", mentor=self.m2.pk),
                         [self.second.pk])

    def test_filters_cannot_widen_what_a_role_sees(self):
        self.assertEqual(self.ids(self.s1, "/api/bookings/", student=self.s2.pk), [])
        self.assertEqual(self.ids(self.m1, "/api/bookings/", mentor=self.m2.pk), [])
        self.assertEqual(self.ids(self.m1, "/api/slots/", mentor=self.m2.pk), [])

    def test_ends_after_includes_a_session_in_progress(self):
        now = timezone.now()
        Slot.objects.filter(pk=self.a.pk).update(
            starts_at=now - timedelta(minutes=10), ends_at=now + timedelta(minutes=50))
        params = {"ends_after": now.isoformat()}
        self.assertEqual(self.ids(self.admin, "/api/slots/", **params), [self.a.pk, self.b.pk])
        params["starts_after"] = now.isoformat()
        self.assertEqual(self.ids(self.admin, "/api/slots/", **params), [self.b.pk])

    def test_cancelled_filter(self):
        services.cancel_slot(actor=self.admin, slot_id=self.a.pk)
        self.assertEqual(self.ids(self.admin, "/api/slots/", cancelled="true"), [self.a.pk])
        self.assertEqual(self.ids(self.admin, "/api/slots/", cancelled="false"), [self.b.pk])

    def test_malformed_values_are_refused_not_ignored(self):
        client = self.client_for(self.admin)
        for url in (
            "/api/slots/?available=ture", "/api/slots/?cancelled=maybe",
            "/api/slots/?mentor=1.5", "/api/slots/?mentor=-1",
            "/api/bookings/?student=abc", f"/api/bookings/?slot={10**30}",
        ):
            self.assertEqual(client.get(url).status_code, 400, url)

    def test_booking_names_its_mentor(self):
        data = self.client_for(self.s1).get(f"/api/bookings/{self.first.pk}/").data
        self.assertEqual(data["mentor"], self.m1.pk)

    def test_ordering_both_ways_with_id_as_tie_break(self):
        tie = self.slot(self.m1, hours=60)
        Slot.objects.filter(pk=tie.pk).update(
            starts_at=self.b.starts_at, ends_at=self.b.ends_at, mentor=self.m1)
        expected = [self.a.pk, self.b.pk, tie.pk]
        self.assertEqual(self.ids(self.admin, "/api/slots/", ordering="starts_at"), expected)
        newest = [
            self.ids(self.admin, "/api/slots/", ordering="-starts_at", page_size=1, page=n)[0]
            for n in (1, 2, 3)
        ]
        self.assertEqual(newest, expected[::-1])
        self.assertEqual(
            self.ids(self.admin, "/api/bookings/", ordering="-starts_at"),
            [self.second.pk, self.first.pk])

    def test_other_ordering_fields_are_ignored(self):
        self.assertEqual(self.ids(self.admin, "/api/slots/", ordering="-topic,mentor"),
                         [self.a.pk, self.b.pk])


class UserDirectoryTests(Factory, TestCase):
    def test_admin_searches_active_mentors(self):
        admin = self.user("boss", User.Role.ADMIN)
        priya, gone = self.mentor("Priya"), self.mentor("priyanka")
        self.mentor("omar")
        User.objects.filter(pk=gone.pk).update(is_active=False)
        client = self.client_for(admin)
        rows = client.get("/api/users/?role=mentor&search=PRI&is_active=true").data["results"]
        self.assertEqual([(r["id"], r["is_active"]) for r in rows], [(priya.pk, True)])
        self.assertEqual(client.get("/api/users/?is_active=false").data["count"], 1)
        self.assertEqual(client.get("/api/users/?is_active=nope").status_code, 400)
        self.assertEqual(self.client_for(priya).get("/api/users/?search=o").status_code, 403)
