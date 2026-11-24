# Contributing

Bug reports, fixes and focused improvements are welcome. For a larger change,
open an issue first so the approach can be agreed before you write it.

Report security problems privately, as described in [SECURITY.md](SECURITY.md).

## Set up

Follow the [quickstart](README.md#quickstart). PostgreSQL is required: the schema
depends on exclusion constraints and the worker on `SKIP LOCKED`, so other
databases do not work.

## Check your change

With `DJANGO_DEBUG` and `DATABASE_URL` exported:

```bash
python manage.py makemigrations --check --dry-run
python manage.py test tests
```

The [test workflow](.github/workflows/test.yml) runs these and also checks
production settings, migrations, restores and the container. The
database user needs permission to create the test database and the `btree_gist`
extension.

## Guidelines

- **State changes to slots, bookings, roles and account status go in
  `scheduling/services.py`.** Views authenticate, validate and serialise.
- **Queue email through `notifications/outbox.py`** inside the transaction that
  makes the change. Never store a link secret.
- **Keep the lock order:** user row, then slot row, then booking row. Take two
  user rows in primary-key order.
- **Back a scheduling rule with a database constraint** where PostgreSQL can
  express it. If a new constraint can be violated by a normal request, add its
  message and code to `CONSTRAINT_ERRORS` so the API returns `409`.
- **Test behaviour, including refusals.** Cover who may not do something as well
  as who may.
- **Race-sensitive changes need a concurrency test** in
  `tests/test_concurrency.py`. Check that it can fail by removing the protection
  it covers. Timing-dependent failures may take several runs to appear.
- **Do not log** request bodies, query strings, tokens or email addresses from
  application code.
- **Include migrations** for model changes.
- **Update the docs** when behaviour changes: [README.md](README.md),
  [docs/API.md](docs/API.md) and
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Claim only what is verified.** Do not describe something as deployed or
  measured unless it has been.

## Pull requests

Keep each pull request to one coherent change, explain why it is needed and fill
in the template. Contributions are licensed under the [MIT licence](LICENSE).
