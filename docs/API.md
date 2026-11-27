# API reference

Examples use `http://127.0.0.1:8000`, the local development server. There is no
hosted instance. IDs, tokens and times are illustrative.

- [Conventions](#conventions)
- [Accounts](#accounts)
- [Invitations and passwords](#invitations-and-passwords)
- [Users](#users)
- [Profiles](#profiles)
- [Slots](#slots)
- [Bookings](#bookings)
- [Feedback](#feedback)
- [Admin tools](#admin-tools)
- [Emails](#emails)
- [Client settings](#client-settings)
- [Health](#health)

## Conventions

**Authentication.** Send `Authorization: Token <token>` on every endpoint except
register, accept-invitation, password reset, login, client
settings and health. A token lasts 12 hours by default
(`TOKEN_TTL_HOURS`), counted from when it was created. After that it returns `401`
`{"detail": "Token has expired."}`.

**Bodies.** Send `Content-Type: application/json`. Form-encoded and multipart
bodies are also accepted. Responses with a body are JSON. Outside debug mode, an
unmatched `/api/` URL returns `404` `{"detail": "Not found."}` and an unhandled
error returns `500` `{"detail": "Server error."}`.

**Paths** end with a slash.

**Times** are ISO 8601. Include an offset or `Z`; a time without one is read as
UTC. Responses are in UTC.

**Request ID.** Responses from the application carry an `X-Request-ID` header.

**Browsers.** Origins listed in `CORS_ALLOWED_ORIGINS` may call `/api/` and
`/health/` and can read the `Retry-After` and `X-Request-ID` headers. Cookies are
not used.

### Pagination

List endpoints accept `page` and `page_size` (default 20, maximum 100; larger
values are capped). A page that does not exist returns `404`
`{"detail": "Invalid page."}`.

```json
{
  "count": 42,
  "next": "http://127.0.0.1:8000/api/slots/?page=2",
  "previous": null,
  "results": []
}
```

### Errors

Validation errors list messages by field:

```json
{"starts_at": ["Must be in the future."]}
```

Other errors have a `detail` string. Every `409` also has a stable `code`; match
on the code, not the message:

```json
{"detail": "This slot is already booked.", "code": "slot_already_booked"}
```

| Code | Returned by |
|---|---|
| `slot_already_booked` | booking |
| `student_overlap` | booking |
| `booking_already_cancelled` | cancelling a booking |
| `session_started` | cancelling a booking |
| `cancel_cutoff` | cancelling a booking as its student |
| `slot_overlap` | publishing |
| `mentor_unavailable` | publishing |
| `slot_not_in_future` | publishing |
| `slot_length` | publishing |
| `slot_already_cancelled` | cancelling a slot |
| `slot_started` | cancelling a slot |
| `own_role` | changing a role |
| `role_has_commitments` | changing a role |
| `own_status` | changing your own account status |
| `email_in_use` | inviting an address that has an account |
| `invitation_in_progress` | two invitations for one address at once |
| `invitation_accepted` | revoking a used invitation |
| `same_slot` | rescheduling into the current slot |
| `student_unavailable` | rescheduling for an inactive or ex-student |
| `session_ended` | editing session details afterwards |
| `session_not_started` | attendance or feedback too early |
| `feedback_exists` | marking a session with feedback as missed |
| `session_missed` | feedback on a missed session |
| `feedback_locked` | revising feedback after the window |
| `not_failed` | retrying a message that has not failed |

Rescheduling can also return `cancel_cutoff`, `session_started`,
`booking_already_cancelled`, `slot_already_booked` and `student_overlap`.
`400` bodies for bad links carry the code `invalid_invitation` or
`invalid_reset_link`.

The `409` examples below show `detail` only. A closed sign-up returns `403` with
the code `registration_closed`.

| Status | Meaning |
|---|---|
| 400 | invalid body or query parameter |
| 401 | missing token (`Authentication credentials were not provided.`), bad token (`Invalid token.`) or expired token (`Token has expired.`) |
| 403 | your role may not do this (`You do not have permission to perform this action.`) |
| 404 | not found, or not visible to you |
| 405 | method not allowed on this path |
| 409 | the request conflicts with the current state |
| 415 | unsupported content type |
| 429 | too many sign-up or login requests |

Role checks run before the object is looked up, so a student who calls a
mentor-only endpoint gets `403` whether or not the ID exists. The `401`, `405`
and `415` responses apply across endpoints and are not repeated below.

## Accounts

Sign-up, login, invitation and password endpoints share one throttle: 10 requests
per minute per client address. A throttled request returns `429` with a `Retry-After`
header:

```json
{"detail": "Request was throttled. Expected available in 42 seconds."}
```

### POST /api/auth/register/

Anyone, while sign-up is open. Creates a student. Extra fields such as `role` are
ignored. Sign-up is open in debug mode and closed otherwise unless
`ALLOW_REGISTRATION` is set; when closed it returns `403`
`{"detail": "Registration is closed.", "code": "registration_closed"}`.

| Field | Rules |
|---|---|
| `username` | required, unique, up to 150 characters: letters, digits and `@ . + - _` |
| `email` | required, valid, unique ignoring case; stored in lower case |
| `password` | required, up to 128 characters; at least 8, not entirely numeric, not a common password, not too similar to the username or email |

```http
POST /api/auth/register/

{"username": "ravi", "email": "Ravi@Example.test", "password": "<password>"}
```

`201 Created`

```json
{"id": 3, "username": "ravi", "email": "ravi@example.test"}
```

`400 Bad Request`

```json
{
  "username": ["A user with that username already exists."],
  "email": ["This field must be unique."]
}
```

A weak password is reported under `password`. If two sign-ups for the same name
or address race, the loser gets `400`
`{"detail": "Username or email already in use."}`.

Statuses: `201`, `400`, `403`, `429`.

### POST /api/auth/login/

Anyone. Returns the user's token, creating one if there is none or the old one has
expired. A token that is still valid is returned unchanged, so `expires_at` can be
less than a full lifetime away. Log in with the username, not the email. Any
`Authorization` header is ignored.

```http
POST /api/auth/login/

{"username": "ravi", "password": "<password>"}
```

`200 OK`

```json
{
  "token": "<token>",
  "expires_at": "2026-11-27T20:15:30.124000Z"
}
```

`400 Bad Request`

```json
{"non_field_errors": ["Unable to log in with provided credentials."]}
```

Statuses: `200`, `400`, `429`.

### POST /api/auth/logout/

Signed in. Deletes the token, which signs out every client using it.

`204 No Content`

Statuses: `204`, `401`.

### GET /api/auth/me/

Signed in.

`200 OK`

```json
{"id": 3, "username": "ravi", "email": "ravi@example.test", "role": "student", "is_active": true}
```

Statuses: `200`, `401`.

## Invitations and passwords

Links point at `APP_BASE_URL`, with their secrets after `#`:
`/accept-invitation#token=...` and `/reset-password#uid=...&token=...`. The client
reads them from the fragment and posts them. The endpoints marked throttled share
the sign-up and login limit.

| Method and path | Who | Body | Success |
|---|---|---|---|
| `GET /api/invitations/` | admin | | `200`, paginated |
| `POST /api/invitations/` | admin | `email`, `role` | `201` invitation |
| `POST /api/invitations/{id}/revoke/` | admin | | `200` invitation |
| `POST /api/auth/accept-invitation/` | anyone, throttled | `token`, `username`, `password` | `201` user |
| `POST /api/auth/password-reset/` | anyone, throttled | `email` | `202`, the same for any address |
| `POST /api/auth/password-reset/confirm/` | anyone, throttled | `uid`, `token`, `password` | `204` |
| `POST /api/auth/password/` | signed in, throttled | `current_password`, `new_password` | `200` new `token`, `expires_at` |

An invitation has `id, email, role, status, invited_by, created_at, expires_at,
accepted_at, accepted_by, revoked_at`; `status` is `pending`, `accepted`,
`revoked` or `expired`. It lasts 7 days and works once. Inviting an address again
replaces the open invitation. Accepting works while public sign-up is closed.

A reset link lasts one hour and stops working once the password changes. Both
password operations revoke the old API token.

## Users

### GET /api/users/

Admin. Paginated, ordered by ID.

| Parameter | Meaning |
|---|---|
| `role` | `student`, `mentor` or `admin` |
| `search` | case-insensitive substring of the username |
| `is_active` | `true` or `false` |

`200 OK`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {"id": 2, "username": "maya", "email": "maya@example.test", "role": "mentor", "is_active": true}
  ]
}
```

`400 Bad Request` for an unknown role:

```json
{"role": ["Select a valid choice. zzz is not one of the available choices."]}
```

Statuses: `200`, `400`, `401`, `403`, `404`.

### PATCH /api/users/{id}/status/

Admin. `{"is_active": false}` deactivates: the person is signed out, and their
future slots and bookings are cancelled with notices to the other participant.
Sessions already started are left alone. `true` restores access, not sessions.
Returns the user. Statuses: `200`, `400`, `401`, `403`, `404`, `409`.

### PATCH /api/users/{id}/role/

Admin.

```http
PATCH /api/users/2/role/

{"role": "mentor"}
```

`200 OK`

```json
{"id": 2, "username": "maya", "email": "maya@example.test", "role": "mentor", "is_active": true}
```

Setting the role the user already has returns `200` and changes nothing.

| Status | Body |
|---|---|
| 400 | `{"role": ["This field is required."]}` |
| 400 | `{"role": ["\"boss\" is not a valid choice."]}` |
| 404 | `{"detail": "User not found."}` |
| 409 | `{"detail": "You cannot change your own role."}` |
| 403 | `{"detail": "Only admins can change roles."}` (caller lost the admin role during the request) |
| 409 | `{"detail": "Cancel this user's upcoming slots and bookings before changing role."}` |

The last applies while the user has an active slot or booking that has not ended.
Moving a user out of the admin role also removes their Django admin access.

Statuses: `200`, `400`, `401`, `403`, `404`, `409`.

## Profiles

A profile: `user, username, role, display_name, headline, bio, experience_level,
target_roles, topics, timezone`. It never includes an email address.

| Method and path | Who | Notes |
|---|---|---|
| `GET /api/profile/` | signed in | own; empty until saved |
| `PATCH /api/profile/` | signed in | any of the editable fields |
| `GET /api/users/{id}/profile/` | see below | otherwise `404` |
| `GET /api/mentors/` | signed in | active mentors, paginated; `topic` (exact, ignoring case), `search` (username or display name) |

Anyone signed in may read their own and any active mentor's profile; a mentor may
read an active student who holds a booking with them; admins read all.

`experience_level` is `student`, `entry`, `mid`, `senior` or empty. `timezone` is
an IANA name. `topics` and `target_roles` hold up to 15 entries of 60 characters,
stored trimmed, in lower case and without repeats. `display_name` is up to 80
characters, `headline` 120, `bio` 2000.

## Slots

A slot object:

```json
{
  "id": 1,
  "mentor": 2,
  "mentor_name": "maya",
  "topic": "System design",
  "starts_at": "2026-12-01T10:00:00Z",
  "ends_at": "2026-12-01T11:00:00Z",
  "cancelled_at": null,
  "is_booked": false
}
```

Visibility depends on role:

| Role | Sees |
|---|---|
| student | slots of active mentors that are not cancelled and have not started, booked or not |
| mentor | own slots, including past and cancelled ones |
| admin | all slots |

### GET /api/slots/

Signed in. Paginated, ordered by `starts_at`, then ID. `ordering=-starts_at`
reverses the order; other ordering fields are ignored.

| Parameter | Meaning |
|---|---|
| `mentor` | mentor's user ID |
| `topic` | case-insensitive substring |
| `available` | `true` for bookable slots, `false` for the rest |
| `cancelled` | `true` or `false` |
| `starts_after` | `starts_at` at or after this time |
| `starts_before` | `starts_at` strictly before this time |
| `ends_after` | `ends_at` strictly after this time, so a session in progress is included |

`true`, `false`, `1` and `0` are accepted for booleans, and anything else is
`400`. IDs must be positive whole numbers.

A slot is bookable when it has no active booking, is not cancelled, has not
started and its mentor is active. The filter applies within the slots your role
can see.

In a query string, write UTC as `Z`, or encode a `+` offset as `%2B`.

```http
GET /api/slots/?available=true&topic=design&starts_after=2026-12-01T00:00:00Z
```

`200 OK` with a paginated list of slot objects.

`400 Bad Request`

```json
{"starts_after": ["Enter a valid date/time."]}
```

Statuses: `200`, `400`, `401`, `404`.

### GET /api/slots/{id}/

Signed in. `200 OK` with a slot object, or `404` if it does not exist or your role
cannot see it:

```json
{"detail": "No Slot matches the given query."}
```

Statuses: `200`, `401`, `404`.

### POST /api/slots/

Mentor or admin.

| Field | Rules |
|---|---|
| `topic` | required, up to 100 characters |
| `starts_at` | required, in the future |
| `ends_at` | required, 15 minutes to 3 hours after `starts_at` |
| `mentor` | required for admins: ID of an active mentor. Mentors omit it or pass their own ID |

```http
POST /api/slots/

{
  "topic": "System design",
  "starts_at": "2026-12-01T10:00:00Z",
  "ends_at": "2026-12-01T11:00:00Z"
}
```

`201 Created` with the slot object.

| Status | Body |
|---|---|
| 400 | `{"starts_at": ["Must be in the future."]}` |
| 400 | `{"ends_at": ["A slot must last between 15 minutes and 3 hours."]}` |
| 400 | `{"mentor": ["Required for admins."]}` |
| 400 | `{"mentor": ["You can only publish your own slots."]}` |
| 400 | `{"mentor": ["Invalid pk \"9\" - object does not exist."]}` (not an active mentor) |
| 409 | `{"detail": "This overlaps another of the mentor's slots."}` |
| 409 | `{"detail": "Slots can only be published for an active mentor."}` (changed during the request) |
| 409 | `{"detail": "A slot must start in the future."}` (start passed during the request) |

Statuses: `201`, `400`, `401`, `403`, `409`.

### POST /api/slots/{id}/cancel/

The owning mentor, or an admin. No body. Cancels the slot and its active booking,
and withdraws unsent notices about that booking. Both participants are emailed.

`204 No Content`

| Status | Body |
|---|---|
| 403 | caller is a student |
| 404 | `{"detail": "Slot not found."}` (missing, or another mentor's) |
| 409 | `{"detail": "This slot is already cancelled."}` |
| 409 | `{"detail": "A slot that has started cannot be cancelled."}` |

Statuses: `204`, `401`, `403`, `404`, `409`.

## Bookings

A booking object:

```json
{
  "id": 1,
  "slot": 1,
  "student": 3,
  "student_name": "ravi",
  "mentor": 2,
  "mentor_name": "maya",
  "topic": "System design",
  "starts_at": "2026-12-01T10:00:00Z",
  "ends_at": "2026-12-01T11:00:00Z",
  "status": "booked",
  "created_at": "2026-11-27T08:15:30.124000Z",
  "cancelled_at": null,
  "cancelled_by": null,
  "meeting_link": "",
  "preparation_notes": "",
  "attendance": "",
  "rescheduled_from": null
}
```

Students see their own bookings, mentors see bookings on their slots, and admins
see all.

### GET /api/bookings/

Signed in. Paginated, ordered by `starts_at`, then ID. `ordering=-starts_at`
reverses the order; other ordering fields are ignored.

| Parameter | Meaning |
|---|---|
| `status` | `booked` or `cancelled` |
| `slot` | slot ID |
| `student` | student's user ID |
| `mentor` | mentor's user ID |
| `starts_after` | `starts_at` at or after this time |
| `starts_before` | `starts_at` strictly before this time |
| `ends_after` | `ends_at` strictly after this time, so a session in progress is included |

An ID with no visible bookings gives an empty list. Filters never widen what your
role can see.

`200 OK` with a paginated list of booking objects.

`400 Bad Request`

```json
{"status": ["Select a valid choice. zzz is not one of the available choices."]}
```

Statuses: `200`, `400`, `401`, `404`.

### GET /api/bookings/{id}/

The booking's student, the slot's mentor, or an admin.

`200 OK` with a booking object. Anyone else gets `404`:

```json
{"detail": "No Booking matches the given query."}
```

Statuses: `200`, `401`, `404`.

### POST /api/bookings/

Student.

```http
POST /api/bookings/

{"slot": 1}
```

`201 Created` with the booking object. Confirmations and reminders are queued in the same
transaction.

| Status | Body |
|---|---|
| 400 | `{"slot": ["This field is required."]}` |
| 400 | `{"slot": ["A valid integer is required."]}` |
| 403 | caller is not a student |
| 404 | `{"detail": "Slot not found."}` |
| 409 | `{"detail": "This slot is already booked."}` |
| 409 | `{"detail": "You already have a booking at this time."}` |

Back-to-back bookings are allowed.

A slot that is cancelled, has started or belongs to an inactive mentor returns
the same `404` as an ID that does not exist.

Statuses: `201`, `400`, `401`, `403`, `404`, `409`.

### POST /api/bookings/{id}/cancel/

The booking's student, the slot's mentor, or an admin. No body. The slot becomes
bookable again, unsent notices are withdrawn and both participants are emailed.

`200 OK`

```json
{
  "id": 1,
  "slot": 1,
  "student": 3,
  "student_name": "ravi",
  "mentor": 2,
  "mentor_name": "maya",
  "topic": "System design",
  "starts_at": "2026-12-01T10:00:00Z",
  "ends_at": "2026-12-01T11:00:00Z",
  "status": "cancelled",
  "created_at": "2026-11-27T08:15:30.124000Z",
  "cancelled_at": "2026-11-27T09:00:00.512000Z",
  "cancelled_by": 3,
  "meeting_link": "",
  "preparation_notes": "",
  "attendance": "",
  "rescheduled_from": null
}
```

| Status | Body |
|---|---|
| 404 | `{"detail": "Booking not found."}` (missing, or not yours) |
| 409 | `{"detail": "This booking is already cancelled."}` |
| 409 | `{"detail": "A session that has started cannot be cancelled or moved."}` |
| 409 | `{"detail": "Students cannot cancel or move a session less than 2 hours before it starts."}` |

Statuses: `200`, `401`, `404`, `409`.

### POST /api/bookings/{id}/reschedule/

The student or an admin. `{"slot": id}`. Cancels this booking and creates a new
one in one transaction, or changes nothing. `201` with the new booking, whose
`rescheduled_from` is the old ID. Preparation notes carry over; the meeting link
only if the mentor is the same. Students need the usual 2 hours' notice. The
mentor gets `403`; others `404`. An unavailable target slot is `404`.

### PATCH /api/bookings/{id}/

| Field | Who | Rules |
|---|---|---|
| `meeting_link` | the mentor or an admin | `https://` only, up to 500 characters, or empty |
| `preparation_notes` | the student or an admin | up to 2000 characters |

Send at least one. Allowed while booked and until the session ends. A new link is
emailed to the student. `200` with the booking.

### POST /api/bookings/{id}/attendance/

The mentor or an admin, after the start. `{"attendance": "completed"}`, or
`student_absent` or `mentor_absent`. `200` with the booking.

## Feedback

A feedback object: `id, booking, student, mentor, mentor_name, topic,
session_starts_at, communication, problem_solving, technical, strengths,
improvements, next_steps, created_at, updated_at`.

| Method and path | Who | Notes |
|---|---|---|
| `PUT /api/bookings/{id}/feedback/` | the session's mentor | `201` first time, `200` after |
| `GET /api/bookings/{id}/feedback/` | student, mentor, admin | `404` if none or not yours |
| `GET /api/feedback/` | signed in | own, written, or all; filters `student`, `mentor` |
| `GET /api/feedback/progress/` | signed in | students get their own; others pass `?student=id` |

All three ratings are whole numbers from 1 to 5; the three texts are required, up
to 4000 characters. Feedback needs a booked session that has started and is not
marked missed; saving it marks the session completed. It can be revised for 7
days. The student is emailed that it is ready, without the comments.

Progress returns `student`, `sessions`, `averages`, `history` (the latest 20,
oldest first) and `latest_next_steps`. A mentor's view covers only their sessions.

## Admin tools

All admin only.

`GET /api/admin/overview/` returns `active_users` by role, `pending_invitations`,
`open_slots`, `upcoming_sessions`, `upcoming_without_link`,
`completed_sessions`, `missed_sessions`, `awaiting_feedback` and
`notifications` (`failed`, `due`, `oldest_due_seconds`).

`GET /api/notifications/` lists messages, newest first, with filters `status` and
`kind`: `id, kind, status, recipient, email, booking, invitation, attempts,
available_at, sent_at, last_error, created_at`.

`POST /api/notifications/{id}/retry/` queues a failed message again.

## Emails

Sent by the `send_notifications` worker, as plain text with times in UTC.

| Kind | To | When |
|---|---|---|
| `booking_confirmed` | student and mentor | on booking |
| `reminder` | student and mentor | 24 hours before, or at once for a later booking |
| `booking_rescheduled` | student and new mentor | on rescheduling; a replaced mentor gets a cancellation |
| `booking_cancelled` | student and mentor | on cancellation; deactivated users get nothing |
| `session_updated` | student | a meeting link is set |
| `feedback_ready` | student | first feedback |
| `invitation` | the invited address | on invitation |
| `password_reset` | the account | on request |

## Client settings

### GET /api/config/

Anyone. The rules a client needs before it has a token.

```json
{
  "registration_open": true,
  "token_ttl_hours": 12,
  "student_cancellation_cutoff_hours": 2,
  "reminder_lead_hours": 24,
  "slot_min_minutes": 15,
  "slot_max_minutes": 180,
  "feedback_edit_days": 7
}
```

Statuses: `200`, `405`.

## Health

### GET /health/

Anyone. Runs a query against the database.

| Status | Body |
|---|---|
| 200 | `{"status": "ok"}` |
| 503 | `{"status": "database unavailable"}` |
