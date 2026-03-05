#!/usr/bin/env bash
# Install and configure Nginx reverse proxy for Kuber Trading
# Run on the server with sudo:
#   sudo bash setup-nginx.sh              # LAN-only (HTTP)
#   sudo bash setup-nginx.sh --ssl        # LAN + Internet (HTTP + HTTPS via Let's Encrypt)
set -euo pipefail

# --- Load config ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/config.env" ]]; then
    source "$SCRIPT_DIR/config.env"
fi
DOMAIN="${DOMAIN:-kubertrading.com}"
REMOTE_DIR="${REMOTE_DIR:-/opt/kubertrading}"

# --- Parse flags ---
SETUP_SSL=false
for arg in "$@"; do
    case $arg in
        --ssl) SETUP_SSL=true ;;
        --help|-h)
            echo "Usage: sudo bash setup-nginx.sh [--ssl]"
            echo ""
            echo "  --ssl    Also obtain Let's Encrypt SSL certificates and enable HTTPS"
            echo "           Requires: domain DNS pointed at this server, ports 80/443 reachable"
            echo ""
            echo "Without --ssl: sets up HTTP-only reverse proxy (LAN access via IP)"
            exit 0
            ;;
    esac
done

# --- Must be root ---
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: Run with sudo." >&2
    exit 1
fi

echo "=== Kuber Trading — Nginx Setup ==="
echo "Domain: $DOMAIN"
echo "SSL:    $SETUP_SSL"
echo ""

# --- 1. Install Nginx ---
echo "[1/4] Installing Nginx..."
if ! command -v nginx &>/dev/null; then
    apt-get update -qq
    apt-get install -y -qq nginx
    systemctl enable nginx
    systemctl start nginx
    echo "  Nginx installed."
else
    echo "  Nginx already installed."
fi

# Install certbot if SSL requested
if [[ "$SETUP_SSL" == "true" ]]; then
    if ! command -v certbot &>/dev/null; then
        apt-get install -y -qq certbot python3-certbot-nginx
        echo "  Certbot installed."
    fi
fi

# --- 2. Write HTTP-only config (works immediately for LAN) ---
echo "[2/4] Writing Nginx config..."

mkdir -p /var/www/certbot

cat > /etc/nginx/sites-available/kubertrading.conf <<'NGINX_HTTP'
# Kuber Trading — Nginx Reverse Proxy
# HTTP config for LAN access. Certbot will modify this for HTTPS.

# Rate limiting
limit_req_zone $binary_remote_addr zone=api:10m rate=20r/s;

# --- Main site + API + Grafana (HTTP) ---
server {
    listen 80;
    listen [::]:80;
    server_name __DOMAIN__ www.__DOMAIN__ api.__DOMAIN__ grafana.__DOMAIN__ _;

    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Frontend (proxied to Docker container)
    location / {
        proxy_pass http://127.0.0.1:4200;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API proxy
    location /api/ {
        limit_req zone=api burst=40 nodelay;

        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
        client_max_body_size 10M;
    }

    # Health endpoint (no rate limit)
    location = /health {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # Swagger docs
    location /docs {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    location /redoc {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # WebSocket for execution streaming
    location /api/v1/ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # Grafana (serves from subpath, expects /grafana/ prefix)
    location /grafana/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Internal services (Flower, Signals, Data Plane, Prometheus) stay on
    # localhost only — access via SSH tunnel or directly on the server.
}
NGINX_HTTP

# Substitute domain and paths
sed -i "s|__DOMAIN__|$DOMAIN|g" /etc/nginx/sites-available/kubertrading.conf
sed -i "s|__REMOTE_DIR__|$REMOTE_DIR|g" /etc/nginx/sites-available/kubertrading.conf

# Enable site, disable default
ln -sf /etc/nginx/sites-available/kubertrading.conf /etc/nginx/sites-enabled/kubertrading.conf
rm -f /etc/nginx/sites-enabled/default

# --- 3. Test and reload ---
echo "[3/4] Testing Nginx config..."
nginx -t
if systemctl is-active --quiet nginx; then
    systemctl reload nginx
    echo "  Nginx reloaded."
else
    systemctl start nginx
    echo "  Nginx started."
fi

# --- 4. SSL (optional) ---
if [[ "$SETUP_SSL" == "true" ]]; then
    echo "[4/4] Obtaining SSL certificates via Let's Encrypt..."
    certbot --nginx \
        -d "$DOMAIN" \
        -d "www.$DOMAIN" \
        -d "api.$DOMAIN" \
        -d "grafana.$DOMAIN" \
        --non-interactive \
        --agree-tos \
        --email "admin@$DOMAIN" \
        --redirect

    echo "  SSL certificates obtained. Certbot auto-renewal is active."
    echo "  Verify: sudo certbot renew --dry-run"
else
    echo "[4/4] Skipping SSL (use --ssl to enable)."
fi

# --- Summary ---
LAN_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=== Nginx Setup Complete ==="
echo ""
echo "LAN access (from your dev Mac):"
echo "  Frontend:     http://$LAN_IP"
echo "  API Docs:     http://$LAN_IP/docs"
echo "  API:          http://$LAN_IP/api/v1/"
echo "  Health:       http://$LAN_IP/health"
echo "  Grafana:      http://$LAN_IP/grafana/"
echo ""
echo "Internal services (localhost only, use SSH tunnel from dev Mac):"
echo "  Flower:       http://127.0.0.1:5555"
echo "  Signals:      http://127.0.0.1:8007"
echo "  Data Plane:   http://127.0.0.1:8005"
echo "  Prometheus:   http://127.0.0.1:9090"
echo ""
if [[ "$SETUP_SSL" == "true" ]]; then
    echo "Internet access (after DNS + port forwarding):"
    echo "  Frontend:     https://$DOMAIN"
    echo "  API:          https://api.$DOMAIN"
    echo "  Grafana:      https://grafana.$DOMAIN"
fi
echo ""
echo "To add SSL later:  sudo bash $0 --ssl"
