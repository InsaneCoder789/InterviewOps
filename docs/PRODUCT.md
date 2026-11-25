# Product direction

InterviewOps is a practice loop for interview preparation in one invite-only
community: a student books a mentor, both attend, the mentor writes feedback and
the student reviews it.

## Working rules

These are defaults chosen to start building. Change them if the real community
differs.

| Question | Rule |
|---|---|
| Who joins | people an admin invites; public sign-up stays closed |
| How mentors are approved | an admin invites them as a mentor or changes their role |
| Price | free; no payments |
| Meeting links | the mentor pastes an `https` link |
| Organisations | one community per installation |

## State

| Area | Built in the API | Not built |
|---|---|---|
| Accounts | invitations, profiles, password change and reset, deactivation | separate email verification for open sign-up, per-device sessions |
| Scheduling | slots, booking, cancelling, rescheduling | recurring availability, editing a slot |
| Session | meeting link, preparation notes, attendance | video calls, calendar sync |
| Email | confirmation, reminder, change, cancellation, feedback, invitation, reset | HTML templates, local-time wording, bounce handling |
| Feedback | ratings, comments, progress | student reply, mentor ratings |
| Admin | users, invitations, overview, delivery records | audit history |
| Operations | CI, backup scripts, health and queue checks | hosting, scheduled backups, alerting |
| Web app | none in this repository yet | all screens |

## Before a pilot

1. Build the web app against [API.md](API.md).
2. Choose an email provider and a domain, then deploy ([OPERATIONS.md](OPERATIONS.md)).
3. Write a privacy notice, and decide how long profiles, notes and feedback are
   kept and how someone can have them removed.
4. Invite a small group and watch whether sessions happen and feedback is read.
