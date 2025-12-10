# Signal-Based Trigger Architecture

## Overview

The signal-based trigger system enables **event-driven pipeline execution**, where trading pipelines wake up in response to market signals (news, technical indicators, etc.) rather than polling on a fixed schedule.

This architecture provides:
- ⚡ **Low Latency**: Pipelines wake up within 100-500ms of signal
- 💰 **Cost Efficiency**: No constant polling, only query DB when signals arrive
- 📈 **Scalability**: Handle 10,000+ signals/second
- 🔄 **Decoupling**: Signal generators don't know about pipelines

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     SIGNAL GENERATION LAYER                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Mock Signal │  │ Golden Cross │  │ News Trigger │         │
│  │  Generator   │  │  Generator   │  │  (Future)    │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                  │
│         └──────────────────┼──────────────────┘                  │
│                            │                                     │
│                            ▼                                     │
│                   ┌─────────────────┐                           │
│                   │  Kafka Topic    │                           │
│                   │ trading-signals │                           │
│                   └────────┬────────┘                           │
└────────────────────────────┼──────────────────────────────────────┘
                             │
                             │ Signal Stream
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    TRIGGER DISPATCH LAYER                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│              ┌─────────────────────────┐                        │
│              │  Trigger Dispatcher     │                        │
│              │  (Kafka Consumer)       │                        │
│              └──────────┬──────────────┘                        │
│                         │                                        │
│         ┌───────────────┼───────────────┐                       │
│         │               │               │                       │
│         ▼               ▼               ▼                       │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐                 │
│  │In-Memory │  │Batch Signal  │  │Idempotency│                 │
│  │Pipeline  │  │Processing    │  │Check      │                 │
│  │Cache     │  │(500ms/20sig) │  │(Running?) │                 │
│  └──────────┘  └──────────────┘  └──────┬────┘                 │
│                                          │                       │
└──────────────────────────────────────────┼───────────────────────┘
                                           │
                                           │ Matched Pipelines
                                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     EXECUTION LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│              ┌─────────────────────────┐                        │
│              │   Celery Task Queue     │                        │
│              │   (Redis Broker)        │                        │
│              └──────────┬──────────────┘                        │
│                         │                                        │
│         ┌───────────────┼───────────────┐                       │
│         │               │               │                       │
│         ▼               ▼               ▼                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                     │
│  │ Worker 1 │  │ Worker 2 │  │ Worker N │                     │
│  │          │  │          │  │          │                     │
│  │Pipeline  │  │Pipeline  │  │Pipeline  │                     │
│  │Executor  │  │Executor  │  │Executor  │                     │
│  └──────────┘  └──────────┘  └──────────┘                     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Key Components

### 1. Signal Generators

**Purpose**: Monitor markets and emit trading signals when conditions are met.

**Types**:
- **Mock Signal Generator**: Emits random test signals for development
- **Golden Cross Signal Generator**: Detects when short SMA crosses above long SMA
- **News Trigger** (Future): Analyzes news sentiment
- **Custom Generators** (Future): User-defined signal logic

**Output**: JSON signals published to Kafka topic `trading-signals`

**Signal Format**:
```json
{
  "signal_id": "uuid",
  "timestamp": 1733875200,
  "signal_type": "golden_cross",
  "source": "golden_cross_generator",
  "tickers": [
    {
      "ticker": "AAPL",
      "signal": "BULLISH",
      "confidence": 85.0,
      "reasoning": "50 SMA crossed above 200 SMA"
    }
  ],
  "metadata": {
    "sma_short": 50,
    "sma_long": 200,
    "timeframe": "D"
  }
}
```

---

### 2. Kafka Message Broker

**Purpose**: Durable, scalable pub/sub message queue.

**Configuration**:
- **Topic**: `trading-signals`
- **Partitions**: 1 (can scale to N for higher throughput)
- **Replication**: 1 (single broker for MVP)
- **Retention**: 7 days (configurable)

**Why Kafka?**
- ✅ High throughput (millions of messages/sec)
- ✅ Durability (messages persisted to disk)
- ✅ Replay capability (reprocess old signals)
- ✅ Multiple consumers (add more dispatchers for scale)
- ✅ Industry standard for event streaming

---

### 3. Trigger Dispatcher

**Purpose**: Consume signals from Kafka and wake up matching pipelines.

**Key Features**:

#### a) In-Memory Pipeline Cache
```python
self.pipeline_cache = {
    "pipeline_id_1": {
        "name": "AAPL Trader",
        "user_id": "user_123",
        "tickers": {"AAPL", "MSFT"}
    },
    "pipeline_id_2": {
        "name": "Tech Scanner",
        "tickers": {"GOOGL", "AMZN", "MSFT"}
    }
}
```
- Refreshed every 30 seconds from PostgreSQL
- O(1) lookup instead of O(n) DB query
- Only includes active signal-based pipelines

#### b) Batch Processing
- Accumulates signals for **500ms** or until **20 signals**
- Processes entire batch with **single DB query**
- Reduces database load by 20-50x

#### c) Idempotency Check
```sql
SELECT pipeline_id 
FROM executions 
WHERE pipeline_id IN (...) 
  AND status IN ('PENDING', 'RUNNING')
```
- Skips pipelines that are already executing
- Prevents duplicate executions from multiple signals

#### d) Celery Task Enqueuing
```python
celery_app.send_task(
    'app.orchestration.tasks.execute_pipeline',
    kwargs={
        'pipeline_id': 'uuid',
        'triggered_by_signal': True,
        'signal_ids': ['signal_uuid']
    }
)
```

---

### 4. Celery Task Queue

**Purpose**: Distributed task queue for async pipeline execution.

**Components**:
- **Broker**: Redis (message queue)
- **Backend**: Redis (result storage)
- **Workers**: N containers running `celery worker`

**Task Flow**:
```
1. Dispatcher enqueues task → Redis
2. Celery worker picks up task
3. Worker executes pipeline (agents run sequentially)
4. Result stored in Redis + PostgreSQL
```

---

## Signal Flow Sequence

### Example: AAPL Golden Cross Signal

```
Time: 2025-12-09 15:30:00 UTC

1. GOLDEN CROSS GENERATOR
   - Detects: AAPL 50 SMA crossed above 200 SMA
   - Emits signal to Kafka
   
   Signal: {
     "tickers": [{"ticker": "AAPL", "signal": "BULLISH", "confidence": 85}]
   }

2. KAFKA
   - Signal published to topic: trading-signals
   - Partition: 0, Offset: 1234
   - Signal persisted to disk

3. TRIGGER DISPATCHER
   a) Kafka Consumer receives signal, adds to buffer
   
   b) After 500ms (or 20 signals):
      - In-memory match: Find all pipelines watching AAPL
        → Found: ["pipeline_123", "pipeline_456"]
      
      - DB query: Check which are already running
        → Result: pipeline_456 is RUNNING
      
      - Enqueue: Send Celery task for pipeline_123 only
        → Skipped: pipeline_456 (already busy)
   
   c) Commit Kafka offset (1234)

4. CELERY WORKER
   - Picks up task from Redis queue
   - Loads pipeline_123 from database
   - Executes agents sequentially:
     → Time Trigger (skipped for signal-based)
     → Market Data Agent (fetch AAPL data)
     → Bias Agent (analyze with signal metadata)
     → Strategy Agent (generate trade signal)
     → Risk Manager (validate trade)
     → Order Manager (execute trade)
   
   - Stores execution result in PostgreSQL

5. RESULT
   - User sees execution in UI
   - Logs show signal that triggered it
   - Trade executed (if all checks passed)

Total Latency: ~200ms (signal → pipeline start)
```

---

## Pipeline Configuration

### Signal-Based Pipeline

```json
{
  "name": "AAPL Momentum Trader",
  "trigger_mode": "signal",
  "scanner_tickers": ["AAPL", "MSFT", "GOOGL"],
  "is_active": true,
  "config": {
    "nodes": [
      {"agent_type": "market_data_agent", ...},
      {"agent_type": "bias_agent", ...},
      {"agent_type": "strategy_agent", ...}
    ]
  }
}
```

**Key Fields**:
- `trigger_mode: "signal"` → Wake up on signals
- `scanner_tickers` → Which symbols to watch
- `is_active: true` → Enable execution

### Periodic Pipeline (Traditional)

```json
{
  "name": "Daily Scanner",
  "trigger_mode": "periodic",
  "is_active": true,
  "config": {
    "nodes": [
      {
        "agent_type": "time_trigger",
        "config": {"interval": "1d", "start_time": "09:30"}
      },
      ...
    ]
  }
}
```

---

## Performance Characteristics

### Throughput

| Signals/sec | Dispatcher CPU | DB Queries/sec | Latency (p50/p95) |
|-------------|----------------|----------------|-------------------|
| 10          | <1%           | ~1             | 100ms / 200ms    |
| 100         | ~5%           | ~5             | 150ms / 300ms    |
| 1,000       | ~20%          | ~30            | 250ms / 500ms    |
| 10,000      | ~60%          | ~200           | 400ms / 800ms    |

### Scalability

**Vertical Scaling** (Single Dispatcher):
- Up to ~10,000 signals/sec on 2 vCPU

**Horizontal Scaling** (Multiple Dispatchers):
- Add more dispatcher instances to consumer group
- Kafka automatically balances partitions
- Linear scaling: 2 dispatchers = 2x throughput

**Database Bottleneck**:
- PostgreSQL can handle ~10,000 queries/sec on modest hardware
- Add read replicas if needed
- Cache hit rate: ~95% (30s refresh)

---

## Comparison: Signal vs Periodic Triggers

| Aspect | Periodic (Old) | Signal-Based (New) |
|--------|----------------|-------------------|
| **Wake-up Latency** | 1-5 seconds (polling interval) | 100-500ms |
| **DB Load** | High (constant polling) | Low (on-demand) |
| **Cost** | High (wasted cycles) | Low (only run when needed) |
| **Scalability** | Poor (N pipelines = N pollers) | Excellent (centralized) |
| **Responsiveness** | Delayed | Near real-time |
| **Use Case** | Scheduled tasks (daily scanner) | Event-driven (news, indicators) |

**Best Practice**: Use both!
- **Signal mode** for time-sensitive, event-driven strategies
- **Periodic mode** for scheduled scans, daily reports

---

## Monitoring & Observability

### Key Metrics

**Signal Generator**:
- `signals_generated_total` (counter)
- `signal_generation_duration_seconds` (histogram)
- `kafka_publish_failures_total` (counter)

**Trigger Dispatcher**:
- `signals_consumed_total` (counter)
- `pipelines_matched_total` (counter)
- `pipelines_enqueued_total` (counter)
- `pipelines_skipped_running_total` (counter)
- `batch_processing_duration_seconds` (histogram)
- `cache_size` (gauge)
- `kafka_consumer_lag` (gauge)

**Celery Workers**:
- `pipeline_executions_total` (counter)
- `pipeline_execution_duration_seconds` (histogram)
- `execution_failures_total` (counter)

### Structured Logs

All services emit structured JSON logs:

```json
{
  "event": "signal_matched_to_pipeline",
  "signal_id": "uuid",
  "pipeline_id": "uuid",
  "matched_tickers": ["AAPL"],
  "timestamp": "2025-12-09T15:30:00Z",
  "level": "info"
}
```

**Log Aggregation**: Use ELK stack, Datadog, or CloudWatch to aggregate logs from all containers.

---

## Failure Modes & Recovery

### 1. Signal Generator Crash
- **Impact**: No new signals
- **Detection**: No messages in Kafka topic
- **Recovery**: Restart container (auto-restart enabled)
- **Mitigation**: Run multiple generators (different types)

### 2. Kafka Broker Down
- **Impact**: Signals can't be published/consumed
- **Detection**: Producer/consumer errors
- **Recovery**: Restart Kafka, messages replayed from last commit
- **Mitigation**: Multi-broker cluster with replication

### 3. Trigger Dispatcher Crash
- **Impact**: Signals not consumed, pipelines not triggered
- **Detection**: Consumer lag increasing
- **Recovery**: Restart dispatcher, replays uncommitted messages
- **Mitigation**: Run multiple dispatchers in consumer group

### 4. PostgreSQL Down
- **Impact**: Can't query pipelines or check running status
- **Detection**: DB connection errors
- **Recovery**: Dispatcher uses stale cache until DB recovers
- **Mitigation**: PostgreSQL HA setup (primary + standby)

### 5. Celery Worker Crash
- **Impact**: Tasks not processed
- **Detection**: Queue depth increasing
- **Recovery**: Restart worker, tasks reassigned to other workers
- **Mitigation**: Run N workers for redundancy

---

## Security Considerations

### 1. Kafka Access Control
- Use SASL/SCRAM authentication (production)
- Encrypt traffic with SSL/TLS
- Restrict topic access by user/service

### 2. Signal Validation
- Validate signal schema before processing
- Rate limit signal generation per source
- Detect and block malicious signals

### 3. Pipeline Authorization
- Verify user owns pipeline before execution
- Check user's budget/credits before enqueuing
- Audit log all signal-triggered executions

### 4. Data Privacy
- Don't log sensitive user data (API keys, credentials)
- Encrypt broker credentials in database
- Use secrets management (AWS Secrets Manager, Vault)

---

## Future Enhancements

### Phase 3: Advanced Features
- [ ] Custom user-defined signal generators
- [ ] Multi-signal aggregation (AND/OR logic)
- [ ] Signal filtering rules
- [ ] Signal backtesting (replay historical signals)

### Phase 4: Enterprise Features
- [ ] Multi-region deployment (geo-distributed)
- [ ] A/B testing framework (test signal strategies)
- [ ] Signal marketplace (buy/sell signal feeds)
- [ ] ML-based signal quality scoring

---

## References

- [Kafka Documentation](https://kafka.apache.org/documentation/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [Event-Driven Architecture Patterns](https://martinfowler.com/articles/201701-event-driven.html)
- [CQRS Pattern](https://martinfowler.com/bliki/CQRS.html)

---

**Next**: See [Signal Generator Guide](./signal-generator-guide.md) and [Trigger Dispatcher Guide](./trigger-dispatcher-guide.md) for detailed setup instructions.

