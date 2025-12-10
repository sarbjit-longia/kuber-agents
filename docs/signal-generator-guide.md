# Signal Generator Guide

## Overview

The Signal Generator service monitors markets and emits trading signals when specific conditions are met. Signals are published to Kafka for consumption by the Trigger Dispatcher.

---

## Architecture

```
┌──────────────────────┐
│  Signal Generators   │
│                      │
│  ┌────────────────┐ │
│  │ Mock Generator │ │  Emits random test signals
│  └────────────────┘ │
│                      │
│  ┌────────────────┐ │
│  │ Golden Cross   │ │  Detects SMA crossovers
│  └────────────────┘ │
│                      │
│  ┌────────────────┐ │
│  │  (Future)      │ │  News, RSI, Custom, etc.
│  └────────────────┘ │
│                      │
└──────────┬───────────┘
           │
           ▼
      ┌────────┐
      │ Kafka  │
      └────────┘
```

---

## Configuration

### Environment Variables

```bash
# Service
SERVICE_NAME=signal-generator
LOG_LEVEL=INFO

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_SIGNAL_TOPIC=trading-signals

# Finnhub API (for real market data)
FINNHUB_API_KEY=your_api_key_here

# Mock Generator
MOCK_GENERATOR_INTERVAL_SECONDS=60
MOCK_GENERATOR_EMISSION_PROBABILITY=0.3

# Golden Cross Generator
GOLDEN_CROSS_CHECK_INTERVAL_SECONDS=300
GOLDEN_CROSS_SMA_SHORT=50
GOLDEN_CROSS_SMA_LONG=200
GOLDEN_CROSS_TIMEFRAME=D
GOLDEN_CROSS_LOOKBACK_DAYS=250
GOLDEN_CROSS_CONFIDENCE=0.85
```

### Watchlist Configuration

Edit `signal-generator/config/watchlist.json` to configure which tickers to monitor:

```json
{
  "version": "1.0",
  "description": "Watchlist for signal generators",
  "tickers": [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "TSLA",
    "NVDA",
    "META"
  ]
}
```

**No rebuild required!** The watchlist is mounted as a volume.

---

## Signal Generators

### 1. Mock Signal Generator

**Purpose**: Generate random test signals for development and testing.

**Configuration**:
- `MOCK_GENERATOR_INTERVAL_SECONDS=60` → Check every 60 seconds
- `MOCK_GENERATOR_EMISSION_PROBABILITY=0.3` → 30% chance to emit

**Output Example**:
```json
{
  "signal_id": "uuid",
  "timestamp": 1733875200,
  "signal_type": "mock",
  "source": "mock_generator",
  "tickers": [
    {
      "ticker": "AAPL",
      "signal": "BULLISH",
      "confidence": 75.0,
      "reasoning": "Mock signal with BULLISH bias (test data)"
    },
    {
      "ticker": "MSFT",
      "signal": "BEARISH",
      "confidence": 82.0,
      "reasoning": "Mock signal with BEARISH bias (test data)"
    }
  ],
  "metadata": {
    "generator": "mock",
    "emission_probability": 0.3,
    "note": "This is test data for development"
  }
}
```

**When to Use**: Development, testing, demo

---

### 2. Golden Cross Signal Generator

**Purpose**: Detect when a short-term SMA crosses above a long-term SMA (bullish signal).

**Configuration**:
- `GOLDEN_CROSS_SMA_SHORT=50` → Short SMA period (50 days)
- `GOLDEN_CROSS_SMA_LONG=200` → Long SMA period (200 days)
- `GOLDEN_CROSS_TIMEFRAME=D` → Daily candles
- `GOLDEN_CROSS_CHECK_INTERVAL_SECONDS=300` → Check every 5 minutes
- `GOLDEN_CROSS_LOOKBACK_DAYS=250` → Fetch 250 days of history
- `GOLDEN_CROSS_CONFIDENCE=0.85` → 85% confidence score

**Logic**:
```python
if (previous_short_sma < previous_long_sma) and \
   (current_short_sma > current_long_sma):
    emit_signal(ticker, "BULLISH", confidence=85%)
```

**Output Example**:
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
      "reasoning": "Golden Cross detected: 50 SMA crossed above 200 SMA."
    }
  ],
  "metadata": {
    "generator": "golden_cross",
    "sma_short": 50,
    "sma_long": 200,
    "timeframe": "D"
  }
}
```

**Requirements**: Requires Finnhub API key for real market data.

**When to Use**: Production, real trading strategies

---

## Running the Service

### With Docker Compose

```bash
# Start all dependencies
docker-compose up -d zookeeper kafka

# Start signal generator
docker-compose up -d signal-generator
```

### View Logs

```bash
docker logs -f trading-signal-generator
```

**Expected Output**:
```
================================================================================
🔔 SIGNAL GENERATED: MOCK
   ID: uuid
   Source: mock_generator
   Timestamp: 2025-12-09 15:30:00 UTC
   📤 Published to Kafka: trading-signals
   Tickers:
     • AAPL: BULLISH (confidence: 75%)
       → Mock signal with BULLISH bias (test data)
================================================================================
```

### Stop Service

```bash
docker-compose stop signal-generator
```

---

## Adding Custom Generators

### Step 1: Create Generator Class

Create `signal-generator/app/generators/my_generator.py`:

```python
from typing import List
from app.generators.base import BaseSignalGenerator
from app.schemas.signal import Signal, TickerSignal, BiasType, SignalType


class MyCustomSignalGenerator(BaseSignalGenerator):
    """Custom signal generator for specific strategy."""
    
    generator_type: SignalType = SignalType.CUSTOM  # Add to SignalType enum
    
    def __init__(self, settings, watchlist: List[str]):
        super().__init__(settings, watchlist)
        # Initialize your custom logic here
        self.my_threshold = settings.MY_CUSTOM_THRESHOLD
    
    async def generate_signals(self) -> List[Signal]:
        """
        Implement your signal generation logic.
        
        Returns:
            List of Signal objects to emit
        """
        signals = []
        
        for ticker in self.watchlist:
            # Your custom logic here
            if self._should_emit_signal(ticker):
                ticker_signal = TickerSignal(
                    ticker=ticker,
                    signal=BiasType.BULLISH,  # or BEARISH, NEUTRAL
                    confidence=80.0,
                    reasoning="My custom condition met"
                )
                
                signals.append(
                    Signal(
                        signal_id=uuid.uuid4(),
                        timestamp=int(datetime.now(timezone.utc).timestamp()),
                        signal_type=self.generator_type,
                        source=self.__class__.__name__.replace("SignalGenerator", "").lower(),
                        tickers=[ticker_signal],
                        metadata={"custom_param": "value"}
                    )
                )
        
        return signals
    
    def _should_emit_signal(self, ticker: str) -> bool:
        """Your custom signal logic."""
        # Implement your conditions here
        return True  # Example
```

### Step 2: Register Generator

Edit `signal-generator/app/main.py`:

```python
from app.generators.my_generator import MyCustomSignalGenerator

# In main() function
if __name__ == "__main__":
    SignalGeneratorRegistry.register(MockSignalGenerator)
    SignalGeneratorRegistry.register(GoldenCrossSignalGenerator)
    SignalGeneratorRegistry.register(MyCustomSignalGenerator)  # Add this
    asyncio.run(main())
```

### Step 3: Add Configuration

Add to `.env`:

```bash
MY_CUSTOM_THRESHOLD=0.75
MY_CUSTOM_CHECK_INTERVAL_SECONDS=60
```

Add to `app/config.py`:

```python
MY_CUSTOM_THRESHOLD: float = 0.75
MY_CUSTOM_CHECK_INTERVAL_SECONDS: int = 60
```

### Step 4: Update Signal Type Enum

Edit `backend/app/schemas/signal.py`:

```python
class SignalType(str, Enum):
    MOCK = "mock"
    GOLDENCROSS = "golden_cross"
    CUSTOM = "my_custom"  # Add this
```

### Step 5: Rebuild and Test

```bash
docker-compose up --build -d signal-generator
docker logs -f trading-signal-generator
```

---

## Signal Schema

### Required Fields

```python
class Signal:
    signal_id: UUID              # Unique identifier
    timestamp: int               # Unix epoch (seconds)
    signal_type: SignalType      # Type of signal (enum)
    source: str                  # Generator name
    tickers: List[TickerSignal]  # List of ticker signals
    metadata: Dict[str, Any]     # Additional context
```

### Ticker Signal

```python
class TickerSignal:
    ticker: str           # Symbol (e.g., "AAPL")
    signal: BiasType      # BULLISH, BEARISH, NEUTRAL
    confidence: float     # 0-100 scale
    reasoning: str        # Human-readable explanation
```

---

## Troubleshooting

### "Kafka connection failed"

**Symptoms**:
```
kafka_producer_initialization_failed
error: "NoBrokersAvailable"
```

**Solutions**:
1. Check Kafka is running: `docker ps | grep kafka`
2. Check Kafka health: `docker logs trading-kafka`
3. Verify `KAFKA_BOOTSTRAP_SERVERS=kafka:9092`
4. Wait for Kafka to be healthy (can take 30-60s on first start)

---

### "Insufficient data for golden cross"

**Symptoms**:
```
{"ticker": "AAPL", "required": 200, "available": 176, "event": "insufficient_data_for_golden_cross"}
```

**Cause**: Finnhub free tier has limited history (usually 6-12 months).

**Solutions**:
1. Reduce `GOLDEN_CROSS_LOOKBACK_DAYS` (e.g., 180 days)
2. Reduce `GOLDEN_CROSS_SMA_LONG` (e.g., 100 instead of 200)
3. Upgrade to Finnhub paid plan
4. Use different data source (e.g., Yahoo Finance)

---

### "No signals generated"

**For Mock Generator**:
- Check `MOCK_GENERATOR_EMISSION_PROBABILITY` (increase to 1.0 for always-emit)
- Wait for `MOCK_GENERATOR_INTERVAL_SECONDS` to pass

**For Golden Cross**:
- Ensure market conditions meet criteria (crossover must occur)
- Check logs for `golden_cross_scan_completed` with count
- May take days/weeks for real signals (rare event)

---

### "Signals not published to Kafka"

**Symptoms**:
```
signals_will_only_log
message: "Kafka unavailable, falling back to logs only"
```

**Cause**: Kafka producer initialization failed, but service continues.

**Solutions**:
1. Fix Kafka connection
2. Restart signal-generator: `docker-compose restart signal-generator`

---

## Performance Tuning

### High Frequency Signals

If generating many signals (100+/min):

1. **Batch Publishing**: Modify producer to batch multiple signals
2. **Compression**: Enable Kafka compression (`compression_type='gzip'`)
3. **Async Publishi**: Use `producer.send()` without waiting for `.get()`

Example:

```python
futures = []
for signal in signals:
    future = self.kafka_producer.send(topic, value=message)
    futures.append(future)

# Wait for all at once
for future in futures:
    future.get(timeout=10)
```

### Reducing API Costs

For Finnhub or paid data sources:

1. **Increase check intervals**: `CHECK_INTERVAL_SECONDS=600` (10 min)
2. **Reduce watchlist**: Monitor fewer tickers
3. **Cache data**: Store recent candles, only fetch new ones
4. **Use websockets**: Subscribe to real-time feeds instead of polling

---

## Monitoring

### Key Metrics

```python
signals_generated_total          # Counter
signal_generation_duration_ms    # Histogram
kafka_publish_success_total      # Counter
kafka_publish_failure_total      # Counter
market_data_api_calls_total      # Counter (track costs)
```

### Health Check

```bash
# Check if signals are being generated
docker exec trading-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic trading-signals \
  --from-beginning \
  --max-messages 1
```

**Expected**: See recent signal JSON

---

## Production Checklist

- [ ] Set real Finnhub API key (not free tier)
- [ ] Configure watchlist with actual trading symbols
- [ ] Set appropriate check intervals (balance latency vs cost)
- [ ] Enable Kafka SSL/SASL for security
- [ ] Set up log aggregation (ELK, Datadog, CloudWatch)
- [ ] Configure alerts for generator failures
- [ ] Implement rate limiting per generator
- [ ] Add signal validation/sanitization
- [ ] Test failover (Kafka down, API down)
- [ ] Document custom generators for team

---

## References

- [Finnhub API Docs](https://finnhub.io/docs/api)
- [Technical Indicators (Golden Cross)](https://www.investopedia.com/terms/g/goldencross.asp)
- [Kafka Producer API](https://kafka-python.readthedocs.io/en/master/apidoc/KafkaProducer.html)

---

**Next**: See [Trigger Dispatcher Guide](./trigger-dispatcher-guide.md)

