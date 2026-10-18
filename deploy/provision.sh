#!/usr/bin/env bash
# One-time server provisioning for SeroTix. Run as root on a fresh Debian/Ubuntu
# box. Idempotent-ish (safe to re-run), but designed for first-time setup.
#
# What this does NOT do: put real secrets in place (that's deploy/.env.production,
# created by hand on the server, never committed) or issue the SSL cert (run
# `certbot --nginx -d serotix.space -d www.serotix.space` yourself once DNS
# resolves — it needs to prompt for an email/agreement interactively).
set -euo pipefail

DOMAIN="serotix.space"
APP_USER="serotix"
APP_ROOT="/srv/serotix"
REPO_DIR="$APP_ROOT/app"
VENV_DIR="$APP_ROOT/venv"
DB_NAME="serotix"
DB_USER="serotix"

echo "==> Installing system packages"
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip \
    postgresql postgresql-contrib \
    nginx tesseract-ocr tesseract-ocr-eng \
    git \
    certbot python3-certbot-nginx \
    ufw

echo "==> Creating app user and directories"
id -u "$APP_USER" &>/dev/null || useradd --system --create-home --shell /bin/bash "$APP_USER"
mkdir -p "$APP_ROOT" /var/log/serotix
chown -R "$APP_USER:$APP_USER" "$APP_ROOT" /var/log/serotix

echo "==> Configuring PostgreSQL"
# hex, not base64 — base64's '/' and '+' characters break naive DATABASE_URL
# parsing (urlparse treats '/' as a path separator), so keep this URL-safe.
DB_PASS="$(openssl rand -hex 24)"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASS';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
echo "    DATABASE_URL=postgres://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"
echo "    ^ save this now — the password is only shown once. Put it in $REPO_DIR/.env"
echo "    If lost: sudo -u postgres psql -c \"ALTER ROLE $DB_USER WITH PASSWORD 'new-password';\""

echo "==> Firewall (ufw) — SSH, HTTP, HTTPS only"
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

echo "==> Nginx site config"
cp "$REPO_DIR/deploy/nginx.conf" "/etc/nginx/sites-available/$DOMAIN"
ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "==> systemd service"
cp "$REPO_DIR/deploy/serotix.service" /etc/systemd/system/serotix.service
systemctl daemon-reload
systemctl enable serotix

echo ""
echo "==> Provisioning done. Remaining manual steps:"
echo "    1. Create $REPO_DIR/.env with real production secrets (see .env.example)."
echo "    2. Run deploy/release.sh to install deps, migrate, collectstatic, and start the app."
echo "    3. Once DNS for $DOMAIN resolves to this server: certbot --nginx -d $DOMAIN -d www.$DOMAIN"
