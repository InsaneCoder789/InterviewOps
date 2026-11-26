"""Unauthenticated endpoints that belong to no single app."""

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from scheduling.models import Slot


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "database unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


@require_GET
def public_config(request):
    """The rules a client needs before it has a token, so it does not hard-code them."""
    return JsonResponse(
        {
            "registration_open": settings.ALLOW_REGISTRATION,
            "token_ttl_hours": settings.TOKEN_TTL_HOURS,
            "student_cancellation_cutoff_hours": settings.STUDENT_CANCELLATION_CUTOFF_HOURS,
            "reminder_lead_hours": settings.REMINDER_LEAD_HOURS,
            "slot_min_minutes": int(Slot.MIN_LENGTH.total_seconds() // 60),
            "slot_max_minutes": int(Slot.MAX_LENGTH.total_seconds() // 60),
            "feedback_edit_days": settings.FEEDBACK_EDIT_DAYS,
        }
    )
