# Data Plane Phase 1 - Testing Guide

## Pre-Test Checklist

- [ ] `.env` file has `FINNHUB_API_KEY`
- [ ] No other services running on ports 5434, 8005, 8006
- [ ] Docker has sufficient resources (4GB+ RAM)

---

## Test 1: Service Startup

### Start all services
```bash
cd /Users/sarbjits/workspace/personal/kuber-agents
docker-compose up -d
```

### Expected: All services start healthy
```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

**Expected Output**:
```
trading-data-plane          Up (healthy)
trading-data-plane-worker   Up
trading-data-plane-beat     Up
trading-timescaledb         Up (healthy)
```

**✅ Pass Criteria**: All 4 new containers running

**❌ If Failed**: Check logs
```bash
docker logs trading-data-plane
docker logs trading-data-plane-worker
docker logs trading-timescaledb
```

---

## Test 2: Health Checks

### Data Plane API Health
```bash
curl http://localhost:8005/health
```

**Expected Output**:
```json
{
  "status": "ok",
  "service": "data-plane",
  "redis": "ok"
}
```

### Prometheus Metrics Endpoint
```bash
curl http://localhost:8006/metrics | head -20
```

**Expected**: Should see metrics like `universe_size`, `quotes_fetched_total`

**✅ Pass Criteria**: Both endpoints respond with 200 OK

---

## Test 3: Universe Discovery

### Check initial universe (should be empty)
```bash
curl http://localhost:8005/api/v1/data/universe
```

**Expected Output**:
```json
{
  "hot": [],
  "warm": [],
  "total": 0
}
```

### Create a scanner with tickers (via UI)
1. Open http://localhost:4200/scanners
2. Click "Create Scanner"
3. Name: "Test Scanner"
4. Tickers: AAPL, GOOGL, MSFT
5. Save

### Create a pipeline using the scanner (via UI)
1. Open http://localhost:4200/pipelines
2. Create new pipeline
3. Settings → Scanner: Select "Test Scanner"
4. Settings → Trigger Mode: Signal
5. Settings → Signals: Select "Golden Cross" (or any)
6. Save and Activate

### Wait 5 minutes, then check universe
```bash
# Wait for universe refresh (runs every 5 min)
sleep 300

curl http://localhost:8005/api/v1/data/universe
```

**Expected Output**:
```json
{
  "hot": [],
  "warm": ["AAPL", "GOOGL", "MSFT"],
  "total": 3
}
```

**✅ Pass Criteria**: Your tickers appear in "warm" list

**❌ If Failed**: Check data-plane-beat logs
```bash
docker logs trading-data-plane-beat --tail 50
```

---

## Test 4: Data Fetching

### Check that warm tickers are being fetched (after 5 min)
```bash
docker logs trading-data-plane-worker --tail 50 | grep "fetching_quotes_batch"
```

**Expected**: Should see logs like:
```
fetching_quotes_batch count=3 ttl=300
quote_cached ticker=AAPL price=178.45
```

### Test quote API (on-demand)
```bash
curl http://localhost:8005/api/v1/data/quote/AAPL
```

**Expected Output**:
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
  "timestamp": "2025-12-10T20:15:00"
}
```

**✅ Pass Criteria**: Valid quote returned with current price

**❌ If Failed**: Check Finnhub API key
```bash
# Check worker logs for errors
docker logs trading-data-plane-worker --tail 100 | grep -i error
```

---

## Test 5: Candles API

### Test 5m candles
```bash
curl "http://localhost:8005/api/v1/data/candles/AAPL?timeframe=5m&limit=10"
```

**Expected Output**:
```json
{
  "ticker": "AAPL",
  "timeframe": "5m",
  "count": 10,
  "candles": [
    {
      "ticker": "AAPL",
      "timeframe": "5m",
      "timestamp": "2025-12-10T20:10:00",
      "open": 178.20,
      "high": 178.50,
      "low": 178.10,
      "close": 178.45,
      "volume": 125000
    }
  ]
}
```

**✅ Pass Criteria**: Returns 10 candles with OHLCV data

---

## Test 6: Market Data Agent Integration

### Execute a pipeline with Market Data Agent
1. Open a pipeline in UI that has Market Data Agent
2. Click "Execute Now" (or wait for signal trigger)
3. Monitor execution on `/monitoring` page

### Check execution logs
```bash
docker logs trading-celery-worker --tail 100 | grep "Market data fetched"
```

**Expected**:
```
Market data fetched from Data Plane cache for AAPL
Current price: $178.45
Timeframes available: 5m, 1h, 4h, 1d
```

### Check Market Data Agent report in UI
1. Go to execution detail page
2. Check Market Data Agent report
3. Should say: "Fetched from Data Plane cache" in summary

**✅ Pass Criteria**: Pipeline executes successfully, Market Data Agent uses Data Plane

**❌ If Failed**: Check if backend can reach data-plane
```bash
docker exec trading-backend curl http://data-plane:8000/health
```

---

## Test 7: Cache Performance

### Test cache hit (should be fast)
```bash
# First call (might be cache miss, fetches from Finnhub)
time curl -s http://localhost:8005/api/v1/data/quote/AAPL > /dev/null

# Second call (should be cache hit, <10ms)
time curl -s http://localhost:8005/api/v1/data/quote/AAPL > /dev/null
```

**Expected**: Second call should be significantly faster (< 0.02s)

**✅ Pass Criteria**: Cache hit is < 20ms

---

## Test 8: Hot vs Warm Tickers

### Execute a pipeline to make tickers "hot"
1. Execute a pipeline (via UI or signal)
2. While it's running, check universe:

```bash
curl http://localhost:8005/api/v1/data/universe
```

**Expected**: Tickers should move from "warm" to "hot"

### Verify hot tickers are fetched every 1 min
```bash
# Watch worker logs for 2 minutes
docker logs trading-data-plane-worker -f
```

**Expected**: Should see `task_fetch_hot_tickers` every 60 seconds

**✅ Pass Criteria**: Hot tickers fetched more frequently than warm

---

## Test 9: Metrics Collection

### Check Prometheus is scraping data-plane
```bash
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="data-plane")'
```

**Expected**: Should show target with state "up"

### Check metrics are being collected
```bash
curl http://localhost:9090/api/v1/query?query=universe_size | jq .
```

**Expected**: Should return current universe size

### View in Grafana (optional for now)
1. Open http://localhost:3000
2. Explore → Metrics → Search "universe_size"
3. Should see data points

**✅ Pass Criteria**: Prometheus is scraping and storing metrics

---

## Test 10: Error Handling

### Test invalid ticker
```bash
curl http://localhost:8005/api/v1/data/quote/INVALID123
```

**Expected**: Should handle gracefully (404 or error message)

### Test with Finnhub rate limit
```bash
# Make many rapid requests
for i in {1..100}; do 
  curl -s http://localhost:8005/api/v1/data/quote/AAPL > /dev/null
  echo "Request $i"
done
```

**Expected**: Should handle gracefully, cache should absorb load

**✅ Pass Criteria**: No crashes, errors logged appropriately

---

## Test 11: Batch API

### Test batch endpoint
```bash
curl "http://localhost:8005/api/v1/data/batch?tickers=AAPL,GOOGL,MSFT&data_types=quote"
```

**Expected Output**:
```json
{
  "AAPL": {
    "quote": {...}
  },
  "GOOGL": {
    "quote": {...}
  },
  "MSFT": {
    "quote": {...}
  }
}
```

**✅ Pass Criteria**: All 3 quotes returned

---

## Success Criteria Summary

| Test | Status | Critical? |
|------|--------|-----------|
| 1. Services Start | ⬜ | ✅ Yes |
| 2. Health Checks | ⬜ | ✅ Yes |
| 3. Universe Discovery | ⬜ | ✅ Yes |
| 4. Data Fetching | ⬜ | ✅ Yes |
| 5. Candles API | ⬜ | ✅ Yes |
| 6. Market Data Agent | ⬜ | ✅ Yes |
| 7. Cache Performance | ⬜ | ⚠️ Nice to have |
| 8. Hot vs Warm | ⬜ | ⚠️ Nice to have |
| 9. Metrics Collection | ⬜ | ⚠️ Nice to have |
| 10. Error Handling | ⬜ | ⚠️ Nice to have |
| 11. Batch API | ⬜ | ⚠️ Nice to have |

**Minimum to Pass**: Tests 1-6 must pass

---

## Common Issues & Fixes

### Issue: TimescaleDB won't start
**Error**: `database "trading_data_plane" does not exist`

**Fix**:
```bash
docker exec -it trading-timescaledb psql -U dev -c "CREATE DATABASE trading_data_plane;"
```

### Issue: Universe is empty after 5 min
**Possible causes**:
1. No active pipelines
2. No scanner attached to pipeline
3. Beat scheduler not running

**Fix**:
```bash
# Check beat is running
docker logs trading-data-plane-beat --tail 20

# Manually trigger universe refresh
docker exec trading-data-plane-worker celery -A app.tasks.celery_tasks call data_plane.refresh_universe
```

### Issue: Quote fetch fails
**Error**: `403 Forbidden` or `401 Unauthorized`

**Fix**: Check Finnhub API key
```bash
docker exec trading-data-plane env | grep FINNHUB_API_KEY
```

### Issue: Backend can't reach data-plane
**Error**: `Connection refused` in celery-worker logs

**Fix**: Check docker network
```bash
docker network inspect kuber-agents_default | grep -A5 "data-plane"
```

---

## Post-Test Cleanup (Optional)

```bash
# Stop all services
docker-compose down

# Remove volumes (clean slate)
docker-compose down -v

# Restart fresh
docker-compose up -d
```

---

## Ready for Phase 2?

Once all critical tests pass (1-6), we can proceed to **Phase 2: Pre-computed Indicators**.

**Report back with**:
- ✅ Which tests passed
- ❌ Which tests failed (with error logs)
- ❓ Any questions or observations

