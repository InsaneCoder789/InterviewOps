from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class InterviewUserAdmin(UserAdmin):
    list_display = ["username", "email", "role", "is_active"]
    # Role and status changes go through the API, which checks or cancels sessions.
    readonly_fields = ["role", "is_active"]
    fieldsets = (*UserAdmin.fieldsets, ("InterviewOps", {"fields": ["role"]}))
    add_fieldsets = ((None, {"fields": ["username", "email", "password1", "password2"]}),)
