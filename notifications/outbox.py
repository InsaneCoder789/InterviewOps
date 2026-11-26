"""Writing to the queue. Call these inside the transaction that changes the data,
so the change and its emails are saved together or not at all."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import Notification

Kind = Notification.Kind
UNSENT = [Notification.Status.PENDING, Notification.Status.SENDING]
# Notices that stop making sense once a booking is cancelled.
LIVE_BOOKING_KINDS = [
    Kind.BOOKING_CONFIRMED,
    Kind.BOOKING_RESCHEDULED,
    Kind.REMINDER,
    Kind.SESSION_UPDATED,
]


def enqueue(kind, *, at=None, **links):
    return Notification.objects.create(kind=kind, available_at=at or timezone.now(), **links)


def _participants(booking):
    return [booking.student_id, booking.slot.mentor_id]


def booking_created(booking, kind=Kind.BOOKING_CONFIRMED):
    now = timezone.now()
    remind_at = max(now, booking.starts_at - timedelta(hours=settings.REMINDER_LEAD_HOURS))
    for user_id in _participants(booking):
        enqueue(kind, booking=booking, recipient_id=user_id, at=now)
        enqueue(Kind.REMINDER, booking=booking, recipient_id=user_id, at=remind_at)


def withdraw(booking):
    """Drop unsent notices about a booking that is no longer live."""
    Notification.objects.filter(
        booking=booking, kind__in=LIVE_BOOKING_KINDS, status__in=UNSENT
    ).update(status=Notification.Status.SKIPPED)


def booking_cancelled(booking):
    withdraw(booking)
    for user_id in _participants(booking):
        enqueue(Kind.BOOKING_CANCELLED, booking=booking, recipient_id=user_id)


def session_updated(booking):
    """Tell the student about a new meeting link, replacing any unsent notice."""
    Notification.objects.filter(
        booking=booking, kind=Kind.SESSION_UPDATED, status__in=UNSENT
    ).update(status=Notification.Status.SKIPPED)
    enqueue(Kind.SESSION_UPDATED, booking=booking, recipient_id=booking.student_id)
