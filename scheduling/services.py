"""All state changes live here. Views only authenticate, validate and serialise.

Lock order is always user row -> slot row -> booking row (two user rows are taken
in primary-key order), so two transactions cannot each hold a lock the other is
waiting for.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import NotFound, PermissionDenied

from accounts.models import User
from notifications import outbox

from .exceptions import Conflict
from .models import Booking, Slot

logger = logging.getLogger("interviewops.scheduling")

# Constraint name -> (error code, message).
CONSTRAINT_ERRORS = {
    "slot_no_mentor_overlap": ("slot_overlap", "This overlaps another of the mentor's slots."),
    "booking_one_active_per_slot": ("slot_already_booked", "This slot is already booked."),
    "booking_no_student_overlap": ("student_overlap", "You already have a booking at this time."),
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
    if name not in CONSTRAINT_ERRORS:
        raise exc
    return _constraint_conflict(name)


def _constraint_conflict(name):
    code, message = CONSTRAINT_ERRORS[name]
    return Conflict(message, code)


def publish_slot(*, mentor_id, topic, starts_at, ends_at):
    try:
        with transaction.atomic():
            mentor = _lock_user(mentor_id)
            if mentor.role != User.Role.MENTOR or not mentor.is_active:
                raise Conflict("Slots can only be published for an active mentor.", "mentor_unavailable")
            if starts_at <= timezone.now():
                raise Conflict("A slot must start in the future.", "slot_not_in_future")
            if not Slot.MIN_LENGTH <= ends_at - starts_at <= Slot.MAX_LENGTH:
                raise Conflict("A slot must last between 15 minutes and 3 hours.", "slot_length")
            slot = Slot.objects.create(
                mentor=mentor, topic=topic, starts_at=starts_at, ends_at=ends_at
            )
    except IntegrityError as exc:
        raise _conflict_from(exc) from exc
    logger.info("slot_published slot_id=%s mentor_id=%s", slot.pk, mentor_id)
    return slot


def _check_open(slot, now):
    # A slot students cannot list answers like one that never existed, so
    # booking attempts do not reveal which IDs are real.
    if slot.cancelled_at or slot.starts_at <= now or not slot.mentor.is_active:
        raise NotFound("Slot not found.")
    if Booking.objects.filter(slot=slot, status=Booking.Status.BOOKED).exists():
        raise _constraint_conflict("booking_one_active_per_slot")


def book_slot(*, student, slot_id):
    try:
        with transaction.atomic():
            locked_student = _lock_user(student.pk)
            # Read under the lock: the account may have changed since sign-in.
            if locked_student.role != User.Role.STUDENT or not locked_student.is_active:
                raise PermissionDenied("Only active students can book slots.")
            slot = _lock_slot(slot_id)
            now = timezone.now()  # read after waiting for locks
            _check_open(slot, now)
            booking = Booking.objects.create(
                slot=slot, student=locked_student, starts_at=slot.starts_at, ends_at=slot.ends_at
            )
            # Same transaction as the booking: both are saved, or neither is.
            outbox.booking_created(booking)
    except IntegrityError as exc:
        raise _conflict_from(exc) from exc
    logger.info("booking_created booking_id=%s slot_id=%s", booking.pk, slot_id)
    return booking


def _mark_cancelled(booking, actor, now, notify=True):
    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = now
    booking.cancelled_by = actor
    booking.save(update_fields=["status", "cancelled_at", "cancelled_by"])
    if notify:
        outbox.booking_cancelled(booking)
    else:
        outbox.withdraw(booking)


def _locked_booking(actor, booking_id):
    """Lock the slot then the booking, hiding it from anyone not taking part."""
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
    return slot, booking


def _check_changeable(actor, booking, now):
    """Rules shared by cancelling and rescheduling."""
    if booking.status == Booking.Status.CANCELLED:
        raise Conflict("This booking is already cancelled.", "booking_already_cancelled")
    now = timezone.now()
    if booking.starts_at <= now:
        raise Conflict("A session that has started cannot be cancelled.", "session_started")
    cutoff = timedelta(hours=settings.STUDENT_CANCELLATION_CUTOFF_HOURS)
    if booking.student_id == actor.pk and booking.starts_at - now < cutoff:
        raise Conflict(
            "Students cannot cancel less than "
            f"{settings.STUDENT_CANCELLATION_CUTOFF_HOURS} hours before the session.",
            "cancel_cutoff",
        )


@transaction.atomic
def cancel_booking(*, actor, booking_id):
    """Cancel one booking. The slot becomes bookable again."""
    _, booking = _locked_booking(actor, booking_id)
    now = timezone.now()
    _check_changeable(actor, booking, now)
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
        raise Conflict("This slot is already cancelled.", "slot_already_cancelled")
    now = timezone.now()
    if slot.starts_at <= now:
        raise Conflict("A slot that has started cannot be cancelled.", "slot_started")
    slot.cancelled_at = now
    slot.save(update_fields=["cancelled_at"])
    for booking in slot.bookings.select_for_update().filter(status=Booking.Status.BOOKED):
        _mark_cancelled(booking, actor, now)
    logger.info("slot_cancelled slot_id=%s actor_id=%s", slot.pk, actor.pk)
    return slot


@transaction.atomic
def change_role(*, actor, user_id, role):
    if user_id == actor.pk:
        raise Conflict("You cannot change your own role.", "own_role")
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
        raise Conflict("Cancel this user's upcoming slots and bookings before changing role.", "role_has_commitments")
    if user.role == User.Role.ADMIN:
        # Leaving the admin role also removes Django admin access.
        user.is_staff = user.is_superuser = False
    user.role = role
    user.save(update_fields=["role", "is_staff", "is_superuser"])
    logger.info("role_changed user_id=%s role=%s actor_id=%s", user.pk, role, actor.pk)
    return user


@transaction.atomic
def set_active(*, actor, user_id, is_active):
    """Deactivate or restore an account. Deactivating cancels its future sessions."""
    if user_id == actor.pk:
        raise Conflict("You cannot change your own account status.", "own_status")
    locked = {pk: _lock_user(pk) for pk in sorted({actor.pk, user_id})}
    if locked[actor.pk].role != User.Role.ADMIN or not locked[actor.pk].is_active:
        raise PermissionDenied("Only admins can change account status.")
    user = locked[user_id]
    if user.is_active == is_active:
        return user
    user.is_active = is_active
    user.save(update_fields=["is_active"])
    if not is_active:
        Token.objects.filter(user=user).delete()
        _cancel_future_sessions(actor, user)
    logger.info("status_changed user_id=%s active=%s actor_id=%s",
                user.pk, is_active, actor.pk)
    return user


def _cancel_future_sessions(actor, user):
    """The caller holds the user's row lock, so no new commitment can appear."""
    now = timezone.now()
    booked = Booking.objects.filter(
        student=user, status=Booking.Status.BOOKED, starts_at__gt=now
    ).values_list("slot_id", flat=True)
    # Every slot lock is taken in primary-key order.
    slots = list(
        Slot.objects.select_for_update(no_key=True)
        .filter(Q(mentor=user, cancelled_at__isnull=True, starts_at__gt=now) | Q(pk__in=booked))
        .order_by("pk")
    )
    for slot in slots:
        bookings = slot.bookings.select_for_update().filter(status=Booking.Status.BOOKED)
        if slot.mentor_id == user.pk:
            slot.cancelled_at = now
            slot.save(update_fields=["cancelled_at"])
        else:
            bookings = bookings.filter(student=user)
        for booking in bookings:
            _mark_cancelled(booking, actor, now)


def reschedule_booking(*, actor, booking_id, slot_id):
    """Move a booking to another slot. Both changes happen, or the old booking stays."""
    found = Booking.objects.filter(pk=booking_id).values_list("student_id", "slot_id").first()
    if found is None:
        raise NotFound("Booking not found.")
    student_id, old_slot_id = found
    # Neither value ever changes on a booking, so reading them before locking is safe.
    if not (actor.role == User.Role.ADMIN or actor.pk == student_id):
        if not Slot.objects.filter(pk=old_slot_id, mentor=actor).exists():
            raise NotFound("Booking not found.")
        raise PermissionDenied("Only the student or an admin can reschedule.")
    try:
        with transaction.atomic():
            student = _lock_user(student_id)
            # Two slot locks are taken in primary-key order.
            slots = {pk: _lock_slot(pk) for pk in sorted({old_slot_id, slot_id})}
            old = Booking.objects.select_for_update().get(pk=booking_id)
            now = timezone.now()
            _check_changeable(actor, old, now)
            if slot_id == old_slot_id:
                raise Conflict("This booking is already in that slot.", "same_slot")
            if student.role != User.Role.STUDENT or not student.is_active:
                raise Conflict("The student can no longer book sessions.", "student_unavailable")
            slot = slots[slot_id]
            _check_open(slot, now)
            # Cancel first, so the old time does not count as an overlap.
            _mark_cancelled(old, actor, now, notify=False)
            same_mentor = slot.mentor_id == slots[old_slot_id].mentor_id
            booking = Booking.objects.create(
                slot=slot, student=student, starts_at=slot.starts_at, ends_at=slot.ends_at,
                preparation_notes=old.preparation_notes,
                meeting_link=old.meeting_link if same_mentor else "",
                rescheduled_from=old,
            )
            outbox.booking_created(booking, kind=outbox.Kind.BOOKING_RESCHEDULED)
            if not same_mentor:
                outbox.enqueue(outbox.Kind.BOOKING_CANCELLED, booking=old,
                               recipient_id=slots[old_slot_id].mentor_id)
    except IntegrityError as exc:
        raise _conflict_from(exc) from exc
    logger.info("booking_rescheduled from=%s to=%s actor_id=%s", booking_id, booking.pk, actor.pk)
    return booking


@transaction.atomic
def update_session(*, actor, booking_id, meeting_link=None, preparation_notes=None):
    """The mentor adds the meeting link; the student adds preparation notes."""
    _, booking = _locked_booking(actor, booking_id)
    admin = actor.role == User.Role.ADMIN
    is_student = booking.student_id == actor.pk
    if meeting_link is not None and not admin and is_student:
        raise PermissionDenied("Only the mentor can set the meeting link.")
    if preparation_notes is not None and not admin and not is_student:
        raise PermissionDenied("Only the student can write preparation notes.")
    if booking.status != Booking.Status.BOOKED:
        raise Conflict("This booking is cancelled.", "booking_already_cancelled")
    if booking.ends_at <= timezone.now():
        raise Conflict("This session has ended.", "session_ended")
    changed = []
    if meeting_link is not None and meeting_link != booking.meeting_link:
        booking.meeting_link = meeting_link
        changed.append("meeting_link")
    if preparation_notes is not None and preparation_notes != booking.preparation_notes:
        booking.preparation_notes = preparation_notes
        changed.append("preparation_notes")
    if changed:
        booking.save(update_fields=changed)
    if "meeting_link" in changed and meeting_link:
        outbox.session_updated(booking)
    return booking


@transaction.atomic
def record_attendance(*, actor, booking_id, attendance):
    _, booking = _locked_booking(actor, booking_id)
    if booking.student_id == actor.pk:
        raise PermissionDenied("Only the mentor or an admin can record attendance.")
    if booking.status != Booking.Status.BOOKED:
        raise Conflict("This booking is cancelled.", "booking_already_cancelled")
    if booking.starts_at > timezone.now():
        raise Conflict("This session has not started.", "session_not_started")
    if attendance != Booking.Attendance.COMPLETED and hasattr(booking, "feedback"):
        raise Conflict("Feedback exists, so the session took place.", "feedback_exists")
    booking.attendance = attendance
    booking.save(update_fields=["attendance"])
    logger.info("attendance_recorded booking_id=%s actor_id=%s", booking.pk, actor.pk)
    return booking
