## What and why

<!-- What changes, and the problem it solves. Link the issue if there is one. -->

## How it was verified

<!-- Commands run and their results. -->

## Checklist

- [ ] `python manage.py test tests` passes against PostgreSQL
- [ ] `python manage.py makemigrations --check --dry-run` reports no changes
- [ ] New or changed behaviour has tests, including refused requests
- [ ] State changes go through `scheduling/services.py` and keep the user, slot, booking lock order
- [ ] README, `docs/API.md` and `docs/ARCHITECTURE.md` are updated if behaviour changed
- [ ] No secrets, tokens or personal data are added to code, logs or fixtures
