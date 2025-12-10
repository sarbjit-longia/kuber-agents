# Monitoring Configuration

This directory contains all configuration for the trading platform's monitoring stack (Prometheus + Grafana).

## Structure

```
monitoring/
├── prometheus.yml                           # Prometheus scrape configuration
├── grafana/
│   ├── datasources/
│   │   └── prometheus.yml                   # Auto-configured Prometheus datasource
│   ├── dashboards/
│   │   ├── dashboard-config.yml             # Dashboard provisioning config
│   │   └── trading-platform-overview.json   # Main system dashboard
└── README.md                                # This file
```

---

## What Each File Does

### 1. `prometheus.yml`
**Purpose**: Tells Prometheus which services to scrape for metrics

**What it does**:
- Scrapes **Backend** (port 8001) every 15 seconds
- Scrapes **Celery Worker** (port 8002) every 15 seconds
- Scrapes **Signal Generator** (port 8003) every 15 seconds
- Scrapes **Trigger Dispatcher** (port 8004) every 15 seconds
- Stores metrics for 30 days
- Labels each service for easy filtering

**How Docker uses it**:
```yaml
# In docker-compose.yml
volumes:
  - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
```

---

### 2. `grafana/datasources/prometheus.yml`
**Purpose**: Auto-configures Grafana to use Prometheus as a data source

**What it does**:
- Automatically adds Prometheus datasource when Grafana starts
- Points to `http://prometheus:9090` (internal Docker network)
- Sets it as the default datasource
- No manual configuration needed!

**How Docker uses it**:
```yaml
# In docker-compose.yml
volumes:
  - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources:ro
```

---

### 3. `grafana/dashboards/dashboard-config.yml`
**Purpose**: Tells Grafana to auto-load dashboards from the `dashboards/` folder

**What it does**:
- Scans `/etc/grafana/provisioning/dashboards/` for `.json` files
- Automatically imports them when Grafana starts
- Allows updates every 10 seconds
- Enables UI editing of dashboards

**How Docker uses it**:
```yaml
# In docker-compose.yml
volumes:
  - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
```

---

### 4. `grafana/dashboards/trading-platform-overview.json`
**Purpose**: **THE MAIN DASHBOARD** - Visual overview of your entire platform

**What it shows**:
- ✅ **Service Health** - Backend, Signal Generator, Trigger Dispatcher status
- 📊 **Pipeline Execution Rate** - Pipelines running per second (by status & trigger mode)
- 🔔 **Signal Generation Rate** - Signals generated per second (by type & source)
- ✅ **Success Rates** - Pipeline success % and Kafka publish success %
- ⏱️ **Latency** - P50, P95, P99 execution duration
- 🔄 **Trigger Dispatcher Stats** - Pipelines matched, enqueued, skipped
- 📈 **24-hour Totals** - Executions, signals, enqueued pipelines
- ⚠️ **Kafka Failures** - Failed publishes in last hour

**Total Panels**: 17 visualizations

---

## How to Use

### Option 1: Auto-Import (Easiest) ✅

The dashboard is **already configured to auto-load**! Just:

1. **Start Grafana**:
   ```bash
   docker-compose up -d grafana
   ```

2. **Open Grafana**:
   ```bash
   open http://localhost:3000
   # Login: admin / admin
   ```

3. **Access the dashboard**:
   - Click "Dashboards" (4-squares icon on left)
   - Find "Trading Platform - System Overview"
   - Click to open!

### Option 2: Manual Import (If Auto-Import Fails)

1. Open Grafana: http://localhost:3000
2. Click "+" → "Import"
3. Click "Upload JSON file"
4. Select `monitoring/grafana/dashboards/trading-platform-overview.json`
5. Click "Import"

---

## Dashboard Preview

### Top Row: Service Health
- 🟢 **Green** = Service UP
- 🔴 **Red** = Service DOWN

### Main Charts
1. **Pipeline Execution Rate** - Real-time execution trends
2. **Signal Generation Rate** - Signal production over time
3. **Success Rate Gauges** - Pipeline & Kafka health (should be > 95%)
4. **Latency Percentiles** - P50/P95/P99 execution times

### Bottom Stats
- Total executions, signals, and pipeline enqueues (24h)
- Average batch size
- Kafka failures

---

## Customizing the Dashboard

### Change Refresh Rate
Current: 5 seconds (top right dropdown)
- Click the refresh icon → Select interval (5s, 10s, 30s, 1m, etc.)

### Change Time Range
Current: Last 1 hour (top right)
- Click time range → Select (Last 6 hours, Last 24 hours, etc.)

### Add New Panels
1. Click "Add" → "Visualization"
2. Select query:
   ```promql
   # Example: Signals by type
   sum by(signal_type) (increase(signals_generated_total[1h]))
   ```
3. Choose visualization (Time series, Gauge, Stat, etc.)
4. Click "Apply"
5. Click "Save" (top right)

### Edit Existing Panels
1. Click panel title → "Edit"
2. Modify query or visualization
3. Click "Apply"
4. Click "Save dashboard"

---

## Useful Queries

### Service Health
```promql
# All services up?
up{job=~"backend|signal-generator|trigger-dispatcher"}
```

### Pipeline Performance
```promql
# Executions per minute
rate(pipeline_executions_total[1m]) * 60

# Success rate (%)
sum(rate(pipeline_executions_total{status="completed"}[5m])) 
/ 
sum(rate(pipeline_executions_total[5m])) * 100

# P95 latency
histogram_quantile(0.95, rate(pipeline_execution_duration_seconds_bucket[5m]))
```

### Signal Generation
```promql
# Signals by type
sum by(signal_type) (rate(signals_generated_total[5m]))

# Kafka publish success rate
sum(rate(kafka_publish_success_total[5m])) 
/ 
(sum(rate(kafka_publish_success_total[5m])) + sum(rate(kafka_publish_failure_total[5m]))) * 100
```

### Trigger Dispatcher
```promql
# Pipeline matching efficiency
sum(rate(pipelines_enqueued_total[5m])) 
/ 
sum(rate(pipelines_matched_total[5m])) * 100

# Average batch size
rate(batch_size_sum[5m]) / rate(batch_size_count[5m])
```

---

## Troubleshooting

### Dashboard shows "No data"
1. **Check Prometheus targets**: http://localhost:9090/targets
   - All services should show "UP"
2. **Check metrics endpoints**:
   ```bash
   curl http://localhost:8001/metrics | head -20  # Backend
   curl http://localhost:8003/metrics | head -20  # Signal Generator
   ```
3. **Generate activity**: Execute a pipeline or wait for signals to be generated
4. **Adjust time range**: Change from "Last 1 hour" to "Last 24 hours"

### Panels show errors
1. **Verify datasource**: Configuration → Data Sources → Prometheus → "Test"
2. **Rebuild services**:
   ```bash
   docker-compose up --build -d backend signal-generator trigger-dispatcher
   ```

### Dashboard not auto-loading
1. **Check Grafana logs**:
   ```bash
   docker logs trading-grafana | grep -i dashboard
   ```
2. **Verify volume mount**:
   ```bash
   docker exec trading-grafana ls -la /etc/grafana/provisioning/dashboards/
   ```
3. **Manual import**: Use Option 2 above

---

## Next Steps

### Create More Dashboards
- **Agent Performance**: Deep dive into individual agents
- **Cost Tracking**: Token usage, API costs, budget limits
- **User Activity**: Pipeline executions per user
- **Infrastructure**: Database, Redis, Kafka metrics

### Set Up Alerts
1. Create `monitoring/prometheus-alerts.yml`
2. Add rules for:
   - Pipeline failure rate > 10%
   - Service down
   - Kafka consumer lag > 1s
   - High execution latency (P95 > 10s)

### Export Dashboards
1. Open dashboard
2. Click "Share" (top right)
3. Click "Export"
4. Save as JSON
5. Commit to Git for version control

---

## File Sizes

| File | Size | Purpose |
|------|------|---------|
| `prometheus.yml` | ~1 KB | Scrape config |
| `grafana/datasources/prometheus.yml` | ~0.5 KB | Datasource config |
| `grafana/dashboards/dashboard-config.yml` | ~0.5 KB | Provisioning config |
| `trading-platform-overview.json` | ~25 KB | Main dashboard (17 panels) |

**Total**: ~27 KB for complete monitoring setup!

---

## Quick Commands

```bash
# Restart monitoring stack
docker-compose restart prometheus grafana

# View Prometheus config
docker exec trading-prometheus cat /etc/prometheus/prometheus.yml

# View Grafana dashboards directory
docker exec trading-grafana ls -la /etc/grafana/provisioning/dashboards/

# Check if dashboard loaded
docker logs trading-grafana | grep "trading-platform-overview"

# Rebuild everything
docker-compose up --build -d prometheus grafana
```

---

**Your dashboard is ready to use!** 🎉

Just open http://localhost:3000 and you'll see your complete trading platform visualized in real-time.

