"""Database-backed email queue.

Delivery is at-least-once: if a worker dies after the mail server accepts a
message but before the row is marked sent, the message is sent again once the
lease expires.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .emails import render
from .models import Notification
from .outbox import LIVE_BOOKING_KINDS, UNSENT

logger = logging.getLogger("interviewops.notifications")

Status = Notification.Status


def still_applies(notification, now):
    recipient, booking = notification.recipient, notification.booking
    if recipient is not None and not recipient.is_active:
        return False
    if notification.kind in LIVE_BOOKING_KINDS:
        return (
            booking.status == booking.Status.BOOKED
            and booking.starts_at > now
            and booking.student.is_active
            and booking.slot.mentor.is_active
        )
    return True


def claim_next():
    """Lease one due message. SKIP LOCKED lets several workers run side by side."""
    with transaction.atomic():
        now = timezone.now()
        notification = (
            Notification.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(status__in=UNSENT, available_at__lte=now)
            .order_by("available_at", "id")
            .first()
        )
        if notification is None:
            return None
        if not still_applies(notification, now):
            notification.status = Status.SKIPPED
        elif notification.attempts >= settings.NOTIFICATION_MAX_ATTEMPTS:
            # Only reachable when the final attempt's worker died mid-send.
            notification.status = Status.FAILED
            notification.last_error = "Lease expired on the final attempt."
        else:
            notification.status = Status.SENDING
            notification.attempts += 1
            notification.available_at = now + timedelta(
                seconds=settings.NOTIFICATION_LEASE_SECONDS)
        notification.save(update_fields=["status", "attempts", "available_at", "last_error"])
        return notification


def deliver(notification):
    """Send outside any transaction so a slow mail server holds no database locks."""
    # Only the worker holding this attempt may record its outcome. A cancellation
    # or a newer claim changes status or attempts, making the update a no-op.
    mine = Notification.objects.filter(
        pk=notification.pk, status=Status.SENDING, attempts=notification.attempts
    )
    if not mine.exists():
        return
    try:
        subject, body, address = render(notification)
        send_mail(subject=subject, message=body, from_email=None, recipient_list=[address])
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
        if notification.attempts >= settings.NOTIFICATION_MAX_ATTEMPTS:
            mine.update(status=Status.FAILED, last_error=error)
            logger.error("notification_failed id=%s attempts=%s",
                         notification.pk, notification.attempts)
        else:
            delay = min(
                settings.NOTIFICATION_RETRY_BASE_SECONDS * 2 ** (notification.attempts - 1),
                settings.NOTIFICATION_RETRY_MAX_SECONDS,
            )
            mine.update(
                status=Status.PENDING,
                last_error=error,
                available_at=timezone.now() + timedelta(seconds=delay),
            )
            # Exception type only: mail errors can echo recipient addresses.
            logger.warning("notification_retry id=%s attempt=%s delay_s=%s error=%s",
                           notification.pk, notification.attempts, delay, type(exc).__name__)
    else:
        mine.update(status=Status.SENT, sent_at=timezone.now(), last_error="")
        logger.info("notification_sent id=%s kind=%s attempt=%s",
                    notification.pk, notification.kind, notification.attempts)


def process_due(limit=100, should_stop=lambda: False):
    handled = 0
    while handled < limit and not should_stop() and (item := claim_next()) is not None:
        if item.status == Status.SENDING:
            deliver(item)
        handled += 1
    return handled
