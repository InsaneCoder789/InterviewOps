"""Illustrative local data, so a client can be built against a database with content."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Profile, User
from feedback.services import save_feedback
from notifications.models import Notification
from scheduling import services
from scheduling.models import Booking, Slot

PEOPLE = [
    ("demo-admin", "admin", []),
    ("demo-mentor-asha", "mentor", ["system design", "dsa"]),
    ("demo-mentor-vik", "mentor", ["behavioural"]),
    ("demo-student-ira", "student", ["dsa"]),
    ("demo-student-noor", "student", ["system design"]),
]


class Command(BaseCommand):
    help = "Create made-up users and sessions in a local database (DEBUG only)."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="shared by the demo users; random if omitted")

    @transaction.atomic
    def handle(self, *args, password, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DJANGO_DEBUG=1.")
        if User.objects.filter(username__startswith="demo-").exists():
            raise CommandError("Demo users already exist.")
        password = password or secrets.token_urlsafe(12)
        users = {}
        for name, role, topics in PEOPLE:
            user = User.objects.create_user(name, f"{name}@example.test", password, role=role)
            Profile.objects.create(user=user, display_name=name, topics=topics)
            users[name] = user
        start = timezone.now().replace(minute=0, second=0, microsecond=0)
        asha, vik = users["demo-mentor-asha"], users["demo-mentor-vik"]
        ira = users["demo-student-ira"]
        slots = [
            services.publish_slot(
                mentor_id=mentor.pk, topic=topic,
                starts_at=start + timedelta(hours=hours),
                ends_at=start + timedelta(hours=hours + 1))
            for mentor, topic, hours in (
                (asha, "System design", 26), (asha, "Data structures", 50),
                (vik, "Behavioural", 74), (vik, "Behavioural", 98))
        ]
        services.book_slot(student=ira, slot_id=slots[0].pk)
        # One finished session with feedback: book it, then move it into the past.
        done = services.book_slot(student=ira, slot_id=slots[1].pk)
        past = {"starts_at": start - timedelta(hours=48), "ends_at": start - timedelta(hours=47)}
        Slot.objects.filter(pk=slots[1].pk).update(**past)
        Booking.objects.filter(pk=done.pk).update(**past)
        save_feedback(actor=asha, booking_id=done.pk, values={
            "communication": 4, "problem_solving": 3, "technical": 3,
            "strengths": "Explained the approach before coding.",
            "improvements": "Check edge cases.",
            "next_steps": "Practise two graph problems.",
        })
        # Demo data sends no mail.
        Notification.objects.update(status=Notification.Status.SKIPPED)
        self.stdout.write(
            "Created " + ", ".join(users) + f"\nPassword for all of them: {password}")
