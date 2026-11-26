import django_filters
from django.db.models import Q

from scheduling.filters import StrictBooleanFilter

from .models import User


class UserFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(field_name="username", lookup_expr="icontains")
    is_active = StrictBooleanFilter()

    class Meta:
        model = User
        fields = ["role"]


class MentorFilter(django_filters.FilterSet):
    topic = django_filters.CharFilter(method="filter_topic")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = User
        fields = []

    def filter_topic(self, queryset, name, value):
        return queryset.filter(profile__topics__contains=[value.strip().lower()])

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(username__icontains=value) | Q(profile__display_name__icontains=value)
        )
