from datetime import timedelta

from django.db import IntegrityError, connection, transaction

from scheduling.models import Booking

from . import test_sessions


class DatabaseRuleTests(test_sessions.SessionCase):
    def test_booking_times_must_match_the_slot(self):
        later = self.booking.starts_at + timedelta(hours=5)
        for change in (
            lambda: Booking.objects.filter(pk=self.booking.pk).update(
                starts_at=later, ends_at=later + timedelta(hours=1)
            ),
            lambda: (
                type(self.slot_a)
                .objects.filter(pk=self.slot_a.pk)
                .update(starts_at=later, ends_at=later + timedelta(hours=1))
            ),
        ):
            with (
                self.assertRaisesMessage(IntegrityError, "booking_times_match_slot"),
                transaction.atomic(),
            ):
                change()
                # Checked at commit; force it inside the test transaction.
                with connection.cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
