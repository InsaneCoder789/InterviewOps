"""All state changes live here. Views only authenticate, validate and serialise.

Lock order is always user row -> slot row -> booking row (two user rows are taken
in primary-key order), so two transactions cannot each hold a lock the other is
waiting for.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from accounts.models import User

from .exceptions import Conflict
from .models import Booking, Reminder, Slot

logger = logging.getLogger("interviewops.scheduling")

CONSTRAINT_MESSAGES = {
    "slot_no_mentor_overlap": "This overlaps another of the mentor's slots.",
    "booking_one_active_per_slot": "This slot is already booked.",
    "booking_no_student_overlap": "You already have a booking at this time.",
}


def _lock_user(user_id):
    # NO KEY UPDATE serialises writers for one user without blocking the key-share
    # locks PostgreSQL takes when other rows reference that user.
    user = User.objects.select_for_update(no_key=True).filter(pk=user_id).first()
    if user is None:
        raise NotFound("User not found.")
    return user


def _lock_slot(slot_id):
    slot = Slot.objects.select_for_update(no_key=True).filter(pk=slot_id).first()
    if slot is None:
        raise NotFound("Slot not found.")
    return slot


def _conflict_from(exc):
    name = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
    if name not in CONSTRAINT_MESSAGES:
        raise exc
    return Conflict(CONSTRAINT_MESSAGES[name])


def publish_slot(*, mentor_id, topic, starts_at, ends_at):
    try:
        with transaction.atomic():
            mentor = _lock_user(mentor_id)
            if mentor.role != User.Role.MENTOR or not mentor.is_active:
                raise Conflict("Slots can only be published for an active mentor.")
            if starts_at <= timezone.now():
                raise Conflict("A slot must start in the future.")
            if not Slot.MIN_LENGTH <= ends_at - starts_at <= Slot.MAX_LENGTH:
                raise Conflict("A slot must last between 15 minutes and 3 hours.")
            slot = Slot.objects.create(
                mentor=mentor, topic=topic, starts_at=starts_at, ends_at=ends_at
            )
    except IntegrityError as exc:
        raise _conflict_from(exc) from exc
    logger.info("slot_published slot_id=%s mentor_id=%s", slot.pk, mentor_id)
    return slot


def book_slot(*, student, slot_id):
    try:
        with transaction.atomic():
            locked_student = _lock_user(student.pk)
            if locked_student.role != User.Role.STUDENT:
                raise PermissionDenied("Only students can book slots.")
            slot = _lock_slot(slot_id)
            now = timezone.now()  # read after waiting for locks
            if not slot.mentor.is_active:
                raise Conflict("This mentor is no longer available.")
            if slot.cancelled_at:
                raise Conflict("This slot has been cancelled.")
            if slot.starts_at <= now:
                raise Conflict("This slot has already started.")
            if Booking.objects.filter(slot=slot, status=Booking.Status.BOOKED).exists():
                raise Conflict(CONSTRAINT_MESSAGES["booking_one_active_per_slot"])
            booking = Booking.objects.create(
                slot=slot, student=locked_student, starts_at=slot.starts_at, ends_at=slot.ends_at
            )
            # Same transaction as the booking: both exist, or neither does.
            Reminder.objects.create(
                booking=booking,
                available_at=max(now, slot.starts_at - timedelta(hours=settings.REMINDER_LEAD_HOURS)),
            )
    except IntegrityError as exc:
        raise _conflict_from(exc) from exc
    logger.info("booking_created booking_id=%s slot_id=%s", booking.pk, slot_id)
    return booking


def _mark_cancelled(booking, actor, now):
    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = now
    booking.cancelled_by = actor
    booking.save(update_fields=["status", "cancelled_at", "cancelled_by"])
    Reminder.objects.filter(
        booking=booking, status__in=[Reminder.Status.PENDING, Reminder.Status.SENDING]
    ).update(status=Reminder.Status.SKIPPED)


@transaction.atomic
def cancel_booking(*, actor, booking_id):
    """Cancel one booking. The slot becomes bookable again."""
    slot_id = Booking.objects.filter(pk=booking_id).values_list("slot_id", flat=True).first()
    if slot_id is None:
        raise NotFound("Booking not found.")
    slot = _lock_slot(slot_id)
    booking = Booking.objects.select_for_update().get(pk=booking_id)

    is_student = booking.student_id == actor.pk
    is_mentor = slot.mentor_id == actor.pk and actor.role == User.Role.MENTOR
    is_admin = actor.role == User.Role.ADMIN
    if not (is_student or is_mentor or is_admin):
        raise NotFound("Booking not found.")  # do not reveal that it exists

    if booking.status == Booking.Status.CANCELLED:
        raise Conflict("This booking is already cancelled.")
    now = timezone.now()
    if booking.starts_at <= now:
        raise Conflict("A session that has started cannot be cancelled.")
    cutoff = timedelta(hours=settings.STUDENT_CANCELLATION_CUTOFF_HOURS)
    if is_student and not is_admin and booking.starts_at - now < cutoff:
        raise Conflict(
            "Students cannot cancel less than "
            f"{settings.STUDENT_CANCELLATION_CUTOFF_HOURS} hours before the session."
        )
    _mark_cancelled(booking, actor, now)
    logger.info("booking_cancelled booking_id=%s actor_id=%s", booking.pk, actor.pk)
    return booking


@transaction.atomic
def cancel_slot(*, actor, slot_id):
    """Withdraw a slot, cancelling its booking if it has one."""
    slot = _lock_slot(slot_id)
    if not (actor.role == User.Role.ADMIN or slot.mentor_id == actor.pk):
        raise NotFound("Slot not found.")
    if slot.cancelled_at:
        raise Conflict("This slot is already cancelled.")
    now = timezone.now()
    if slot.starts_at <= now:
        raise Conflict("A slot that has started cannot be cancelled.")
    slot.cancelled_at = now
    slot.save(update_fields=["cancelled_at"])
    for booking in slot.bookings.select_for_update().filter(status=Booking.Status.BOOKED):
        _mark_cancelled(booking, actor, now)
    logger.info("slot_cancelled slot_id=%s actor_id=%s", slot.pk, actor.pk)
    return slot


@transaction.atomic
def change_role(*, actor, user_id, role):
    if user_id == actor.pk:
        raise Conflict("You cannot change your own role.")
    # Lock both rows in primary-key order, then re-check the actor: two admins
    # demoting each other must not both succeed.
    locked = {pk: _lock_user(pk) for pk in sorted({actor.pk, user_id})}
    if locked[actor.pk].role != User.Role.ADMIN:
        raise PermissionDenied("Only admins can change roles.")
    user = locked[user_id]
    if user.role == role:
        return user
    now = timezone.now()
    if (
        user.slots.filter(cancelled_at__isnull=True, ends_at__gt=now).exists()
        or user.bookings.filter(status=Booking.Status.BOOKED, ends_at__gt=now).exists()
    ):
        raise Conflict("Cancel this user's upcoming slots and bookings before changing role.")
    if user.role == User.Role.ADMIN:
        # Leaving the admin role also removes Django admin access.
        user.is_staff = user.is_superuser = False
    user.role = role
    user.save(update_fields=["role", "is_staff", "is_superuser"])
    logger.info("role_changed user_id=%s role=%s actor_id=%s", user.pk, role, actor.pk)
    return user
