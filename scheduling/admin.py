from django.contrib import admin

from .models import Booking, Reminder, Slot


class ReadOnlyAdmin(admin.ModelAdmin):
    """Edits would bypass the rules in services.py, so the admin only inspects."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Slot)
class SlotAdmin(ReadOnlyAdmin):
    list_display = ["id", "mentor", "topic", "starts_at", "cancelled_at"]
    list_select_related = ["mentor"]


@admin.register(Booking)
class BookingAdmin(ReadOnlyAdmin):
    list_display = ["id", "slot_id", "student", "status", "starts_at"]
    list_select_related = ["student"]
    list_filter = ["status"]


@admin.register(Reminder)
class ReminderAdmin(ReadOnlyAdmin):
    list_display = ["id", "booking_id", "status", "attempts", "available_at"]
    list_filter = ["status"]
