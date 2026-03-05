#!/usr/bin/env bash
# Provision PostgreSQL databases for Kuber Trading on a host with native PG + TimescaleDB.
# Run once on the server:
#   sudo bash provision-db.sh
# Or with a custom password:
#   sudo DB_PASSWORD=mysecretpw bash provision-db.sh
set -euo pipefail

# --- Configuration (override via environment) ---
DB_ROLE="${DB_ROLE:-kuber}"
DB_PASSWORD="${DB_PASSWORD:-CHANGE_ME_STRONG_DB_PASSWORD}"
MAIN_DB="${MAIN_DB:-trading_platform}"
TSDB_DB="${TSDB_DB:-trading_data_plane}"
DOCKER_SUBNET="${DOCKER_SUBNET:-172.17.0.0/16}"
DEPLOY_USER="${DEPLOY_USER:-sarbjit}"
REMOTE_DIR="${REMOTE_DIR:-/opt/kubertrading}"

echo "=== Kuber Trading — Database Provisioning ==="
echo "Role:     $DB_ROLE"
echo "Main DB:  $MAIN_DB"
echo "TSDB DB:  $TSDB_DB"
echo "Docker:   $DOCKER_SUBNET"
echo ""

# --- Must be root ---
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: Run with sudo." >&2
    exit 1
fi

# --- Verify PostgreSQL is running ---
if ! systemctl is-active --quiet postgresql; then
    echo "ERROR: PostgreSQL is not running." >&2
    exit 1
fi
echo "[OK] PostgreSQL is active."

# --- 1. Create role ---
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_ROLE'" | grep -q 1; then
    echo "[SKIP] Role '$DB_ROLE' already exists."
    # Update password in case it changed
    sudo -u postgres psql -c "ALTER ROLE $DB_ROLE WITH PASSWORD '$DB_PASSWORD';" >/dev/null
    echo "  Password updated."
else
    sudo -u postgres psql -c "CREATE ROLE $DB_ROLE WITH LOGIN PASSWORD '$DB_PASSWORD';"
    echo "[OK] Role '$DB_ROLE' created."
fi

# --- 2. Create main database ---
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$MAIN_DB'" | grep -q 1; then
    echo "[SKIP] Database '$MAIN_DB' already exists."
else
    sudo -u postgres psql -c "CREATE DATABASE $MAIN_DB OWNER $DB_ROLE;"
    echo "[OK] Database '$MAIN_DB' created."
fi
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $MAIN_DB TO $DB_ROLE;" >/dev/null

# --- 3. Create TimescaleDB database ---
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$TSDB_DB'" | grep -q 1; then
    echo "[SKIP] Database '$TSDB_DB' already exists."
else
    sudo -u postgres psql -c "CREATE DATABASE $TSDB_DB OWNER $DB_ROLE;"
    echo "[OK] Database '$TSDB_DB' created."
fi
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $TSDB_DB TO $DB_ROLE;" >/dev/null

# --- 4. Enable TimescaleDB extension ---
sudo -u postgres psql -d "$TSDB_DB" -c "CREATE EXTENSION IF NOT EXISTS timescaledb;" 2>/dev/null || {
    echo "WARNING: Could not enable TimescaleDB extension. Is the package installed?"
}
TSDB_VER=$(sudo -u postgres psql -d "$TSDB_DB" -tAc "SELECT extversion FROM pg_extension WHERE extname='timescaledb'" 2>/dev/null || echo "not found")
echo "[OK] TimescaleDB extension: $TSDB_VER"

# --- 5. Configure pg_hba.conf for Docker subnet ---
PG_HBA=$(sudo -u postgres psql -tAc "SHOW hba_file")
if grep -q "$DOCKER_SUBNET" "$PG_HBA" 2>/dev/null; then
    echo "[SKIP] Docker subnet already in pg_hba.conf."
else
    echo "" >> "$PG_HBA"
    echo "# Allow Docker containers to connect (added by provision-db.sh)" >> "$PG_HBA"
    echo "host    all    $DB_ROLE    $DOCKER_SUBNET    md5" >> "$PG_HBA"
    systemctl reload postgresql
    echo "[OK] Added Docker subnet to pg_hba.conf and reloaded PG."
fi

# --- 6. Add deploy user to docker group ---
if id "$DEPLOY_USER" &>/dev/null; then
    if groups "$DEPLOY_USER" | grep -q '\bdocker\b'; then
        echo "[SKIP] '$DEPLOY_USER' already in docker group."
    else
        usermod -aG docker "$DEPLOY_USER"
        echo "[OK] Added '$DEPLOY_USER' to docker group (re-login required)."
    fi
fi

# --- 7. Create deployment directory ---
mkdir -p "$REMOTE_DIR"/{config/signal-generator,config/grafana/dashboards,config/grafana/datasources,backups,frontend}
chown -R "$DEPLOY_USER":"$DEPLOY_USER" "$REMOTE_DIR"
echo "[OK] Directory $REMOTE_DIR ready."

# --- 8. Install backup cron ---
BACKUP_SCRIPT="$REMOTE_DIR/backup-databases.sh"
cat > "$BACKUP_SCRIPT" <<BACKUP
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$REMOTE_DIR/backups"
DATE=\$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=14
PGPASSWORD="$DB_PASSWORD" pg_dump -U "$DB_ROLE" -h localhost "$MAIN_DB" | gzip > "\$BACKUP_DIR/postgres_\$DATE.sql.gz"
PGPASSWORD="$DB_PASSWORD" pg_dump -U "$DB_ROLE" -h localhost "$TSDB_DB" | gzip > "\$BACKUP_DIR/timescaledb_\$DATE.sql.gz"
find "\$BACKUP_DIR" -name "*.sql.gz" -mtime +\$RETENTION_DAYS -delete
echo "[\$DATE] Backup complete."
BACKUP
chmod +x "$BACKUP_SCRIPT"
chown "$DEPLOY_USER":"$DEPLOY_USER" "$BACKUP_SCRIPT"

CRON_LINE="0 3 * * * $BACKUP_SCRIPT >> $REMOTE_DIR/backups/backup.log 2>&1"
(crontab -u "$DEPLOY_USER" -l 2>/dev/null | grep -v "$BACKUP_SCRIPT"; echo "$CRON_LINE") | crontab -u "$DEPLOY_USER" -
echo "[OK] Backup cron installed (daily 3AM)."

# --- 9. Verify connectivity ---
echo ""
echo "=== Verification ==="
PGPASSWORD="$DB_PASSWORD" psql -U "$DB_ROLE" -h localhost -d "$MAIN_DB" -c "SELECT 'trading_platform OK' AS status;" 2>&1 | grep -q "OK" \
    && echo "[OK] Can connect to $MAIN_DB" \
    || echo "[FAIL] Cannot connect to $MAIN_DB — check password/pg_hba"

PGPASSWORD="$DB_PASSWORD" psql -U "$DB_ROLE" -h localhost -d "$TSDB_DB" -c "SELECT 'trading_data_plane OK' AS status;" 2>&1 | grep -q "OK" \
    && echo "[OK] Can connect to $TSDB_DB" \
    || echo "[FAIL] Cannot connect to $TSDB_DB — check password/pg_hba"

echo ""
echo "=== Done! Next steps ==="
echo "1. Log out and back in (for docker group to take effect)"
echo "2. Copy .env.prod to $REMOTE_DIR/.env.prod and fill in secrets"
echo "3. Run deploy.sh from your dev machine"
