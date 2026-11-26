"""Hostile and malformed input on every route must never cause a server error.

The random generator is seeded, so a failure repeats.
"""

import json
import random

from django.core.cache import cache
from django.db import transaction
from django.test import TestCase, override_settings

from .test_authorization import CALLERS, POLICY, World

ROUNDS = 40

FIELDS = [
    "username", "email", "password", "token", "uid", "role", "is_active", "slot", "topic",
    "starts_at", "ends_at", "mentor", "meeting_link", "preparation_notes", "attendance",
    "communication", "problem_solving", "technical", "strengths", "improvements",
    "next_steps", "current_password", "new_password", "display_name", "headline", "bio",
    "experience_level", "target_roles", "topics", "timezone", "id", "student", "status",
]  # fmt: skip
PARAMS = [
    "page", "page_size", "ordering", "mentor", "student", "slot", "status", "topic", "search",
    "available", "cancelled", "is_active", "kind", "starts_after", "starts_before",
    "ends_after", "format",
]  # fmt: skip
VALUES = [
    None, True, False, 0, 1, -1, 2**31, 2**63, 10**40, 1.5, float("1e308"), "", " ", "0", "-1",
    "1", "true", "null", "undefined", "abc", "a" * 5000, "\x00", "a\x00b", "\ud800",
    "\U0001f600", "‮evil", "' OR 1=1 --", "; DROP TABLE accounts_user; --", "%", "_",
    "../../etc/passwd", "<script>alert(1)</script>", "{{7*7}}", "${jndi:ldap://x}",
    "https://", "http://[", "javascript:alert(1)", "2026-13-45T99:99:99Z", "9999-12-31T23:59:59Z",
    "0001-01-01T00:00:00+14:00", "now", "Asia/Kolkata", "../zoneinfo", [], [1, 2], [None],
    ["x"] * 100, {}, {"a": {"b": {}}}, [[[[[[[]]]]]]],
]  # fmt: skip
RAW_BODIES = [
    b"", b"{", b"[]", b"null", b'"text"', b"123", b"\xff\xfe", b"{" * 3000,
    b'{"slot": NaN}', b'{"slot": 1, "slot": "x"}', b"a=1&b=2",
]  # fmt: skip
CONTENT_TYPES = [
    "application/json", "text/plain", "application/xml", "multipart/form-data",
    "application/x-www-form-urlencoded", "",
]  # fmt: skip


@override_settings(ALLOW_REGISTRATION=True)
class FuzzTests(World, TestCase):
    def setUp(self):
        super().setUp()
        self.build()

    def random_body(self, rng):
        names = rng.sample(FIELDS, rng.randint(0, 8))
        return {name: rng.choice(VALUES) for name in names}

    def send(self, client, rng, method, url):
        if method == "get":
            query = {n: str(rng.choice(VALUES)) for n in rng.sample(PARAMS, rng.randint(0, 5))}
            try:
                return client.get(url, query)
            except UnicodeEncodeError:  # the client cannot encode a lone surrogate
                return None
        if rng.random() < 0.25:
            return client.generic(
                method.upper(), url, rng.choice(RAW_BODIES), content_type=rng.choice(CONTENT_TYPES)
            )
        return client.generic(
            method.upper(),
            url,
            json.dumps(self.random_body(rng)),
            content_type="application/json",
        )

    def check(self, response, context):
        if response is None:
            return
        self.assertLess(response.status_code, 500, context)
        if response.content and response.status_code != 204:
            self.assertEqual(response["Content-Type"], "application/json", context)

    def test_random_input_on_every_route(self):
        rng = random.Random(20261127)
        calls = 0
        for method, route, _, _ in POLICY:
            if route == "health/":
                continue
            for _ in range(ROUNDS):
                caller = rng.choice(CALLERS)
                with transaction.atomic():
                    cache.clear()  # otherwise the throttle answers instead of the route
                    client = self.client_named(caller)
                    url = "/" + route.format(**self.ids)
                    context = (method, url, caller, rng.getstate()[1][0])
                    self.check(self.send(client, rng, method, url), context)
                    calls += 1
                    transaction.set_rollback(True)
        self.assertGreater(calls, 1000)

    def test_hostile_path_ids(self):
        ids = ["0", "-1", "1.5", "abc", str(2**31), str(2**63), "9" * 18, "9" * 40, "%00", "\u0661"]
        client = self.client_named("admin")
        for method, route, template, _ in POLICY:
            if "{" not in route:
                continue
            for value in ids:
                url = "/" + route.format(**dict.fromkeys(self.ids, value))
                with self.subTest(url=url, method=method), transaction.atomic():
                    response = getattr(client, method)(url, self.body(template), format="json")
                    self.assertLess(response.status_code, 500)
                    transaction.set_rollback(True)

    def test_hostile_headers(self):
        client = self.client_named("anonymous")
        headers = [
            {"HTTP_AUTHORIZATION": value}
            for value in ("Token", "Token a b", "Token " + "x" * 5000, "Bearer x", "Token é", "  ")
        ]
        headers += [{"HTTP_ORIGIN": "null"}, {"HTTP_X_FORWARDED_FOR": "1.1.1.1, " * 500}]
        for extra in headers:
            with self.subTest(extra=str(extra)[:60]):
                cache.clear()
                self.assertLess(client.get("/api/slots/", **extra).status_code, 500)
                self.assertLess(client.post("/api/auth/login/", {}, **extra).status_code, 500)

    def test_a_forged_client_address_does_not_escape_the_rate_limit(self):
        client = self.client_named("anonymous")
        codes = [
            client.post("/api/auth/login/", {}, HTTP_X_FORWARDED_FOR=f"10.0.0.{n}").status_code
            for n in range(14)
        ]
        self.assertEqual(codes[-1], 429)
