import django_filters
from django.db.models import Avg, Count
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from scheduling.filters import IdFilter

from . import services
from .models import RATINGS, Feedback
from .serializers import FeedbackSerializer


def visible_feedback(user):
    """Students read their own, mentors what they wrote, admins everything."""
    rows = Feedback.objects.select_related("booking__slot__mentor")
    if user.role == User.Role.ADMIN:
        return rows
    if user.role == User.Role.MENTOR:
        return rows.filter(booking__slot__mentor=user)
    return rows.filter(booking__student=user)


class FeedbackFilter(django_filters.FilterSet):
    student = IdFilter(field_name="booking__student_id")
    mentor = IdFilter(field_name="booking__slot__mentor_id")

    class Meta:
        model = Feedback
        fields = []


class FeedbackListView(generics.ListAPIView):
    serializer_class = FeedbackSerializer
    filterset_class = FeedbackFilter

    def get_queryset(self):
        return visible_feedback(self.request.user)


class BookingFeedbackView(APIView):
    def get(self, request, pk):
        feedback = visible_feedback(request.user).filter(booking_id=pk).first()
        if feedback is None:
            raise NotFound("No feedback to show for this booking.")
        return Response(FeedbackSerializer(feedback).data)

    def put(self, request, pk):
        serializer = FeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        feedback, created = services.save_feedback(
            actor=request.user, booking_id=pk, values=serializer.validated_data)
        return Response(
            FeedbackSerializer(feedback).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ProgressView(APIView):
    """One student's ratings over time."""

    def get(self, request):
        user = request.user
        if user.role == User.Role.STUDENT:
            student = user.pk
        else:
            value = request.query_params.get("student", "")
            if not (value.isascii() and value.isdigit() and len(value) <= 18):
                raise ValidationError({"student": ["Name a student by ID."]})
            student = int(value)
        # A mentor sees only the sessions they ran.
        rows = visible_feedback(user).filter(booking__student_id=student)
        totals = rows.aggregate(
            sessions=Count("id"), **{name: Avg(name) for name in RATINGS})
        recent = rows.order_by("-booking__starts_at", "-id")[:20]
        return Response({
            "student": student,
            "sessions": totals["sessions"],
            "averages": {
                name: None if totals[name] is None else round(float(totals[name]), 2)
                for name in RATINGS
            },
            # Oldest first, ready to plot.
            "history": [
                {
                    "booking": row.booking_id,
                    "topic": row.booking.slot.topic,
                    "session_starts_at": row.booking.starts_at,
                    **{name: getattr(row, name) for name in RATINGS},
                }
                for row in reversed(recent)
            ],
            "latest_next_steps": recent[0].next_steps if recent else "",
        })
