"""Real threads, real connections, real PostgreSQL locks.

TransactionTestCase is required: inside TestCase's wrapping transaction other
connections could not see the fixtures.
"""

import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.core import mail
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from notifications import delivery
from notifications.models import Notification
from scheduling import services
from scheduling.exceptions import Conflict
from scheduling.models import Booking, Slot

from .base import Factory

ROUNDS = 10


def race(*calls):
    """Start every call at the same moment; return 'ok' or the exception name."""
    barrier = threading.Barrier(len(calls))

    def run(call):
        try:
            barrier.wait(timeout=10)
            call()
            return "ok"
        except Exception as exc:
            return type(exc).__name__
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return Counter(pool.map(run, calls))


class ConcurrencyTests(Factory, TransactionTestCase):
    def test_many_students_one_slot(self):
        slot = self.slot(self.mentor())
        students = [self.user(f"s{i}") for i in range(12)]
        result = race(*[
            lambda s=s: services.book_slot(student=s, slot_id=slot.pk) for s in students
        ])
        self.assertEqual(result, {"ok": 1, "Conflict": 11})
        self.assertEqual(Booking.objects.filter(status="booked").count(), 1)
        # One confirmation and one reminder for each of the two participants.
        self.assertEqual(Notification.objects.count(), 4)

    def test_http_requests_for_one_slot(self):
        slot = self.slot(self.mentor())
        clients = [self.client_for(self.user(f"s{i}")) for i in range(8)]
        codes = []

        def post(client):
            codes.append(client.post("/api/bookings/", {"slot": slot.pk}).status_code)

        self.assertEqual(race(*[lambda c=c: post(c) for c in clients]), {"ok": 8})
        self.assertEqual(Counter(codes), {201: 1, 409: 7})

    def test_one_student_two_overlapping_slots(self):
        student = self.user("student")
        first, second = self.mentor("m1"), self.mentor("m2")
        for i in range(ROUNDS):
            a, b = self.slot(first, hours=48 + 3 * i), self.slot(second, hours=48 + 3 * i)
            result = race(
                lambda: services.book_slot(student=student, slot_id=a.pk),
                lambda: services.book_slot(student=student, slot_id=b.pk),
            )
            self.assertEqual(result, {"ok": 1, "Conflict": 1}, f"round {i}")

    def test_one_mentor_publishing_overlapping_slots(self):
        mentor = self.mentor()
        for i in range(ROUNDS):
            result = race(*[lambda h=48 + 3 * i: self.slot(mentor, hours=h)] * 4)
            self.assertEqual(result, {"ok": 1, "Conflict": 3}, f"round {i}")

    def test_admins_demoting_each_other(self):
        for i in range(ROUNDS):
            a, b = self.user(f"a{i}", "admin"), self.user(f"b{i}", "admin")
            result = race(
                lambda: services.change_role(actor=a, user_id=b.pk, role="student"),
                lambda: services.change_role(actor=b, user_id=a.pk, role="student"),
            )
            self.assertEqual(result, {"ok": 1, "PermissionDenied": 1}, f"round {i}")

    def test_double_cancel(self):
        mentor, student = self.mentor(), self.user("student")
        booking = services.book_slot(student=student, slot_id=self.slot(mentor).pk)
        result = race(
            lambda: services.cancel_booking(actor=student, booking_id=booking.pk),
            lambda: services.cancel_booking(actor=mentor, booking_id=booking.pk),
        )
        self.assertEqual(result, {"ok": 1, "Conflict": 1})

    def test_slot_cancellation_racing_a_booking(self):
        mentor, student = self.mentor(), self.user("student")
        for i in range(ROUNDS):
            slot = self.slot(mentor, hours=48 + 3 * i)
            result = race(
                lambda: services.cancel_slot(actor=mentor, slot_id=slot.pk),
                lambda: services.book_slot(student=student, slot_id=slot.pk),
            )
            # Either order is valid; a live booking on a cancelled slot is not.
            self.assertIn(dict(result), [{"ok": 2}, {"ok": 1, "NotFound": 1}])
            self.assertIsNotNone(Slot.objects.get(pk=slot.pk).cancelled_at)
            self.assertFalse(Booking.objects.filter(slot=slot, status="booked").exists())

    def test_parallel_workers_send_each_message_once(self):
        mentor = self.mentor()
        for i in range(10):
            services.book_slot(
                student=self.user(f"s{i}"), slot_id=self.slot(mentor, hours=48 + 2 * i).pk
            )
        Notification.objects.update(available_at=timezone.now() - timedelta(seconds=1))
        result = race(*[delivery.process_due] * 4)
        self.assertEqual(result, {"ok": 4})
        self.assertEqual(len(mail.outbox), 40)
        self.assertEqual(len({(m.to[0], m.subject) for m in mail.outbox}), 40)
        self.assertEqual(Notification.objects.filter(status="sent", attempts=1).count(), 40)

    def test_worker_skips_a_message_locked_by_another(self):
        services.book_slot(student=self.user("s"), slot_id=self.slot(self.mentor()).pk)
        Notification.objects.exclude(
            pk=Notification.objects.order_by("id").first().pk).delete()
        locked, release = threading.Event(), threading.Event()

        def holder():
            from django.db import transaction
            try:
                with transaction.atomic():
                    list(Notification.objects.select_for_update())
                    locked.set()
                    release.wait(10)
            finally:
                connection.close()

        thread = threading.Thread(target=holder)
        thread.start()
        try:
            self.assertTrue(locked.wait(10))
            self.assertIsNone(delivery.claim_next())
        finally:
            release.set()
            thread.join()
        self.assertIsNotNone(delivery.claim_next())

    def test_deactivation_racing_a_booking(self):
        admin = self.user("boss", "admin")
        for i in range(ROUNDS):
            mentor, student = self.mentor(f"m{i}"), self.user(f"s{i}")
            slot = self.slot(mentor)
            target = student if i % 2 else mentor
            result = race(
                lambda: services.set_active(actor=admin, user_id=target.pk, is_active=False),
                lambda: services.book_slot(student=student, slot_id=slot.pk),
            )
            # Either order is valid; a live booking with a deactivated person is not.
            self.assertEqual(result["ok"] >= 1, True, result)
            self.assertNotIn("OperationalError", result, f"round {i}")
            self.assertFalse(Booking.objects.filter(slot=slot, status="booked").exists(), i)
