from rest_framework.filters import OrderingFilter


class StableOrderingFilter(OrderingFilter):
    """Always break ties by ID, so rows cannot repeat or vanish between pages."""

    def get_ordering(self, request, queryset, view):
        ordering = list(super().get_ordering(request, queryset, view) or [])
        if not ordering:
            return None
        return [*ordering, "-id" if ordering[-1].startswith("-") else "id"]
