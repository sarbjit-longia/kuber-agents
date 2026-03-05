#!/usr/bin/env bash
# One-time Ubuntu server provisioning for Kuber Trading
# Run as root or with sudo on the target Ubuntu server:
#   curl -sL <url>/server-setup.sh | sudo bash
# Or: sudo bash server-setup.sh
set -euo pipefail

# --- Load config (if available locally, otherwise use defaults) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/config.env" ]]; then
    source "$SCRIPT_DIR/config.env"
fi
DOMAIN="${DOMAIN:-kubertrading.com}"
REMOTE_DIR="${REMOTE_DIR:-/opt/kubertrading}"
SERVER_USER="${SERVER_USER:-kuber}"

echo "=== Kuber Trading Server Setup ==="
echo "Domain: $DOMAIN"
echo "Install dir: $REMOTE_DIR"
echo ""

# --- Must be root ---
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)."
    exit 1
fi

# --- System updates ---
echo "[1/8] Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq

# --- Install essentials ---
echo "[2/8] Installing Docker, Nginx, Certbot, fail2ban..."
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

# --- Create service user ---
echo "[3/8] Creating user '$SERVER_USER'..."
if ! id "$SERVER_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$SERVER_USER"
    usermod -aG docker "$SERVER_USER"
    echo "User '$SERVER_USER' created and added to docker group."
else
    usermod -aG docker "$SERVER_USER"
    echo "User '$SERVER_USER' already exists, ensured docker group membership."
fi

# --- Directory structure ---
echo "[4/8] Creating directory structure..."
mkdir -p "$REMOTE_DIR"/{config/signal-generator,config/grafana/dashboards,config/grafana/datasources,backups,frontend}
chown -R "$SERVER_USER":"$SERVER_USER" "$REMOTE_DIR"

# --- Docker log rotation ---
echo "[5/8] Configuring Docker log rotation..."
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
echo "[6/8] Configuring firewall (UFW)..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
echo "UFW enabled: allowing 22, 80, 443 only."

# --- fail2ban ---
echo "[7/8] Configuring fail2ban..."
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

# --- Daily DB backup cron ---
echo "[8/8] Setting up daily database backup cron..."
BACKUP_SCRIPT="$REMOTE_DIR/backup-databases.sh"
cat > "$BACKUP_SCRIPT" <<BACKUP
#!/usr/bin/env bash
# Daily database backup — called by cron
set -euo pipefail
BACKUP_DIR="$REMOTE_DIR/backups"
DATE=\$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=14

# PostgreSQL (main)
docker exec trading-postgres pg_dump -U "\$(docker exec trading-postgres printenv POSTGRES_USER)" "\$(docker exec trading-postgres printenv POSTGRES_DB)" | gzip > "\$BACKUP_DIR/postgres_\$DATE.sql.gz"

# TimescaleDB
docker exec trading-timescaledb pg_dump -U "\$(docker exec trading-timescaledb printenv POSTGRES_USER)" "\$(docker exec trading-timescaledb printenv POSTGRES_DB)" | gzip > "\$BACKUP_DIR/timescaledb_\$DATE.sql.gz"

# Prune old backups
find "\$BACKUP_DIR" -name "*.sql.gz" -mtime +\$RETENTION_DAYS -delete

echo "[\$DATE] Backup complete. Retained last \$RETENTION_DAYS days."
BACKUP

chmod +x "$BACKUP_SCRIPT"
chown "$SERVER_USER":"$SERVER_USER" "$BACKUP_SCRIPT"

# Add cron job (runs daily at 3:00 AM)
CRON_LINE="0 3 * * * $BACKUP_SCRIPT >> $REMOTE_DIR/backups/backup.log 2>&1"
(crontab -u "$SERVER_USER" -l 2>/dev/null | grep -v "$BACKUP_SCRIPT"; echo "$CRON_LINE") | crontab -u "$SERVER_USER" -

# --- Nginx: create ACME webroot ---
mkdir -p /var/www/certbot

# --- Nginx: install config with domain substitution ---
if [[ -f "$SCRIPT_DIR/nginx/kubertrading.conf" ]]; then
    echo "Installing Nginx config with domain=$DOMAIN..."
    sed "s/__DOMAIN__/$DOMAIN/g" "$SCRIPT_DIR/nginx/kubertrading.conf" > /etc/nginx/sites-available/kubertrading.conf
    ln -sf /etc/nginx/sites-available/kubertrading.conf /etc/nginx/sites-enabled/kubertrading.conf
    rm -f /etc/nginx/sites-enabled/default
    echo "Nginx config installed. Run certbot before enabling HTTPS:"
    echo "  sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN -d api.$DOMAIN -d grafana.$DOMAIN"
else
    echo "NOTE: Nginx config not found locally. Deploy it with deploy.sh first, then run:"
    echo "  sudo sed 's/__DOMAIN__/$DOMAIN/g' $REMOTE_DIR/nginx/kubertrading.conf > /etc/nginx/sites-available/kubertrading.conf"
fi

# --- No-IP DUC (Dynamic DNS) ---
echo ""
echo "=== MANUAL STEPS REMAINING ==="
echo ""
echo "1. Install No-IP DUC (Dynamic DNS):"
echo "   cd /usr/local/src && wget https://dmej8g5cpdyqd.cloudfront.net/downloads/noip-duc_3.3.0.tar.gz"
echo "   tar xzf noip-duc_3.3.0.tar.gz && cd noip-duc_3.3.0 && sudo apt install -y make gcc"
echo "   make && sudo make install"
echo "   noip-duc --username YOUR_EMAIL --password YOUR_PASS -g $DOMAIN,api.$DOMAIN,grafana.$DOMAIN,www.$DOMAIN --check-interval 5m -d"
echo "   (Or set up as systemd service — see README.md)"
echo ""
echo "2. SSL certificates:"
echo "   sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN -d api.$DOMAIN -d grafana.$DOMAIN"
echo ""
echo "3. Copy .env.prod to server:"
echo "   scp .env.prod $SERVER_USER@<server-ip>:$REMOTE_DIR/.env.prod"
echo "   ssh $SERVER_USER@<server-ip> 'chmod 600 $REMOTE_DIR/.env.prod'"
echo ""
echo "4. Configure router port forwarding (80, 443 → this server)"
echo ""
echo "=== Setup complete! ==="
