# API reference

Examples use `http://127.0.0.1:8000`, the local development server. There is no
hosted instance. IDs, tokens and times are illustrative.

- [Conventions](#conventions)
- [Accounts](#accounts)
- [Users](#users)
- [Slots](#slots)
- [Bookings](#bookings)
- [Health](#health)

## Conventions

**Authentication.** Send `Authorization: Token <token>` on every endpoint except
register, login and health.

**Bodies.** Send `Content-Type: application/json`. Form-encoded and multipart
bodies are also accepted. Responses with a body are JSON, except for URLs that
match no route.

**Paths** end with a slash.

**Times** are ISO 8601. Include an offset or `Z`; a time without one is read as
UTC. Responses are in UTC.

**Request ID.** Responses from the application carry an `X-Request-ID` header.

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

Other errors have a `detail` string:

```json
{"detail": "This slot is already booked."}
```

| Status | Meaning |
|---|---|
| 400 | invalid body or query parameter |
| 401 | missing token (`Authentication credentials were not provided.`) or bad token (`Invalid token.`) |
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

Register and login share one throttle: 10 requests per minute per client address,
counted per web process. A throttled request returns `429` with a `Retry-After`
header:

```json
{"detail": "Request was throttled. Expected available in 42 seconds."}
```

### POST /api/auth/register/

Anyone. Creates a student. Extra fields such as `role` are ignored.

| Field | Rules |
|---|---|
| `username` | required, unique, up to 150 characters: letters, digits and `@ . + - _` |
| `email` | required, valid, unique ignoring case; stored in lower case |
| `password` | required, up to 128 characters; at least 8, not entirely numeric, not a common password, not too similar to the username or email |

```http
POST /api/auth/register/

{"username": "ravi", "email": "Ravi@Example.test", "password": "local-demo-pass-ravi"}
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

Statuses: `201`, `400`, `429`.

### POST /api/auth/login/

Anyone. Returns the user's token, creating it if needed. Log in with the
username, not the email. Do not send an `Authorization` header: a bad token is
rejected with `401`.

```http
POST /api/auth/login/

{"username": "ravi", "password": "local-demo-pass-ravi"}
```

`200 OK`

```json
{"token": "0123456789abcdef0123456789abcdef01234567"}
```

`400 Bad Request`

```json
{"non_field_errors": ["Unable to log in with provided credentials."]}
```

Statuses: `200`, `400`, `401`, `429`.

### POST /api/auth/logout/

Signed in. Deletes the token, which signs out every client using it.

`204 No Content`

Statuses: `204`, `401`.

### GET /api/auth/me/

Signed in.

`200 OK`

```json
{"id": 3, "username": "ravi", "email": "ravi@example.test", "role": "student"}
```

Statuses: `200`, `401`.

## Users

### GET /api/users/

Admin. Paginated, ordered by ID. Filter with `role=student|mentor|admin`.

`200 OK`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {"id": 2, "username": "maya", "email": "maya@example.test", "role": "mentor"}
  ]
}
```

`400 Bad Request` for an unknown role:

```json
{"role": ["Select a valid choice. zzz is not one of the available choices."]}
```

Statuses: `200`, `400`, `401`, `403`, `404`.

### PATCH /api/users/{id}/role/

Admin.

```http
PATCH /api/users/2/role/

{"role": "mentor"}
```

`200 OK`

```json
{"id": 2, "username": "maya", "email": "maya@example.test", "role": "mentor"}
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

Signed in. Paginated, ordered by `starts_at`, then ID.

| Parameter | Meaning |
|---|---|
| `mentor` | mentor's user ID |
| `topic` | case-insensitive substring |
| `available` | `true` for bookable slots, `false` for the rest; other values are ignored |
| `starts_after` | `starts_at` at or after this time |
| `starts_before` | `starts_at` strictly before this time |

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
and skips that booking's unsent reminder. No cancellation email is sent.

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
  "mentor_name": "maya",
  "topic": "System design",
  "starts_at": "2026-12-01T10:00:00Z",
  "ends_at": "2026-12-01T11:00:00Z",
  "status": "booked",
  "created_at": "2026-11-27T08:15:30.124000Z",
  "cancelled_at": null,
  "cancelled_by": null
}
```

Students see their own bookings, mentors see bookings on their slots, and admins
see all.

### GET /api/bookings/

Signed in. Paginated, ordered by `starts_at`, then ID.

| Parameter | Meaning |
|---|---|
| `status` | `booked` or `cancelled` |
| `slot` | slot ID; an ID with no visible bookings gives an empty list |
| `starts_after` | `starts_at` at or after this time |
| `starts_before` | `starts_at` strictly before this time |

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

`201 Created` with the booking object. A reminder is queued in the same
transaction.

| Status | Body |
|---|---|
| 400 | `{"slot": ["This field is required."]}` |
| 400 | `{"slot": ["A valid integer is required."]}` |
| 403 | caller is not a student |
| 404 | `{"detail": "Slot not found."}` |
| 409 | `{"detail": "This mentor is no longer available."}` |
| 409 | `{"detail": "This slot has been cancelled."}` |
| 409 | `{"detail": "This slot has already started."}` |
| 409 | `{"detail": "This slot is already booked."}` |
| 409 | `{"detail": "You already have a booking at this time."}` |

Back-to-back bookings are allowed.

Statuses: `201`, `400`, `401`, `403`, `404`, `409`.

### POST /api/bookings/{id}/cancel/

The booking's student, the slot's mentor, or an admin. No body. The slot becomes
bookable again and an unsent reminder is skipped.

`200 OK`

```json
{
  "id": 1,
  "slot": 1,
  "student": 3,
  "student_name": "ravi",
  "mentor_name": "maya",
  "topic": "System design",
  "starts_at": "2026-12-01T10:00:00Z",
  "ends_at": "2026-12-01T11:00:00Z",
  "status": "cancelled",
  "created_at": "2026-11-27T08:15:30.124000Z",
  "cancelled_at": "2026-11-27T09:00:00.512000Z",
  "cancelled_by": 3
}
```

| Status | Body |
|---|---|
| 404 | `{"detail": "Booking not found."}` (missing, or not yours) |
| 409 | `{"detail": "This booking is already cancelled."}` |
| 409 | `{"detail": "A session that has started cannot be cancelled."}` |
| 409 | `{"detail": "Students cannot cancel less than 2 hours before the session."}` |

Statuses: `200`, `401`, `404`, `409`.

## Health

### GET /health/

Anyone. Runs a query against the database.

| Status | Body |
|---|---|
| 200 | `{"status": "ok"}` |
| 503 | `{"status": "database unavailable"}` |
