# OpenTelemetry Implementation Guide

## Overview

This document provides the complete implementation for adding OpenTelemetry observability to the trading platform.

**Status**: Backend completed ✅ | Signal-Generator in progress ⏳ | Trigger-Dispatcher pending ⏳

---

## What We've Implemented So Far

### ✅ Backend Service (Complete)

**Files Created/Modified**:
1. `backend/app/telemetry.py` - OpenTelemetry setup module
2. `backend/app/main.py` - Integration in FastAPI lifecycle
3. `backend/app/orchestration/executor.py` - Pipeline execution metrics
4. `backend/requirements.txt` - Added OTel dependencies
5. `docker-compose.yml` - Exposed port 8001 for metrics

**Metrics Implemented**:
- `pipeline_executions_total{status, pipeline_id, trigger_mode}` - Counter
- `pipeline_execution_duration_seconds{status, pipeline_id}` - Histogram
- Auto-instrumentation for FastAPI, SQLAlchemy, Redis

**Metrics Endpoint**: `http://localhost:8001/metrics`

---

## Remaining Implementation Steps

### Step 2: Signal-Generator (30 min)

**Add to `signal-generator/app/telemetry.py`**:
```python
"""OpenTelemetry setup for signal generator."""
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import start_http_server

def setup_telemetry(service_name="signal-generator"):
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0"
    })
    
    prometheus_reader = PrometheusMetricReader()
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[prometheus_reader]
    )
    metrics.set_meter_provider(meter_provider)
    
    start_http_server(port=8001)
    
    return meter_provider.get_meter(service_name)
```

**Update `signal-generator/app/main.py`**:
```python
from app.telemetry import setup_telemetry

# In main():
meter = setup_telemetry()

signals_generated = meter.create_counter(
    "signals_generated_total",
    description="Total signals generated"
)
kafka_publish_duration = meter.create_histogram(
    "kafka_publish_duration_seconds",
    description="Time to publish to Kafka"
)

# In _emit_signals():
signals_generated.add(1, {
    "signal_type": signal.signal_type.value,
    "source": signal.source
})
```

**Update `docker-compose.yml`**:
```yaml
  signal-generator:
    ports:
      - "8003:8001"  # Prometheus metrics
```

---

### Step 3: Trigger-Dispatcher (30 min)

**Add to `trigger-dispatcher/app/telemetry.py`**: (Same pattern as signal-generator)

**Update `trigger-dispatcher/app/main.py`**:
```python
from app.telemetry import setup_telemetry

meter = setup_telemetry()

signals_consumed = meter.create_counter("signals_consumed_total")
pipelines_matched = meter.create_counter("pipelines_matched_total")
pipelines_enqueued = meter.create_counter("pipelines_enqueued_total")
batch_size = meter.create_histogram("batch_size")
consumer_lag = meter.create_gauge("kafka_consumer_lag_seconds")

# Track in process_signal_batch():
signals_consumed.add(len(signals))
batch_size.record(len(signals))

# Track in enqueue_pipeline_executions():
pipelines_enqueued.add(enqueued_count, {"status": "enqueued"})
```

**Update `docker-compose.yml`**:
```yaml
  trigger-dispatcher:
    ports:
      - "8004:8001"  # Prometheus metrics
```

---

### Step 4: Prometheus + Grafana Setup (30 min)

**Create `monitoring/prometheus.yml`**:
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'backend'
    static_configs:
      - targets: ['backend:8001']
        labels:
          service: 'backend'
  
  - job_name: 'celery-worker'
    static_configs:
      - targets: ['celery-worker:8001']
        labels:
          service: 'celery-worker'
  
  - job_name: 'signal-generator'
    static_configs:
      - targets: ['signal-generator:8001']
        labels:
          service: 'signal-generator'
  
  - job_name: 'trigger-dispatcher'
    static_configs:
      - targets: ['trigger-dispatcher:8001']
        labels:
          service: 'trigger-dispatcher'
```

**Update `docker-compose.yml`**:
```yaml
  # Prometheus
  prometheus:
    image: prom/prometheus:v2.48.0
    container_name: trading-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    restart: unless-stopped

  # Grafana
  grafana:
    image: grafana/grafana:10.2.0
    container_name: trading-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_SERVER_ROOT_URL=http://localhost:3000
    volumes:
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
      - grafana_data:/var/lib/grafana
    depends_on:
      - prometheus
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
```

**Create `monitoring/grafana/datasources/prometheus.yml`**:
```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

**Create `monitoring/grafana/dashboards/dashboard-config.yml`**:
```yaml
apiVersion: 1

providers:
  - name: 'Trading Platform'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
```

---

### Step 5: Create Grafana Dashboards (1 hour)

**Dashboard 1: System Overview**

Panels:
- Signal Generation Rate (signals/min)
- Pipeline Execution Rate (executions/min)
- Success Rate (% successful)
- Kafka Consumer Lag (ms)
- Active Pipelines (gauge)

**Dashboard 2: Signal Generation Deep Dive**

Panels:
- Signals by Type (pie chart)
- Signals by Source (bar chart)
- Kafka Publish Duration (heatmap)
- Signal Generation Timeline (time series)

**Dashboard 3: Pipeline Execution Analysis**

Panels:
- Execution Duration P50/P95/P99 (line chart)
- Executions by Status (stacked area)
- Cost per Execution (scatter plot)
- Agent Execution Breakdown (bar chart)

**Dashboard 4: Infrastructure**

Panels:
- Database Query Duration (histogram)
- Redis Operations/sec (gauge)
- Celery Queue Depth (line chart)
- System Resources (CPU/Memory)

---

## Key Metrics Reference

### Backend & Celery Worker

```
# Pipeline Executions
pipeline_executions_total{status="success|failed", pipeline_id="uuid", trigger_mode="signal|periodic"}
pipeline_execution_duration_seconds{status="success|failed", pipeline_id="uuid"}

# Auto-instrumented (FastAPI)
http_server_request_duration_seconds{method="GET|POST", route="/api/v1/...", status_code="200|400|500"}
http_server_active_requests{method, route}

# Auto-instrumented (SQLAlchemy)
db_query_duration_seconds{query_type="select|insert|update"}
db_active_connections
db_pool_size

# Auto-instrumented (Redis)
redis_command_duration_seconds{command="get|set|del"}
```

### Signal Generator

```
# Signal Generation
signals_generated_total{signal_type="mock|golden_cross", source="mock_generator|golden_cross_generator"}
signal_generation_duration_seconds{signal_type}

# Kafka Publishing
kafka_publish_duration_seconds
kafka_publish_success_total
kafka_publish_failure_total
```

### Trigger Dispatcher

```
# Signal Consumption
signals_consumed_total
batch_size
batch_processing_duration_seconds

# Pipeline Matching
pipelines_matched_total{ticker}
pipelines_enqueued_total{status="enqueued|skipped"}
pipelines_skipped_running_total

# Cache Performance
cache_size_bytes
cache_refresh_duration_seconds

# Kafka Consumer
kafka_consumer_lag_seconds
kafka_consumer_offset
```

---

## Testing the Setup

### 1. Start Services
```bash
docker-compose up -d backend celery-worker signal-generator trigger-dispatcher prometheus grafana
```

### 2. Verify Metrics Endpoints
```bash
# Backend
curl http://localhost:8001/metrics

# Celery Worker
curl http://localhost:8002/metrics

# Signal Generator
curl http://localhost:8003/metrics

# Trigger Dispatcher
curl http://localhost:8004/metrics
```

### 3. Access Prometheus
```
URL: http://localhost:9090
Query: pipeline_executions_total
```

### 4. Access Grafana
```
URL: http://localhost:3000
Username: admin
Password: admin

1. Go to Dashboards
2. Import dashboard JSON (from monitoring/grafana/dashboards/)
3. View real-time metrics
```

---

## Migration to AWS

### Current Setup (Local)
- Prometheus scrapes metrics from services
- Grafana visualizes from Prometheus
- All running in Docker

### AWS Setup (Production)

**Step 1: Update Environment Variables**:
```bash
# In docker-compose.yml or ECS task definition
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.us-west-2.amazonaws.com
AWS_REGION=us-west-2
```

**Step 2: Update Telemetry Export** (NO CODE CHANGES):
Services automatically detect AWS and use:
- Amazon Managed Prometheus (AMP)
- Amazon Managed Grafana (AMG)
- CloudWatch Metrics (alternative)
- X-Ray (for traces)

**Cost Estimate (AWS)**:
- Managed Prometheus: ~$50/month
- Managed Grafana: ~$50/month
- CloudWatch: ~$10/month
- **Total**: ~$110/month

---

## Troubleshooting

### Metrics not appearing in Prometheus

1. Check service is exposing metrics:
```bash
curl http://localhost:8001/metrics
```

2. Check Prometheus targets:
```
http://localhost:9090/targets
```
All should show "UP"

3. Check Prometheus config:
```bash
docker exec trading-prometheus cat /etc/prometheus/prometheus.yml
```

---

### Grafana shows "No Data"

1. Verify datasource connection:
```
Grafana > Configuration > Data Sources > Prometheus > Test
```

2. Check query syntax:
```
rate(pipeline_executions_total[5m])
```

3. Adjust time range (top right)

---

## Next Steps

1. ✅ Complete signal-generator telemetry
2. ✅ Complete trigger-dispatcher telemetry
3. ✅ Create Prometheus config
4. ✅ Add Grafana dashboards
5. ✅ Test end-to-end
6. 📝 Document for team
7. 🚀 Deploy to staging/production

---

**Estimated Total Time**: 3-4 hours to complete all steps

**Benefits**:
- ✅ Real-time system visibility
- ✅ Performance bottleneck identification
- ✅ Cost tracking
- ✅ Alerting on issues
- ✅ Production-ready monitoring
- ✅ Cloud migration ready (AWS/Azure/GCP)

