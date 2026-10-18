#!/usr/bin/env bash
# Run this as root after provision.sh (first time) or on every subsequent
# deploy. Expects the repo already at /srv/serotix/app and a real .env in
# place there. App-level commands run as the unprivileged `serotix` user
# (matching serotix.service's User= directive); only the final restart
# needs root.
set -euo pipefail

APP_ROOT="/srv/serotix"
REPO_DIR="$APP_ROOT/app"
VENV_DIR="$APP_ROOT/venv"
APP_USER="serotix"

# Archives may retain workstation numeric owners and group-only read access.
# All application source/config must remain readable by the service account.
chown -R "$APP_USER:$APP_USER" "$REPO_DIR"

echo "==> Creating/updating virtualenv"
sudo -u "$APP_USER" python3 -m venv "$VENV_DIR" 2>/dev/null || true
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install -q -r "$REPO_DIR/requirements.lock"

echo "==> Django checks against production settings"
sudo -u "$APP_USER" env DJANGO_SETTINGS_MODULE=config.settings.prod \
    "$VENV_DIR/bin/python" "$REPO_DIR/manage.py" check --deploy

echo "==> Migrations"
sudo -u "$APP_USER" env DJANGO_SETTINGS_MODULE=config.settings.prod \
    "$VENV_DIR/bin/python" "$REPO_DIR/manage.py" migrate --noinput

echo "==> Collecting static files"
sudo -u "$APP_USER" env DJANGO_SETTINGS_MODULE=config.settings.prod \
    "$VENV_DIR/bin/python" "$REPO_DIR/manage.py" collectstatic --noinput

echo "==> Installing scheduled operations"
for job in retry-emails backup-full monitor; do
    install -m 644 "$REPO_DIR/deploy/serotix-$job.service" /etc/systemd/system/
    install -m 644 "$REPO_DIR/deploy/serotix-$job.timer" /etc/systemd/system/
done
systemctl daemon-reload
systemctl enable --now serotix-retry-emails.timer serotix-backup-full.timer serotix-monitor.timer

echo "==> Restarting application"
systemctl restart serotix
systemctl is-active --quiet serotix

echo "==> Done. Health check:"
for attempt in {1..15}; do
    if curl -sf --max-time 5 --unix-socket /run/serotix/gunicorn.sock \
        -H 'Host: serotix.co.ke' -H 'X-Forwarded-Proto: https' http://localhost/healthz/; then
        exit 0
    fi
    sleep 1
done
echo 'Readiness failed; inspect journalctl and execute the reviewed rollback plan.' >&2
exit 1
