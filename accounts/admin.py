from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class InterviewUserAdmin(UserAdmin):
    list_display = ["username", "email", "role", "is_active"]
    # Role changes go through the API, which checks for upcoming bookings first.
    readonly_fields = ["role"]
    fieldsets = UserAdmin.fieldsets + (("InterviewOps", {"fields": ["role"]}),)
    add_fieldsets = (
        (None, {"fields": ["username", "email", "password1", "password2"]}),
    )
