from rest_framework import serializers

from .models import RATINGS, Feedback


def _rating():
    return serializers.IntegerField(min_value=1, max_value=5)


class FeedbackSerializer(serializers.ModelSerializer):
    communication = _rating()
    problem_solving = _rating()
    technical = _rating()
    student = serializers.IntegerField(source="booking.student_id", read_only=True)
    mentor = serializers.IntegerField(source="booking.slot.mentor_id", read_only=True)
    mentor_name = serializers.CharField(source="booking.slot.mentor.username", read_only=True)
    topic = serializers.CharField(source="booking.slot.topic", read_only=True)
    session_starts_at = serializers.DateTimeField(source="booking.starts_at", read_only=True)

    class Meta:
        model = Feedback
        fields = ["id", "booking", "student", "mentor", "mentor_name", "topic",
                  "session_starts_at", *RATINGS, "strengths", "improvements", "next_steps",
                  "created_at", "updated_at"]
        read_only_fields = ["id", "booking", "created_at", "updated_at"]
