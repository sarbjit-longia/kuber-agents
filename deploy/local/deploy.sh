#!/usr/bin/env bash
# Deploy Kuber Trading to self-hosted Ubuntu server
# Run from the dev Mac at the project root:
#   ./deploy/local/deploy.sh
#   ./deploy/local/deploy.sh --skip-build
#   ./deploy/local/deploy.sh --skip-frontend
#   ./deploy/local/deploy.sh --rollback
set -euo pipefail

# --- Load config ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/config.env"

DOMAIN="${DOMAIN:?DOMAIN not set in config.env}"
SERVER="${SERVER_HOST:?SERVER_HOST not set in config.env}"
USER="${SERVER_USER:-kuber}"
REMOTE="${REMOTE_DIR:-/opt/kubertrading}"
GIT_SHA=$(git -C "$PROJECT_ROOT" rev-parse --short HEAD)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# --- Parse flags ---
SKIP_BUILD=false
SKIP_FRONTEND=false
ROLLBACK=false

for arg in "$@"; do
    case $arg in
        --skip-build)    SKIP_BUILD=true ;;
        --skip-frontend) SKIP_FRONTEND=true ;;
        --rollback)      ROLLBACK=true ;;
        --help|-h)
            echo "Usage: $0 [--skip-build] [--skip-frontend] [--rollback]"
            echo ""
            echo "  --skip-build     Skip Docker image builds (use existing local images)"
            echo "  --skip-frontend  Skip Angular build and frontend deployment"
            echo "  --rollback       Roll back to :previous tagged images on server"
            exit 0
            ;;
        *)
            echo "Unknown flag: $arg"
            exit 1
            ;;
    esac
done

echo "=== Kuber Trading Deploy ==="
echo "Server: $USER@$SERVER"
echo "Remote: $REMOTE"
echo "Git SHA: $GIT_SHA"
echo ""

# ==========================================
# ROLLBACK
# ==========================================
if [[ "$ROLLBACK" == "true" ]]; then
    echo "[ROLLBACK] Reverting to :previous images on server..."
    ssh "$USER@$SERVER" bash <<ROLLBACK_CMD
        cd "$REMOTE"
        for svc in backend signal-generator trigger-dispatcher data-plane; do
            if docker image inspect "kubertrading/\$svc:previous" &>/dev/null; then
                docker tag "kubertrading/\$svc:previous" "kubertrading/\$svc:latest"
                echo "  Rolled back kubertrading/\$svc to :previous"
            else
                echo "  WARNING: No :previous tag for kubertrading/\$svc, skipping"
            fi
        done
        docker compose -f docker-compose.prod.yml up -d
        echo "Rollback complete."
ROLLBACK_CMD
    exit 0
fi

# ==========================================
# BUILD IMAGES
# ==========================================
if [[ "$SKIP_BUILD" == "false" ]]; then
    echo "[1/6] Building Docker images..."

    # Backend (shared by backend, celery-worker, celery-beat, flower)
    echo "  Building backend..."
    docker build -t "kubertrading/backend:latest" -t "kubertrading/backend:$GIT_SHA" \
        -f "$PROJECT_ROOT/deploy/Dockerfile.prod" "$PROJECT_ROOT"

    # Signal Generator
    echo "  Building signal-generator..."
    docker build -t "kubertrading/signal-generator:latest" -t "kubertrading/signal-generator:$GIT_SHA" \
        -f "$PROJECT_ROOT/signal-generator/Dockerfile" "$PROJECT_ROOT/signal-generator"

    # Trigger Dispatcher
    echo "  Building trigger-dispatcher..."
    docker build -t "kubertrading/trigger-dispatcher:latest" -t "kubertrading/trigger-dispatcher:$GIT_SHA" \
        -f "$PROJECT_ROOT/trigger-dispatcher/Dockerfile" "$PROJECT_ROOT/trigger-dispatcher"

    # Data Plane
    echo "  Building data-plane..."
    docker build -t "kubertrading/data-plane:latest" -t "kubertrading/data-plane:$GIT_SHA" \
        -f "$PROJECT_ROOT/data-plane/Dockerfile" "$PROJECT_ROOT/data-plane"

    echo "  All images built."
else
    echo "[1/6] Skipping image builds (--skip-build)."
fi

# ==========================================
# BUILD FRONTEND
# ==========================================
if [[ "$SKIP_FRONTEND" == "false" ]]; then
    echo "[2/6] Building Angular frontend..."
    cd "$PROJECT_ROOT/frontend"
    npx ng build --configuration production
    echo "  Frontend built."
    cd "$PROJECT_ROOT"
else
    echo "[2/6] Skipping frontend build (--skip-frontend)."
fi

# ==========================================
# TAG PREVIOUS ON SERVER (for rollback)
# ==========================================
echo "[3/6] Tagging current server images as :previous..."
ssh "$USER@$SERVER" bash <<TAG_CMD
    for svc in backend signal-generator trigger-dispatcher data-plane; do
        if docker image inspect "kubertrading/\$svc:latest" &>/dev/null; then
            docker tag "kubertrading/\$svc:latest" "kubertrading/\$svc:previous"
        fi
    done
    echo "  Tagged existing images as :previous"
TAG_CMD

# ==========================================
# TRANSFER IMAGES
# ==========================================
if [[ "$SKIP_BUILD" == "false" ]]; then
    echo "[4/6] Transferring Docker images to server..."
    for svc in backend signal-generator trigger-dispatcher data-plane; do
        echo "  Sending kubertrading/$svc..."
        docker save "kubertrading/$svc:latest" | ssh "$USER@$SERVER" 'docker load'
    done
    echo "  All images transferred."
else
    echo "[4/6] Skipping image transfer (--skip-build)."
fi

# ==========================================
# TRANSFER FILES
# ==========================================
echo "[5/6] Syncing config and frontend files..."

# Frontend static files
if [[ "$SKIP_FRONTEND" == "false" ]]; then
    rsync -az --delete "$PROJECT_ROOT/frontend/dist/frontend/browser/" "$USER@$SERVER:$REMOTE/frontend/"
    echo "  Frontend files synced."
fi

# Docker compose
scp -q "$SCRIPT_DIR/docker-compose.prod.yml" "$USER@$SERVER:$REMOTE/docker-compose.prod.yml"

# Nginx config (with domain substitution)
ssh "$USER@$SERVER" "mkdir -p $REMOTE/nginx"
sed "s/__DOMAIN__/$DOMAIN/g" "$SCRIPT_DIR/nginx/kubertrading.conf" | ssh "$USER@$SERVER" "cat > $REMOTE/nginx/kubertrading.conf"

# Prometheus config
scp -q "$PROJECT_ROOT/monitoring/prometheus.yml" "$USER@$SERVER:$REMOTE/config/prometheus.yml"

# Signal generator watchlist config
if [[ -d "$PROJECT_ROOT/signal-generator/config" ]]; then
    rsync -az "$PROJECT_ROOT/signal-generator/config/" "$USER@$SERVER:$REMOTE/config/signal-generator/"
fi

# Grafana dashboards & datasources
rsync -az "$PROJECT_ROOT/monitoring/grafana/dashboards/" "$USER@$SERVER:$REMOTE/config/grafana/dashboards/"
rsync -az "$PROJECT_ROOT/monitoring/grafana/datasources/" "$USER@$SERVER:$REMOTE/config/grafana/datasources/"

echo "  Config files synced."

# ==========================================
# DEPLOY ON SERVER
# ==========================================
echo "[6/6] Deploying on server..."
ssh "$USER@$SERVER" bash <<DEPLOY_CMD
    set -euo pipefail
    cd "$REMOTE"

    # Install Nginx config if changed
    if ! diff -q "$REMOTE/nginx/kubertrading.conf" /etc/nginx/sites-available/kubertrading.conf &>/dev/null 2>&1; then
        sudo cp "$REMOTE/nginx/kubertrading.conf" /etc/nginx/sites-available/kubertrading.conf
        sudo ln -sf /etc/nginx/sites-available/kubertrading.conf /etc/nginx/sites-enabled/kubertrading.conf
        sudo nginx -t && sudo systemctl reload nginx
        echo "  Nginx config updated and reloaded."
    else
        echo "  Nginx config unchanged."
    fi

    # Start/update containers
    docker compose -f docker-compose.prod.yml up -d
    echo "  Containers started."

    # Wait for backend to be healthy
    echo "  Waiting for backend health..."
    for i in {1..30}; do
        if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
            echo "  Backend is healthy."
            break
        fi
        if [[ \$i -eq 30 ]]; then
            echo "  WARNING: Backend not healthy after 30s. Check logs: docker logs trading-backend"
        fi
        sleep 1
    done

    # Run migrations
    echo "  Running database migrations..."
    docker exec trading-backend alembic upgrade head
    echo "  Migrations complete."

    # Seed database (idempotent)
    docker exec trading-backend python seed_database.py
    echo "  Database seeded."

    echo ""
    echo "=== Deploy complete! ==="
    echo "  Frontend: https://$DOMAIN"
    echo "  API:      https://api.$DOMAIN"
    echo "  Grafana:  https://grafana.$DOMAIN"
DEPLOY_CMD
