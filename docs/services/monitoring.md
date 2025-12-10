# Monitoring & Observability System

**Last Updated**: December 2025  
**Status**: Production Ready  
**Stack**: OpenTelemetry + Prometheus + Grafana

## Overview

The Trading Platform uses a production-grade observability stack that provides:
- **Metrics**: Application and system performance metrics
- **Traces**: Request flow through services
- **Logs**: Structured logging with context
- **Dashboards**: Real-time visualization in Grafana

### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Observability Architecture                     │
└──────────────────────────────────────────────────────────────────┘

  APPLICATION LAYER            COLLECTION LAYER        VISUALIZATION
  
┌─────────────────┐          ┌─────────────────┐     ┌──────────────┐
│ Backend API     │──metrics─>│                │     │              │
│ (OpenTelemetry) │          │   Prometheus    │────>│   Grafana    │
└─────────────────┘          │   (TSDB)        │     │  (Dashboards)│
                             │                 │     │              │
┌─────────────────┐          │   Scrapes every │     └──────────────┘
│ Celery Worker   │──metrics─>│   15 seconds    │           │
│ (OpenTelemetry) │          │                 │           │
└─────────────────┘          └─────────────────┘           │
                                                            │
┌─────────────────┐          http://service:8001           │
│ Signal Gen      │──metrics─>    /metrics                 │
│ (OpenTelemetry) │                                         │
└─────────────────┘                                         │
                                                            │
┌─────────────────┐                                         │
│ Trigger Disp    │──metrics──────────────────────────────┘
│ (OpenTelemetry) │
└─────────────────┘
```

---

## 1. OpenTelemetry Setup

### 1.1 What is OpenTelemetry?

OpenTelemetry (OTel) is a **vendor-neutral** observability framework. This means:
- ✅ Works with Prometheus (local)
- ✅ Can switch to AWS CloudWatch (future)
- ✅ Can switch to Datadog, New Relic, etc.
- ✅ No vendor lock-in
- ✅ Standardized instrumentation

### 1.2 Instrumentation

Each service is instrumented with OpenTelemetry:

**Backend** (`backend/app/telemetry.py`):
```python
from opentelemetry import metrics
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

def setup_telemetry(app, service_name="trading-backend"):
    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    # Auto-instrument SQLAlchemy
    SQLAlchemyInstrumentor().instrument()
    
    # Auto-instrument Redis
    RedisInstrumentor().instrument()
    
    # Create meter for custom metrics
    meter = meter_provider.get_meter(service_name)
    
    return meter
```

**Auto-Instrumentation Provides**:
- HTTP request metrics (count, duration, errors)
- Database query metrics (count, duration)
- Redis operation metrics
- Error rates and 5xx responses

### 1.3 Custom Metrics

We also define custom business metrics:

**System Metrics**:
- `system_active_pipelines` - Active pipelines count
- `system_active_users` - Users with active pipelines
- `system_executions_today` - Executions started today
- `system_success_rate_24h` - Success rate (%)

**Pipeline Metrics**:
- `pipeline_executions_total` - Executions by status
- `pipeline_execution_duration_seconds` - Execution time
- `pipeline_agent_execution_duration_seconds` - Per-agent time

**Signal Metrics**:
- `signals_generated_total` - By signal type
- `signals_consumed_total` - Consumed from Kafka
- `pipelines_matched_total` - Matched to pipelines

---

## 2. Prometheus

### 2.1 Configuration

**File**: `monitoring/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'backend'
    static_configs:
      - targets: ['backend:8001']
  
  - job_name: 'celery-worker'
    static_configs:
      - targets: ['celery-worker:8001']
  
  - job_name: 'signal-generator'
    static_configs:
      - targets: ['signal-generator:8001']
  
  - job_name: 'trigger-dispatcher'
    static_configs:
      - targets: ['trigger-dispatcher:8001']
```

### 2.2 Metrics Scraping

Prometheus **scrapes** each service's `/metrics` endpoint every 15 seconds:

```bash
# Check what Prometheus is scraping
curl http://localhost:9090/api/v1/targets

# Query a specific metric
curl 'http://localhost:9090/api/v1/query?query=system_active_pipelines'
```

### 2.3 Query Language (PromQL)

Examples of useful queries:

```promql
# Total executions in last hour
sum(increase(pipeline_executions_total[1h]))

# Success rate
sum(pipeline_executions_total{status="completed"}) / sum(pipeline_executions_total) * 100

# 95th percentile execution duration
histogram_quantile(0.95, pipeline_execution_duration_seconds)

# Signals per minute
rate(signals_generated_total[1m]) * 60
```

---

## 3. Grafana

### 3.1 Access

- **URL**: http://localhost:3000
- **Username**: `admin`
- **Password**: `admin` (change on first login)

### 3.2 Dashboard

**Trading Platform Overview** dashboard includes:

#### **Row 1: System Health**
- Active Pipelines
- Active Users
- Executions Today
- Success Rate (24h)
- Running Now
- Pending

#### **Row 2: System Status**
- Backend API (UP/DOWN)
- Celery Worker (UP/DOWN)
- Signal Generator (UP/DOWN)
- Trigger Dispatcher (UP/DOWN)

#### **Row 3: Signal Generator Service**
- Signal Generation Rate
- Total Signals Generated
- Kafka Publish Latency
- Kafka Publish Success Rate
- Kafka Failures

#### **Row 4: Trigger Dispatcher Service**
- Cached Pipelines
- Signals Consumed
- Pipelines Matched
- Pipelines Enqueued
- Pipelines Skipped (already running)
- Batch Processing Latency

#### **Row 5: Pipeline Execution (Celery)**
- Pipeline Executions (by status)
- Execution Duration (p50, p95, p99)
- Execution Success Rate
- Total Execution Cost

### 3.3 Dashboard Provisioning

Dashboards are automatically loaded from:
```
monitoring/grafana/dashboards/
├── dashboard-config.yml          # Provisioning config
└── trading-platform-overview.json # Main dashboard
```

**Auto-reload**: Set to 10 seconds in `dashboard-config.yml`

### 3.4 Creating Custom Dashboards

1. Create dashboard in Grafana UI
2. Export JSON: Share → Export → Save to file
3. Save to `monitoring/grafana/dashboards/my-dashboard.json`
4. Restart Grafana: `docker-compose restart grafana`

---

## 4. Metrics Reference

### 4.1 System Health Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `system_active_pipelines` | Gauge | Number of active pipelines |
| `system_total_pipelines` | Gauge | Total pipelines (all users) |
| `system_signal_pipelines` | Gauge | Active signal-based pipelines |
| `system_periodic_pipelines` | Gauge | Active periodic pipelines |
| `system_active_users` | Gauge | Users with ≥1 active pipeline |
| `system_total_users` | Gauge | Total registered users |
| `system_executions_today_executions` | Gauge | Executions started today |
| `system_executions_running_executions` | Gauge | Currently running |
| `system_executions_pending_executions` | Gauge | Pending in queue |
| `system_success_rate_24h_percent` | Gauge | Success % (last 24h) |

### 4.2 Pipeline Execution Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `pipeline_executions_total` | Counter | Total executions | `status`, `pipeline_id`, `trigger_mode` |
| `pipeline_execution_duration_seconds` | Histogram | Execution time | `pipeline_id`, `status` |
| `pipeline_agent_execution_duration_seconds` | Histogram | Per-agent time | `agent_type`, `pipeline_id` |
| `pipeline_execution_cost` | Histogram | Cost per execution | `pipeline_id` |

### 4.3 Signal System Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `signals_generated_total` | Counter | Signals generated | `signal_type`, `source` |
| `signal_generation_duration_seconds` | Histogram | Generation time | `generator` |
| `kafka_publish_success_total` | Counter | Successful publishes | `topic` |
| `kafka_publish_failure_total` | Counter | Failed publishes | `topic`, `error` |
| `kafka_publish_duration_seconds` | Histogram | Publish latency | `topic` |
| `signals_consumed_total` | Counter | Signals consumed | `consumer_group` |
| `pipelines_matched_total` | Counter | Signals matched | `signal_type` |
| `pipelines_enqueued_total` | Counter | Pipelines enqueued | — |
| `pipelines_skipped_running_total` | Counter | Skipped (already running) | — |
| `pipeline_cache_size` | Gauge | Cached pipelines | — |
| `batch_processing_duration_seconds` | Histogram | Batch processing time | — |

### 4.4 Auto-Instrumented Metrics

OpenTelemetry auto-instrumentation provides:

**HTTP (FastAPI)**:
- `http_server_request_duration_seconds`
- `http_server_active_requests`
- `http_server_requests_total`

**Database (SQLAlchemy)**:
- `db_client_operation_duration_seconds`
- `db_client_connections_usage`

**Redis**:
- `redis_command_duration_seconds`
- `redis_commands_total`

---

## 5. Alerting (Future)

### 5.1 Alert Rules

Add to `monitoring/prometheus-alerts.yml`:

```yaml
groups:
  - name: trading_platform_alerts
    interval: 30s
    rules:
      - alert: HighExecutionFailureRate
        expr: rate(pipeline_executions_total{status="failed"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High execution failure rate"
          
      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.job }} is down"
```

### 5.2 Alert Destinations

- Email (via AlertManager)
- Slack webhook
- PagerDuty integration
- SMS (Twilio)

---

## 6. Log Aggregation

### 6.1 Structured Logging

All services use `structlog` for structured JSON logs:

```python
logger.info(
    "pipeline_execution_started",
    pipeline_id=str(pipeline.id),
    user_id=str(user.id),
    mode="paper"
)
```

**Output**:
```json
{
  "event": "pipeline_execution_started",
  "pipeline_id": "uuid",
  "user_id": "uuid",
  "mode": "paper",
  "timestamp": "2025-12-10T19:41:00.123Z",
  "level": "info"
}
```

### 6.2 Viewing Logs

```bash
# Backend
docker logs trading-backend -f | jq .

# Celery Worker
docker logs trading-celery-worker -f | jq .

# Signal Generator
docker logs signal-generator -f | jq .

# Trigger Dispatcher
docker logs trigger-dispatcher -f | jq .

# Filter by event
docker logs trading-backend -f | jq 'select(.event=="pipeline_execution_started")'
```

### 6.3 Future: Centralized Logging

For production, integrate with:
- AWS CloudWatch Logs
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Loki (Grafana's log aggregation)

---

## 7. Tracing (Future)

OpenTelemetry is configured for tracing but not yet fully utilized.

**Future Implementation**:
- Distributed tracing across services
- Trace pipeline execution end-to-end
- Identify bottlenecks in agent execution
- Correlate logs with traces

**Export to**:
- Jaeger (local)
- AWS X-Ray (production)

---

## 8. Production Migration

### 8.1 Current Setup (Local)

- Prometheus: Local container
- Grafana: Local container
- Metrics: Scraped every 15s
- Retention: 15 days

### 8.2 Future Setup (AWS)

**Option A: Managed Services**
- Amazon Managed Prometheus
- Amazon Managed Grafana
- CloudWatch for logs

**Option B: Self-Hosted**
- ECS Fargate for Prometheus + Grafana
- RDS for Grafana database
- S3 for long-term metric storage

**Recommended**: Option A for simplicity

### 8.3 Migration Steps

1. Update OpenTelemetry exporter in `backend/app/telemetry.py`
2. Configure AWS credentials
3. Update Prometheus remote write config
4. Update Grafana datasource
5. Export/import dashboards
6. Set up alerting via SNS

**No code changes needed** - just configuration!

---

## 9. Best Practices

### 9.1 Metric Naming

Follow Prometheus conventions:
- Use snake_case: `pipeline_executions_total`
- Suffix with unit: `_seconds`, `_bytes`, `_total`
- Use base units: seconds (not milliseconds), bytes (not MB)

### 9.2 Label Cardinality

**Good** (low cardinality):
```python
counter.add(1, {"status": "completed", "trigger_mode": "signal"})
```

**Bad** (high cardinality):
```python
counter.add(1, {"user_id": "uuid", "execution_id": "uuid"})
# Millions of unique label combinations = performance issues
```

### 9.3 Dashboard Organization

- Group by service (rows)
- Use consistent color schemes
- Show rate (not raw counts) for counters
- Use p50/p95/p99 for latency (not average)
- Add units to all metrics

---

## 10. Troubleshooting

### 10.1 No Data in Grafana

**Check Prometheus targets**:
```bash
curl http://localhost:9090/api/v1/targets | jq .
```

Look for services with `"health": "down"` and check their logs.

**Check metric exists**:
```bash
curl http://localhost:8001/metrics | grep system_active_pipelines
```

**Check Prometheus can scrape**:
```bash
docker exec trading-backend curl http://localhost:8001/metrics
```

### 10.2 Metrics Not Updating

**Check scrape interval**:
- Prometheus scrapes every 15s
- Grafana refresh based on dashboard settings

**Check collector logic**:
- System metrics query database on each scrape
- Observable gauges execute callbacks

**Force refresh**:
- Restart Grafana: `docker-compose restart grafana`
- Restart Prometheus: `docker-compose restart prometheus`

### 10.3 Grafana Dashboard Not Loading

**Check provisioning**:
```bash
docker logs trading-grafana | grep -i dashboard

# Check file exists
ls -la monitoring/grafana/dashboards/
```

**Manually import**:
1. Go to Grafana → Dashboards → Import
2. Upload `monitoring/grafana/dashboards/trading-platform-overview.json`

---

## 11. Monitoring Checklist

### 11.1 Development

- [ ] All services expose metrics on port 8001
- [ ] Prometheus scraping all services
- [ ] Grafana dashboard loads
- [ ] System health metrics updating
- [ ] Service status showing UP
- [ ] Execution metrics incrementing

### 11.2 Production

- [ ] Metrics exported to AWS
- [ ] Alerts configured
- [ ] Alert destinations tested
- [ ] Dashboards shared with team
- [ ] Retention policy set (30+ days)
- [ ] Backup dashboards to Git
- [ ] Monitor monitoring (meta!)

---

## 12. Metrics Glossary

**Counter**: Monotonically increasing value (resets on restart)
- Use for: Total executions, total errors, total requests
- Example: `pipeline_executions_total{status="completed"}`

**Gauge**: Value that can go up or down
- Use for: Current state, queue size, active connections
- Example: `system_active_pipelines`

**Histogram**: Distribution of values (latency, size, etc.)
- Use for: Request duration, execution time, costs
- Example: `pipeline_execution_duration_seconds`
- Provides: p50, p95, p99, avg, count

**Observable Gauge**: Gauge that's computed on-demand
- Use for: Database queries, external API calls
- Example: System metrics that query PostgreSQL

---

## 13. Future Enhancements

- [ ] Distributed tracing (Jaeger/X-Ray)
- [ ] Log aggregation (Loki/CloudWatch)
- [ ] Alerting (Prometheus AlertManager)
- [ ] SLA monitoring
- [ ] Cost optimization dashboard
- [ ] User behavior analytics
- [ ] Anomaly detection (ML-based)
- [ ] Auto-scaling based on metrics

---

**Related Documentation**:
- [Signal System](./signal-system.md)
- [Scanner System](./scanner.md)
- [Design Document](../design.md)

