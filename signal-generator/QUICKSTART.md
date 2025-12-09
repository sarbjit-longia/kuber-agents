# Signal Generator Quick Start Guide

Get the signal generator running in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- Finnhub API key ([Get one here](https://finnhub.io/register))

## Quick Start

### Option 1: Run with Docker Compose (Recommended)

1. **Ensure Finnhub API key is set:**

```bash
# Add to your root .env file (or export in shell)
echo "FINNHUB_API_KEY=your_api_key_here" >> ../.env
```

2. **Start the signal generator:**

```bash
# From project root
docker-compose up signal-generator
```

3. **Watch for signals:**

You'll see output like:
```
================================================================================
🔔 SIGNAL GENERATED: GOLDEN_CROSS
   ID: 550e8400-e29b-41d4-a716-446655440000
   Tickers: AAPL
   Source: golden_cross_generator
   Timestamp: 2025-12-05 14:30:00 UTC
   Bias:
     AAPL: BULLISH (confidence: 0.85)
       → 50-day SMA crossed above 200-day SMA
================================================================================
```

### Option 2: Run Locally (Development)

1. **Create virtual environment:**

```bash
cd signal-generator
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. **Install dependencies:**

```bash
pip install -r requirements.txt
```

3. **Create .env file:**

```bash
# Copy from example
cp env.example .env

# Edit and add your Finnhub API key
# FINNHUB_API_KEY=your_api_key_here
```

4. **Configure watchlist (optional):**

Edit `config/watchlist.json` to add/remove tickers:

```json
{
  "tickers": [
    "AAPL",
    "MSFT",
    "GOOGL"
  ]
}
```

5. **Run the service:**

```bash
python -m app.main
```

## Testing

### Run Unit Tests

```bash
# Install dev dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/ -v
```

### Expected Test Output

```
tests/test_signal_schema.py::test_signal_bias_creation PASSED
tests/test_signal_schema.py::test_signal_creation PASSED
tests/test_signal_schema.py::test_signal_to_kafka_message PASSED
tests/test_mock_generator.py::test_mock_generator_creation PASSED
tests/test_mock_generator.py::test_mock_generator_always_emit PASSED
tests/test_golden_cross.py::test_golden_cross_detection PASSED
```

## Configuration

### Quick Config Examples

**Testing (Mock signals every 30 seconds):**

1. Edit `.env`:
```bash
MOCK_GENERATOR_INTERVAL_SECONDS=30
GOLDEN_CROSS_CHECK_INTERVAL_SECONDS=600
```

2. Edit `config/watchlist.json` (small list):
```json
{
  "tickers": ["AAPL", "MSFT"]
}
```

**Production (Real signals, larger watchlist):**

1. Edit `.env`:
```bash
MOCK_GENERATOR_INTERVAL_SECONDS=3600  # Disable or slow down
GOLDEN_CROSS_CHECK_INTERVAL_SECONDS=300
```

2. Edit `config/watchlist.json` (large list):
```json
{
  "tickers": [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
    "META", "NVDA", "AMD", "NFLX", "SPY"
  ]
}
```

## Troubleshooting

### No signals appearing

**Mock Generator:**
- Check: `emission_probability` is random (default 30% chance)
- Solution: Set to `1.0` for guaranteed signals:
  ```bash
  # Modify app/main.py MockSignalGenerator config
  "emission_probability": 1.0
  ```

**Golden Cross Generator:**
- Check: Golden cross is rare, may take time
- Check: Finnhub API key is valid
- Solution: Check logs for errors:
  ```bash
  docker logs -f trading-signal-generator 2>&1 | grep ERROR
  ```

### Finnhub API rate limit errors

**Error:** `429 Too Many Requests`

**Solution:**
- Reduce watchlist size (fewer tickers)
- Increase check interval:
  ```bash
  GOLDEN_CROSS_CHECK_INTERVAL_SECONDS=600  # 10 minutes instead of 5
  ```
- Free tier: 60 calls/min

### Service crashes on startup

**Check:**
1. Finnhub API key is set
2. Dependencies installed
3. Python 3.11+ is being used

**Debug:**
```bash
docker logs trading-signal-generator
```

## Next Steps

1. ✅ **Phase 1 Complete:** Signal generator runs and emits signals
2. 🚧 **Phase 2 (Next):** Integrate with Kafka for pipeline consumption
3. 🔮 **Future:** Add more generators (news, volatility, custom webhooks)

## Verify It's Working

### Expected Logs

**Startup:**
```
🚀 Signal Generator Service Starting...
   Generators: 2
   Watchlist: ['AAPL', 'MSFT', 'GOOGL', ...]
   Log Level: INFO
```

**Generator Started:**
```json
{
  "event": "generator_started",
  "generator": "mock",
  "interval_seconds": 60,
  "timestamp": "2025-12-05T10:00:00Z"
}
```

**Signal Emitted:**
```json
{
  "event": "signal_emitted",
  "signal_id": "550e8400-e29b-41d4-a716-446655440000",
  "signal_type": "golden_cross",
  "tickers": ["AAPL"],
  "timestamp": "2025-12-05T10:30:00Z"
}
```

## Development Tips

### Add a New Generator

1. Create file: `app/generators/my_generator.py`
2. Inherit from `BaseSignalGenerator`
3. Implement `async def generate() -> List[Signal]`
4. Register in `app/generators/__init__.py`
5. Add to `app/main.py` service initialization
6. Write tests in `tests/test_my_generator.py`

### Test Individually

```python
# Test mock generator
from app.generators.mock import MockSignalGenerator

config = {"tickers": ["AAPL"], "emission_probability": 1.0}
generator = MockSignalGenerator(config)

# Run it
import asyncio
signals = asyncio.run(generator.generate())
print(signals)
```

## Support

- **Documentation:** See `/docs/signal-generator-architecture.md`
- **Architecture:** Event-driven signal bus design
- **Issues:** Check logs with `docker logs trading-signal-generator`

---

**You're all set! 🚀**

The signal generator is now running. In Phase 2, we'll connect it to Kafka and have it wake up trading pipelines in real-time.

