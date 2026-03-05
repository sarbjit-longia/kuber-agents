#!/usr/bin/env bash
# One-time Ubuntu server provisioning for Clover Charts
# Assumes PostgreSQL 17 + TimescaleDB are already installed natively.
# Run as root or with sudo on the target Ubuntu server:
#   sudo bash server-setup.sh
set -euo pipefail

# --- Load config (if available locally, otherwise use defaults) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/config.env" ]]; then
    source "$SCRIPT_DIR/config.env"
fi
DOMAIN="${DOMAIN:-clovercharts.com}"
REMOTE_DIR="${REMOTE_DIR:-/opt/clovercharts}"
SERVER_USER="${SERVER_USER:-sarbjit}"

# DB provisioning settings (override via environment if needed)
DB_ROLE="${DB_ROLE:-kuber}"
DB_PASSWORD="${DB_PASSWORD:-CHANGE_ME_STRONG_DB_PASSWORD}"
MAIN_DB="${MAIN_DB:-trading_platform}"
TSDB_DB="${TSDB_DB:-trading_data_plane}"
DOCKER_SUBNET="${DOCKER_SUBNET:-172.17.0.0/16}"

echo "=== Clover Charts Server Setup ==="
echo "Domain: $DOMAIN"
echo "Install dir: $REMOTE_DIR"
echo "Server user: $SERVER_USER"
echo ""

# --- Must be root ---
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)."
    exit 1
fi

# --- System updates ---
echo "[1/9] Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq

# --- Install essentials ---
echo "[2/9] Installing Docker, Nginx, Certbot, fail2ban..."
apt-get install -y -qq \
    ca-certificates curl gnupg lsb-release \
    nginx certbot python3-certbot-nginx \
    fail2ban ufw \
    jq htop

# Docker (official repo)
if ! command -v docker &>/dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    echo "Docker installed."
else
    echo "Docker already installed, skipping."
fi

# --- Ensure server user is in docker group ---
echo "[3/9] Ensuring '$SERVER_USER' is in docker group..."
if id "$SERVER_USER" &>/dev/null; then
    usermod -aG docker "$SERVER_USER"
    echo "User '$SERVER_USER' added to docker group (re-login required for effect)."
else
    echo "WARNING: User '$SERVER_USER' does not exist. Create the user first."
fi

# --- Directory structure ---
echo "[4/9] Creating directory structure..."
mkdir -p "$REMOTE_DIR"/{config/signal-generator,config/grafana/dashboards,config/grafana/datasources,backups,frontend}
chown -R "$SERVER_USER":"$SERVER_USER" "$REMOTE_DIR"

# --- Provision PostgreSQL databases (delegates to provision-db.sh) ---
echo "[5/9] Provisioning PostgreSQL databases..."
if [[ -f "$SCRIPT_DIR/provision-db.sh" ]]; then
    DB_ROLE="$DB_ROLE" DB_PASSWORD="$DB_PASSWORD" MAIN_DB="$MAIN_DB" TSDB_DB="$TSDB_DB" \
        DOCKER_SUBNET="$DOCKER_SUBNET" DEPLOY_USER="$SERVER_USER" REMOTE_DIR="$REMOTE_DIR" \
        bash "$SCRIPT_DIR/provision-db.sh"
else
    echo "WARNING: provision-db.sh not found. Run it separately:"
    echo "  sudo bash provision-db.sh"
fi
echo "[6/9] (handled by provision-db.sh)"

# --- Docker log rotation ---
echo "[7/9] Configuring Docker log rotation..."
cat > /etc/docker/daemon.json <<'DAEMON_JSON'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
DAEMON_JSON
systemctl restart docker

# --- UFW Firewall ---
echo "[8/9] Configuring firewall (UFW)..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
echo "UFW enabled: allowing 22, 80, 443 only."

# --- fail2ban ---
cat > /etc/fail2ban/jail.local <<'JAIL'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
JAIL
systemctl enable fail2ban
systemctl restart fail2ban

# --- Daily DB backup cron (handled by provision-db.sh) ---
echo "[9/9] Backup cron handled by provision-db.sh."

# --- Nginx: create ACME webroot ---
mkdir -p /var/www/certbot

# --- Nginx: install config with domain substitution ---
if [[ -f "$SCRIPT_DIR/nginx/clovercharts.conf" ]]; then
    echo "Installing Nginx config with domain=$DOMAIN..."
    sed "s/__DOMAIN__/$DOMAIN/g" "$SCRIPT_DIR/nginx/clovercharts.conf" > /etc/nginx/sites-available/clovercharts.conf
    ln -sf /etc/nginx/sites-available/clovercharts.conf /etc/nginx/sites-enabled/clovercharts.conf
    rm -f /etc/nginx/sites-enabled/default
    echo "Nginx config installed. Run certbot before enabling HTTPS:"
    echo "  sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN -d api.$DOMAIN -d grafana.$DOMAIN"
else
    echo "NOTE: Nginx config not found locally. Deploy it with deploy.sh first, then run:"
    echo "  sudo sed 's/__DOMAIN__/$DOMAIN/g' $REMOTE_DIR/nginx/clovercharts.conf > /etc/nginx/sites-available/clovercharts.conf"
fi

# --- Summary ---
echo ""
echo "=== MANUAL STEPS REMAINING ==="
echo ""
echo "1. Update the DB password in the backup script and .env.prod:"
echo "   Edit $BACKUP_SCRIPT and set the real password"
echo "   Copy .env.prod.template to $REMOTE_DIR/.env.prod and fill in secrets"
echo ""
echo "2. SSL certificates:"
echo "   sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN -d api.$DOMAIN -d grafana.$DOMAIN"
echo ""
echo "3. Re-login as '$SERVER_USER' for docker group to take effect:"
echo "   su - $SERVER_USER"
echo ""
echo "4. Configure router port forwarding (80, 443 -> this server)"
echo ""
echo "=== Setup complete! ==="
