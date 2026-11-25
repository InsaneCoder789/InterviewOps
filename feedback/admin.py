from django.contrib import admin

from scheduling.admin import ReadOnlyAdmin

from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(ReadOnlyAdmin):
    list_display = ["id", "booking_id", "created_at"]
