"""Plain-text messages. Built at send time, so they reflect current details and no
secret is ever stored in the queue."""

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
    )


BOOKING_MESSAGES = {
    Kind.BOOKING_CONFIRMED: ("Booked", "A mock interview has been booked."),
    Kind.BOOKING_RESCHEDULED: ("Moved", "A mock interview has moved to a new time."),
    Kind.BOOKING_CANCELLED: ("Cancelled", "This mock interview has been cancelled."),
    Kind.REMINDER: ("Reminder", "Your mock interview is coming up."),
}


def render(notification):
    """Return (subject, body, address)."""
    recipient, booking = notification.recipient, notification.booking
    label, lead = BOOKING_MESSAGES[notification.kind]
    return (
        f"{label}: mock interview on {_when(booking.starts_at)}",
        f"Hi {recipient.username},\n\n{lead}\n\n{_session(booking, recipient)}\n",
        recipient.email,
    )
