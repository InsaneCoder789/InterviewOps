from django.db.models import Exists, OuterRef
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsMentorOrAdmin, IsStudent

from . import services
from .filters import BookingFilter, SlotFilter
from .models import Booking, Slot
from .serializers import (
    BookingCreateSerializer,
    BookingSerializer,
    SlotCreateSerializer,
    SlotSerializer,
)


class SlotViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = SlotSerializer
    filterset_class = SlotFilter
    lookup_value_regex = r"\d{1,18}"

    def get_permissions(self):
        if self.action in {"create", "cancel"}:
            return [IsMentorOrAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        """Admins see all. Mentors see their own. Students see open future slots."""
        user = self.request.user
        slots = Slot.objects.select_related("mentor").annotate(
            is_booked=Exists(
                Booking.objects.filter(slot=OuterRef("pk"), status=Booking.Status.BOOKED)
            )
        )
        if user.role == User.Role.ADMIN:
            return slots
        if user.role == User.Role.MENTOR:
            return slots.filter(mentor=user)
        return slots.filter(
            cancelled_at__isnull=True, starts_at__gt=timezone.now(), mentor__is_active=True
        )

    def create(self, request):
        serializer = SlotCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        slot = services.publish_slot(
            mentor_id=data["mentor"].pk,
            topic=data["topic"],
            starts_at=data["starts_at"],
            ends_at=data["ends_at"],
        )
        slot.is_booked = False
        return Response(SlotSerializer(slot).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        services.cancel_slot(actor=request.user, slot_id=pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = BookingSerializer
    filterset_class = BookingFilter
    lookup_value_regex = r"\d{1,18}"

    def get_permissions(self):
        if self.action == "create":
            return [IsStudent()]
        return [IsAuthenticated()]

    def get_queryset(self):
        # Scoping the queryset makes other people's bookings 404 rather than 403.
        user = self.request.user
        bookings = Booking.objects.select_related("student", "slot__mentor")
        if user.role == User.Role.ADMIN:
            return bookings
        if user.role == User.Role.MENTOR:
            return bookings.filter(slot__mentor=user)
        return bookings.filter(student=user)

    def create(self, request):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = services.book_slot(
            student=request.user, slot_id=serializer.validated_data["slot"]
        )
        booking = self.get_queryset().get(pk=booking.pk)
        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = services.cancel_booking(actor=request.user, booking_id=pk)
        booking = Booking.objects.select_related("student", "slot__mentor").get(pk=booking.pk)
        return Response(BookingSerializer(booking).data)
