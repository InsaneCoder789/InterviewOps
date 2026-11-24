# Operations

Nothing is deployed. These steps have been checked locally only where stated.

## Run locally

With Docker:

```bash
docker compose up --build
```

```bash
docker compose exec api python manage.py seed_demo
```

Without Docker, follow the quickstart in the README, set
`CORS_ALLOWED_ORIGINS=http://localhost:5173`, and run
`python manage.py send_notifications` in a second terminal. In debug mode, emails
(including invitation and reset links) are printed by the worker.

## CI

`.github/workflows/test.yml` runs on pushes to `main` and on pull requests:
missing-migration check, tests, production settings check, migration reversal,
backup and restore, then an image build with a sign-in smoke test.

## Deploy

1. Create the services from `render.yaml`. Check current plans and prices first;
   the worker is a paid service type.
2. Set `CORS_ALLOWED_ORIGINS`, `APP_BASE_URL` and the SMTP variables. Set the
   worker's variables too.
3. Create the first admin: `python manage.py createsuperuser`.
4. In GitHub, create an environment named `production` with required reviewers, add
   the secrets `RENDER_API_DEPLOY_HOOK` and `RENDER_WORKER_DEPLOY_HOOK` and the
   variable `API_URL`.
5. Run the **deploy** workflow. It checks that the tests passed for the commit,
   triggers both services and checks `/health/`. Confirm the new release in the
   Render dashboard.

The API runs migrations when it starts. A release whose migration is not
compatible with the running worker needs the worker stopped first. The upgrade
from the old reminder table is one such release.

## Monitor

- `GET /health/`: the web process can reach the database.
- `python manage.py check_queue`: fails if mail is overdue by 10 minutes or any
  message has failed. Run it on a schedule and alert on a non-zero exit.
- `GET /api/admin/overview/`: queue state and sessions needing attention.
- Logs carry a request ID, also returned as `X-Request-ID`.

No error tracker, metrics service or alerting is configured.

## Back up and restore

```bash
DATABASE_URL=... scripts/backup.sh
```

```bash
scripts/verify_backup.sh FILE.dump postgresql://USER@HOST:PORT/EMPTY_SCRATCH_DB
```

Dumps contain personal data: store them encrypted, restrict access and delete old
ones. Scheduled backups depend on the hosting plan; a free database may have
none. Restore into a new database, check it, then point the services at it.

`pg_dump` must be at least the server's major version.
