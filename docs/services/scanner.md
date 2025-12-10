# Scanner System

**Last Updated**: December 2025  
**Status**: Phase 1 Complete (Manual Scanners)

## Overview

The Scanner system allows users to create reusable ticker lists for signal-based pipelines. Scanners define which stocks a pipeline monitors, and signals matching those tickers trigger pipeline execution.

### Key Concepts

```
Scanner → defines tickers → used by Pipeline → matched by Trigger Dispatcher → executes
```

**Example Flow**:
1. User creates "Tech Stocks" scanner with [AAPL, GOOGL, MSFT]
2. User creates pipeline, selects "Tech Stocks" scanner, subscribes to "golden_cross" signal
3. Signal Generator emits golden_cross signal for AAPL
4. Trigger Dispatcher matches: AAPL in scanner + golden_cross subscribed → trigger pipeline
5. Celery executes pipeline for AAPL

---

## 1. Scanner Types

### 1.1 Manual Scanner (Phase 1 - ✅ Complete)

**User manually enters ticker list**:
```json
{
  "name": "Tech Stocks",
  "scanner_type": "manual",
  "tickers": ["AAPL", "GOOGL", "MSFT", "NVDA", "AMD"]
}
```

**Use Cases**:
- Custom watchlists
- Sector-specific lists
- Personal portfolio tracking
- Testing with known tickers

### 1.2 Filter-Based Scanner (Phase 2 - Future)

**User defines filters, system evaluates universe**:
```json
{
  "name": "Large Cap Tech",
  "scanner_type": "filter",
  "filters": {
    "market_cap_min": 100000000000,
    "sector": ["Technology"],
    "price_min": 50,
    "volume_avg_min": 1000000,
    "rsi": {"min": 30, "max": 70}
  }
}
```

Results auto-refresh periodically.

### 1.3 API-Based Scanner (Phase 3 - Future)

**User provides webhook/API endpoint**:
```json
{
  "name": "TrendSpider Screener",
  "scanner_type": "api",
  "api_config": {
    "endpoint": "https://api.trendspider.com/screener/xyz",
    "auth_type": "api_key",
    "refresh_interval": 3600
  }
}
```

---

## 2. Database Schema

### 2.1 Scanner Model

```python
class ScannerType(str, enum.Enum):
    MANUAL = "manual"
    FILTER = "filter"
    API = "api"

class Scanner(Base):
    __tablename__ = "scanners"
    
    id = Column(UUID, primary_key=True)
    user_id = Column(UUID, ForeignKey("users.id"))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    scanner_type = Column(Enum(ScannerType), default=ScannerType.MANUAL)
    
    # Manual scanner: direct ticker list
    tickers = Column(JSONB, default=list)
    
    # Filter scanner: filter configuration
    filter_config = Column(JSONB, nullable=True)
    
    # API scanner: external API configuration
    api_config = Column(JSONB, nullable=True)
    
    # Metadata
    ticker_count = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 2.2 Pipeline-Scanner Relationship

```python
class Pipeline(Base):
    # ...
    scanner_id = Column(UUID, ForeignKey("scanners.id"), nullable=True)
    
    # Deprecated: Use scanner_id instead
    scanner_tickers = Column(JSONB, nullable=True, default=list)
```

**Migration Path**:
- Old pipelines: Use `scanner_tickers` (deprecated)
- New pipelines: Use `scanner_id` (linked to Scanner entity)

---

## 3. API Endpoints

### 3.1 Scanner CRUD

**Create Scanner**:
```http
POST /api/v1/scanners
Content-Type: application/json

{
  "name": "Tech Stocks",
  "description": "My tech watchlist",
  "scanner_type": "manual",
  "tickers": ["AAPL", "GOOGL", "MSFT"]
}
```

**List Scanners**:
```http
GET /api/v1/scanners
```

**Update Scanner**:
```http
PUT /api/v1/scanners/{scanner_id}

{
  "tickers": ["AAPL", "GOOGL", "MSFT", "NVDA", "AMD"]
}
```

**Delete Scanner**:
```http
DELETE /api/v1/scanners/{scanner_id}
```

Deletion fails if scanner is used by active pipelines.

### 3.2 Scanner Queries

**Get Scanner Tickers**:
```http
GET /api/v1/scanners/{scanner_id}/tickers

Response:
{
  "scanner_id": "uuid",
  "name": "Tech Stocks",
  "tickers": ["AAPL", "GOOGL", "MSFT"],
  "ticker_count": 3
}
```

**Get Scanner Usage**:
```http
GET /api/v1/scanners/{scanner_id}/usage

Response:
{
  "scanner_id": "uuid",
  "pipelines_using": [
    {"pipeline_id": "uuid", "name": "My Strategy", "is_active": true}
  ],
  "total_pipelines": 1
}
```

---

## 4. Frontend Components

### 4.1 Scanner Management Page

**Route**: `/scanners`

**Features**:
- List all user scanners (card view)
- Create new scanner dialog
- Edit scanner (add/remove tickers)
- Delete scanner (with usage validation)
- View pipelines using scanner

**Components**:
- `scanner-management.component.ts/html/scss`
- `create-scanner-dialog.component.ts/html/scss`

### 4.2 Pipeline Integration

**Pipeline Settings Dialog**:
- Scanner selector dropdown
- Shows scanner name + ticker count
- Signal subscription configuration
- Validation: Signal-based pipelines require scanner

**Pipeline Builder**:
- Scanner shown in pipeline config
- Can change scanner without rebuilding pipeline

---

## 5. Trigger Dispatcher Integration

### 5.1 Pipeline Caching

Trigger Dispatcher caches **signal-based** pipelines every 5 minutes:

```python
# Query
SELECT 
  pipelines.id, 
  pipelines.user_id,
  scanners.tickers,
  pipelines.signal_subscriptions
FROM pipelines
JOIN scanners ON pipelines.scanner_id = scanners.id
WHERE 
  pipelines.is_active = true 
  AND pipelines.trigger_mode = 'signal'
```

**Cache Structure**:
```python
{
  "pipeline_uuid": {
    "user_id": "uuid",
    "scanner_tickers": ["AAPL", "GOOGL"],
    "signal_subscriptions": [
      {"signal_type": "golden_cross", "min_confidence": 80}
    ]
  }
}
```

### 5.2 Signal Matching

For each signal ticker:
```python
for ticker in signal.tickers:
    for pipeline_id, data in cached_pipelines.items():
        # Check 1: Ticker in scanner?
        if ticker not in data['scanner_tickers']:
            continue
        
        # Check 2: Signal type subscribed?
        if not matches_subscription(signal, data['signal_subscriptions']):
            continue
        
        # Check 3: Already running?
        if is_pipeline_running(pipeline_id):
            skip_and_increment_metric()
            continue
        
        # Match! Enqueue for execution
        enqueue_pipeline(pipeline_id, user_id, signal)
```

---

## 6. Usage Examples

### 6.1 Create Manual Scanner

```typescript
// Frontend
this.scannerService.createScanner({
  name: 'Tech Stocks',
  description: 'Major tech companies',
  scanner_type: 'manual',
  tickers: ['AAPL', 'GOOGL', 'MSFT', 'NVDA', 'AMD']
}).subscribe(scanner => {
  console.log('Scanner created:', scanner.id);
});
```

### 6.2 Use Scanner in Pipeline

```typescript
// Pipeline settings
this.pipelineForm.patchValue({
  trigger_mode: 'signal',
  scanner_id: scanner.id,
  signal_subscriptions: [
    {
      signal_type: 'golden_cross',
      min_confidence: 80
    }
  ]
});
```

### 6.3 Update Scanner

```typescript
// Add new ticker
this.scannerService.updateScanner(scannerId, {
  tickers: [...existingTickers, 'TSLA']
}).subscribe(() => {
  // Trigger dispatcher will auto-refresh cache within 5 min
});
```

---

## 7. Best Practices

### 7.1 Scanner Size

**Recommended**:
- Free tier: 5-10 tickers
- Basic tier: 20-50 tickers
- Pro tier: 100-200 tickers
- Enterprise: Unlimited

**Why**: Each ticker × signal subscription = potential execution

### 7.2 Scanner Organization

**Good Practices**:
- Create focused scanners (not "All Tech")
- Use descriptive names ("Large Cap Tech" not "Scanner 1")
- Document scanner purpose in description
- Review and clean up unused tickers

**Anti-Patterns**:
- Don't create one scanner per ticker
- Don't create duplicate scanners
- Don't add tickers you're not monitoring

### 7.3 Scanner Reuse

Scanners are **reusable across pipelines**:
```
Scanner: "Tech Stocks" [AAPL, GOOGL, MSFT]
  ├─ Pipeline 1: Golden Cross Strategy
  ├─ Pipeline 2: RSI Mean Reversion
  └─ Pipeline 3: News Sentiment Scalping
```

---

## 8. Future Phases

### Phase 2: Filter-Based Scanners

**Features**:
- Visual filter builder UI
- Real-time result preview
- Auto-refresh results
- Filter templates

**Filters**:
- Market cap, price, volume
- Technical indicators (RSI, MACD, SMA)
- Sector, industry
- Fundamentals (P/E, EPS growth)

**Data Sources**:
- Local universe file (CSV)
- Free API (Alpha Vantage)
- Paid API (Finnhub, Finviz)

### Phase 3: Advanced Scanners

**Features**:
- External integrations (Finviz, TradingView)
- Scanner backtesting
- Scanner alerts
- Community marketplace
- Scanner versioning

---

## 9. Database Queries

### 9.1 Get Scanners with Usage

```sql
SELECT 
  s.id,
  s.name,
  s.ticker_count,
  COUNT(p.id) as pipeline_count,
  COUNT(CASE WHEN p.is_active THEN 1 END) as active_pipeline_count
FROM scanners s
LEFT JOIN pipelines p ON s.id = p.scanner_id
GROUP BY s.id, s.name, s.ticker_count
ORDER BY pipeline_count DESC;
```

### 9.2 Get Most Popular Tickers

```sql
SELECT 
  ticker,
  COUNT(DISTINCT s.id) as scanner_count,
  COUNT(DISTINCT p.id) as pipeline_count
FROM scanners s,
  LATERAL jsonb_array_elements_text(s.tickers) ticker
LEFT JOIN pipelines p ON s.id = p.scanner_id
GROUP BY ticker
ORDER BY pipeline_count DESC
LIMIT 20;
```

---

## 10. Testing

### 10.1 Manual Scanner

```bash
# Create scanner via API
curl -X POST http://localhost:8000/api/v1/scanners \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Scanner",
    "scanner_type": "manual",
    "tickers": ["AAPL"]
  }'

# Create signal-based pipeline using scanner
# Trigger signal for AAPL
# Verify pipeline executes
```

### 10.2 Scanner Update

```bash
# Update scanner
curl -X PUT http://localhost:8000/api/v1/scanners/{id} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL", "GOOGL"]}'

# Wait 5 min for cache refresh or restart trigger-dispatcher
docker-compose restart trigger-dispatcher

# Trigger signal for GOOGL
# Verify pipeline executes
```

---

**Related Documentation**:
- [Signal System](./signal-system.md)
- [Monitoring](./monitoring.md)
- [Design Document](../design.md#scanner-system)

