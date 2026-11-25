#!/bin/sh
# Prove a dump restores: load it into an empty scratch database and count rows.
# Usage: scripts/verify_backup.sh dump-file scratch-database-url
# The scratch database must be empty. Never point this at a database in use.
set -eu
dump="${1:?dump file}"
target="${2:?scratch database URL}"
tables=$(psql -XAtc "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'" "$target")
if [ "$tables" != "0" ]; then
    echo "Refusing: the scratch database is not empty." >&2
    exit 1
fi
pg_restore --exit-on-error --no-owner --dbname="$target" "$dump"
for table in accounts_user scheduling_slot scheduling_booking feedback_feedback django_migrations; do
    echo "$table $(psql -XAtc "SELECT count(*) FROM $table" "$target")"
done
