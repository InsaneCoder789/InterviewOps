import logging

from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError

from notifications import outbox
from notifications.models import Notification

from .models import User
from .serializers import check_password_strength

logger = logging.getLogger("interviewops.accounts")


def _lock(pk):
    return User.objects.select_for_update(no_key=True).filter(pk=pk, is_active=True).first()


def _set_password(user, password):
    user.set_password(password)
    user.save(update_fields=["password"])
    # Anyone holding the old token is signed out.
    Token.objects.filter(user=user).delete()


@transaction.atomic
def change(*, user, current_password, new_password):
    locked = _lock(user.pk)
    if locked is None or not locked.check_password(current_password):
        raise ValidationError({"current_password": ["Your current password is not correct."]})
    check_password_strength(new_password, locked, field="new_password")
    _set_password(locked, new_password)
    logger.info("password_changed user_id=%s", locked.pk)
    return Token.objects.create(user=locked)


@transaction.atomic
def request_reset(*, email):
    """Queue a reset link if the address belongs to an account. Callers learn nothing."""
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user is None or not user.has_usable_password():
        return
    _lock(user.pk)
    waiting = Notification.objects.filter(
        recipient=user, kind=outbox.Kind.PASSWORD_RESET, status__in=outbox.UNSENT)
    if not waiting.exists():
        outbox.enqueue(outbox.Kind.PASSWORD_RESET, recipient=user)


@transaction.atomic
def confirm_reset(*, uid, token, password):
    try:
        user = _lock(int(force_str(urlsafe_base64_decode(uid))))
    except (ValueError, OverflowError):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationError({
            "detail": "This reset link is not valid. Ask for a new one.",
            "code": "invalid_reset_link",
        })
    check_password_strength(password, user)
    _set_password(user, password)
    logger.info("password_reset user_id=%s", user.pk)
