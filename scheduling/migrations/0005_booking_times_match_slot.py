from django.db import migrations

# A booking copies its slot's times so that the overlap constraint can see them.
# These triggers make the database check the copy. They run at commit.
FORWARD = """
CREATE FUNCTION scheduling_check_booking_times() RETURNS trigger AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM scheduling_booking b
        JOIN scheduling_slot s ON s.id = b.slot_id
        WHERE b.status = 'booked'
          AND (b.starts_at <> s.starts_at OR b.ends_at <> s.ends_at)
          AND CASE TG_TABLE_NAME
                  WHEN 'scheduling_slot' THEN s.id = NEW.id
                  ELSE b.id = NEW.id
              END
    ) THEN
        RAISE EXCEPTION 'booking_times_match_slot: booking times differ from the slot'
            USING ERRCODE = 'check_violation', CONSTRAINT = 'booking_times_match_slot';
    END IF;
    RETURN NULL;
END
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER booking_times_match_slot
    AFTER INSERT OR UPDATE OF slot_id, starts_at, ends_at, status ON scheduling_booking
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION scheduling_check_booking_times();

CREATE CONSTRAINT TRIGGER slot_times_match_bookings
    AFTER UPDATE OF starts_at, ends_at ON scheduling_slot
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION scheduling_check_booking_times();
"""

BACKWARD = """
DROP TRIGGER booking_times_match_slot ON scheduling_booking;
DROP TRIGGER slot_times_match_bookings ON scheduling_slot;
DROP FUNCTION scheduling_check_booking_times();
"""


class Migration(migrations.Migration):
    dependencies = [("scheduling", "0004_session_details")]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
