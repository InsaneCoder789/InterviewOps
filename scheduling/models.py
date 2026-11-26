from datetime import timedelta

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import F, Func, Q


class TsTzRange(Func):
    """Half-open [start, end), so back-to-back sessions do not overlap."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class Slot(models.Model):
    MIN_LENGTH = timedelta(minutes=15)
    MAX_LENGTH = timedelta(hours=3)

    mentor = models.ForeignKey(settings.AUTH_USER_MODEL, models.PROTECT, related_name="slots")
    topic = models.CharField(max_length=100)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at", "id"]
        indexes = [
            models.Index(
                fields=["starts_at", "id"],
                condition=Q(cancelled_at__isnull=True),
                name="slot_active_start_idx",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="slot_ends_after_start"
            ),
            ExclusionConstraint(
                name="slot_no_mentor_overlap",
                expressions=[
                    ("mentor", RangeOperators.EQUAL),
                    (TsTzRange("starts_at", "ends_at"), RangeOperators.OVERLAPS),
                ],
                condition=Q(cancelled_at__isnull=True),
            ),
        ]

    def __str__(self):
        return f"slot {self.pk}: {self.topic}"


class Booking(models.Model):
    class Status(models.TextChoices):
        BOOKED = "booked"
        CANCELLED = "cancelled"

    class Attendance(models.TextChoices):
        COMPLETED = "completed"
        STUDENT_ABSENT = "student_absent"
        MENTOR_ABSENT = "mentor_absent"

    slot = models.ForeignKey(Slot, models.PROTECT, related_name="bookings")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, models.PROTECT, related_name="bookings")
    # Copied from the slot (slot times are immutable) so the database can reject
    # overlapping bookings for one student.
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.BOOKED)
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.PROTECT, null=True, blank=True, related_name="+"
    )
    # Supplied by the mentor; this project does not host calls.
    meeting_link = models.URLField(max_length=500, blank=True)
    preparation_notes = models.TextField(max_length=2000, blank=True)
    # Empty until someone records what happened after the start time.
    attendance = models.CharField(max_length=16, choices=Attendance.choices, blank=True)
    rescheduled_from = models.OneToOneField(
        "self", models.PROTECT, null=True, blank=True, related_name="rescheduled_to"
    )

    class Meta:
        ordering = ["starts_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["slot"], condition=Q(status="booked"), name="booking_one_active_per_slot"
            ),
            ExclusionConstraint(
                name="booking_no_student_overlap",
                expressions=[
                    ("student", RangeOperators.EQUAL),
                    (TsTzRange("starts_at", "ends_at"), RangeOperators.OVERLAPS),
                ],
                condition=Q(status="booked"),
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="booked", cancelled_at__isnull=True, cancelled_by__isnull=True)
                    | Q(status="cancelled", cancelled_at__isnull=False, cancelled_by__isnull=False)
                ),
                name="booking_cancel_fields_consistent",
            ),
        ]

    def __str__(self):
        return f"booking {self.pk} for slot {self.slot_id} ({self.status})"
