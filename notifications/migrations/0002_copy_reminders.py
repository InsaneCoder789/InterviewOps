from django.db import migrations

# Reminders move into the general queue, keeping their delivery history.
COPY = """
INSERT INTO notifications_notification
    (kind, recipient_id, booking_id, status, available_at, attempts, last_error,
     sent_at, created_at)
SELECT 'reminder', b.student_id, r.booking_id, r.status, r.available_at, r.attempts,
       r.last_error, r.sent_at, b.created_at
FROM scheduling_reminder r JOIN scheduling_booking b ON b.id = r.booking_id
"""


class Migration(migrations.Migration):
    dependencies = [("notifications", "0001_initial"), ("scheduling", "0002_initial")]

    operations = [migrations.RunSQL(COPY, migrations.RunSQL.noop)]
