#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AlohaAI Emergency Watchtower — Ubuntu VPS Deployment Script
# Run once on a fresh Ubuntu 22.04 / 24.04 server.
# Usage: chmod +x deploy.sh && sudo ./deploy.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

DOMAIN="kaipoi.site"          # ← CHANGE THIS
APP_DIR="/var/www/watchtower"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"  # directory this script lives in

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AlohaAI Emergency Watchtower — Deploying"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. System packages ────────────────────────────────────────────────────────
echo "[1/7] Installing system packages…"
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# ── 2. Copy app files ─────────────────────────────────────────────────────────
echo "[2/7] Copying app files to $APP_DIR…"
mkdir -p "$APP_DIR"
cp -r "$REPO_DIR/backend"     "$APP_DIR/"
cp -r "$REPO_DIR/frontend"    "$APP_DIR/"
cp    "$REPO_DIR/requirements.txt" "$APP_DIR/"

# ── 3. Python virtualenv + deps ───────────────────────────────────────────────
echo "[3/7] Setting up Python virtualenv…"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# ── 4. Environment file ───────────────────────────────────────────────────────
echo "[4/7] Environment file…"
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$REPO_DIR/.env.example" "$APP_DIR/.env"
    echo ""
    echo "  ⚠️  IMPORTANT: Edit $APP_DIR/.env and add your API keys!"
    echo "      nano $APP_DIR/.env"
    echo ""
fi

# ── 5. Set permissions ────────────────────────────────────────────────────────
echo "[5/7] Setting file permissions…"
chown -R www-data:www-data "$APP_DIR"
chmod 640 "$APP_DIR/.env"
mkdir -p "$APP_DIR/watchtower_reports"
chown www-data:www-data "$APP_DIR/watchtower_reports"

# ── 6. Systemd service ────────────────────────────────────────────────────────
echo "[6/7] Installing systemd service…"
# Update paths in service file
sed "s|/var/www/watchtower|$APP_DIR|g" "$REPO_DIR/watchtower.service" \
    > /etc/systemd/system/watchtower.service

systemctl daemon-reload
systemctl enable watchtower
systemctl restart watchtower
sleep 2
systemctl is-active watchtower && echo "  ✅ Service running" || echo "  ❌ Service failed — check: journalctl -u watchtower"

# ── 7. Nginx ──────────────────────────────────────────────────────────────────
echo "[7/7] Configuring Nginx…"
sed "s/yourdomain.com/$DOMAIN/g" "$REPO_DIR/nginx.conf" \
    > /etc/nginx/sites-available/watchtower

ln -sf /etc/nginx/sites-available/watchtower /etc/nginx/sites-enabled/watchtower
rm -f /etc/nginx/sites-enabled/default  # remove default page

nginx -t && systemctl reload nginx && echo "  ✅ Nginx reloaded"

# ── SSL ───────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Deployment complete!"
echo ""
echo "  Next steps:"
echo "  1. Edit your .env file:  nano $APP_DIR/.env"
echo "  2. Restart the service:  sudo systemctl restart watchtower"
echo "  3. Get SSL certificate:  sudo certbot --nginx -d $DOMAIN"
echo ""
echo "  Useful commands:"
echo "  View logs:    sudo journalctl -u watchtower -f"
echo "  Restart app:  sudo systemctl restart watchtower"
echo "  Nginx logs:   sudo tail -f /var/log/nginx/error.log"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
