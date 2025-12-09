# Signal Generator Service

The Signal Generator Service is a standalone microservice that monitors market conditions and emits trading signals. These signals are consumed by user-defined trading pipelines to initiate trades.

## Architecture

```
Signal Generators → Signals (stdout/logs Phase 1, Kafka Phase 2) → Pipeline Dispatcher → Pipeline Executions
```

## Phase 1: MVP (Current)

In Phase 1, the service:
- Runs multiple signal generators concurrently
- Emits signals to **stdout/logs** (no Kafka yet)
- Supports **Mock** and **Golden Cross** generators
- Can be tested independently

## Available Generators

### 1. Mock Signal Generator
Generates random test signals for development.

**Configuration:**
```python
{
    "tickers": ["AAPL", "MSFT", "GOOGL"],
    "emission_probability": 0.3,  # 30% chance each cycle
    "bias_options": ["BULLISH", "BEARISH"]
}
```

**Interval:** 60 seconds (default)

### 2. Golden Cross Signal Generator
Detects golden cross patterns (50-day SMA crosses above 200-day SMA).

**Configuration:**
```python
{
    "tickers": ["AAPL", "MSFT", ...],
    "sma_short": 50,
    "sma_long": 200,
    "timeframe": "D",  # Daily candles
    "lookback_days": 5,
    "confidence": 0.85
}
```

**Interval:** 300 seconds (5 minutes, default)

## Signal Schema

All signals follow this structure:

```json
{
  "signal_id": "uuid-here",
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

## Setup

### Local Development

1. **Create `.env` file:**
```bash
cp .env.example .env
```

2. **Set Finnhub API key (required for Golden Cross generator):**
```bash
# In .env
FINNHUB_API_KEY=your_api_key_here
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Run the service:**
```bash
python -m app.main
```

### Docker

1. **Build the image:**
```bash
docker build -t signal-generator:latest .
```

2. **Run the container:**
```bash
docker run --rm \
  -e FINNHUB_API_KEY=your_api_key \
  -e WATCHLIST_TICKERS=AAPL,MSFT,GOOGL \
  signal-generator:latest
```

### Docker Compose

Add to your `docker-compose.yml`:

```yaml
signal-generator:
  build:
    context: ./signal-generator
    dockerfile: Dockerfile
  container_name: trading-signal-generator
  environment:
    - FINNHUB_API_KEY=${FINNHUB_API_KEY}
    - WATCHLIST_TICKERS=AAPL,MSFT,GOOGL,AMZN,TSLA
    - LOG_LEVEL=INFO
    - MOCK_GENERATOR_INTERVAL_SECONDS=60
    - GOLDEN_CROSS_CHECK_INTERVAL_SECONDS=300
  restart: unless-stopped
  networks:
    - trading-network
```

## Configuration

### Watchlist Configuration

Tickers are configured in `config/watchlist.json`:

```json
{
  "version": "1.0",
  "tickers": [
    "AAPL",
    "MSFT",
    "GOOGL",
    "..."
  ]
}
```

**To add tickers:**
1. Edit `signal-generator/config/watchlist.json`
2. Add ticker symbols to the `tickers` array
3. Restart the service: `docker-compose restart signal-generator`

**Benefits:**
- ✅ Easy to expand (just add to JSON array)
- ✅ Version controlled
- ✅ No need to rebuild container
- ✅ Supports comments and metadata

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_NAME` | Service identifier | `signal-generator` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `FINNHUB_API_KEY` | Finnhub API key (required) | `None` |
| `WATCHLIST_CONFIG_PATH` | Path to watchlist config | `config/watchlist.json` |
| `MOCK_GENERATOR_INTERVAL_SECONDS` | Mock generator interval | `60` |
| `GOLDEN_CROSS_CHECK_INTERVAL_SECONDS` | Golden cross check interval | `300` |
| `GOLDEN_CROSS_SMA_SHORT` | Short SMA period | `50` |
| `GOLDEN_CROSS_SMA_LONG` | Long SMA period | `200` |
| `GOLDEN_CROSS_TIMEFRAME` | Candle resolution | `D` |

## Testing

Run tests with pytest:

```bash
pytest tests/ -v
```

Run tests in Docker:

```bash
docker run --rm signal-generator:latest pytest tests/ -v
```

## Adding New Generators

1. **Create a new generator class** in `app/generators/`:

```python
from app.generators.base import BaseSignalGenerator
from app.schemas.signal import Signal, SignalType

class MyCustomGenerator(BaseSignalGenerator):
    async def generate(self) -> List[Signal]:
        # Your logic here
        return [Signal(...)]
```

2. **Register the generator** in `app/generators/__init__.py`:

```python
from app.generators.my_custom import MyCustomGenerator

def _initialize_registry():
    registry = get_registry()
    registry.register(MyCustomGenerator)
```

3. **Add configuration** in `app/config.py` and `app/main.py`.

## Output Example

When running, the service will output signals like this:

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
   Metadata: {
      "sma_short": 50,
      "sma_long": 200,
      "current_sma_short": 175.23,
      "current_sma_long": 173.45,
      "current_price": 176.50
   }
================================================================================
```

## Phase 2: Kafka Integration (Future)

In Phase 2, signals will be published to Kafka:
- Topic: `trading-signals`
- Format: JSON (via `Signal.to_kafka_message()`)
- Consumed by: Pipeline Dispatcher Service

## Architecture Diagram

```
┌──────────────────────┐
│  Signal Generator    │
│  Service             │
│                      │
│  ┌────────────────┐  │
│  │ Mock Generator │  │
│  └────────────────┘  │
│                      │
│  ┌────────────────┐  │     Phase 1: stdout/logs
│  │Golden Cross Gen│──┼─────────────────────────→
│  └────────────────┘  │     Phase 2: Kafka
│                      │
└──────────────────────┘
```

## Troubleshooting

### No signals being generated

- **Mock Generator:** Check `MOCK_GENERATOR_INTERVAL_SECONDS` and `emission_probability` (it's random)
- **Golden Cross:** 
  - Ensure `FINNHUB_API_KEY` is set
  - Check logs for market data fetch errors
  - Golden crosses are rare - may take time to detect

### API rate limits (Finnhub)

- Free tier: 60 calls/minute
- Reduce `WATCHLIST_TICKERS` count
- Increase `GOLDEN_CROSS_CHECK_INTERVAL_SECONDS`

## Monitoring

Check service health:

```bash
docker logs -f trading-signal-generator
```

Logs are structured JSON for easy parsing:

```json
{
  "event": "signal_emitted",
  "signal_id": "...",
  "signal_type": "golden_cross",
  "tickers": ["AAPL"],
  "timestamp": "2025-12-05T14:30:00Z"
}
```

## Contributing

When adding new generators:
1. Inherit from `BaseSignalGenerator`
2. Implement `async def generate() -> List[Signal]`
3. Add unit tests in `tests/`
4. Update this README
5. Register in `app/generators/__init__.py`

