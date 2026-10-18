#!/usr/bin/env bash
# Nightly PostgreSQL backup — dumps to /srv/serotix/backups, keeps 14 days.
# Reads DATABASE_URL from the app's own .env so credentials live in one place.
set -euo pipefail

APP_ENV=/srv/serotix/app/.env
BACKUP_DIR=/srv/serotix/backups
RETENTION_DAYS=14

mkdir -p "$BACKUP_DIR"

DATABASE_URL="$(grep -E '^DATABASE_URL=' "$APP_ENV" | cut -d= -f2-)"
if [ -z "$DATABASE_URL" ]; then
    echo "backup-db.sh: DATABASE_URL not found in $APP_ENV" >&2
    exit 1
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="$BACKUP_DIR/serotix-${TIMESTAMP}.sql.gz"

pg_dump "$DATABASE_URL" | gzip > "$OUT_FILE"

# Fail loudly on an empty/truncated dump rather than silently keeping a
# useless backup file — pg_dump piping through gzip can still exit 0 even if
# the connection dropped partway.
if [ ! -s "$OUT_FILE" ]; then
    echo "backup-db.sh: $OUT_FILE is empty — backup failed" >&2
    rm -f "$OUT_FILE"
    exit 1
fi

find "$BACKUP_DIR" -name 'serotix-*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete

echo "backup-db.sh: wrote $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"
