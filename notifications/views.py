from django.db.models import Count
from django.utils import timezone
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Invitation, User
from accounts.permissions import IsAdminRole
from scheduling.exceptions import Conflict
from scheduling.models import Booking, Slot

from .health import queue_health
from .models import Notification
from .serializers import NotificationSerializer

Status = Notification.Status


class NotificationListView(generics.ListAPIView):
    """Delivery record for admins. Newest first."""

    permission_classes = [IsAdminRole]
    serializer_class = NotificationSerializer
    queryset = Notification.objects.select_related("recipient", "invitation").order_by(
        "-created_at", "-id"
    )
    filterset_fields = ["status", "kind"]


class NotificationRetryView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        updated = Notification.objects.filter(pk=pk, status=Status.FAILED).update(
            status=Status.PENDING, attempts=0, available_at=timezone.now()
        )
        notification = Notification.objects.filter(pk=pk).first()
        if notification is None:
            raise NotFound("Notification not found.")
        if not updated:
            raise Conflict("Only a failed message can be retried.", "not_failed")
        return Response(NotificationSerializer(notification).data)


class OverviewView(APIView):
    """What an admin may need to act on."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        now = timezone.now()
        live = Booking.objects.filter(status=Booking.Status.BOOKED)
        started = live.filter(starts_at__lte=now)
        users = dict(User.objects.filter(is_active=True).values_list("role").annotate(Count("id")))
        return Response(
            {
                "active_users": {role: users.get(role, 0) for role in User.Role.values},
                "pending_invitations": Invitation.objects.filter(
                    accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=now
                ).count(),
                "open_slots": Slot.objects.filter(
                    cancelled_at__isnull=True, starts_at__gt=now, mentor__is_active=True
                )
                .exclude(bookings__status=Booking.Status.BOOKED)
                .count(),
                "upcoming_sessions": live.filter(starts_at__gt=now).count(),
                "upcoming_without_link": live.filter(starts_at__gt=now, meeting_link="").count(),
                "completed_sessions": live.filter(attendance="completed").count(),
                "missed_sessions": live.filter(
                    attendance__in=["student_absent", "mentor_absent"]
                ).count(),
                "awaiting_feedback": started.filter(
                    ends_at__lte=now, feedback__isnull=True, attendance__in=["", "completed"]
                ).count(),
                "notifications": queue_health(now),
            }
        )
