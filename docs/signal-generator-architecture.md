# Signal Generator Architecture

## Overview

The Signal Generator is a new microservice architecture for waking up trading pipelines. It replaces the per-pipeline polling model with an event-driven signal bus architecture.

**Date:** December 2025  
**Status:** Phase 1 Implemented  
**Version:** 1.0

---

## Problem Statement

### Old Architecture Issues
- **High latency:** Pipelines poll every N seconds, missing real-time opportunities
- **Resource waste:** Every pipeline runs its own scheduler
- **Scalability:** Doesn't scale to thousands of users
- **Complexity:** Trigger logic embedded in pipelines

### Solution: Signal Generator + Event Bus

Centralized signal generation with pub/sub distribution to pipelines.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SIGNAL GENERATOR SERVICE                     │
│                                                                     │
│  ┌──────────────────┐    ┌──────────────────┐                     │
│  │ Mock Generator   │    │ Golden Cross Gen │                     │
│  │ (Test signals)   │    │ (SMA crossover)  │                     │
│  └────────┬─────────┘    └────────┬─────────┘                     │
│           │                       │                                │
│           └───────────┬───────────┘                                │
│                       ▼                                            │
│            ┌─────────────────────┐                                 │
│            │   Signal Emitter    │                                 │
│            │  (Phase 1: stdout)  │                                 │
│            │  (Phase 2: Kafka)   │                                 │
│            └──────────┬──────────┘                                 │
└────────────────────────┼──────────────────────────────────────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │    Kafka Topic         │  ← Phase 2
            │  "trading-signals"     │
            └────────┬───────────────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
         ▼           ▼           ▼
    ┌────────┐  ┌────────┐  ┌────────┐
    │Pipeline│  │Pipeline│  │Pipeline│
    │   #1   │  │   #2   │  │   #3   │
    └────────┘  └────────┘  └────────┘
```

---

## Components

### 1. Signal Generator Service

**Location:** `/signal-generator/`  
**Language:** Python 3.11+  
**Deployment:** Separate Docker container

**Responsibilities:**
- Run multiple signal generators concurrently
- Emit signals to output (stdout in Phase 1, Kafka in Phase 2)
- Monitor watchlist of tickers
- Aggregate signals from multiple sources

### 2. Signal Generators

**Base Class:** `BaseSignalGenerator`

**Current Implementations:**

#### MockSignalGenerator
- **Purpose:** Testing and development
- **Logic:** Random signal generation based on probability
- **Config:**
  - `tickers`: List of symbols
  - `emission_probability`: 0-1 chance of emitting
  - `bias_options`: Allowed bias types
- **Interval:** 60 seconds (configurable)

#### GoldenCrossSignalGenerator
- **Purpose:** Detect bullish SMA crossovers
- **Logic:** 50-day SMA crosses above 200-day SMA
- **Config:**
  - `tickers`: Watchlist
  - `sma_short`: 50 (default)
  - `sma_long`: 200 (default)
  - `timeframe`: "D" (daily)
  - `lookback_days`: 5 (recent window)
  - `confidence`: 0.85
- **Interval:** 300 seconds (5 minutes)
- **Data Source:** Finnhub API

**Future Generators:**
- NewsSignalGenerator (news sentiment analysis)
- DeathCrossGenerator (bearish SMA crossover)
- VolatilityBreakoutGenerator (volatility spikes)
- PriceLevelGenerator (support/resistance breaks)
- ExternalSignalGenerator (webhooks, TradingView alerts)

### 3. Signal Schema

**File:** `backend/app/schemas/signal.py`

```python
class Signal(BaseModel):
    signal_id: UUID
    signal_type: SignalType  # GOLDEN_CROSS, NEWS, etc.
    tickers: List[str]       # Affected symbols
    bias: Dict[str, SignalBias]  # Per-ticker bias
    metadata: Dict[str, Any]     # Generator-specific data
    timestamp: datetime
    source: str              # Generator name
```

**Example Signal:**
```json
{
  "signal_id": "550e8400-e29b-41d4-a716-446655440000",
  "signal_type": "golden_cross",
  "tickers": ["AAPL"],
  "bias": {
    "AAPL": {
      "ticker": "AAPL",
      "bias": "BULLISH",
      "confidence": 0.85,
      "reasoning": "50-day SMA crossed above 200-day SMA"
    }
  },
  "metadata": {
    "sma_short": 50,
    "sma_long": 200,
    "current_price": 175.50
  },
  "timestamp": "2025-12-05T10:30:00Z",
  "source": "golden_cross_generator"
}
```

---

## Implementation Phases

### ✅ Phase 1: MVP (Implemented)

**Goal:** Standalone signal generator emitting to stdout/logs

**Deliverables:**
- ✅ Signal schema (`Signal`, `SignalBias`, `SignalType`)
- ✅ Base generator framework (`BaseSignalGenerator`, registry)
- ✅ Mock generator (testing)
- ✅ Golden cross generator (real signals)
- ✅ Service runner with concurrent generators
- ✅ Unit tests (schema, mock, golden cross)
- ✅ Docker container
- ✅ Documentation

**Testing:**
```bash
# Run locally
cd signal-generator
python -m app.main

# Run in Docker
docker-compose up signal-generator

# Run tests
pytest tests/ -v
```

**Current Output:** Signals logged to stdout (see console)

---

### 🚧 Phase 2: Kafka Integration (Next)

**Goal:** Publish signals to Kafka topic for pipeline consumption

**Tasks:**
1. Add Kafka container to `docker-compose.yml`
2. Update signal emitter to publish to Kafka topic `trading-signals`
3. Create `TriggerDispatcherService` to consume signals
4. Match signals to pipelines based on scanner config
5. Enqueue pipeline executions via Celery
6. Add signal history tracking (database)
7. Add idempotency (prevent duplicate executions)

**Changes to Pipeline:**
- Add `trigger_mode` field: `"signal"` or `"periodic"`
- If `signal`: Wake on matching Kafka messages
- If `periodic`: Use Celery Beat scheduler (existing)

**Changes to Backend:**
- `/api/v1/pipelines` endpoint: Add `trigger_mode` to schema
- Trigger Dispatcher service: New service consuming Kafka
- Pipeline matching logic: Match signal tickers to scanner config

---

### 🔮 Phase 3: Advanced Features (Future)

**Features:**
- Dead-letter queue for failed signals
- Signal replay (reprocess historical signals)
- Signal aggregation (combine multiple signals)
- User-defined signal generators (custom webhooks)
- Signal analytics dashboard
- Rate limiting per user
- Cost tracking per generator

---

## Configuration

### Watchlist Configuration

Tickers are configured in `signal-generator/config/watchlist.json`:

```json
{
  "version": "1.0",
  "description": "Watchlist configuration for signal generators",
  "tickers": [
    "AAPL",
    "MSFT",
    "GOOGL",
    "..."
  ]
}
```

**Benefits:**
- Easy to expand (just add to JSON array)
- No container rebuild needed (mounted as volume in Docker)
- Version controlled
- Supports metadata and documentation

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FINNHUB_API_KEY` | Finnhub API key (required) | - |
| `WATCHLIST_CONFIG_PATH` | Path to watchlist config file | `config/watchlist.json` |
| `MOCK_GENERATOR_INTERVAL_SECONDS` | Mock emit interval | `60` |
| `GOLDEN_CROSS_CHECK_INTERVAL_SECONDS` | Golden cross check interval | `300` |
| `LOG_LEVEL` | Logging level | `INFO` |

---

## Adding New Generators

### Step 1: Create Generator Class

```python
# app/generators/my_generator.py
from app.generators.base import BaseSignalGenerator
from app.schemas.signal import Signal, SignalType

class MyCustomGenerator(BaseSignalGenerator):
    async def generate(self) -> List[Signal]:
        # Your logic here
        signals = []
        
        # Check conditions
        if condition_met:
            signal = Signal(
                signal_type=SignalType.CUSTOM,
                tickers=["AAPL"],
                bias={...},
                metadata={...},
                source="my_custom_generator"
            )
            signals.append(signal)
        
        return signals
```

### Step 2: Register Generator

```python
# app/generators/__init__.py
from app.generators.my_generator import MyCustomGenerator

def _initialize_registry():
    registry = get_registry()
    registry.register(MyCustomGenerator)
```

### Step 3: Add to Service

```python
# app/main.py - _initialize_generators()
my_config = {"param": "value"}
self.generators.append({
    "name": "my_custom",
    "generator": MyCustomGenerator(my_config),
    "interval": 120  # seconds
})
```

### Step 4: Add Tests

```python
# tests/test_my_generator.py
@pytest.mark.asyncio
async def test_my_generator():
    config = {...}
    generator = MyCustomGenerator(config)
    signals = await generator.generate()
    assert len(signals) > 0
```

---

## Testing

### Run All Tests

```bash
cd signal-generator
pytest tests/ -v
```

### Run Specific Tests

```bash
pytest tests/test_signal_schema.py -v
pytest tests/test_mock_generator.py -v
pytest tests/test_golden_cross.py -v
```

### Test Coverage

```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

---

## Deployment

### Local Development

```bash
# Start signal generator only
docker-compose up signal-generator

# Start entire stack
docker-compose up
```

### Production

```bash
# Build production image
docker build -t signal-generator:prod -f signal-generator/Dockerfile signal-generator/

# Run with env file
docker run --env-file .env signal-generator:prod
```

---

## Monitoring & Debugging

### Logs

**Structured JSON logs:**
```json
{
  "event": "signal_emitted",
  "signal_id": "...",
  "signal_type": "golden_cross",
  "tickers": ["AAPL"],
  "timestamp": "2025-12-05T10:30:00Z"
}
```

**View logs:**
```bash
docker logs -f trading-signal-generator
```

### Common Issues

**1. No signals generated**
- Check generator intervals (may need to wait)
- Mock generator: `emission_probability` is random
- Golden cross: Rare pattern, may take time

**2. Finnhub API errors**
- Check `FINNHUB_API_KEY` is set
- Free tier: 60 calls/min
- Reduce watchlist size or increase interval

**3. Golden cross not detected**
- Pattern is rare (may take weeks/months)
- Use mock data for testing
- Check logs for "insufficient_data" warnings

---

## Performance Considerations

### Scalability

- **Concurrent generators:** Each runs in separate asyncio task
- **Market data caching:** Future enhancement (cache Finnhub responses)
- **Rate limiting:** Respect API limits (60/min for Finnhub free tier)

### Resource Usage

- **CPU:** Low (async I/O, no heavy computation)
- **Memory:** ~100MB per container
- **Network:** Depends on generator count and intervals
- **Finnhub API calls:** `(num_tickers * num_generators * (3600/interval)) / hour`

**Example:** 10 tickers, 1 golden cross generator, 5-min interval:
- API calls: `10 * (60/5) = 120 calls/hour` (within free tier)

---

## Migration Path

### From Old Architecture

**Old (Per-Pipeline Polling):**
```python
# TimeTriggerAgent in each pipeline
if current_time matches config:
    execute_pipeline()
```

**New (Signal-Driven):**
```python
# Signal Generator (centralized)
if golden_cross_detected(ticker):
    emit_signal(ticker, bias=BULLISH)

# Pipeline Dispatcher (Phase 2)
def on_signal_received(signal):
    matching_pipelines = find_by_scanner(signal.tickers)
    for pipeline in matching_pipelines:
        if pipeline.trigger_mode == "signal":
            execute_pipeline(pipeline, signal)
```

**Benefits:**
1. ✅ Lower latency (real-time vs polling)
2. ✅ Better resource efficiency (one scheduler vs per-pipeline)
3. ✅ Scalability (handles thousands of pipelines)
4. ✅ Separation of concerns (trigger logic separate from execution)

---

## Future Enhancements

### Short-term (Phase 2)
- Kafka integration
- Trigger Dispatcher service
- Signal-to-pipeline matching
- Idempotency

### Mid-term
- More generators (news, death cross, volatility)
- Signal history tracking
- Signal replay
- User-defined generators (webhooks)

### Long-term
- Signal marketplace (users create/sell generators)
- Advanced signal aggregation
- Machine learning-based generators
- Custom backtesting against signals

---

## Conclusion

The Signal Generator architecture provides a **scalable, event-driven foundation** for waking up trading pipelines. Phase 1 (MVP) is complete and ready for testing. Phase 2 (Kafka integration) will enable real-time signal distribution to pipelines.

**Next Steps:**
1. Test Phase 1 (run signal generator, verify output)
2. Plan Phase 2 (Kafka setup, trigger dispatcher)
3. Add more generators (news, death cross)
4. Integrate with pipeline execution flow

