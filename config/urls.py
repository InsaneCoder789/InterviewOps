from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    path("health/", views.health),
    path("api/config/", views.public_config),
    path("api/", include("accounts.urls")),
    path("api/", include("scheduling.urls")),
    path("api/", include("feedback.urls")),
    path("api/", include("notifications.urls")),
]
if settings.ENABLE_ADMIN:
    urlpatterns.append(path("admin/", admin.site.urls))

# Used when DEBUG is off.
handler404 = "config.errors.not_found"
handler500 = "config.errors.server_error"
