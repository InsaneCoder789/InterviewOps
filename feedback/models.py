from django.db import models
from django.db.models import Q

RATINGS = ["communication", "problem_solving", "technical"]


class Feedback(models.Model):
    """What the mentor observed in one session. The mentor and topic come from the slot."""

    booking = models.OneToOneField("scheduling.Booking", models.PROTECT, related_name="feedback")
    # 1 (needs a lot of work) to 5 (ready).
    communication = models.PositiveSmallIntegerField()
    problem_solving = models.PositiveSmallIntegerField()
    technical = models.PositiveSmallIntegerField()
    strengths = models.TextField(max_length=4000)
    improvements = models.TextField(max_length=4000)
    next_steps = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(**{f"{name}__gte": 1, f"{name}__lte": 5}),
                name=f"feedback_{name}_range",
            )
            for name in RATINGS
        ]

    def __str__(self):
        return f"feedback for booking {self.booking_id}"
