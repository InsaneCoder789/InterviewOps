from django.conf import settings
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "database unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health),
    path("api/", include("accounts.urls")),
    path("api/", include("scheduling.urls")),
]
if settings.ENABLE_ADMIN:
    urlpatterns.append(path("admin/", admin.site.urls))
