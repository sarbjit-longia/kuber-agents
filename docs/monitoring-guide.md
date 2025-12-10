# Trading Platform Monitoring - Complete Guide

## Overview

The trading platform uses **OpenTelemetry** for observability, with **Prometheus** for metrics storage and **Grafana** for visualization.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       SERVICES                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Backend  │  │  Celery  │  │  Signal  │  │ Trigger  │   │
│  │ :8001    │  │  :8001   │  │  Gen     │  │ Dispatch │   │
│  │          │  │          │  │  :8001   │  │  :8001   │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │             │              │              │          │
│       └─────────────┼──────────────┼──────────────┘          │
│                     │ Metrics (/metrics endpoint)            │
└─────────────────────┼────────────────────────────────────────┘
                      │
                      ▼
            ┌───────────────────┐
            │   Prometheus      │  Scrapes metrics every 15s
            │   :9090           │  Stores 30 days of data
            └─────────┬─────────┘
                      │
                      ▼
            ┌───────────────────┐
            │    Grafana        │  Visualizes metrics
            │    :3000          │  Dashboards & Alerts
            └───────────────────┘
```

---

## Services & Metrics

### 1. Backend (FastAPI) - Port 8001

**Auto-instrumented**:
- `http_server_request_duration_seconds` - API response times
- `http_server_active_requests` - Current requests
- `db_query_duration_seconds` - Database query performance
- `db_active_connections` - Active DB connections

**Custom**:
- `pipeline_executions_total{status, pipeline_id, trigger_mode}` - Execution counter
- `pipeline_execution_duration_seconds{status, pipeline_id}` - Execution time

**Endpoint**: http://localhost:8001/metrics

---

### 2. Celery Worker - Port 8002

**Auto-instrumented**:
- `celery_tasks_total` - Tasks processed
- `celery_task_duration_seconds` - Task execution time
- `celery_active_tasks` - Currently running tasks

**Custom**:
- Same as backend (executes pipelines)

**Endpoint**: http://localhost:8002/metrics

---

### 3. Signal Generator - Port 8003

**Metrics**:
- `signals_generated_total{signal_type, source}` - Signals generated
- `signal_generation_duration_seconds{generator}` - Generation time
- `kafka_publish_duration_seconds{signal_type}` - Kafka publish time
- `kafka_publish_success_total{signal_type}` - Successful publishes
- `kafka_publish_failure_total{signal_type, error_type}` - Failed publishes

**Endpoint**: http://localhost:8003/metrics

---

### 4. Trigger Dispatcher - Port 8004

**Metrics**:
- `signals_consumed_total` - Signals consumed from Kafka
- `pipelines_matched_total` - Pipelines matched to signals
- `pipelines_enqueued_total` - Tasks enqueued
- `pipelines_skipped_running_total` - Duplicates avoided
- `batch_size` - Signal batch sizes
- `batch_processing_duration_seconds` - Batch processing time
- `pipeline_cache_size` - Cached pipelines count

**Endpoint**: http://localhost:8004/metrics

---

## Quick Start

### 1. Start Services

```bash
cd /Users/sarbjits/workspace/personal/kuber-agents

# Start all services
docker-compose up --build -d

# Wait for services to be healthy (30-60s)
docker-compose ps
```

### 2. Verify Metrics

```bash
# Check all metrics endpoints
curl -s http://localhost:8001/metrics | grep pipeline_executions
curl -s http://localhost:8002/metrics | grep pipeline_executions
curl -s http://localhost:8003/metrics | grep signals_generated
curl -s http://localhost:8004/metrics | grep signals_consumed
```

**Expected output**: Metrics in Prometheus format
```
# HELP pipeline_executions_total Total pipeline executions
# TYPE pipeline_executions_total counter
pipeline_executions_total{pipeline_id="...",status="success",trigger_mode="periodic"} 5.0
```

### 3. Access Prometheus

```bash
open http://localhost:9090
```

**Verify targets**:
1. Go to Status → Targets
2. All 4 services should show "UP"
3. Click on a target to see scraped metrics

**Run queries**:
1. Go to Graph tab
2. Try these queries:
   - `rate(pipeline_executions_total[5m])`
   - `rate(signals_generated_total[5m])`
   - `histogram_quantile(0.95, rate(pipeline_execution_duration_seconds_bucket[5m]))`

### 4. Access Grafana

```bash
open http://localhost:3000
```

**Login**: admin / admin

**Verify datasource**:
1. Go to Configuration (gear icon) → Data Sources
2. Prometheus should be configured
3. Click "Test" - should show "Data source is working"

**Create your first dashboard**:
1. Click "+" → Dashboard
2. Add Panel
3. Query: `rate(pipeline_executions_total[5m])`
4. Title: "Pipeline Executions per Second"
5. Save

---

## Key Queries (PromQL)

### System Health

```promql
# All services up?
up{job=~"backend|celery-worker|signal-generator|trigger-dispatcher"}

# Service uptime
(time() - process_start_time_seconds)
```

### Pipeline Execution

```promql
# Executions per minute
rate(pipeline_executions_total[1m]) * 60

# Success rate (%)
sum(rate(pipeline_executions_total{status="success"}[5m])) 
/ 
sum(rate(pipeline_executions_total[5m])) * 100

# P50, P95, P99 latency
histogram_quantile(0.50, rate(pipeline_execution_duration_seconds_bucket[5m]))
histogram_quantile(0.95, rate(pipeline_execution_duration_seconds_bucket[5m]))
histogram_quantile(0.99, rate(pipeline_execution_duration_seconds_bucket[5m]))

# Executions by trigger mode
sum by(trigger_mode) (rate(pipeline_executions_total[5m]))
```

### Signal Generation

```promql
# Signals per minute
rate(signals_generated_total[1m]) * 60

# Signals by type
sum by(signal_type) (rate(signals_generated_total[5m]))

# Kafka publish success rate
sum(rate(kafka_publish_success_total[5m])) 
/ 
(sum(rate(kafka_publish_success_total[5m])) + sum(rate(kafka_publish_failure_total[5m]))) * 100
```

### Trigger Dispatcher

```promql
# Batch processing rate
rate(batch_processing_duration_seconds_count[5m])

# Average batch size
rate(batch_size_sum[5m]) / rate(batch_size_count[5m])

# Pipeline matching efficiency
sum(rate(pipelines_enqueued_total[5m])) 
/ 
sum(rate(pipelines_matched_total[5m])) * 100

# Cache size
pipeline_cache_size
```

---

## Creating Dashboards

### Quick Method: Import Pre-built Dashboard

1. Go to Grafana (http://localhost:3000)
2. Click "+" → "Import"
3. Paste dashboard ID or JSON
4. Select "Prometheus" datasource
5. Click "Import"

### Manual Method: Build Your Own

**Panel 1: Pipeline Executions Rate**
- Visualization: Time series (Graph)
- Query: `rate(pipeline_executions_total[5m])`
- Legend: `{{status}} - {{trigger_mode}}`

**Panel 2: Success Rate Gauge**
- Visualization: Gauge
- Query: `sum(rate(pipeline_executions_total{status="success"}[5m])) / sum(rate(pipeline_executions_total[5m])) * 100`
- Min: 0, Max: 100
- Thresholds: Red < 80%, Yellow < 95%, Green >= 95%

**Panel 3: Signal Generation**
- Visualization: Bar chart
- Query: `sum by(signal_type) (increase(signals_generated_total[1h]))`

**Panel 4: Execution Duration Heatmap**
- Visualization: Heatmap
- Query: `sum(rate(pipeline_execution_duration_seconds_bucket[5m])) by (le)`

---

## Alerts (Optional)

Create `monitoring/prometheus-alerts.yml`:

```yaml
groups:
  - name: trading_platform
    interval: 30s
    rules:
      # High failure rate
      - alert: HighPipelineFailureRate
        expr: |
          sum(rate(pipeline_executions_total{status="failed"}[5m])) 
          / 
          sum(rate(pipeline_executions_total[5m])) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Pipeline failure rate above 10%"
      
      # Service down
      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{$labels.job}} is down"
      
      # High consumer lag
      - alert: HighKafkaConsumerLag
        expr: kafka_consumer_lag_seconds > 1.0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Kafka consumer lag above 1 second"
```

---

## Troubleshooting

### Metrics endpoint returns 404

**Cause**: Telemetry not initialized or metrics server failed to start

**Fix**:
1. Check service logs: `docker logs trading-backend`
2. Look for: `"telemetry_initialized"` or `"Prometheus metrics endpoint started"`
3. If missing, rebuild: `docker-compose up --build -d backend`

### Prometheus shows target as "DOWN"

**Cause**: Service not exposing metrics or network issue

**Fix**:
1. Test metrics endpoint directly: `curl http://localhost:8001/metrics`
2. Check service is running: `docker ps | grep backend`
3. Check Prometheus logs: `docker logs trading-prometheus`

### Grafana shows "No data"

**Cause**: Datasource not configured or no metrics yet

**Fix**:
1. Test datasource in Grafana: Configuration → Data Sources → Prometheus → Test
2. Check Prometheus has data: http://localhost:9090 → Graph → Query: `up`
3. Adjust time range in Grafana (top right)
4. Generate some activity (execute pipelines)

---

## Performance Impact

**Overhead per service**:
- CPU: < 1% (metrics collection)
- Memory: ~20MB (OpenTelemetry SDK)
- Network: ~1KB/s per service (Prometheus scrape)

**Prometheus storage**:
- ~1GB for 30 days of data (4 services × 100 metrics × 15s interval)

**Grafana**:
- ~500MB memory
- Minimal CPU

**Total overhead**: < 5% system resources

---

## AWS Migration Guide

### Step 1: Update Environment Variables

```yaml
# In docker-compose.yml or ECS task definition
services:
  backend:
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.us-west-2.amazonaws.com
      - AWS_REGION=us-west-2
      - OTEL_METRICS_EXPORTER=otlp
```

### Step 2: Update Telemetry Export

No code changes! OpenTelemetry SDK automatically detects AWS and uses:
- **Amazon Managed Service for Prometheus (AMP)**
- **AWS X-Ray** (for traces)
- **CloudWatch Logs** (for logs)

### Step 3: Update Grafana

Replace local Grafana with **Amazon Managed Grafana**:
1. Create AMG workspace in AWS Console
2. Add AMP as datasource
3. Import your dashboards
4. Done!

**Cost**: ~$110/month for production workload

---

## Best Practices

### 1. Dashboard Organization

Create separate dashboards for:
- **System Overview** - High-level health
- **Signal Generation** - Generator deep dive
- **Pipeline Execution** - Execution analysis
- **Infrastructure** - Kafka, DB, Redis

### 2. Use Variables

Add dashboard variables for dynamic filtering:
- `$service` - Filter by service
- `$pipeline_id` - Filter by pipeline
- `$signal_type` - Filter by signal type
- `$time_range` - Quick time range selector

### 3. Set Up Alerts

Monitor critical metrics:
- Service down (up == 0)
- High failure rate (> 10%)
- Consumer lag (> 1s)
- Long execution time (P95 > 10s)

### 4. Retention Policies

- **Development**: 30 days
- **Production**: 90-180 days
- **Archive**: Export to S3 for long-term storage

---

## Useful Grafana Dashboard IDs

Public Grafana dashboards you can import:
- **1860** - Node Exporter (system metrics)
- **7362** - Kafka Overview
- **9628** - PostgreSQL Database
- **11019** - Celery monitoring

Customize these for your needs!

---

## Next Steps

1. ✅ Complete trigger-dispatcher telemetry
2. ✅ Test all metrics endpoints
3. ✅ Create custom dashboards
4. 🚀 Generate test load (execute pipelines)
5. 📊 Analyze performance bottlenecks
6. 🎯 Set up alerts
7. 📝 Document team runbooks

---

## Access URLs

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **Backend Metrics**: http://localhost:8001/metrics
- **Celery Metrics**: http://localhost:8002/metrics
- **Signal Gen Metrics**: http://localhost:8003/metrics
- **Dispatcher Metrics**: http://localhost:8004/metrics

---

**Status**: ~90% Complete | Ready for Testing!

