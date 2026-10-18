#!/usr/bin/env bash
# One-time server provisioning for SeroTix — Arch Linux variant (the box we
# actually landed on; deploy/provision.sh remains the Debian/Ubuntu version
# in case of a future migration). Run as root on a fresh Arch install.
#
# What this does NOT do: put real secrets in place (that's
# /srv/serotix/app/.env, created by hand on the server, never committed) or
# issue the SSL cert (run `certbot --nginx -d serotix.space -d www.serotix.space`
# yourself once DNS resolves — it needs to prompt for an email/agreement
# interactively).
set -euo pipefail

DOMAIN="serotix.space"
APP_USER="serotix"
APP_ROOT="/srv/serotix"
REPO_DIR="$APP_ROOT/app"
DB_NAME="serotix"
DB_USER="serotix"

echo "==> Refreshing keyring and updating system"
pacman -Sy --noconfirm archlinux-keyring
pacman-key --populate archlinux
pacman -Syu --noconfirm

echo "==> Installing system packages"
pacman -S --needed --noconfirm \
    python python-pip python-virtualenv \
    postgresql \
    nginx \
    git \
    certbot certbot-nginx \
    ufw \
    base-devel

echo "==> Creating app user and directories"
id -u "$APP_USER" &>/dev/null || useradd --system --create-home --shell /bin/bash "$APP_USER"
mkdir -p "$APP_ROOT" /var/log/serotix
chown -R "$APP_USER:$APP_USER" "$APP_ROOT" /var/log/serotix

echo "==> Initializing PostgreSQL (first run only)"
if [ ! -d /var/lib/postgres/data/base ]; then
    sudo -u postgres initdb -D /var/lib/postgres/data
fi
systemctl enable --now postgresql

echo "==> Configuring PostgreSQL role/database"
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

echo "==> Firewall (ufw) — SSH (22 + 2222 fallback for networks that block 22), HTTP, HTTPS"
ufw allow 22/tcp
ufw allow 2222/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Nginx site config"
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
if ! grep -q "sites-enabled" /etc/nginx/nginx.conf; then
    sed -i '/http {/a\    include /etc/nginx/sites-enabled/*;' /etc/nginx/nginx.conf
fi
cp "$REPO_DIR/deploy/nginx.conf" "/etc/nginx/sites-available/$DOMAIN"
ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo "==> systemd service"
cp "$REPO_DIR/deploy/serotix.service" /etc/systemd/system/serotix.service
systemctl daemon-reload
systemctl enable serotix

echo ""
echo "==> Provisioning done. Remaining manual steps:"
echo "    1. Create $REPO_DIR/.env with real production secrets (see .env.example),"
echo "       including the DATABASE_URL printed above."
echo "    2. Run deploy/release.sh to install deps, migrate, collectstatic, and start the app."
echo "    3. Once DNS for $DOMAIN resolves to this server: certbot --nginx -d $DOMAIN -d www.$DOMAIN"
