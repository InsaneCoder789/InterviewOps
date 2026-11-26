from django.db.models import Count, Min, Q
from django.utils import timezone

from .models import Notification

Status = Notification.Status


def queue_health(now=None):
    """Counts a monitor can alert on."""
    now = now or timezone.now()
    overdue = Q(status=Status.PENDING, available_at__lte=now)
    totals = Notification.objects.aggregate(
        failed=Count("id", filter=Q(status=Status.FAILED)),
        due=Count("id", filter=overdue),
        oldest=Min("available_at", filter=overdue),
    )
    oldest = totals.pop("oldest")
    # A growing value means no worker is keeping up.
    totals["oldest_due_seconds"] = int((now - oldest).total_seconds()) if oldest else 0
    return totals
