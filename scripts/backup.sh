#!/bin/sh
# Dump the database in PostgreSQL's custom format.
# Usage: DATABASE_URL=... scripts/backup.sh [output-file]
set -eu
: "${DATABASE_URL:?set DATABASE_URL}"
out="${1:-interviewops-$(date -u +%Y%m%dT%H%M%SZ).dump}"
umask 077 # the dump holds personal data
pg_dump --format=custom --no-owner --file="$out" "$DATABASE_URL"
echo "$out"
