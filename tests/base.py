from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import User
from scheduling import services
from scheduling.models import Booking, Slot

PASSWORD = "test-only-passphrase-417"


class Factory:
    def setUp(self):
        super().setUp()
        cache.clear()  # throttle counters

    def user(self, name, role=User.Role.STUDENT):
        return User.objects.create_user(name, f"{name}@example.test", PASSWORD, role=role)

    def mentor(self, name="mentor"):
        return self.user(name, User.Role.MENTOR)

    def slot(self, mentor, hours=48, length=1, topic="System design"):
        start = timezone.now().replace(microsecond=0) + timedelta(hours=hours)
        return services.publish_slot(
            mentor_id=mentor.pk, topic=topic,
            starts_at=start, ends_at=start + timedelta(hours=length),
        )

    def client_for(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=user)[0].key}")
        return client

    def move(self, slot, start, length=timedelta(hours=1)):
        """Put a session at any time, including the past, keeping its bookings in step."""
        pk = getattr(slot, "pk", slot)
        Slot.objects.filter(pk=pk).update(starts_at=start, ends_at=start + length)
        Booking.objects.filter(slot_id=pk).update(starts_at=start, ends_at=start + length)
