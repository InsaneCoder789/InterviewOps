"""Plain-text messages. Built at send time, so they reflect current details and no
secret is ever stored in the queue."""

from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.invitations import make_token

from .models import Notification

Kind = Notification.Kind


def _when(moment):
    return f"{moment:%d %b %Y %H:%M} UTC"


def _session(booking, recipient):
    mentor = booking.slot.mentor
    other = mentor if recipient.pk == booking.student_id else booking.student
    return (
        f"Topic: {booking.slot.topic}\n"
        f"With: {other.username}\n"
        f"Starts: {_when(booking.starts_at)}\n"
        f"Ends: {_when(booking.ends_at)}"
        + (f"\nMeeting link: {booking.meeting_link}" if booking.meeting_link else "")
    )


BOOKING_MESSAGES = {
    Kind.BOOKING_CONFIRMED: ("Booked", "A mock interview has been booked."),
    Kind.BOOKING_RESCHEDULED: ("Moved", "A mock interview has moved to a new time."),
    Kind.BOOKING_CANCELLED: ("Cancelled", "This mock interview has been cancelled."),
    Kind.REMINDER: ("Reminder", "Your mock interview is coming up."),
    Kind.SESSION_UPDATED: ("Meeting link", "The meeting link for your session has been set."),
}


def _link(page, **values):
    # Secrets go after "#", which browsers do not send to servers or put in their logs.
    return f"{settings.APP_BASE_URL}/{page}#{urlencode(values)}"


def _invitation(invitation):
    return (
        "You are invited to InterviewOps",
        f"You have been invited to join as a {invitation.role}.\n\n"
        f"Create your account:\n{_link('accept-invitation', token=make_token(invitation))}\n\n"
        f"The link works once and expires on {_when(invitation.expires_at)}.\n",
        invitation.email,
    )


def _password_reset(user):
    link = _link(
        "reset-password",
        uid=urlsafe_base64_encode(force_bytes(user.pk)),
        token=default_token_generator.make_token(user),
    )
    return (
        "Reset your InterviewOps password",
        f"Hi {user.username},\n\nChoose a new password:\n{link}\n\n"
        "If you did not ask for this, ignore this message. Your password is unchanged.\n",
        user.email,
    )


def render(notification):
    """Return (subject, body, address)."""
    if notification.kind == Kind.INVITATION:
        return _invitation(notification.invitation)
    if notification.kind == Kind.PASSWORD_RESET:
        return _password_reset(notification.recipient)
    recipient, booking = notification.recipient, notification.booking
    label, lead = BOOKING_MESSAGES[notification.kind]
    return (
        f"{label}: mock interview on {_when(booking.starts_at)}",
        f"Hi {recipient.username},\n\n{lead}\n\n{_session(booking, recipient)}\n",
        recipient.email,
    )
