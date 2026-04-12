# Self-Hosted Deployment Guide

Deploy Clover Charts to a personal Ubuntu server with Nginx reverse proxy, Let's Encrypt SSL, and No-IP dynamic DNS.

## Server Requirements

- Ubuntu 22.04+ LTS
- 8GB+ RAM (16GB recommended)
- 4-core CPU
- 100GB SSD
- Public IP (static or dynamic with No-IP DUC)
- **PostgreSQL 17+ with TimescaleDB** installed natively on the host

## Architecture

```
Internet → Router (ports 80,443) → Ubuntu Server
  → Nginx (host, SSL termination)
    → clovercharts.com        → /opt/clovercharts/frontend/ (static)
    → api.clovercharts.com    → 127.0.0.1:8000 (Docker: backend)
    → grafana.clovercharts.com → 127.0.0.1:3000 (Docker: grafana)
  → PostgreSQL + TimescaleDB (host-native, port 5432)
  → Docker Compose (12 containers, all ports on 127.0.0.1)
    → Containers connect to host DB via host.docker.internal:5432
```

## Initial Setup

### 1. Configure SSH access

Add to `~/.ssh/config` on your Mac:

```
Host quantum
    HostName 192.168.1.188
    User sarbjit
    IdentityFile ~/.ssh/id_ed25519
```

### 2. Update config.env

Edit `deploy/local/config.env` with your domain and server details:

```bash
DOMAIN=clovercharts.com
SERVER_HOST=quantum
SERVER_USER=sarbjit
REMOTE_DIR=/opt/clovercharts
```

### 3. Run server setup (once)

Copy the `deploy/local/` directory to the server and run:

```bash
scp -r deploy/local/ quantum:/tmp/clovercharts-setup/
ssh quantum 'sudo bash /tmp/clovercharts-setup/server-setup.sh'
```

This installs Docker, Nginx, Certbot, fail2ban, UFW, provisions the PostgreSQL databases (`trading_platform` and `trading_data_plane`), enables TimescaleDB, configures `pg_hba.conf` for Docker access, and sets up native backup cron.

### 4. DNS configuration

**Option A: No-IP (Dynamic IP)**

1. Create a free account at [noip.com](https://www.noip.com)
2. Create hostnames: `clovercharts.com`, `api.clovercharts.com`, `grafana.clovercharts.com`, `www.clovercharts.com`
3. Install No-IP DUC on the server:

```bash
cd /usr/local/src
wget https://dmej8g5cpdyqd.cloudfront.net/downloads/noip-duc_3.3.0.tar.gz
tar xzf noip-duc_3.3.0.tar.gz && cd noip-duc_3.3.0
sudo apt install -y make gcc && make && sudo make install
```

4. Run as systemd service:

```bash
sudo tee /etc/systemd/system/noip-duc.service <<EOF
[Unit]
Description=No-IP Dynamic DNS Update Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/noip-duc --username YOUR_EMAIL --password YOUR_PASS -g clovercharts.com,api.clovercharts.com,grafana.clovercharts.com,www.clovercharts.com --check-interval 5m
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now noip-duc
```

**Option B: Static IP** — Point A records directly in your DNS provider.

### 5. Router port forwarding

Forward these ports to the Ubuntu server's LAN IP:

| External Port | Internal Port | Protocol |
|---------------|---------------|----------|
| 80 | 80 | TCP |
| 443 | 443 | TCP |

### 6. Create .env.prod on server

```bash
# Copy template and fill in real values
scp deploy/local/.env.prod.template quantum:/opt/clovercharts/.env.prod
ssh quantum 'nano /opt/clovercharts/.env.prod'  # Edit with real secrets
ssh quantum 'chmod 600 /opt/clovercharts/.env.prod'
```

**Critical secrets to set:**
- `POSTGRES_PASSWORD` — strong random password for the `kuber` PostgreSQL role
- `JWT_SECRET` — generate with `openssl rand -hex 64`
- `OPENAI_API_KEY` — your OpenAI key
- `FINNHUB_API_KEY` — your Finnhub key
- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` — your Alpaca credentials
- `FLOWER_BASIC_AUTH` — e.g., `admin:strongpassword`
- `GF_SECURITY_ADMIN_PASSWORD` — Grafana admin password

### 7. SSL certificates

```bash
ssh quantum
sudo certbot --nginx -d clovercharts.com -d www.clovercharts.com -d api.clovercharts.com -d grafana.clovercharts.com
```

Certbot auto-renews via systemd timer. Verify: `sudo certbot renew --dry-run`

### 8. First deploy

```bash
./deploy/local/deploy.sh
```

## Day-to-Day Operations

### Deploy latest code

```bash
./deploy/local/deploy.sh
```

### Deploy backend only (skip frontend)

```bash
./deploy/local/deploy.sh --skip-frontend
```

### Deploy with pre-built images

```bash
./deploy/local/deploy.sh --skip-build
```

### Enable production-parity backtests on self-hosted Docker

Set these in `/opt/clovercharts/.env.prod`:

```bash
BACKTEST_RUNTIME_MODE=docker_container
BACKTEST_RUNTIME_IMAGE=clovercharts/backend:latest
BACKTEST_RUNTIME_DOCKER_NETWORK=
```

`BACKTEST_RUNTIME_DOCKER_NETWORK` may be left blank. The worker will infer its
current Docker Compose network automatically.

Requirements:

- `celery-worker` must keep `/var/run/docker.sock` mounted
- the backend image must include the backtest runtime code
- run `alembic upgrade head` before the first backtest

After deploying, backtests started from the API will spawn isolated runtime
containers instead of using the legacy shared worker path.

### Rollback

```bash
./deploy/local/deploy.sh --rollback
```

This reverts all 4 custom images to their `:previous` tags and restarts containers.

### View logs

```bash
ssh quantum
cd /opt/clovercharts
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f celery-worker
docker compose -f docker-compose.prod.yml logs --tail=100 signal-generator
```

### View active backtest runtimes

```bash
ssh quantum
docker ps --filter "label=clovercharts.runtime=backtest"
docker logs <backtest-container-name>
```

### Restart a service

```bash
ssh quantum 'cd /opt/clovercharts && docker compose -f docker-compose.prod.yml restart backend'
```

## Accessing Internal Tools

Flower and Prometheus are NOT exposed publicly. Access via SSH tunnel:

### Flower (Celery monitoring)

```bash
ssh -L 5555:localhost:5555 quantum
# Then open http://localhost:5555
```

### Prometheus

```bash
ssh -L 9090:localhost:9090 quantum
# Then open http://localhost:9090
```

## Database Access

PostgreSQL runs natively on the host (not in Docker). Connect directly:

```bash
# From the server
psql -U kuber -d trading_platform

# From your Mac
PGPASSWORD=<pw> psql -U kuber -h 192.168.1.188 -d trading_platform
```

### Verify TimescaleDB

```bash
psql -U kuber -d trading_data_plane -c "SELECT * FROM timescaledb_information.hypertables;"
```

## Backups

Daily automated backups run at 3:00 AM via cron using native `pg_dump`:
- `trading_platform` and `trading_data_plane` dumps in `/opt/clovercharts/backups/`
- 14-day retention (older backups auto-deleted)
- Logs: `/opt/clovercharts/backups/backup.log`

### Manual backup

```bash
ssh quantum '/opt/clovercharts/backup-databases.sh'
```

### Restore from backup

```bash
ssh quantum
gunzip -c /opt/clovercharts/backups/postgres_20260301_030000.sql.gz | \
    psql -U kuber trading_platform

gunzip -c /opt/clovercharts/backups/timescaledb_20260301_030000.sql.gz | \
    psql -U kuber trading_data_plane
```

## Estimated Memory Usage (~5.2GB containers + host PostgreSQL)

| Service | Memory Limit |
|---------|-------------|
| PostgreSQL (host-native) | ~3.9GB shared_buffers (not Docker) |
| Redis | 300M |
| Kafka + Zookeeper | 1024M |
| Backend (2 workers) | 512M |
| Celery Worker | 768M |
| Celery Beat | 256M |
| Flower | 256M |
| Signal Generator | 256M |
| Trigger Dispatcher | 256M |
| Data Plane (2 workers) | 512M |
| Data Plane Worker | 384M |
| Data Plane Beat | 256M |
| Prometheus | 512M |
| Grafana | 256M |
| **Docker Total** | **~5.2GB** |

> Compared to the previous setup, removing PostgreSQL (512M) and TimescaleDB (512M) Docker containers saves ~1GB of container memory.

## Troubleshooting

### Backend not starting
```bash
ssh quantum 'docker logs clovercharts-backend --tail=50'
```

### Backend can't connect to PostgreSQL
```bash
# Verify PostgreSQL is listening
ssh quantum 'ss -tlnp | grep 5432'

# Verify pg_hba.conf allows Docker subnet
ssh quantum 'sudo grep docker /etc/postgresql/*/main/pg_hba.conf'

# Test from inside a container
ssh quantum 'docker exec clovercharts-backend python -c "import sqlalchemy; print(sqlalchemy.create_engine(\"postgresql://kuber:pw@host.docker.internal:5432/trading_platform\").connect())"'
```

### Nginx errors
```bash
ssh quantum 'sudo nginx -t'
ssh quantum 'sudo tail -50 /var/log/nginx/error.log'
```

### SSL certificate issues
```bash
ssh quantum 'sudo certbot certificates'
ssh quantum 'sudo certbot renew --force-renewal'
```

### Check all container status
```bash
ssh quantum 'cd /opt/clovercharts && docker compose -f docker-compose.prod.yml ps'
```

### Disk usage
```bash
ssh quantum 'df -h && docker system df'
```
