"""Many threads doing random things to the same few people and sessions.

Refusals are expected. Deadlocks, integrity errors and broken invariants are not.
Set STRESS_OPERATIONS to run longer, and STRESS_SEED to replay a choice sequence
(thread timing still varies).
"""

import os
import random
import threading
from collections import Counter
from datetime import timedelta

from django.db import connection
from django.db.models import F, Q
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from accounts import passwords
from accounts.models import User
from feedback.models import Feedback
from feedback.services import save_feedback
from notifications import delivery
from notifications.models import Notification
from notifications.outbox import LIVE_BOOKING_KINDS, UNSENT
from scheduling import services
from scheduling.exceptions import Conflict
from scheduling.models import Booking, Slot

from .base import Factory

THREADS = 10
OPERATIONS = int(os.environ.get("STRESS_OPERATIONS", "120"))
REFUSALS = (Conflict, NotFound, PermissionDenied)
FEEDBACK = {
    "communication": 3,
    "problem_solving": 3,
    "technical": 3,
    "strengths": "a",
    "improvements": "b",
    "next_steps": "c",
}


class StressTests(Factory, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.admins = [self.user(f"admin{i}", "admin") for i in range(2)]
        self.mentors = [self.mentor(f"m{i}") for i in range(3)]
        self.students = [self.user(f"s{i}") for i in range(5)]
        self.now = timezone.now().replace(minute=0, second=0, microsecond=0)
        for index, mentor in enumerate(self.mentors):
            for n in range(4):
                self.slot(mentor, hours=48 + n * 2 + index)
        # Sessions that already happened, for attendance and feedback.
        for n, student in enumerate(self.students):
            slot = self.slot(self.mentors[n % 3], hours=200 + n * 3)
            services.book_slot(student=student, slot_id=slot.pk)
            self.move(slot, timezone.now() - timedelta(hours=10 + n * 3))

    # Each operation reads fresh IDs, as a client with a slightly old screen would.
    def operations(self, rng):
        def pick(queryset):
            ids = list(queryset.values_list("pk", flat=True))
            return rng.choice(ids) if ids else 0

        def user(pk):
            return User.objects.get(pk=pk)

        admin = rng.choice(self.admins)
        student = rng.choice(self.students)
        mentor = rng.choice(self.mentors)

        # Mostly plausible targets, so that operations succeed and can collide;
        # sometimes anything at all, so that refusals are exercised too.
        def slot():
            open_slots = Slot.objects.filter(
                cancelled_at__isnull=True, starts_at__gt=timezone.now()
            ).exclude(bookings__status="booked")
            plausible = rng.random() < 0.8 and open_slots.exists()
            return pick(open_slots if plausible else Slot.objects.all())

        def booking():
            upcoming = Booking.objects.filter(status="booked", starts_at__gt=timezone.now())
            plausible = rng.random() < 0.8 and upcoming.exists()
            return pick(upcoming if plausible else Booking.objects.all())

        def past_booking():
            return pick(Booking.objects.filter(status="booked", starts_at__lte=timezone.now()))

        def owner_of(pk):
            found = Booking.objects.filter(pk=pk).first()
            if found is None:
                return admin
            return user(rng.choice([found.student_id, found.slot.mentor_id, admin.pk]))

        def publish():
            start = self.now + timedelta(hours=rng.randint(24, 90), minutes=rng.choice([0, 30]))
            services.publish_slot(
                mentor_id=mentor.pk,
                topic="stress",
                starts_at=start,
                ends_at=start + timedelta(hours=1),
            )

        def cancel():
            pk = booking()
            services.cancel_booking(actor=owner_of(pk), booking_id=pk)

        def reschedule():
            pk = booking()
            services.reschedule_booking(actor=owner_of(pk), booking_id=pk, slot_id=slot())

        def update():
            pk = booking()
            services.update_session(
                actor=admin, booking_id=pk, meeting_link=f"https://m.example.test/{rng.random()}"
            )

        def attend():
            pk = past_booking() if rng.random() < 0.8 else booking()
            services.record_attendance(
                actor=owner_of(pk),
                booking_id=pk,
                attendance=rng.choice(["completed", "student_absent"]),
            )

        def review():
            pk = past_booking() if rng.random() < 0.8 else booking()
            found = Booking.objects.filter(pk=pk).first()
            if found is None:
                raise NotFound("Nothing to review.")
            save_feedback(actor=user(found.slot.mentor_id), booking_id=pk, values=FEEDBACK)

        def status():
            target = rng.choice(self.students + self.mentors)
            services.set_active(actor=admin, user_id=target.pk, is_active=rng.random() < 0.75)

        def role():
            target = rng.choice(self.students + self.mentors)
            home = "mentor" if target in self.mentors else "student"
            services.change_role(
                actor=admin,
                user_id=target.pk,
                role=home if rng.random() < 0.8 else "admin",
            )

        return [
            (6, "book", lambda: services.book_slot(student=user(student.pk), slot_id=slot())),
            (3, "publish", publish),
            (3, "cancel", cancel),
            (2, "cancel_slot", lambda: services.cancel_slot(actor=admin, slot_id=slot())),
            (4, "reschedule", reschedule),
            (2, "update", update),
            (1, "attendance", attend),
            (2, "feedback", review),
            (2, "status", status),
            (1, "role", role),
            (1, "reset", lambda: passwords.request_reset(email=student.email)),
            (2, "worker", lambda: delivery.process_due(limit=10)),
        ]

    def test_random_concurrent_operations_keep_every_invariant(self):
        seed = int(os.environ.get("STRESS_SEED", "7"))
        outcomes, failures = Counter(), []
        barrier = threading.Barrier(THREADS)

        def run(number):
            rng = random.Random(seed * 1000 + number)
            try:
                barrier.wait(timeout=30)
                for _ in range(OPERATIONS):
                    table = self.operations(rng)
                    ((_, name, call),) = rng.choices(table, weights=[w for w, _, _ in table])
                    try:
                        call()
                        outcomes[name, "ok"] += 1
                    except REFUSALS:
                        outcomes[name, "refused"] += 1
                    except Exception as exc:
                        failures.append(f"{name}: {type(exc).__name__}: {exc}"[:300])
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(n,)) for n in range(THREADS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=600)
        self.assertFalse(any(t.is_alive() for t in threads), "a thread hung")
        self.assertEqual(failures[:10], [], f"{len(failures)} unexpected errors")
        self.assertEqual(sum(outcomes.values()), THREADS * OPERATIONS)
        for name in ("book", "publish", "cancel", "reschedule", "status", "feedback"):
            self.assertGreater(
                outcomes[name, "ok"], 0, f"{name} never succeeded (seed {seed}): {outcomes}"
            )
        self.assert_invariants()

    def assert_invariants(self):
        now = timezone.now()
        live = Booking.objects.filter(status="booked")
        upcoming = live.filter(starts_at__gt=now)
        open_slots = Slot.objects.filter(cancelled_at__isnull=True, starts_at__gt=now)
        checks = {
            "live booking on a cancelled slot": live.filter(slot__cancelled_at__isnull=False),
            "booking times differ from slot": live.exclude(
                starts_at=F("slot__starts_at"), ends_at=F("slot__ends_at")
            ),
            "inactive person has an upcoming booking": upcoming.filter(
                Q(student__is_active=False) | Q(slot__mentor__is_active=False)
            ),
            "upcoming booking with a wrong role": upcoming.exclude(
                student__role="student", slot__mentor__role="mentor"
            ),
            "inactive or ex-mentor has an open slot": open_slots.exclude(
                mentor__is_active=True, mentor__role="mentor"
            ),
            "unsent notice for a cancelled booking": Notification.objects.filter(
                booking__status="cancelled", kind__in=LIVE_BOOKING_KINDS, status__in=UNSENT
            ),
            "feedback on a session not completed": Feedback.objects.exclude(
                booking__status="booked", booking__attendance="completed"
            ),
        }
        for message, rows in checks.items():
            self.assertEqual(list(rows.values_list("pk", flat=True)), [], message)
        for booking in live:
            overlapping = live.filter(
                student=booking.student,
                starts_at__lt=booking.ends_at,
                ends_at__gt=booking.starts_at,
            ).exclude(pk=booking.pk)
            self.assertFalse(overlapping.exists(), f"student overlap at booking {booking.pk}")
