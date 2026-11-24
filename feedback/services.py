import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from notifications import outbox
from scheduling.exceptions import Conflict
from scheduling.models import Booking
from scheduling.services import _locked_booking

from .models import Feedback

logger = logging.getLogger("interviewops.feedback")


@transaction.atomic
def save_feedback(*, actor, booking_id, values):
    """Create or revise feedback. Returns (feedback, created)."""
    slot, booking = _locked_booking(actor, booking_id)
    if slot.mentor_id != actor.pk or actor.role != "mentor":
        raise PermissionDenied("Only the session's mentor can write feedback.")
    now = timezone.now()
    if booking.status != Booking.Status.BOOKED:
        raise Conflict("This booking is cancelled.", "booking_already_cancelled")
    if booking.starts_at > now:
        raise Conflict("This session has not started.", "session_not_started")
    if booking.attendance not in ("", Booking.Attendance.COMPLETED):
        raise Conflict("This session is marked as missed.", "session_missed")
    existing = Feedback.objects.filter(booking=booking).first()
    window = timedelta(days=settings.FEEDBACK_EDIT_DAYS)
    if existing and now - existing.created_at > window:
        raise Conflict(
            f"Feedback can be changed for {settings.FEEDBACK_EDIT_DAYS} days.",
            "feedback_locked",
        )
    feedback, created = Feedback.objects.update_or_create(booking=booking, defaults=values)
    if booking.attendance != Booking.Attendance.COMPLETED:
        booking.attendance = Booking.Attendance.COMPLETED
        booking.save(update_fields=["attendance"])
    if created:
        outbox.enqueue(
            outbox.Kind.FEEDBACK_READY, booking=booking, recipient_id=booking.student_id)
    logger.info("feedback_saved booking_id=%s created=%s", booking.pk, created)
    return feedback, created
