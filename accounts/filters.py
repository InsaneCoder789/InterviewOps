import django_filters

from scheduling.filters import StrictBooleanFilter

from .models import User


class UserFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(field_name="username", lookup_expr="icontains")
    is_active = StrictBooleanFilter()

    class Meta:
        model = User
        fields = ["role"]
