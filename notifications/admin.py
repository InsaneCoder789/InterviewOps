from django.contrib import admin

from scheduling.admin import ReadOnlyAdmin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(ReadOnlyAdmin):
    list_display = ["id", "kind", "status", "attempts", "available_at", "sent_at"]
    list_filter = ["status", "kind"]
