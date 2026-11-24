import django_filters
from django import forms
from django.db.models import Q
from django.utils import timezone

from .models import Booking, Slot


class StrictBooleanField(forms.Field):
    VALUES = {"true": True, "1": True, "false": False, "0": False}

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            return self.VALUES[str(value).lower()]
        except KeyError:
            raise forms.ValidationError("Use true or false.") from None


class StrictBooleanFilter(django_filters.Filter):
    """Unlike BooleanFilter, a misspelt value is a 400 instead of being ignored."""

    field_class = StrictBooleanField


class IdFilter(django_filters.Filter):
    """A plain whole number: a model choice filter would reveal which IDs exist."""

    field_class = forms.IntegerField

    def __init__(self, *args, **kwargs):
        super().__init__(*args, min_value=1, max_value=2**63 - 1, **kwargs)


class TimeWindowFilter(django_filters.FilterSet):
    starts_after = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="gte")
    starts_before = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="lt")
    # Includes a session that is in progress.
    ends_after = django_filters.IsoDateTimeFilter(field_name="ends_at", lookup_expr="gt")


class SlotFilter(TimeWindowFilter):
    mentor = IdFilter(field_name="mentor_id")
    topic = django_filters.CharFilter(lookup_expr="icontains")
    available = StrictBooleanFilter(method="filter_available")
    cancelled = StrictBooleanFilter(field_name="cancelled_at", method="filter_cancelled")

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

    def filter_cancelled(self, queryset, name, value):
        return queryset.filter(cancelled_at__isnull=not value)


class BookingFilter(TimeWindowFilter):
    slot = IdFilter(field_name="slot_id")
    student = IdFilter(field_name="student_id")
    mentor = IdFilter(field_name="slot__mentor_id")

    class Meta:
        model = Booking
        fields = ["status"]
