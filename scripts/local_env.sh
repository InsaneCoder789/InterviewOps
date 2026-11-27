#!/bin/sh
# Write random values for the local Compose stack to .env, which Git ignores.
set -eu
cd "$(dirname "$0")/.."
if [ -e .env ]; then
    echo ".env already exists; leaving it unchanged." >&2
    exit 0
fi
umask 077
random() { python3 -c 'import secrets; print(secrets.token_hex(32))'; }
printf 'POSTGRES_PASSWORD=%s\nDJANGO_SECRET_KEY=%s\n' "$(random)" "$(random)" > .env
echo "Wrote .env"
