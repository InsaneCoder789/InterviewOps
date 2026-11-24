from django.conf import settings
from django.db import models
from django.db.models import Q


class Notification(models.Model):
    """One email to send. The table is both the queue and the delivery record."""

    class Kind(models.TextChoices):
        BOOKING_CONFIRMED = "booking_confirmed"
        BOOKING_CANCELLED = "booking_cancelled"
        BOOKING_RESCHEDULED = "booking_rescheduled"
        REMINDER = "reminder"

    class Status(models.TextChoices):
        PENDING = "pending"
        SENDING = "sending"
        SENT = "sent"
        FAILED = "failed"
        SKIPPED = "skipped"

    kind = models.CharField(max_length=32, choices=Kind.choices)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.CASCADE, null=True, blank=True,
        related_name="notifications",
    )
    booking = models.ForeignKey(
        "scheduling.Booking", models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # When pending: earliest next attempt. When sending: when the worker's lease expires.
    available_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["available_at", "id"]
        indexes = [
            models.Index(
                fields=["available_at", "id"],
                condition=Q(status__in=["pending", "sending"]),
                name="notification_due_idx",
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "recipient"],
                condition=Q(kind="reminder"),
                name="notification_one_reminder_per_person",
            )
        ]
