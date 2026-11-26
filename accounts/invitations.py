"""Invitations: the way people join a closed community.

The emailed token is a signature over the invitation, made when the message is
sent. Nothing that can be used to join is stored in the database.
"""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from notifications import outbox
from scheduling.exceptions import Conflict

from .models import Invitation, User

logger = logging.getLogger("interviewops.accounts")
SALT = "accounts.invitation"


def make_token(invitation):
    return signing.dumps({"id": invitation.pk, "nonce": invitation.nonce}, salt=SALT)


def _invalid():
    return ValidationError(
        {
            "detail": "This invitation is not valid. Ask for a new one.",
            "code": "invalid_invitation",
        }
    )


@transaction.atomic
def invite(*, actor, email, role):
    email = email.lower()
    # Inviting again replaces the earlier invitation. This waits for anyone who is
    # accepting it, so the account check that follows sees their new account.
    Invitation.objects.filter(
        email=email, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=timezone.now())
    if User.objects.filter(email__iexact=email).exists():
        # Raising rolls the revocation back with the transaction.
        raise Conflict("An account already uses this email address.", "email_in_use")
    try:
        with transaction.atomic():
            invitation = Invitation.objects.create(
                email=email,
                role=role,
                invited_by=actor,
                nonce=secrets.token_urlsafe(16),
                expires_at=timezone.now() + timedelta(days=settings.INVITATION_TTL_DAYS),
            )
    except IntegrityError as exc:
        raise Conflict(
            "This address was just invited by someone else.", "invitation_in_progress"
        ) from exc
    outbox.enqueue(outbox.Kind.INVITATION, invitation=invitation)
    logger.info("invitation_created id=%s role=%s actor_id=%s", invitation.pk, role, actor.pk)
    return invitation


@transaction.atomic
def revoke(*, invitation_id):
    invitation = Invitation.objects.select_for_update().filter(pk=invitation_id).first()
    if invitation is None:
        return None
    if invitation.accepted_at:
        raise Conflict("This invitation has already been accepted.", "invitation_accepted")
    if not invitation.revoked_at:
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
    return invitation


def accept(*, token, username, password, validate):
    """Create the account. `validate` checks the username and password for this email."""
    try:
        data = signing.loads(token, salt=SALT)
        pk, nonce = int(data["id"]), str(data["nonce"])
    except signing.BadSignature, KeyError, TypeError, ValueError:
        raise _invalid() from None
    try:
        with transaction.atomic():
            invitation = Invitation.objects.select_for_update().filter(pk=pk, nonce=nonce).first()
            if invitation is None or not invitation.is_pending():
                raise _invalid()
            validate(username, invitation.email, password)
            user = User.objects.create_user(
                username, invitation.email, password, role=invitation.role
            )
            invitation.accepted_at = timezone.now()
            invitation.accepted_by = user
            invitation.save(update_fields=["accepted_at", "accepted_by"])
    except IntegrityError as exc:
        raise ValidationError({"detail": "Username or email already in use."}) from exc
    logger.info("invitation_accepted id=%s user_id=%s", pk, user.pk)
    return user
