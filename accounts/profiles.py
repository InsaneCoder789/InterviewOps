from django.db.models import Q

from .models import Profile, User


def profile_of(user):
    """The saved profile, or an empty unsaved one."""
    return Profile.objects.filter(user=user).first() or Profile(user=user)


def visible_users(viewer):
    """Whose profile this person may read: themselves, any active mentor, and for a
    mentor the students who have booked them. Admins read all."""
    if viewer.role == User.Role.ADMIN:
        return User.objects.all()
    allowed = Q(pk=viewer.pk) | Q(role=User.Role.MENTOR, is_active=True)
    if viewer.role == User.Role.MENTOR:
        allowed |= Q(bookings__slot__mentor=viewer, is_active=True)
    return User.objects.filter(allowed).distinct()
