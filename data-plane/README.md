# Data Plane Service

**Version**: 3.0.0
**Status**: Phase 3 Complete ✅

## Overview

The Data Plane is a centralized market data service that provides cached, fast access to real-time quotes, historical candles, and **pre-computed technical indicators** for all pipelines. It stores 1-minute candles in TimescaleDB, derives higher timeframes via continuous aggregates, and serves them from Redis — eliminating redundant API calls and reducing provider bandwidth by ~80%.

### Key Benefits

- ✅ **~80% Bandwidth Reduction**: Candle caching in TimescaleDB avoids re-fetching historical data
- ✅ **Multi-Provider**: Tiingo (primary), Finnhub, and OANDA with automatic fallback
- ✅ **20-50x Faster**: <10ms from Redis cache vs 200-500ms from external API
- ✅ **TimescaleDB Continuous Aggregates**: 5m/15m/1h/4h/D views materialized from 1m candles
- ✅ **EOD Seeding**: 400 daily candles at startup for SMA(200) history
- ✅ **No User API Keys**: Centralized provider integration
- ✅ **Scalable**: 1,000 users = same API call volume
- ✅ **Pre-Computed Indicators**: 15 indicators via TA-Lib (~2ms vs 600ms API), cached and ready

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Data Plane Service                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Provider Layer        Storage Layer         Cache Layer      API       │
│  ┌──────────┐         ┌──────────────┐      ┌──────────┐             │
│  │ Tiingo   │─1m──→  │ TimescaleDB  │──→  │  Redis   │──→ /api/v1  │
│  │ Finnhub  │  candles │  ohlcv       │ agg  │  candles │             │
│  │ OANDA    │         │  hypertable  │      │  quotes  │             │
│  └──────────┘         └──────┬───────┘      │  indics  │             │
│                              │              └──────────┘             │
│                    Continuous Aggregates                               │
│                    ┌──────────────────┐                                │
│                    │ ohlcv_5m         │                                │
│                    │ ohlcv_15m        │                                │
│                    │ ohlcv_1h         │                                │
│                    │ ohlcv_4h         │                                │
│                    │ ohlcv_daily      │                                │
│                    └──────────────────┘                                │
│                                                                         │
│  Celery Beat Tasks:                                                    │
│  • prefetch_candles    (60s)  → 1m candles → TimescaleDB → Redis      │
│  • seed_eod_candles    (24h)  → 400 daily candles → TimescaleDB       │
│  • prefetch_indicators (5m)   → TA-Lib batch compute → Redis          │
│  • refresh_universe    (5m)   → backend DB → Redis sets               │
│  • fetch_hot_tickers   (60s)  → quotes → Redis                       │
│  • fetch_warm_tickers  (5m)   → quotes → Redis                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                               │
                   ┌───────────┴───────────┐
                   ↓                       ↓
        Market Data Agent         Frontend Charts
        (reads from cache)        (future)
```

---

## Quick Start

### 1. Prerequisites

- Docker & Docker Compose
- At least one provider API key (Tiingo recommended, or Finnhub)

### 2. Configuration

Add to your `.env` file:

```bash
# Recommended: Tiingo (better rate limits, adjusted EOD prices)
TIINGO_API_KEY=your_tiingo_key
STOCK_PROVIDER=tiingo

# Alternative: Finnhub
FINNHUB_API_KEY=your_finnhub_key
STOCK_PROVIDER=finnhub
```

### 3. Start Services

```bash
# Start all services (including data-plane)
docker-compose up -d

# Check data-plane is running
docker ps | grep data-plane

# View logs
docker logs -f trading-data-plane
docker logs -f trading-data-plane-worker
docker logs -f trading-data-plane-beat
```

### 4. Verify

```bash
# Health check
curl http://localhost:8005/health

# Check universe
curl http://localhost:8005/api/v1/data/universe

# Get quote for AAPL
curl http://localhost:8005/api/v1/data/quote/AAPL

# Get candles
curl "http://localhost:8005/api/v1/data/candles/AAPL?timeframe=5m&limit=100"

# Get technical indicators
curl "http://localhost:8005/api/v1/data/indicators/AAPL?timeframe=D&indicators=sma,rsi,macd"
```

---

## API Endpoints

### **GET `/api/v1/data/quote/{ticker}`**

Get latest quote (cached).

**Example**:
```bash
curl http://localhost:8005/api/v1/data/quote/AAPL
```

**Response**:
```json
{
  "ticker": "AAPL",
  "current_price": 178.45,
  "change": 2.15,
  "percent_change": 1.22,
  "high": 179.50,
  "low": 176.80,
  "open": 177.00,
  "previous_close": 176.30,
  "timestamp": "2025-12-10T19:45:00Z"
}
```

---

### **GET `/api/v1/data/candles/{ticker}`**

Get OHLCV candles.

**Query Parameters**:
- `timeframe`: 1m, 5m, 15m, 30m, 1h, 4h, 1d (default: 5m)
- `limit`: Number of candles (1-500, default: 100)

**Example**:
```bash
curl "http://localhost:8005/api/v1/data/candles/AAPL?timeframe=5m&limit=50"
```

**Response**:
```json
{
  "ticker": "AAPL",
  "timeframe": "5m",
  "count": 50,
  "candles": [
    {
      "ticker": "AAPL",
      "timeframe": "5m",
      "timestamp": "2025-12-10T19:40:00Z",
      "open": 178.20,
      "high": 178.50,
      "low": 178.10,
      "close": 178.45,
      "volume": 125000
    }
  ]
}
```

---

### **GET `/api/v1/data/indicators/{ticker}`**

Get pre-computed technical indicators.

**Supported Indicators**:
- `sma`: Simple Moving Average (periods: 20, 50, 200)
- `ema`: Exponential Moving Average (periods: 12, 26)
- `rsi`: Relative Strength Index (period: 14)
- `macd`: MACD (fixed params: 12/26/9)
- `bbands`: Bollinger Bands (period: 20)
- `stoch`, `atr`, `adx`, `cci`, `mfi`, `obv`, `stochrsi`, `aroon`, `willr`, `sar`

**Query Parameters**:
- `timeframe`: 5m, 15m, 1h, 4h, D (default: D)
- `indicators`: Comma-separated list (default: sma,rsi)
- `sma_period`: SMA period (default: 20)
- `ema_period`: EMA period (default: 12)
- `rsi_period`: RSI period (default: 14)
- `bbands_period`: Bollinger Bands period (default: 20)

**Example**:
```bash
curl "http://localhost:8005/api/v1/data/indicators/AAPL?timeframe=D&indicators=sma,rsi,macd&sma_period=50"
```

**Response**:
```json
{
  "ticker": "AAPL",
  "timeframe": "D",
  "indicators": {
    "sma": {
      "indicator": "sma",
      "timeframe": "D",
      "ticker": "AAPL",
      "timestamp": "2025-12-10T20:00:00Z",
      "values": {
        "sma": 175.32,
        "sma_history": [172.45, 173.12, "...", 175.32]
      }
    },
    "rsi": {
      "indicator": "rsi",
      "timeframe": "D",
      "ticker": "AAPL",
      "timestamp": "2025-12-10T20:00:00Z",
      "values": {
        "rsi": 62.5,
        "rsi_history": [58.3, 60.1, "...", 62.5]
      }
    },
    "macd": {
      "indicator": "macd",
      "timeframe": "D",
      "ticker": "AAPL",
      "timestamp": "2025-12-10T20:00:00Z",
      "values": {
        "macd": 2.45,
        "macd_signal": 1.89,
        "macd_hist": 0.56,
        "macd_history": [1.23, 1.56, "...", 2.45],
        "macd_signal_history": [1.01, 1.34, "...", 1.89]
      }
    }
  }
}
```

---

### **GET `/api/v1/data/batch`**

Batch fetch multiple tickers.

**Query Parameters**:
- `tickers`: Comma-separated list of tickers
- `data_types`: Comma-separated list (quote, candles)

**Example**:
```bash
curl "http://localhost:8005/api/v1/data/batch?tickers=AAPL,GOOGL,MSFT&data_types=quote"
```

---

### **GET `/api/v1/data/universe`**

Get current tracked tickers.

**Example**:
```bash
curl http://localhost:8005/api/v1/data/universe
```

**Response**:
```json
{
  "hot": ["AAPL", "GOOGL"],
  "warm": ["MSFT", "NVDA", "AMD"],
  "total": 5
}
```

---

## How It Works

### Universe Manager

Queries the backend database every 5 minutes to discover:
- **Hot Tickers**: From currently RUNNING executions
- **Warm Tickers**: From active pipelines/scanners

Stores in Redis sets: `tickers:hot` and `tickers:warm`.

### Candle Pipeline (`prefetch_candles_task` — every 60s)

The core bandwidth optimization loop:

1. Fetch **500 1-minute candles** per ticker from the configured provider (Tiingo/Finnhub)
2. Write 1m candles to TimescaleDB `ohlcv` hypertable (idempotent `ON CONFLICT DO NOTHING`)
3. Call `refresh_continuous_aggregate()` on all 5 materialized views
4. Read aggregated 5m/15m/1h/4h candles from TimescaleDB continuous aggregates
5. Cache all timeframes in Redis with timeframe-appropriate TTLs

**Candle Cache TTLs**:

| Timeframe | TTL | Redis Key Pattern |
|-----------|-----|-------------------|
| 1m | 120s | `candles:1m:{ticker}` |
| 5m | 360s | `candles:5m:{ticker}` |
| 15m | 960s | `candles:15m:{ticker}` |
| 1h | 3,900s | `candles:1h:{ticker}` |
| 4h | 14,700s | `candles:4h:{ticker}` |
| D | 3,600s | `candles:D:{ticker}` |
| W | 7,200s | `candles:W:{ticker}` |
| M | 14,400s | `candles:M:{ticker}` |

### EOD Seed (`seed_eod_candles_task` — daily + on worker startup)

Seeds historical daily candles to support long-period indicators:

1. Triggered on every **Celery worker startup** (30s delay) and then once daily
2. Fetches **400 daily candles** per ticker from the provider — enough headroom for SMA(200)
3. Writes to TimescaleDB with `timeframe='D'` using `ON CONFLICT DO NOTHING`
4. Daily candle reads merge the seeded EOD rows with the `ohlcv_daily` continuous aggregate via `UNION ALL`

### Indicator Pre-fetch (`prefetch_indicators_task` — every 5m)

Batch-computes 8 indicators across 3 key timeframes (1h, 4h, D):

1. For each ticker+timeframe: fetch candles once from Redis cache
2. Compute all indicators in one pass using **TA-Lib** (~2ms per indicator vs 600ms API)
3. Cache each indicator in Redis (TTL 300s) at `indicators:{ticker}:{timeframe}:{indicator}:{params}`

**Pre-fetched indicators**: SMA(20), SMA(50), SMA(200), EMA(12), EMA(26), RSI(14), MACD(12/26/9), Bollinger Bands(20)

### Provider Selection

Providers are selected based on ticker type and configuration:

- **Forex** (tickers with `_`): Always routed to OANDA
- **Stocks/Crypto**: Selected by `STOCK_PROVIDER` env var with automatic fallback:
  - `tiingo` (recommended): Better rate limits, adjusted EOD prices, stocks + crypto
  - `finnhub`: Free tier, stocks only, 60 calls/min

### TimescaleDB Continuous Aggregates

All higher timeframes are derived from 1-minute candles via materialized views:

| View | Bucket | Auto-Refresh | Refresh Window |
|------|--------|-------------|----------------|
| `ohlcv_5m` | 5 min | Every 1 min | Last 2 hours |
| `ohlcv_15m` | 15 min | Every 5 min | Last 4 hours |
| `ohlcv_1h` | 1 hour | Every 10 min | Last 12 hours |
| `ohlcv_4h` | 4 hours | Every 30 min | Last 2 days |
| `ohlcv_daily` | 1 day | Every 1 hour | Last 7 days |

Each view aggregates with `first(open)`, `max(high)`, `min(low)`, `last(close)`, `sum(volume)`.
Compression policy: data older than 7 days is compressed, segmented by `ticker, timeframe`.

---

## Monitoring

### Prometheus Metrics

Data Plane exposes metrics on port `8001`:

```bash
curl http://localhost:8006/metrics
```

**Counters**:

| Metric | Labels | Description |
|--------|--------|-------------|
| `api_calls_total` | `provider`, `endpoint`, `status` | Total API calls to providers |
| `provider_bandwidth_bytes_total` | `provider`, `endpoint` | Bytes received from providers |
| `candle_cache_hits_total` | `timeframe` | Redis candle cache hits |
| `candle_cache_misses_total` | `timeframe` | Redis candle cache misses |
| `timescale_candles_written_total` | `timeframe` | Rows written to TimescaleDB |
| `timescale_aggregates_read_total` | `timeframe` | Rows read from continuous aggregates |

**Histograms**:

| Metric | Labels | Description |
|--------|--------|-------------|
| `api_call_duration_seconds` | `provider`, `endpoint` | Provider API call latency |
| `timescale_aggregate_refresh_seconds` | — | Duration of aggregate refresh calls |
| `prefetch_task_duration_seconds` | `task` | Celery prefetch task duration |

**Gauges**:

| Metric | Labels | Description |
|--------|--------|-------------|
| `api_rate_limit_remaining` | `provider` | Remaining API calls in rate-limit window |
| `api_rate_limit_total` | `provider` | Total API calls allowed per window |
| `process_cpu_percent` | `service` | Process CPU usage % |
| `process_memory_bytes` | `service`, `type` | Process memory (RSS/VMS) |
| `process_threads` | `service` | Thread count |
| `process_open_files` | `service` | Open file descriptors |
| `universe_size` | — | Total tickers in universe |
| `universe_hot_tickers` | — | Hot ticker count |
| `universe_warm_tickers` | — | Warm ticker count |

**OpenTelemetry counters** (via OTel meter):
`quotes_fetched_total`, `quotes_cached_total`, `quotes_fetch_failures_total`, `candles_fetched_total`, `indicators_calculated_total`, `indicator_calculation_failures_total`, `universe_refresh_total`

### Grafana Dashboards

The **Trading Platform - System Overview** dashboard (`monitoring/grafana/dashboards/trading-platform-overview.json`) includes a "Data Plane Service" row with the following panels:

| Panel | Type | Description |
|-------|------|-------------|
| Universe Size / Hot / Warm | stat | Current ticker counts |
| Quotes Fetched | timeseries | Quote fetch rate over time |
| Quote Failures (1h) | stat | Recent failure count |
| Candles Fetched | stat | Total candles fetched |
| Indicator Fetch Rate | timeseries | Indicator calculations per second |
| Indicator Failures (1h) | stat | Recent indicator failures |
| Indicators by Type | timeseries | Breakdown by indicator name |
| Total Bandwidth / Bandwidth Rate | stat | Provider bandwidth consumption |
| Candle Cache Hit Ratio | gauge | Redis hit/miss ratio |
| TimescaleDB Rows Written | stat | Total rows persisted |
| Bandwidth by Provider | timeseries | Bytes/sec per provider |
| Candle Cache Hits vs Misses | timeseries | Cache effectiveness over time |
| TimescaleDB Write Rate by Timeframe | timeseries | Rows/sec per timeframe |
| Bandwidth by Provider & Endpoint | timeseries | Granular bandwidth breakdown |
| Aggregate Refresh Duration | timeseries | Continuous aggregate refresh latency |
| Prefetch Task Duration | timeseries | Average Celery task durations |

Additional dashboard: **Application Resources** (`app-resources.json`) — CPU, memory, threads, and open files per service.

---

## Configuration

### Environment Variables

```bash
# Service
SERVICE_NAME=data-plane
LOG_LEVEL=INFO

# Stock Provider (tiingo or finnhub)
STOCK_PROVIDER=tiingo

# Tiingo (recommended — better rate limits, adjusted EOD prices)
TIINGO_API_KEY=your_tiingo_key

# Finnhub (alternative)
FINNHUB_API_KEY=your_finnhub_key

# OANDA (forex)
OANDA_API_KEY=your_oanda_key
OANDA_ACCOUNT_TYPE=practice        # practice or live
OANDA_ACCOUNT_ID=your_account_id

# Redis (separate database from main app)
REDIS_URL=redis://redis:6379/1

# TimescaleDB (historical candle storage + continuous aggregates)
TIMESCALE_URL=postgresql+asyncpg://dev:devpass@timescaledb:5432/trading_data_plane

# Backend DB (read-only, to query scanners/pipelines for universe)
BACKEND_DB_URL=postgresql+asyncpg://dev:devpass@postgres:5432/trading_platform

# Celery
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/1

# Metrics
METRICS_PORT=8001
```

---

## Troubleshooting

### No Data in Cache

**Check universe**:
```bash
# Should show tickers from active pipelines
curl http://localhost:8005/api/v1/data/universe
```

If empty, ensure you have:
1. Active pipelines with scanners
2. Data Plane services running
3. Universe refresh task running (check data-plane-beat logs)

### API Call Failures

**Check logs**:
```bash
docker logs trading-data-plane-worker --tail 50
```

Common issues:
- Invalid API key (check `TIINGO_API_KEY` or `FINNHUB_API_KEY`)
- Rate limit exceeded (Finnhub free: 60/min, Tiingo free: ~50/hr)
- Provider fallback: if primary provider key missing, falls back to the other
- Network connectivity

### High Latency

**Check cache hit rate**:
```bash
# Should be >80% after first prefetch cycle
curl http://localhost:8006/metrics | grep candle_cache_hits
```

If low, check:
- Redis is running: `docker ps | grep redis`
- Prefetch tasks are running: check data-plane-beat logs
- TimescaleDB is healthy: `docker ps | grep timescaledb`

---

## Roadmap

### Phase 1: Basic Caching (✅ Complete)
- Universe discovery
- Quote caching (hot/warm tiers)
- On-demand candle fetching
- Market Data Agent integration

### Phase 2: Technical Indicators (✅ Complete)
- TA-Lib indicator calculation (15 indicators)
- Indicator caching (5min TTL)
- `/data/indicators/{ticker}` endpoint
- Pre-fetch indicators for universe tickers
- Grafana dashboard metrics

### Phase 3: TimescaleDB Storage & Bandwidth Optimization (✅ Complete)
- 1m candle storage in TimescaleDB hypertable
- Continuous aggregates for 5m/15m/1h/4h/D timeframes
- EOD candle seeding (400 daily candles for SMA(200) history)
- Multi-provider support (Tiingo, Finnhub, OANDA) with automatic fallback
- Candle caching pipeline (provider → TimescaleDB → Redis)
- Data compression after 7 days
- Prometheus metrics for bandwidth, cache hits, TimescaleDB writes
- Grafana panels for bandwidth monitoring and cache effectiveness

### Phase 4: Real-Time Streaming (Future)
- WebSocket endpoint `/data/stream/{ticker}`
- Sub-second price updates
- Frontend real-time charts (TradingView)

### Phase 5: Advanced Provider Features (Future)
- Provider health monitoring and scoring
- Cost optimization (cheapest provider per ticker)
- Backfill historical data (500+ days)

---

## Development

### Project Structure

```
data-plane/
├── app/
│   ├── main.py                    # FastAPI app
│   ├── config.py                  # Settings (env vars)
│   ├── database.py                # DB connections (Redis, TimescaleDB, Backend)
│   ├── telemetry.py               # Prometheus metrics + OpenTelemetry
│   ├── models/
│   │   └── ohlcv.py               # TimescaleDB hypertable model
│   ├── providers/
│   │   ├── __init__.py            # Provider exports
│   │   ├── base.py                # BaseProvider ABC (rate limit tracking)
│   │   ├── tiingo.py              # Tiingo provider (stocks + crypto)
│   │   ├── finnhub.py             # Finnhub provider (stocks)
│   │   └── oanda.py               # OANDA provider (forex)
│   ├── services/
│   │   ├── universe_manager.py    # Ticker discovery from backend DB
│   │   ├── data_fetcher.py        # Quote/candle fetching + caching
│   │   ├── indicator_calculator.py # TA-Lib indicator computation
│   │   └── timescale_writer.py    # TimescaleDB writes + aggregate refresh
│   ├── tasks/
│   │   └── celery_tasks.py        # Celery Beat scheduled tasks
│   └── api/
│       └── v1/
│           └── data.py            # API endpoints
├── requirements.txt
├── Dockerfile
└── README.md
```

### Running Locally

```bash
# Install dependencies
cd data-plane
pip install -r requirements.txt

# Set environment variables
export STOCK_PROVIDER=tiingo
export TIINGO_API_KEY=your_key
export REDIS_URL=redis://localhost:6379/1
export TIMESCALE_URL=postgresql+asyncpg://localhost:5434/trading_data_plane
# ... other vars

# Run API
uvicorn app.main:app --reload --port 8000

# Run worker
celery -A app.tasks.celery_tasks worker --loglevel=INFO

# Run beat
celery -A app.tasks.celery_tasks beat --loglevel=INFO
```

### Adding New Endpoints

1. Add endpoint in `app/api/v1/data.py`
2. Add metrics in service layer
3. Update this README
4. Test with curl/httpx

---

## Performance

### Benchmarks (Local Docker)

| Operation | Before (Direct API) | After (Cache) | Improvement |
|-----------|---------------------|---------------|-------------|
| Quote Fetch | 250ms | 8ms | **31x faster** |
| Candle Fetch (100 candles) | 450ms | <10ms | **45x faster** |
| 5 Tickers Batch | 1,250ms | 40ms | **31x faster** |
| Indicator Calc (TA-Lib) | 600ms (API) | ~2ms | **300x faster** |

### Bandwidth & Cost

| Metric | Before (Phase 2) | After (Phase 3) | Improvement |
|--------|-------------------|------------------|-------------|
| Provider Bandwidth | ~300-500 MB/day | ~50-80 MB/day | **~80% reduction** |
| API Calls/Day (100 users) | 4,000 | 500 | **87.5% reduction** |
| Candle Latency | 450ms (on-demand) | <10ms (Redis) | **45x faster** |

---

## Support

- **Documentation**: `/docs/services/signal-system.md` (includes Data Plane)
- **Issues**: GitHub Issues
- **Logs**: `docker logs trading-data-plane`

---

**Related Services**:
- [Signal Generator](../signal-generator/README.md)
- [Trigger Dispatcher](../trigger-dispatcher/README.md)
- [Monitoring Setup](../monitoring/README.md)
