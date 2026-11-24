from datetime import timedelta
from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from notifications import delivery
from notifications.models import Notification
from scheduling import services

from .base import Factory

SEND = "notifications.delivery.send_mail"


@override_settings(NOTIFICATION_MAX_ATTEMPTS=3, NOTIFICATION_RETRY_BASE_SECONDS=60)
class QueueTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.student = self.user("student")
        self.mentor_user = self.mentor()
        self.slot_obj = self.slot(self.mentor_user, hours=48)
        self.booking = services.book_slot(student=self.student, slot_id=self.slot_obj.pk)
        # Follow one message through the queue: the student's reminder.
        Notification.objects.exclude(kind="reminder", recipient=self.student).delete()

    def make_due(self):
        Notification.objects.update(available_at=timezone.now() - timedelta(seconds=1))

    def reminder(self):
        return Notification.objects.get(booking=self.booking, kind="reminder")

    def test_scheduled_a_day_ahead(self):
        self.assertEqual(self.reminder().available_at,
                         self.slot_obj.starts_at - timedelta(hours=24))
        self.assertEqual(delivery.process_due(), 0)

    def test_sends_once(self):
        self.make_due()
        self.assertEqual(delivery.process_due(), 1)
        self.assertEqual(delivery.process_due(), 0)
        self.assertEqual([m.to for m in mail.outbox], [["student@example.test"]])
        self.assertEqual(self.reminder().status, "sent")

    def test_backs_off_then_gives_up(self):
        with patch(SEND, side_effect=SMTPException("down")):
            for attempt, delay in ((1, 60), (2, 120)):
                self.make_due()
                before = timezone.now()
                delivery.process_due()
                r = self.reminder()
                self.assertEqual((r.status, r.attempts), ("pending", attempt))
                self.assertGreaterEqual(r.available_at, before + timedelta(seconds=delay))
                self.assertEqual(delivery.process_due(), 0)  # not due yet
            self.make_due()
            delivery.process_due()
        r = self.reminder()
        self.assertEqual((r.status, r.attempts), ("failed", 3))
        self.assertIn("down", r.last_error)

    def test_recovers_on_retry(self):
        self.make_due()
        with patch(SEND, side_effect=TimeoutError):
            delivery.process_due()
        self.make_due()
        delivery.process_due()
        r = self.reminder()
        self.assertEqual((r.status, r.attempts, r.last_error), ("sent", 2, ""))

    @override_settings(NOTIFICATION_MAX_ATTEMPTS=10, NOTIFICATION_RETRY_MAX_SECONDS=100)
    def test_backoff_is_capped(self):
        Notification.objects.update(attempts=6)
        self.make_due()
        with patch(SEND, side_effect=TimeoutError):
            delivery.process_due()
        self.assertLessEqual(
            self.reminder().available_at, timezone.now() + timedelta(seconds=100))

    def test_inactive_student_is_not_reminded(self):
        type(self.student).objects.filter(pk=self.student.pk).update(is_active=False)
        self.make_due()
        delivery.process_due()
        self.assertEqual((self.reminder().status, mail.outbox), ("skipped", []))

    def test_stop_request_prevents_further_claims(self):
        self.make_due()
        self.assertEqual(delivery.process_due(should_stop=lambda: True), 0)
        self.assertEqual(self.reminder().status, "pending")

    @override_settings(
        DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_worker_refuses_console_email_in_production(self):
        with self.assertRaises(CommandError):
            call_command("send_reminders", once=True)

    def test_expired_lease_is_reclaimed(self):
        self.make_due()
        delivery.claim_next()  # worker "dies" here
        self.assertIsNone(delivery.claim_next())
        self.make_due()  # lease expires
        delivery.process_due()
        self.assertEqual(self.reminder().attempts, 2)
        self.assertEqual(len(mail.outbox), 1)

    def test_crash_on_final_attempt_marks_failed(self):
        Notification.objects.update(status="sending", attempts=3)
        self.make_due()
        delivery.process_due()
        self.assertEqual(self.reminder().status, "failed")
        self.assertEqual(mail.outbox, [])

    def test_cancelled_booking_is_not_reminded(self):
        services.cancel_booking(actor=self.student, booking_id=self.booking.pk)
        Notification.objects.filter(kind="booking_cancelled").delete()
        self.make_due()
        delivery.process_due()
        self.assertEqual(self.reminder().status, "skipped")
        self.assertEqual(mail.outbox, [])

    def test_cancellation_between_claim_and_send(self):
        self.make_due()
        claimed = delivery.claim_next()
        services.cancel_booking(actor=self.student, booking_id=self.booking.pk)
        delivery.deliver(claimed)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(self.reminder().status, "skipped")

    def test_stale_worker_cannot_overwrite_newer_attempt(self):
        self.make_due()
        stale = delivery.claim_next()
        self.make_due()
        delivery.claim_next()
        delivery.deliver(stale)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(self.reminder().status, "sending")


class BookingEmailTests(Factory, TestCase):
    def setUp(self):
        super().setUp()
        self.student, self.m = self.user("student"), self.mentor()
        self.booking = services.book_slot(student=self.student, slot_id=self.slot(self.m).pk)

    def sent(self):
        delivery.process_due()
        messages = sorted((m.to[0].split("@")[0], m.subject.split(":")[0]) for m in mail.outbox)
        mail.outbox.clear()
        return messages

    def test_booking_confirms_both_people_now_and_reminds_them_later(self):
        self.assertEqual(self.sent(), [("mentor", "Booked"), ("student", "Booked")])
        Notification.objects.update(available_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.sent(), [("mentor", "Reminder"), ("student", "Reminder")])

    def test_cancellation_tells_both_and_withdraws_the_rest(self):
        services.cancel_booking(actor=self.m, booking_id=self.booking.pk)
        Notification.objects.exclude(status="skipped").update(
            available_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.sent(), [("mentor", "Cancelled"), ("student", "Cancelled")])

    def test_message_names_the_other_person(self):
        delivery.process_due()
        bodies = {m.to[0].split("@")[0]: m.body for m in mail.outbox}
        self.assertIn("With: mentor", bodies["student"])
        self.assertIn("With: student", bodies["mentor"])
