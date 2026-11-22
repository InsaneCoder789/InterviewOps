from rest_framework.permissions import BasePermission

from .models import User


def has_role(*roles):
    class HasRole(BasePermission):
        def has_permission(self, request, view):
            return bool(request.user.is_authenticated and request.user.role in roles)

    return HasRole


IsStudent = has_role(User.Role.STUDENT)
IsAdminRole = has_role(User.Role.ADMIN)
IsMentorOrAdmin = has_role(User.Role.MENTOR, User.Role.ADMIN)
