#!/usr/bin/env bash
# Kuber Trading — Interactive Deploy Console
# Run from the dev Mac at the project root:
#   ./deploy/local/deploy.sh              # interactive menu
#   ./deploy/local/deploy.sh status       # direct status check
#   ./deploy/local/deploy.sh migrate      # direct migrations
#   ./deploy/local/deploy.sh rollback     # direct rollback
#   ./deploy/local/deploy.sh sync         # direct config sync
#   ./deploy/local/deploy.sh logs <svc>   # direct log tail
set -euo pipefail

# ============================================================
# CONFIG
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/config.env"

DOMAIN="${DOMAIN:?DOMAIN not set in config.env}"
SERVER="${SERVER_HOST:?SERVER_HOST not set in config.env}"
USER="${SERVER_USER:-kuber}"
REMOTE="${REMOTE_DIR:-/opt/kubertrading}"
GIT_SHA=$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_PLATFORM="${BUILD_PLATFORM:-linux/amd64}"

# Compose command run on server
COMPOSE="docker compose --env-file .env.prod -f docker-compose.prod.yml"

# Image-to-service mappings (indexed arrays for macOS bash 3.x compat)
IMAGES=(backend signal-generator trigger-dispatcher data-plane frontend)
DOCKERFILES=("deploy/Dockerfile.prod" "signal-generator/Dockerfile" "trigger-dispatcher/Dockerfile" "data-plane/Dockerfile" "frontend/Dockerfile")
CONTEXTS=("." "signal-generator" "trigger-dispatcher" "data-plane" "frontend")
IMAGE_SERVICES=("backend celery-worker celery-beat flower" "signal-generator" "trigger-dispatcher" "data-plane data-plane-worker data-plane-beat" "frontend")

# All compose service names (for restart sub-menu)
ALL_SERVICES=(backend celery-worker celery-beat flower signal-generator trigger-dispatcher data-plane data-plane-worker data-plane-beat frontend)

# ============================================================
# COLORS & HELPERS
# ============================================================
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${CYAN}$*${NC}"; }
success() { echo -e "${GREEN}$*${NC}"; }
warn()    { echo -e "${YELLOW}WARNING: $*${NC}"; }
err()     { echo -e "${RED}ERROR: $*${NC}" >&2; }

header() {
    echo ""
    echo -e "${CYAN}${BOLD}=== $* ===${NC}"
    echo ""
}

pause() {
    echo ""
    read -rp "Press Enter to continue..."
}

confirm() {
    local msg="${1:-Are you sure?}"
    echo -e "${YELLOW}${msg}${NC}"
    read -rp "(y/N) " ans
    [[ "$ans" =~ ^[Yy]$ ]]
}

elapsed() {
    local start=$1
    local end
    end=$(date +%s)
    local secs=$((end - start))
    printf "%dm%02ds" $((secs / 60)) $((secs % 60))
}

# Run a command on the server
remote() {
    ssh "$USER@$SERVER" "$@"
}

remote_bash() {
    ssh "$USER@$SERVER" bash -s
}

remote_tty() {
    ssh -t "$USER@$SERVER" "$@"
}

# ============================================================
# CHECK SSH CONNECTIVITY
# ============================================================
check_ssh() {
    if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$USER@$SERVER" true 2>/dev/null; then
        err "Cannot reach $USER@$SERVER — check SSH config."
        exit 1
    fi
}

# ============================================================
# 1) DEPLOY IMAGES
# ============================================================
deploy_images() {
    header "Deploy Images"
    echo " 1) backend              (backend, celery-worker, celery-beat, flower)"
    echo " 2) signal-generator     (signal-generator)"
    echo " 3) trigger-dispatcher   (trigger-dispatcher)"
    echo " 4) data-plane           (data-plane, data-plane-worker, data-plane-beat)"
    echo " 5) frontend             (frontend)"
    echo " 6) All"
    echo " 0) Back"
    echo ""
    read -rp "Select images (comma-separated, e.g. 1,3,5): " choice

    [[ "$choice" == "0" || -z "$choice" ]] && return 0

    # Parse selection into index list
    local selected=()
    if [[ "$choice" == "6" ]]; then
        selected=(0 1 2 3 4)
    else
        IFS=',' read -ra parts <<< "$choice"
        for p in "${parts[@]}"; do
            p=$(echo "$p" | tr -d ' ')
            if [[ "$p" =~ ^[1-5]$ ]]; then
                selected+=($((p - 1)))
            else
                warn "Ignoring invalid selection: $p"
            fi
        done
    fi

    if [[ ${#selected[@]} -eq 0 ]]; then
        warn "No valid images selected."
        return 0
    fi

    # Pick which steps to run
    echo ""
    info "Selected images:"
    for idx in "${selected[@]}"; do
        echo "  - ${IMAGES[$idx]} → services: ${IMAGE_SERVICES[$idx]}"
    done
    echo ""
    echo "Steps to run:"
    echo " 1) Build + Push + Start  (full deploy)"
    echo " 2) Push + Start          (already built locally)"
    echo " 3) Start only            (already on server)"
    echo " 0) Back"
    echo ""
    read -rp "Select steps [1]: " steps_choice
    steps_choice="${steps_choice:-1}"

    local do_build=true do_push=true do_start=true
    case "$steps_choice" in
        1) do_build=true;  do_push=true;  do_start=true ;;
        2) do_build=false; do_push=true;  do_start=true ;;
        3) do_build=false; do_push=false; do_start=true ;;
        0) return 0 ;;
        *) warn "Invalid choice."; return 0 ;;
    esac

    # Summary
    echo ""
    info "Plan:"
    [[ "$do_build" == "true" ]] && echo "  - Build locally (platform: $BUILD_PLATFORM)"
    [[ "$do_push" == "true" ]]  && echo "  - Push to $SERVER (docker save | ssh docker load)"
    [[ "$do_start" == "true" ]] && echo "  - Start/restart affected services"
    echo ""

    if ! confirm "Proceed?"; then
        return 0
    fi

    local succeeded=()
    local all_services=""

    for idx in "${selected[@]}"; do
        local img="${IMAGES[$idx]}"
        local dockerfile="${DOCKERFILES[$idx]}"
        local context="${CONTEXTS[$idx]}"
        local services="${IMAGE_SERVICES[$idx]}"
        local start_time
        local img_ok=true

        # --- Build ---
        if [[ "$do_build" == "true" ]]; then
            start_time=$(date +%s)
            echo ""
            info "[$img] Building..."
            if ! docker build --platform "$BUILD_PLATFORM" \
                -t "kubertrading/$img:latest" -t "kubertrading/$img:$GIT_SHA" \
                -f "$PROJECT_ROOT/$dockerfile" "$PROJECT_ROOT/$context"; then
                err "[$img] Build failed — skipping."
                continue
            fi
            success "[$img] Built in $(elapsed "$start_time")."
        fi

        # --- Push ---
        if [[ "$do_push" == "true" ]]; then
            # Verify image exists locally before pushing
            if ! docker image inspect "kubertrading/$img:latest" &>/dev/null; then
                err "[$img] Image kubertrading/$img:latest not found locally — skipping."
                continue
            fi

            info "[$img] Tagging :previous on server..."
            remote "docker tag kubertrading/$img:latest kubertrading/$img:previous 2>/dev/null || true"

            start_time=$(date +%s)
            info "[$img] Transferring to $SERVER..."
            if ! docker save "kubertrading/$img:latest" | ssh "$USER@$SERVER" 'docker load'; then
                err "[$img] Transfer failed — skipping."
                continue
            fi
            success "[$img] Transferred in $(elapsed "$start_time")."
        fi

        succeeded+=("$img")
        all_services="$all_services $services"
    done

    if [[ ${#succeeded[@]} -eq 0 ]]; then
        err "No images processed successfully."
        return 1
    fi

    # --- Start ---
    if [[ "$do_start" == "true" ]]; then
        echo ""
        info "Restarting affected services:$all_services"
        remote "cd $REMOTE && $COMPOSE up -d $all_services"
        success "Services restarted."

        # Health check if backend was deployed
        for img in "${succeeded[@]}"; do
            if [[ "$img" == "backend" ]]; then
                info "Waiting for backend health check..."
                local healthy=false
                for i in $(seq 1 30); do
                    if remote "curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1"; then
                        success "Backend is healthy."
                        healthy=true
                        break
                    fi
                    sleep 1
                done
                if [[ "$healthy" != "true" ]]; then
                    warn "Backend not healthy after 30s. Check: docker logs trading-backend"
                fi
                break
            fi
        done
    fi

    echo ""
    success "Done: ${succeeded[*]} [$(
        [[ "$do_build" == "true" ]] && printf "built "
        [[ "$do_push" == "true" ]]  && printf "pushed "
        [[ "$do_start" == "true" ]] && printf "started"
    )]"
}

# ============================================================
# 2) DEPLOY DATABASE
# ============================================================
deploy_database() {
    header "Deploy Database"
    info "This will scp provision-db.sh to the server and run it with sudo."
    echo ""

    if ! confirm "Run database provisioning on $SERVER?"; then
        return 0
    fi

    info "Uploading provision-db.sh..."
    scp -q "$SCRIPT_DIR/provision-db.sh" "$USER@$SERVER:/tmp/provision-db.sh"

    info "Running provision-db.sh on server (requires sudo)..."
    remote_tty "sudo bash /tmp/provision-db.sh && rm -f /tmp/provision-db.sh"

    success "Database provisioning complete."
}

# ============================================================
# 3) DEPLOY NGINX
# ============================================================
deploy_nginx() {
    header "Deploy Nginx"
    echo " 1) HTTP only (LAN access)"
    echo " 2) HTTP + SSL (Let's Encrypt)"
    echo " 0) Back"
    echo ""
    read -rp "Select: " choice

    case "$choice" in
        1) local ssl_flag="" ;;
        2) local ssl_flag="--ssl" ;;
        0|"") return 0 ;;
        *) warn "Invalid choice."; return 0 ;;
    esac

    if ! confirm "Deploy Nginx ($( [[ -n "${ssl_flag:-}" ]] && echo "with SSL" || echo "HTTP only")) on $SERVER?"; then
        return 0
    fi

    info "Uploading setup-nginx.sh and config.env..."
    scp -q "$SCRIPT_DIR/setup-nginx.sh" "$USER@$SERVER:/tmp/setup-nginx.sh"
    scp -q "$SCRIPT_DIR/config.env" "$USER@$SERVER:/tmp/config.env"

    info "Running setup-nginx.sh on server (requires sudo)..."
    remote_tty "sudo bash /tmp/setup-nginx.sh ${ssl_flag:-} && rm -f /tmp/setup-nginx.sh /tmp/config.env"

    success "Nginx setup complete."
}

# ============================================================
# 4) SYNC CONFIG
# ============================================================
sync_config() {
    header "Sync Config Files"

    info "Syncing docker-compose.prod.yml..."
    scp -q "$SCRIPT_DIR/docker-compose.prod.yml" "$USER@$SERVER:$REMOTE/docker-compose.prod.yml"

    info "Syncing Nginx config..."
    remote "mkdir -p $REMOTE/nginx"
    sed "s/__DOMAIN__/$DOMAIN/g" "$SCRIPT_DIR/nginx/kubertrading.conf" 2>/dev/null \
        | ssh "$USER@$SERVER" "cat > $REMOTE/nginx/kubertrading.conf" \
        || warn "No nginx/kubertrading.conf template found — skipped."

    info "Syncing Prometheus config..."
    scp -q "$PROJECT_ROOT/monitoring/prometheus.yml" "$USER@$SERVER:$REMOTE/config/prometheus.yml" 2>/dev/null \
        || warn "No monitoring/prometheus.yml found — skipped."

    info "Syncing signal-generator config..."
    if [[ -d "$PROJECT_ROOT/signal-generator/config" ]]; then
        rsync -az "$PROJECT_ROOT/signal-generator/config/" "$USER@$SERVER:$REMOTE/config/signal-generator/"
    else
        warn "No signal-generator/config/ directory — skipped."
    fi

    info "Syncing Grafana dashboards & datasources..."
    rsync -az "$PROJECT_ROOT/monitoring/grafana/dashboards/" "$USER@$SERVER:$REMOTE/config/grafana/dashboards/" 2>/dev/null \
        || warn "No Grafana dashboards found — skipped."
    rsync -az "$PROJECT_ROOT/monitoring/grafana/datasources/" "$USER@$SERVER:$REMOTE/config/grafana/datasources/" 2>/dev/null \
        || warn "No Grafana datasources found — skipped."

    # Reload Nginx if config changed
    info "Checking Nginx config on server..."
    remote_bash <<'EOF'
        if command -v nginx &>/dev/null; then
            if ! diff -q /opt/kubertrading/nginx/kubertrading.conf /etc/nginx/sites-available/kubertrading.conf &>/dev/null 2>&1; then
                sudo cp /opt/kubertrading/nginx/kubertrading.conf /etc/nginx/sites-available/kubertrading.conf
                sudo nginx -t && sudo systemctl reload nginx
                echo "  Nginx config updated and reloaded."
            else
                echo "  Nginx config unchanged."
            fi
        else
            echo "  Nginx not installed — skipping reload."
        fi
EOF

    success "Config sync complete."
}

# ============================================================
# 5) RESTART CONTAINERS
# ============================================================
restart_containers() {
    header "Restart Containers"
    local i=1
    for svc in "${ALL_SERVICES[@]}"; do
        printf " %2d) %s\n" "$i" "$svc"
        i=$((i + 1))
    done
    printf " %2d) All\n" "$i"
    echo "  0) Back"
    echo ""
    read -rp "Select containers (comma-separated, e.g. 1,2): " choice

    [[ "$choice" == "0" || -z "$choice" ]] && return 0

    local selected_services=""
    local all_idx=${#ALL_SERVICES[@]}
    all_idx=$((all_idx + 1))

    if [[ "$choice" == "$all_idx" ]]; then
        selected_services="${ALL_SERVICES[*]}"
    else
        IFS=',' read -ra parts <<< "$choice"
        for p in "${parts[@]}"; do
            p=$(echo "$p" | tr -d ' ')
            if [[ "$p" =~ ^[0-9]+$ ]] && [[ "$p" -ge 1 ]] && [[ "$p" -le ${#ALL_SERVICES[@]} ]]; then
                selected_services="$selected_services ${ALL_SERVICES[$((p - 1))]}"
            else
                warn "Ignoring invalid selection: $p"
            fi
        done
    fi

    selected_services=$(echo "$selected_services" | xargs)
    if [[ -z "$selected_services" ]]; then
        warn "No valid containers selected."
        return 0
    fi

    info "Restarting: $selected_services"
    remote "cd $REMOTE && $COMPOSE restart $selected_services"
    success "Restarted: $selected_services"
}

# ============================================================
# 6) RUN MIGRATIONS
# ============================================================
run_migrations() {
    header "Run Migrations"

    info "Running alembic upgrade head..."
    remote "docker exec trading-backend alembic upgrade head"
    success "Migrations complete."

    info "Running seed_database.py (idempotent)..."
    remote "docker exec trading-backend python seed_database.py"
    success "Database seeded."
}

# ============================================================
# 7) VIEW LOGS
# ============================================================
view_logs() {
    header "View Logs"
    local svc_name="${1:-}"

    if [[ -z "$svc_name" ]]; then
        local i=1
        for svc in "${ALL_SERVICES[@]}"; do
            printf " %2d) %s\n" "$i" "$svc"
            i=$((i + 1))
        done
        echo "  0) Back"
        echo ""
        read -rp "Select container: " choice

        [[ "$choice" == "0" || -z "$choice" ]] && return 0

        if [[ "$choice" =~ ^[0-9]+$ ]] && [[ "$choice" -ge 1 ]] && [[ "$choice" -le ${#ALL_SERVICES[@]} ]]; then
            svc_name="${ALL_SERVICES[$((choice - 1))]}"
        else
            warn "Invalid selection."
            return 0
        fi
    fi

    read -rp "Number of lines [100]: " lines
    lines="${lines:-100}"

    echo ""
    echo " 1) Static (tail)"
    echo " 2) Follow (Ctrl+C to stop)"
    read -rp "Select [1]: " mode
    mode="${mode:-1}"

    echo ""
    info "Logs for $svc_name (last $lines lines):"
    echo "---"

    if [[ "$mode" == "2" ]]; then
        # Follow mode — Ctrl+C stops tailing, returns to menu
        remote_tty "cd $REMOTE && $COMPOSE logs --tail=$lines -f $svc_name" || true
    else
        remote "cd $REMOTE && $COMPOSE logs --tail=$lines $svc_name"
    fi
}

# ============================================================
# 8) ROLLBACK
# ============================================================
rollback() {
    header "Rollback"

    info "Checking :previous tags on server..."
    echo ""
    remote_bash <<'EOF'
        for svc in backend signal-generator trigger-dispatcher data-plane frontend; do
            if docker image inspect "kubertrading/$svc:previous" &>/dev/null; then
                prev_id=$(docker image inspect "kubertrading/$svc:previous" --format '{{.Id}}' | cut -c8-19)
                curr_id=$(docker image inspect "kubertrading/$svc:latest" --format '{{.Id}}' 2>/dev/null | cut -c8-19 || echo "none")
                if [[ "$prev_id" == "$curr_id" ]]; then
                    echo "  $svc: :previous == :latest (same image)"
                else
                    echo "  $svc: :previous=$prev_id  :latest=$curr_id"
                fi
            else
                echo "  $svc: no :previous tag"
            fi
        done
EOF

    echo ""
    if ! confirm "Roll back all images with :previous tags to :latest?"; then
        return 0
    fi

    info "Rolling back..."
    remote_bash <<ROLLBACK
        cd "$REMOTE"
        rolled=0
        for svc in backend signal-generator trigger-dispatcher data-plane frontend; do
            if docker image inspect "kubertrading/\$svc:previous" &>/dev/null; then
                docker tag "kubertrading/\$svc:previous" "kubertrading/\$svc:latest"
                echo "  Rolled back kubertrading/\$svc"
                rolled=1
            fi
        done
        if [[ \$rolled -eq 1 ]]; then
            $COMPOSE up -d
            echo "Containers restarted."
        else
            echo "Nothing to roll back."
        fi
ROLLBACK

    success "Rollback complete."
}

# ============================================================
# 10) HEALTH CHECK
# ============================================================
health_check() {
    header "Health Check"

    remote_bash <<'HEALTH'
        RED='\033[0;31m'
        GREEN='\033[0;32m'
        YELLOW='\033[1;33m'
        NC='\033[0m'

        pass() { echo -e "  ${GREEN}[OK]${NC}  $1"; }
        fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }
        skip() { echo -e "  ${YELLOW}[SKIP]${NC} $1"; }

        echo "--- Service Endpoints ---"

        # Backend API
        if curl -sf http://127.0.0.1:8000/health -o /dev/null --max-time 5 2>/dev/null; then
            pass "Backend API         (http://127.0.0.1:8000/health)"
        else
            fail "Backend API         (http://127.0.0.1:8000/health)"
        fi

        # Data Plane API
        if curl -sf http://127.0.0.1:8005/health -o /dev/null --max-time 5 2>/dev/null; then
            pass "Data Plane API      (http://127.0.0.1:8005/health)"
        else
            fail "Data Plane API      (http://127.0.0.1:8005/health)"
        fi

        # Signal Generator
        if curl -sf http://127.0.0.1:8007/ -o /dev/null --max-time 5 2>/dev/null; then
            pass "Signal Generator    (http://127.0.0.1:8007)"
        else
            fail "Signal Generator    (http://127.0.0.1:8007)"
        fi

        # Flower
        if curl -sf http://127.0.0.1:5555/ -o /dev/null --max-time 5 2>/dev/null; then
            pass "Flower              (http://127.0.0.1:5555)"
        else
            fail "Flower              (http://127.0.0.1:5555)"
        fi

        # Frontend
        if curl -sf http://127.0.0.1:4200/ -o /dev/null --max-time 5 2>/dev/null; then
            pass "Frontend            (http://127.0.0.1:4200)"
        else
            fail "Frontend            (http://127.0.0.1:4200)"
        fi

        # Grafana
        if curl -sf http://127.0.0.1:3000/api/health -o /dev/null --max-time 5 2>/dev/null; then
            pass "Grafana             (http://127.0.0.1:3000)"
        else
            fail "Grafana             (http://127.0.0.1:3000)"
        fi

        # Prometheus
        if curl -sf http://127.0.0.1:9090/-/healthy -o /dev/null --max-time 5 2>/dev/null; then
            pass "Prometheus          (http://127.0.0.1:9090)"
        else
            fail "Prometheus          (http://127.0.0.1:9090)"
        fi

        echo ""
        echo "--- Docker Health Status ---"
        docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep trading || echo "  (no trading containers)"

        echo ""
        echo "--- Database ---"
        if docker exec trading-backend python -c "
from app.config import settings
from sqlalchemy import create_engine, text
e = create_engine(settings.DATABASE_URL.replace('+asyncpg',''))
with e.connect() as c:
    c.execute(text('SELECT 1'))
    print('OK')
" 2>/dev/null | grep -q OK; then
            pass "PostgreSQL          (via backend container)"
        else
            fail "PostgreSQL          (via backend container)"
        fi

        echo ""
        echo "--- Redis ---"
        if docker exec trading-redis redis-cli ping 2>/dev/null | grep -q PONG; then
            pass "Redis               (PONG)"
        else
            fail "Redis"
        fi

        echo ""
        echo "--- Kafka ---"
        if docker exec trading-kafka kafka-broker-api-versions --bootstrap-server localhost:9092 &>/dev/null; then
            pass "Kafka               (broker responsive)"
        else
            fail "Kafka"
        fi

        echo ""
        echo "--- Celery Workers ---"
        if docker exec trading-celery-worker celery -A app.orchestration.celery_app inspect ping --timeout 5 2>/dev/null | grep -q "pong"; then
            pass "Celery Worker       (pong)"
        else
            fail "Celery Worker"
        fi

        echo ""
        echo "--- Nginx ---"
        if command -v nginx &>/dev/null && systemctl is-active --quiet nginx; then
            pass "Nginx               (active)"
        elif command -v nginx &>/dev/null; then
            fail "Nginx               (installed but not running)"
        else
            skip "Nginx               (not installed)"
        fi
HEALTH
}

# ============================================================
# 9) GET STATUS
# ============================================================
get_status() {
    header "Server Status — $USER@$SERVER"

    remote_bash <<STATUS
        echo "--- Uptime ---"
        uptime
        echo ""
        echo "--- Disk ---"
        df -h / | tail -1
        echo ""
        echo "--- Docker Compose ---"
        cd "$REMOTE" 2>/dev/null && $COMPOSE ps 2>/dev/null || echo "(compose not available)"
        echo ""
        echo "--- Container Resources ---"
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" 2>/dev/null | grep trading || echo "(no trading containers)"
STATUS
}

# ============================================================
# MAIN MENU
# ============================================================
show_menu() {
    echo ""
    echo -e "${CYAN}${BOLD}=== Kuber Trading Deploy Console ===${NC}"
    echo -e "Server: ${BOLD}$USER@$SERVER${NC} | Dir: $REMOTE | Git: $GIT_SHA"
    echo ""
    echo "  1) Deploy Images          6) Run Migrations"
    echo "  2) Deploy Database        7) View Logs"
    echo "  3) Deploy Nginx           8) Rollback"
    echo "  4) Sync Config            9) Get Status"
    echo "  5) Restart Containers    10) Health Check"
    echo "  0) Exit"
    echo ""
}

menu_loop() {
    # Trap Ctrl+C to return to menu instead of exiting
    trap 'echo ""; info "Returning to menu..."; continue' INT

    while true; do
        show_menu
        read -rp "Select option: " opt
        case "$opt" in
            1) deploy_images    || warn "Deploy images encountered an error." ;;
            2) deploy_database  || warn "Deploy database encountered an error." ;;
            3) deploy_nginx     || warn "Deploy nginx encountered an error." ;;
            4) sync_config      || warn "Sync config encountered an error." ;;
            5) restart_containers || warn "Restart encountered an error." ;;
            6) run_migrations   || warn "Migrations encountered an error." ;;
            7) view_logs        || warn "View logs encountered an error." ;;
            8) rollback         || warn "Rollback encountered an error." ;;
            9) get_status       || warn "Status check encountered an error." ;;
            10) health_check    || warn "Health check encountered an error." ;;
            0) echo "Bye."; exit 0 ;;
            *) warn "Invalid option: $opt" ;;
        esac
        pause
    done
}

# ============================================================
# CLI PASSTHROUGH (non-interactive)
# ============================================================
if [[ $# -gt 0 ]]; then
    cmd="$1"; shift
    case "$cmd" in
        -h|--help)
            echo "Usage: $0 [command] [args]"
            echo ""
            echo "Commands (non-interactive):"
            echo "  status            Show server status"
            echo "  health            Run health checks on all services"
            echo "  migrate           Run alembic migrations + seed"
            echo "  rollback          Roll back to :previous images"
            echo "  sync              Sync config files to server"
            echo "  logs [service]    View logs for a service"
            echo ""
            echo "No arguments → interactive menu"
            exit 0
            ;;
        status)   check_ssh; get_status ;;
        health)   check_ssh; health_check ;;
        migrate)  check_ssh; run_migrations ;;
        rollback) check_ssh; rollback ;;
        sync)     check_ssh; sync_config ;;
        logs)     check_ssh; view_logs "${1:-}" ;;
        *)
            err "Unknown command: $cmd"
            echo "Run '$0 --help' for usage."
            exit 1
            ;;
    esac
    exit 0
fi

# ============================================================
# INTERACTIVE MODE
# ============================================================
check_ssh
menu_loop
