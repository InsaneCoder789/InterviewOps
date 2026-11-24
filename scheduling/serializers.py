from django.core.validators import URLValidator
from django.utils import timezone
from rest_framework import serializers

from accounts.models import User

from .models import Booking, Slot


class SlotSerializer(serializers.ModelSerializer):
    mentor = serializers.IntegerField(source="mentor_id", read_only=True)
    mentor_name = serializers.CharField(source="mentor.username", read_only=True)
    is_booked = serializers.BooleanField(read_only=True)

    class Meta:
        model = Slot
        fields = ["id", "mentor", "mentor_name", "topic", "starts_at", "ends_at",
                  "cancelled_at", "is_booked"]


class SlotCreateSerializer(serializers.Serializer):
    mentor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.MENTOR, is_active=True), required=False
    )
    topic = serializers.CharField(max_length=100)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()

    def validate(self, attrs):
        user = self.context["request"].user
        if user.role == User.Role.ADMIN:
            if "mentor" not in attrs:
                raise serializers.ValidationError({"mentor": "Required for admins."})
        elif attrs.get("mentor", user) != user:
            raise serializers.ValidationError({"mentor": "You can only publish your own slots."})
        else:
            attrs["mentor"] = user
        if attrs["starts_at"] <= timezone.now():
            raise serializers.ValidationError({"starts_at": "Must be in the future."})
        length = attrs["ends_at"] - attrs["starts_at"]
        if not Slot.MIN_LENGTH <= length <= Slot.MAX_LENGTH:
            raise serializers.ValidationError(
                {"ends_at": "A slot must last between 15 minutes and 3 hours."}
            )
        return attrs


class BookingSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.username", read_only=True)
    mentor = serializers.IntegerField(source="slot.mentor_id", read_only=True)
    mentor_name = serializers.CharField(source="slot.mentor.username", read_only=True)
    topic = serializers.CharField(source="slot.topic", read_only=True)

    class Meta:
        model = Booking
        fields = ["id", "slot", "student", "student_name", "mentor", "mentor_name", "topic",
                  "starts_at", "ends_at", "status", "created_at", "cancelled_at", "cancelled_by",
                  "meeting_link", "preparation_notes", "attendance", "rescheduled_from"]
        read_only_fields = fields


class BookingCreateSerializer(serializers.Serializer):
    slot = serializers.IntegerField(min_value=1, max_value=2**63 - 1)


class SessionUpdateSerializer(serializers.Serializer):
    # https only: the link is shown to another person as something to open.
    meeting_link = serializers.CharField(
        max_length=500, required=False, allow_blank=True,
        validators=[URLValidator(schemes=["https"], message="Use a full https:// address.")],
    )
    preparation_notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                {"detail": "Send meeting_link or preparation_notes."})
        return attrs


class AttendanceSerializer(serializers.Serializer):
    attendance = serializers.ChoiceField(choices=Booking.Attendance.choices)
