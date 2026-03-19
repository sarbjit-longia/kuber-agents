#!/usr/bin/env bash
# system-health-check.sh — Colored CLI health dashboard for CloverCharts
#
# Usage: ./scripts/system-health-check.sh [--json] [--quiet]
# Exit codes: 0=healthy, 1=warnings, 2=critical

set -uo pipefail

# --- Flags ---
JSON_OUTPUT=false
QUIET=false
for arg in "$@"; do
  case "$arg" in
    --json)  JSON_OUTPUT=true ;;
    --quiet) QUIET=true ;;
  esac
done

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- State ---
WARNINGS=0
CRITICALS=0
JSON_SECTIONS=()

log() { $QUIET || echo -e "$@"; }
header() { log "\n${BOLD}${CYAN}═══ $1 ═══${NC}"; }

ok()   { log "  ${GREEN}✔${NC} $1"; }
warn() { log "  ${YELLOW}⚠${NC} $1"; WARNINGS=$((WARNINGS + 1)); }
crit() { log "  ${RED}✘${NC} $1"; CRITICALS=$((CRITICALS + 1)); }

# ── 1. Docker Containers ─────────────────────────────────────────────
EXPECTED_CONTAINERS=(
  clovercharts-postgres
  clovercharts-redis
  clovercharts-timescaledb
  clovercharts-backend
  clovercharts-celery-worker
  clovercharts-celery-beat
  clovercharts-flower
  clovercharts-zookeeper
  clovercharts-kafka
  clovercharts-signal-generator
  clovercharts-trigger-dispatcher
  clovercharts-data-plane
  clovercharts-data-plane-worker
  clovercharts-data-plane-beat
  clovercharts-prometheus
  clovercharts-grafana
)

check_containers() {
  header "Docker Containers"
  local json_items=()
  for name in "${EXPECTED_CONTAINERS[@]}"; do
    local info
    info=$(docker inspect --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}|{{.RestartCount}}' "$name" 2>/dev/null) || info="not_found||"
    IFS='|' read -r state health restarts <<< "$info"

    local entry="{\"name\":\"$name\",\"state\":\"$state\",\"health\":\"$health\",\"restarts\":\"$restarts\"}"
    json_items+=("$entry")

    if [[ "$state" == "not_found" ]]; then
      crit "$name — ${RED}NOT FOUND${NC}"
    elif [[ "$state" != "running" ]]; then
      crit "$name — ${RED}$state${NC} (restarts: $restarts)"
    elif [[ -n "$health" && "$health" != "healthy" && "$health" != "n/a" && "$health" != "" ]]; then
      warn "$name — running but ${YELLOW}$health${NC} (restarts: $restarts)"
    else
      local extra=""
      [[ "$restarts" -gt 0 ]] 2>/dev/null && extra=" (restarts: $restarts)"
      ok "$name — running${extra}"
    fi
  done
  local joined
  joined=$(IFS=,; echo "${json_items[*]}")
  JSON_SECTIONS+=("\"containers\":[$joined]")
}

# ── 2. TCP Port Checks ───────────────────────────────────────────────
PORTS=(5433 6380 5434 8000 5555 9093 2181 8005 8007 9090 3000)
PORT_LABELS=("PostgreSQL" "Redis" "TimescaleDB" "Backend API" "Flower" "Kafka" "Zookeeper" "Data Plane" "Signal Generator" "Prometheus" "Grafana")

check_ports() {
  header "TCP Ports"
  local json_items=()
  local i=0
  for port in "${PORTS[@]}"; do
    local label="${PORT_LABELS[$i]}"
    i=$((i + 1))
    if nc -z -w 2 localhost "$port" 2>/dev/null; then
      ok "$label (localhost:$port)"
      json_items+=("{\"port\":$port,\"service\":\"$label\",\"status\":\"open\"}")
    else
      crit "$label (localhost:$port) — ${RED}CLOSED${NC}"
      json_items+=("{\"port\":$port,\"service\":\"$label\",\"status\":\"closed\"}")
    fi
  done
  local joined
  joined=$(IFS=,; echo "${json_items[*]}")
  JSON_SECTIONS+=("\"ports\":[$joined]")
}

# ── 3. HTTP Endpoints ────────────────────────────────────────────────
ENDPOINT_LABELS=("Backend /health" "Backend /readiness" "Flower" "Prometheus" "Grafana")
ENDPOINT_URLS=("http://localhost:8000/health" "http://localhost:8000/api/v1/readiness" "http://localhost:5555/" "http://localhost:9090/-/healthy" "http://localhost:3000/api/health")

check_endpoints() {
  header "HTTP Endpoints"
  local json_items=()
  local i=0
  for label in "${ENDPOINT_LABELS[@]}"; do
    local url="${ENDPOINT_URLS[$i]}"
    i=$((i + 1))
    local code
    code=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null) || code="000"
    if [[ "$code" =~ ^2 ]]; then
      ok "$label — HTTP $code"
      json_items+=("{\"endpoint\":\"$label\",\"url\":\"$url\",\"status\":$code}")
    elif [[ "$code" == "503" ]]; then
      warn "$label — HTTP $code (degraded)"
      json_items+=("{\"endpoint\":\"$label\",\"url\":\"$url\",\"status\":$code}")
    else
      crit "$label — HTTP $code"
      json_items+=("{\"endpoint\":\"$label\",\"url\":\"$url\",\"status\":$code}")
    fi
  done
  local joined
  joined=$(IFS=,; echo "${json_items[*]}")
  JSON_SECTIONS+=("\"endpoints\":[$joined]")
}

# ── 4. Prometheus Targets ────────────────────────────────────────────
check_prometheus_targets() {
  header "Prometheus Scrape Targets"
  local json_items=()
  local response
  response=$(curl -sf --max-time 5 "http://localhost:9090/api/v1/targets" 2>/dev/null) || {
    warn "Could not reach Prometheus targets API"
    JSON_SECTIONS+=("\"prometheus_targets\":[]")
    return
  }

  if command -v python3 &>/dev/null; then
    local target_info
    target_info=$(python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
targets = data.get('data', {}).get('activeTargets', [])
for t in targets:
    job = t.get('labels', {}).get('job', 'unknown')
    health = t.get('health', 'unknown')
    print(f'{job}|{health}')
" <<< "$response" 2>/dev/null) || true

    while IFS='|' read -r job health; do
      [[ -z "$job" ]] && continue
      if [[ "$health" == "up" ]]; then
        ok "Prometheus target: $job — ${GREEN}UP${NC}"
      else
        warn "Prometheus target: $job — ${YELLOW}$health${NC}"
      fi
      json_items+=("{\"job\":\"$job\",\"health\":\"$health\"}")
    done <<< "$target_info"
  else
    ok "Prometheus API reachable (install python3 for detailed target info)"
  fi

  local joined
  joined=$(IFS=,; echo "${json_items[*]}")
  JSON_SECTIONS+=("\"prometheus_targets\":[$joined]")
}

# ── 5. Disk & Volumes ────────────────────────────────────────────────
check_disk() {
  header "Disk & Docker Volumes"
  local json_items=()

  # Host disk
  local usage
  usage=$(df -h . | tail -1 | awk '{print $5}' | tr -d '%')
  local disk_info
  disk_info=$(df -h . | tail -1 | awk '{print $4 " free (" $5 " used)"}')
  if [[ "$usage" -gt 90 ]]; then
    crit "Host disk: $disk_info"
  elif [[ "$usage" -gt 80 ]]; then
    warn "Host disk: $disk_info"
  else
    ok "Host disk: $disk_info"
  fi
  json_items+=("{\"check\":\"host_disk\",\"usage_pct\":$usage}")

  # Docker volumes count
  local vol_count
  vol_count=$(docker volume ls -q 2>/dev/null | wc -l | tr -d ' ')
  ok "Docker volumes: $vol_count"
  json_items+=("{\"check\":\"docker_volumes\",\"count\":$vol_count}")

  local joined
  joined=$(IFS=,; echo "${json_items[*]}")
  JSON_SECTIONS+=("\"disk\":[$joined]")
}

# ── Run all checks ───────────────────────────────────────────────────
check_containers
check_ports
check_endpoints
check_prometheus_targets
check_disk

# ── Summary ──────────────────────────────────────────────────────────
if $JSON_OUTPUT; then
  local_joined=$(IFS=,; echo "${JSON_SECTIONS[*]}")
  echo "{$local_joined,\"summary\":{\"warnings\":$WARNINGS,\"criticals\":$CRITICALS}}"
else
  header "Summary"
  if [[ $CRITICALS -gt 0 ]]; then
    log "  ${RED}${BOLD}CRITICAL${NC}: $CRITICALS critical issue(s), $WARNINGS warning(s)"
  elif [[ $WARNINGS -gt 0 ]]; then
    log "  ${YELLOW}${BOLD}WARNING${NC}: $WARNINGS warning(s)"
  else
    log "  ${GREEN}${BOLD}ALL HEALTHY${NC}"
  fi
fi

# Exit code
if [[ $CRITICALS -gt 0 ]]; then
  exit 2
elif [[ $WARNINGS -gt 0 ]]; then
  exit 1
else
  exit 0
fi
