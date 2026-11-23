"""Database-backed reminder queue.

Delivery is at-least-once: if a worker dies after the mail server accepts a
message but before the row is marked sent, the reminder is sent again once the
lease expires.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Booking, Reminder

logger = logging.getLogger("interviewops.reminders")


def claim_next():
    """Lease one due reminder. SKIP LOCKED lets several workers run side by side."""
    with transaction.atomic():
        now = timezone.now()
        reminder = (
            Reminder.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(
                Q(status=Reminder.Status.PENDING) | Q(status=Reminder.Status.SENDING),
                available_at__lte=now,
            )
            .order_by("available_at", "id")
            .first()
        )
        if reminder is None:
            return None
        booking = reminder.booking
        if (
            booking.status != Booking.Status.BOOKED
            or booking.starts_at <= now
            or not booking.student.is_active
            or not booking.slot.mentor.is_active
        ):
            reminder.status = Reminder.Status.SKIPPED
        elif reminder.attempts >= settings.REMINDER_MAX_ATTEMPTS:
            # Only reachable when the final attempt's worker died mid-send.
            reminder.status = Reminder.Status.FAILED
            reminder.last_error = "Lease expired on the final attempt."
        else:
            reminder.status = Reminder.Status.SENDING
            reminder.attempts += 1
            reminder.available_at = now + timedelta(seconds=settings.REMINDER_LEASE_SECONDS)
        reminder.save(update_fields=["status", "attempts", "available_at", "last_error"])
        return reminder


def deliver(reminder):
    """Send outside any transaction so a slow mail server holds no database locks."""
    booking = Booking.objects.select_related("student", "slot__mentor").get(pk=reminder.booking_id)
    # Only the worker holding this attempt may record its outcome. A cancellation
    # or a newer claim changes status or attempts, making the update a no-op.
    mine = Reminder.objects.filter(
        pk=reminder.pk, status=Reminder.Status.SENDING, attempts=reminder.attempts
    )
    if not mine.exists():
        return
    try:
        send_mail(
            subject=f"Reminder: mock interview on {booking.starts_at:%d %b %Y %H:%M} UTC",
            message=(
                f"Hi {booking.student.username},\n\n"
                f"Your {booking.slot.topic} interview with {booking.slot.mentor.username} "
                f"starts at {booking.starts_at:%d %b %Y %H:%M} UTC."
            ),
            from_email=None,
            recipient_list=[booking.student.email],
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
        if reminder.attempts >= settings.REMINDER_MAX_ATTEMPTS:
            mine.update(status=Reminder.Status.FAILED, last_error=error)
            logger.error("reminder_failed reminder_id=%s attempts=%s", reminder.pk, reminder.attempts)
        else:
            delay = min(
                settings.REMINDER_RETRY_BASE_SECONDS * 2 ** (reminder.attempts - 1),
                settings.REMINDER_RETRY_MAX_SECONDS,
            )
            mine.update(
                status=Reminder.Status.PENDING,
                last_error=error,
                available_at=timezone.now() + timedelta(seconds=delay),
            )
            # Exception type only: mail errors can echo recipient addresses.
            logger.warning(
                "reminder_retry reminder_id=%s attempt=%s delay_s=%s error=%s",
                reminder.pk, reminder.attempts, delay, type(exc).__name__,
            )
    else:
        mine.update(status=Reminder.Status.SENT, sent_at=timezone.now(), last_error="")
        logger.info("reminder_sent reminder_id=%s attempt=%s", reminder.pk, reminder.attempts)


def process_due(limit=100, should_stop=lambda: False):
    handled = 0
    while handled < limit and not should_stop() and (reminder := claim_next()) is not None:
        if reminder.status == Reminder.Status.SENDING:
            deliver(reminder)
        handled += 1
    return handled
