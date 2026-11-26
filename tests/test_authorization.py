"""Every route, called by every kind of caller.

The table below is the access policy. A route that is added without a row here
fails `test_every_route_is_covered`.
"""

from datetime import timedelta

from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Invitation, User
from feedback.models import Feedback
from notifications.models import Notification
from scheduling import services

from .base import PASSWORD, Factory

CALLERS = ["anonymous", "admin", "mentor", "other_mentor", "student", "other_student"]
FEEDBACK = {
    "communication": 3,
    "problem_solving": 3,
    "technical": 3,
    "strengths": "a",
    "improvements": "b",
    "next_steps": "c",
}


def row(anonymous, admin, mentor, other_mentor, student, other_student):
    return dict(
        zip(CALLERS, (anonymous, admin, mentor, other_mentor, student, other_student), strict=True)
    )


def everyone(code):
    return row(401, code, code, code, code, code)


def admin_only(code):
    return row(401, code, 403, 403, 403, 403)


def public(code):
    return row(code, code, code, code, code, code)


# (method, route, body, expected status per caller)
POLICY = [
    ("get", "health/", None, public(200)),
    ("get", "api/config/", None, public(200)),
    ("post", "api/auth/register/", {}, public(400)),
    ("post", "api/auth/login/", {}, public(400)),
    ("post", "api/auth/accept-invitation/", {}, public(400)),
    ("post", "api/auth/password-reset/", {"email": "x@example.test"}, public(202)),
    ("post", "api/auth/password-reset/confirm/", {}, public(400)),
    ("post", "api/auth/logout/", {}, everyone(204)),
    ("post", "api/auth/password/", {}, everyone(400)),
    ("get", "api/auth/me/", None, everyone(200)),
    ("get", "api/profile/", None, everyone(200)),
    ("patch", "api/profile/", {"headline": "x"}, everyone(200)),
    ("get", "api/mentors/", None, everyone(200)),
    ("get", "api/users/", None, admin_only(200)),
    ("get", "api/users/{student}/profile/", None, row(401, 200, 200, 404, 200, 404)),
    ("patch", "api/users/{other_student}/role/", {"role": "mentor"}, admin_only(200)),
    ("patch", "api/users/{other_student}/status/", {"is_active": False}, admin_only(200)),
    ("get", "api/invitations/", None, admin_only(200)),
    (
        "post",
        "api/invitations/",
        {"email": "n@example.test", "role": "student"},
        admin_only(201),
    ),
    ("post", "api/invitations/{invitation}/revoke/", {}, admin_only(200)),
    ("get", "api/slots/", None, everyone(200)),
    ("post", "api/slots/", "new_slot", row(401, 400, 201, 201, 403, 403)),
    # A student sees upcoming slots; another mentor does not see this one.
    ("get", "api/slots/{open_slot}/", None, row(401, 200, 200, 404, 200, 200)),
    ("post", "api/slots/{open_slot}/cancel/", {}, row(401, 204, 204, 404, 403, 403)),
    ("get", "api/bookings/", None, everyone(200)),
    ("post", "api/bookings/", {"slot": "{open_slot}"}, row(401, 403, 403, 403, 201, 201)),
    ("get", "api/bookings/{booking}/", None, row(401, 200, 200, 404, 200, 404)),
    (
        "patch",
        "api/bookings/{booking}/",
        {"meeting_link": "https://meet.example.test/a"},
        row(401, 200, 200, 404, 403, 404),
    ),
    (
        "patch",
        "api/bookings/{booking}/",
        {"preparation_notes": "x"},
        row(401, 200, 403, 404, 200, 404),
    ),
    ("post", "api/bookings/{booking}/cancel/", {}, row(401, 200, 200, 404, 200, 404)),
    (
        "post",
        "api/bookings/{booking}/reschedule/",
        {"slot": "{open_slot}"},
        row(401, 201, 403, 404, 201, 404),
    ),
    (
        "post",
        "api/bookings/{past}/attendance/",
        {"attendance": "completed"},
        row(401, 200, 200, 404, 403, 404),
    ),
    ("get", "api/bookings/{past}/feedback/", None, row(401, 200, 200, 404, 200, 404)),
    ("put", "api/bookings/{past}/feedback/", FEEDBACK, row(401, 403, 200, 404, 403, 404)),
    ("get", "api/feedback/", None, everyone(200)),
    ("get", "api/feedback/progress/", None, row(401, 400, 400, 400, 200, 200)),
    ("get", "api/admin/overview/", None, admin_only(200)),
    ("get", "api/notifications/", None, admin_only(200)),
    ("post", "api/notifications/{failed}/retry/", {}, admin_only(200)),
]


class World(Factory):
    """One of everything the routes refer to."""

    def build(self):
        self.people = {
            "admin": self.user("admin", User.Role.ADMIN),
            "mentor": self.mentor("mentor"),
            "other_mentor": self.mentor("other_mentor"),
            "student": self.user("student"),
            "other_student": self.user("other_student"),
        }
        mentor, student = self.people["mentor"], self.people["student"]
        booked = self.slot(mentor, hours=48)
        past = self.slot(mentor, hours=60)
        open_slot = self.slot(mentor, hours=72)
        booking = services.book_slot(student=student, slot_id=booked.pk)
        done = services.book_slot(student=student, slot_id=past.pk)
        self.move(past, timezone.now() - timedelta(hours=3))
        Feedback.objects.create(booking=done, **FEEDBACK)
        invitation = Invitation.objects.create(
            email="i@example.test",
            role="student",
            nonce="n",
            invited_by=self.people["admin"],
            expires_at=timezone.now() + timedelta(days=1),
        )
        failed = Notification.objects.filter(booking=booking).first()
        Notification.objects.filter(pk=failed.pk).update(status="failed")
        self.ids = {
            "student": student.pk,
            "other_student": self.people["other_student"].pk,
            "booking": booking.pk,
            "past": done.pk,
            "open_slot": open_slot.pk,
            "invitation": invitation.pk,
            "failed": failed.pk,
        }

    def body(self, template):
        if template == "new_slot":
            start = timezone.now() + timedelta(days=30)
            return {
                "topic": "t",
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=1)).isoformat(),
            }
        if template is None:
            return None
        return {
            key: value.format(**self.ids) if isinstance(value, str) else value
            for key, value in template.items()
        }

    def client_named(self, caller):
        return APIClient() if caller == "anonymous" else self.client_for(self.people[caller])


@override_settings(ALLOW_REGISTRATION=True)
class AccessPolicyTests(World, TestCase):
    def setUp(self):
        super().setUp()
        self.build()

    def test_every_caller_gets_the_expected_answer_on_every_route(self):
        for method, route, template, expected in POLICY:
            for caller in CALLERS:
                # Each call starts from the same world.
                case = self.subTest(method=method, route=route, caller=caller)
                with case, transaction.atomic():
                    self.assert_answer(method, route, template, caller, expected[caller])
                    transaction.set_rollback(True)

    def assert_answer(self, method, route, template, caller, expected):
        url = "/" + route.format(**self.ids)
        client = self.client_named(caller)
        response = getattr(client, method)(url, self.body(template), format="json")
        self.assertEqual(response.status_code, expected, getattr(response, "data", None))

    def test_no_response_ever_carries_a_password_hash(self):
        for caller in CALLERS[1:]:
            client = self.client_named(caller)
            for method, route, _, _ in POLICY:
                if method != "get":
                    continue
                text = client.get("/" + route.format(**self.ids)).content.decode()
                self.assertNotIn("pbkdf2", text, route)
                self.assertNotIn(PASSWORD, text, route)

    def test_email_addresses_reach_only_their_owner_and_admins(self):
        mine = {"mentor": "mentor@", "student": "student@", "other_student": "other_student@"}
        for caller, own in mine.items():
            client = self.client_named(caller)
            for method, route, _, _ in POLICY:
                if method != "get":
                    continue
                text = client.get("/" + route.format(**self.ids)).content.decode()
                for address in ("admin@", "mentor@", "student@"):
                    leaked = f'"{address}example.test"' in text and address != own
                    self.assertFalse(leaked, f"{caller} saw {address} at {route}")

    def test_every_route_is_covered(self):
        def walk(resolver, prefix=""):
            for entry in resolver.url_patterns:
                path = prefix + str(entry.pattern)
                if isinstance(entry, URLResolver):
                    if entry.app_name != "admin":
                        yield from walk(entry, path)
                elif isinstance(entry, URLPattern):
                    yield path

        def normalise(route):
            import re

            route = route.replace("^", "").replace("$", "")
            route = re.sub(r"\(\?P<\w+>[^)]*\)", "{}", route)
            return re.sub(r"<[^>]+>|\{\w+\}", "{}", route)

        routed = {normalise(path) for path in walk(get_resolver())}
        covered = {normalise(route) for _, route, _, _ in POLICY}
        self.assertEqual({p for p in routed if not p.startswith("admin/")} - covered, set())
