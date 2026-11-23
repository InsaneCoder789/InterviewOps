# Investigation 001: deadlock on concurrent overlapping bookings

**Status:** guarded. This was reproduced by deliberately removing a lock during
testing; it was never seen in a deployed system.

## Symptom
One student sends two requests at once for two different slots at the same time.
Expected: one succeeds, one gets 409. Without the student lock, some requests
instead raised `OperationalError`, which the API would return as a 500.

## Evidence
30 rounds of two simultaneous bookings, lock removed (PostgreSQL 18, local):

| Outcome | Count |
|---|---|
| booking created | 30 |
| clean conflict (`IntegrityError` mapped to 409) | 27 |
| `DeadlockDetected`, SQLSTATE `40P01` | 3 |

```
deadlock detected
DETAIL:  Process A waits for ShareLock on transaction X; blocked by process B.
         Process B waits for ShareLock on transaction Y; blocked by process A.
CONTEXT:  while checking exclusion constraint on tuple (0,2) in relation "scheduling_booking"
```
(Process and transaction numbers replaced with letters.) Counts vary by run.

## Cause
The two requests lock *different* slot rows, so the slot lock does not order
them. Each inserts its booking, then checks the exclusion constraint, finds the
other's uncommitted row and waits for that transaction. When both have inserted
before either checks, each waits on the other.

## Fix
`book_slot` locks the student row first (`FOR NO KEY UPDATE`), so one student's
bookings run one at a time and the second sees a committed conflict.
`publish_slot` locks the mentor row for the same reason; removing that lock also
produced `OperationalError` in the tests.

Catching the deadlock and retrying would also work, but needs retry logic and
waits for PostgreSQL's deadlock detector (`deadlock_timeout`, 1 s by default).

## Reproduce
In `scheduling/services.py`, replace `_lock_user(student.pk)` with
`User.objects.get(pk=student.pk)` and run
`python manage.py test tests.test_concurrency`. The test
`test_one_student_two_overlapping_slots` usually fails. The race depends on
timing, so repeat the run if it passes. Restore the line afterwards.
