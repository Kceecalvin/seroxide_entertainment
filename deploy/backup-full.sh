#!/usr/bin/env bash
# Run as serotix. Keep this private: dumps/media can contain customer information.
set -euo pipefail
umask 077
cd /srv/serotix/app
destination=/srv/serotix/backups
mkdir -p "$destination"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
sql="$destination/full-$stamp.sql.gz"
# Read credentials inside Python; don't expose the database URL in process argv.
/srv/serotix/venv/bin/python - <<'PY' | gzip > "$sql"
import os, subprocess
from dotenv import dotenv_values
from urllib.parse import urlparse, unquote
db=urlparse(dotenv_values('.env')['DATABASE_URL'])
env=os.environ.copy()
env.update(PGHOST=db.hostname or 'localhost', PGPORT=str(db.port or 5432),
           PGUSER=unquote(db.username or ''), PGPASSWORD=unquote(db.password or ''),
           PGDATABASE=db.path.lstrip('/'))
subprocess.run(['pg_dump','--no-owner','--no-acl'],env=env,check=True)
PY
gzip -t "$sql"
tar -czf "$destination/media-$stamp.tar.gz" media
tar -tzf "$destination/media-$stamp.tar.gz" >/dev/null
sha256sum "$sql" "$destination/media-$stamp.tar.gz" > "$destination/full-$stamp.sha256"
find "$destination" -maxdepth 1 -type f \( -name 'full-*.sql.gz' -o -name 'media-*.tar.gz' -o -name 'full-*.sha256' \) -mtime +14 -delete
echo "Database and media backup completed: $stamp"
