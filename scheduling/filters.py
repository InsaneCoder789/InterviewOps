import django_filters
from django.db.models import Q
from django.utils import timezone

from .models import Booking, Slot


class SlotFilter(django_filters.FilterSet):
    mentor = django_filters.NumberFilter(field_name="mentor_id")
    topic = django_filters.CharFilter(lookup_expr="icontains")
    starts_after = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="gte")
    starts_before = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="lt")
    available = django_filters.BooleanFilter(method="filter_available")

    class Meta:
        model = Slot
        fields = []

    def filter_available(self, queryset, name, value):
        bookable = Q(
            is_booked=False,
            cancelled_at__isnull=True,
            starts_at__gt=timezone.now(),
            mentor__is_active=True,
        )
        return queryset.filter(bookable) if value else queryset.exclude(bookable)


class BookingFilter(django_filters.FilterSet):
    starts_after = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="gte")
    starts_before = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="lt")
    # A plain number: a model choice filter would reveal which slot IDs exist.
    slot = django_filters.NumberFilter(field_name="slot_id")

    class Meta:
        model = Booking
        fields = ["status"]
