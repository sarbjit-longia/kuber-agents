# Self-Hosted Deployment Guide

Deploy Kuber Trading to a personal Ubuntu server with Nginx reverse proxy, Let's Encrypt SSL, and No-IP dynamic DNS.

## Server Requirements

- Ubuntu 22.04+ LTS
- 8GB+ RAM (16GB recommended)
- 4-core CPU
- 100GB SSD
- Public IP (static or dynamic with No-IP DUC)

## Architecture

```
Internet → Router (ports 80,443) → Ubuntu Server
  → Nginx (host, SSL termination)
    → kubertrading.com        → /opt/kubertrading/frontend/ (static)
    → api.kubertrading.com    → 127.0.0.1:8000 (Docker: backend)
    → grafana.kubertrading.com → 127.0.0.1:3000 (Docker: grafana)
  → Docker Compose (14 containers, all ports on 127.0.0.1)
```

## Initial Setup

### 1. Configure SSH access

Add to `~/.ssh/config` on your Mac:

```
Host kuber-server
    HostName <server-ip>
    User kuber
    IdentityFile ~/.ssh/id_ed25519
```

### 2. Update config.env

Edit `deploy/local/config.env` with your domain and server details:

```bash
DOMAIN=kubertrading.com
SERVER_HOST=kuber-server
SERVER_USER=kuber
REMOTE_DIR=/opt/kubertrading
```

### 3. Run server setup (once)

Copy the `deploy/local/` directory to the server and run:

```bash
scp -r deploy/local/ kuber-server:/tmp/kuber-setup/
ssh kuber-server 'sudo bash /tmp/kuber-setup/server-setup.sh'
```

This installs Docker, Nginx, Certbot, fail2ban, UFW, and creates the directory structure.

### 4. DNS configuration

**Option A: No-IP (Dynamic IP)**

1. Create a free account at [noip.com](https://www.noip.com)
2. Create hostnames: `kubertrading.com`, `api.kubertrading.com`, `grafana.kubertrading.com`, `www.kubertrading.com`
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
ExecStart=/usr/local/bin/noip-duc --username YOUR_EMAIL --password YOUR_PASS -g kubertrading.com,api.kubertrading.com,grafana.kubertrading.com,www.kubertrading.com --check-interval 5m
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
scp deploy/local/.env.prod.template kuber-server:/opt/kubertrading/.env.prod
ssh kuber-server 'nano /opt/kubertrading/.env.prod'  # Edit with real secrets
ssh kuber-server 'chmod 600 /opt/kubertrading/.env.prod'
```

**Critical secrets to set:**
- `POSTGRES_PASSWORD` / `TIMESCALE_PASSWORD` — strong random passwords
- `JWT_SECRET` — generate with `openssl rand -hex 64`
- `OPENAI_API_KEY` — your OpenAI key
- `FINNHUB_API_KEY` — your Finnhub key
- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` — your Alpaca credentials
- `FLOWER_BASIC_AUTH` — e.g., `admin:strongpassword`
- `GF_SECURITY_ADMIN_PASSWORD` — Grafana admin password

### 7. SSL certificates

```bash
ssh kuber-server
sudo certbot --nginx -d kubertrading.com -d www.kubertrading.com -d api.kubertrading.com -d grafana.kubertrading.com
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

### Rollback

```bash
./deploy/local/deploy.sh --rollback
```

This reverts all 4 custom images to their `:previous` tags and restarts containers.

### View logs

```bash
ssh kuber-server
cd /opt/kubertrading
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f celery-worker
docker compose -f docker-compose.prod.yml logs --tail=100 signal-generator
```

### Restart a service

```bash
ssh kuber-server 'cd /opt/kubertrading && docker compose -f docker-compose.prod.yml restart backend'
```

## Accessing Internal Tools

Flower and Prometheus are NOT exposed publicly. Access via SSH tunnel:

### Flower (Celery monitoring)

```bash
ssh -L 5555:localhost:5555 kuber-server
# Then open http://localhost:5555
```

### Prometheus

```bash
ssh -L 9090:localhost:9090 kuber-server
# Then open http://localhost:9090
```

## Backups

Daily automated backups run at 3:00 AM via cron:
- PostgreSQL and TimescaleDB dumps in `/opt/kubertrading/backups/`
- 14-day retention (older backups auto-deleted)
- Logs: `/opt/kubertrading/backups/backup.log`

### Manual backup

```bash
ssh kuber-server '/opt/kubertrading/backup-databases.sh'
```

### Restore from backup

```bash
ssh kuber-server
gunzip -c /opt/kubertrading/backups/postgres_20260301_030000.sql.gz | \
    docker exec -i trading-postgres psql -U kuber trading_platform
```

## Estimated Memory Usage (~6.2GB)

| Service | Memory Limit |
|---------|-------------|
| PostgreSQL | 512M |
| TimescaleDB | 512M |
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
| **Total** | **~6.2GB** |

## Troubleshooting

### Backend not starting
```bash
ssh kuber-server 'docker logs trading-backend --tail=50'
```

### Nginx errors
```bash
ssh kuber-server 'sudo nginx -t'
ssh kuber-server 'sudo tail -50 /var/log/nginx/error.log'
```

### SSL certificate issues
```bash
ssh kuber-server 'sudo certbot certificates'
ssh kuber-server 'sudo certbot renew --force-renewal'
```

### Check all container status
```bash
ssh kuber-server 'cd /opt/kubertrading && docker compose -f docker-compose.prod.yml ps'
```

### Disk usage
```bash
ssh kuber-server 'df -h && docker system df'
```
