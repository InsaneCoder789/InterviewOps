from django.conf import settings
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.http import require_GET

from scheduling.models import Slot


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "database unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def public_config(request):
    """The rules a client needs before it has a token, so it does not hard-code them."""
    return JsonResponse({
        "registration_open": settings.ALLOW_REGISTRATION,
        "token_ttl_hours": settings.TOKEN_TTL_HOURS,
        "student_cancellation_cutoff_hours": settings.STUDENT_CANCELLATION_CUTOFF_HOURS,
        "reminder_lead_hours": settings.REMINDER_LEAD_HOURS,
        "slot_min_minutes": int(Slot.MIN_LENGTH.total_seconds() // 60),
        "slot_max_minutes": int(Slot.MAX_LENGTH.total_seconds() // 60),
    })


urlpatterns = [
    path("health/", health),
    path("api/config/", require_GET(public_config)),
    path("api/", include("accounts.urls")),
    path("api/", include("scheduling.urls")),
]
if settings.ENABLE_ADMIN:
    urlpatterns.append(path("admin/", admin.site.urls))

# Used when DEBUG is off.
handler404 = "config.errors.not_found"
handler500 = "config.errors.server_error"
