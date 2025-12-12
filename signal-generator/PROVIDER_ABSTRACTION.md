# Market Data Provider Abstraction Layer

## Overview

This layer provides a **provider-agnostic interface** for fetching market data. Generators use a standard interface, making it easy to switch between data providers without changing any generator code.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Signal Generators                         │
│  (RSI, MACD, Bollinger, Golden Cross, etc.)                 │
└───────────────────┬─────────────────────────────────────────┘
                    │ Uses standard interface
                    ▼
┌─────────────────────────────────────────────────────────────┐
│          MarketDataProvider (Abstract Base Class)            │
│  • fetch_candles()                                           │
│  • fetch_indicator()                                         │
│  • get_latest_price()                                        │
│  • search_symbol()                                           │
└───────────────────┬─────────────────────────────────────────┘
                    │ Implemented by
      ┌─────────────┼─────────────┬─────────────┐
      ▼             ▼             ▼             ▼
┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
│ Finnhub   │ │   Alpha   │ │  Yahoo    │ │ Polygon   │
│ Provider  │ │  Vantage  │ │  Finance  │ │    .io    │
│  ✅ Done  │ │ TODO      │ │ TODO      │ │ TODO      │
└───────────┘ └───────────┘ └───────────┘ └───────────┘
```

## Current Status

### ✅ Implemented
- **Finnhub Provider** - Full implementation using official SDK
- **Provider abstraction layer** - Standard interface for all providers
- **Factory pattern** - Easy provider switching
- **Backward compatibility** - Existing generators work without changes

### 🚧 Future Providers
- **Alpha Vantage** - Free tier: 500 calls/day
- **Yahoo Finance** - Unlimited free data via `yfinance`
- **Polygon.io** - Free tier: 5 calls/min

## Usage

### For New Code (Recommended)

```python
from app.utils.market_data_factory import get_market_data_provider

# Get the configured provider
provider = get_market_data_provider()

# Fetch candles
df = await provider.fetch_candles("AAPL", resolution="D", lookback_days=365)

# Fetch indicator
data = await provider.fetch_indicator(
    "AAPL", 
    "rsi", 
    resolution="D",
    timeperiod=14
)

# Get latest price
price = await provider.get_latest_price("AAPL")
```

### For Existing Code (Backward Compatible)

```python
from app.utils.market_data import MarketDataFetcher

# Old interface still works!
fetcher = MarketDataFetcher()
df = await fetcher.fetch_candles("AAPL", "D", 365)
```

## Configuration

Set the provider in environment variables:

```bash
# Use Finnhub (default)
MARKET_DATA_PROVIDER=finnhub
FINNHUB_API_KEY=your_key_here

# Switch to Alpha Vantage (when implemented)
MARKET_DATA_PROVIDER=alpha_vantage
ALPHA_VANTAGE_API_KEY=your_key_here

# Switch to Yahoo Finance (when implemented)
MARKET_DATA_PROVIDER=yahoo_finance
# No API key needed for Yahoo!
```

## Switching Providers

To switch providers:

1. **Set environment variable**:
   ```bash
   export MARKET_DATA_PROVIDER=finnhub  # or alpha_vantage, yahoo_finance, etc.
   ```

2. **Restart service**:
   ```bash
   docker-compose restart signal-generator
   ```

That's it! All generators automatically use the new provider. No code changes needed.

## Adding a New Provider

To add a new provider (e.g., Twelve Data):

### 1. Create Provider Class

Create `app/utils/providers/twelve_data_provider.py`:

```python
from app.utils.market_data_provider import MarketDataProvider

class TwelveDataProvider(MarketDataProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Initialize SDK/client
    
    async def fetch_candles(self, symbol, resolution, lookback_days):
        # Implement using Twelve Data API
        pass
    
    async def fetch_indicator(self, symbol, indicator, resolution, lookback_days, **params):
        # Implement using Twelve Data API
        pass
    
    # ... implement other required methods
    
    @property
    def provider_name(self) -> str:
        return "Twelve Data"
    
    @property
    def rate_limit_per_minute(self) -> int:
        return 800  # Free tier
```

### 2. Register in Factory

Add to `app/utils/market_data_factory.py`:

```python
from app.utils.providers.twelve_data_provider import TwelveDataProvider

def get_market_data_provider(provider_type=None):
    # ... existing code ...
    
    elif provider_type == ProviderType.TWELVE_DATA:
        if not settings.TWELVE_DATA_API_KEY:
            raise RuntimeError("Twelve Data API key not configured")
        provider = TwelveDataProvider(api_key=settings.TWELVE_DATA_API_KEY)
    
    # ... rest of factory code
```

### 3. Add to Enum

Update `app/utils/market_data_provider.py`:

```python
class ProviderType(str, Enum):
    FINNHUB = "finnhub"
    ALPHA_VANTAGE = "alpha_vantage"
    YAHOO_FINANCE = "yahoo_finance"
    POLYGON = "polygon"
    TWELVE_DATA = "twelve_data"  # Add new provider
```

### 4. Test

```python
# Test the new provider
from app.utils.market_data_factory import get_market_data_provider
from app.utils.market_data_provider import ProviderType

provider = get_market_data_provider(ProviderType.TWELVE_DATA)
df = await provider.fetch_candles("AAPL", "D", 30)
```

Done! All generators can now use the new provider.

## Provider Comparison

| Provider       | Rate Limit       | Indicators | Real-time | Cost (Free Tier) |
|----------------|------------------|------------|-----------|------------------|
| **Finnhub**    | 160 calls/min    | 80+        | ✅        | Basic $0/mo      |
| Alpha Vantage  | 500 calls/day    | 50+        | ✅        | Free             |
| Yahoo Finance  | Unlimited        | Calculate  | ✅        | Free             |
| Polygon.io     | 5 calls/min      | Calculate  | ✅        | Free             |
| Twelve Data    | 800 calls/day    | 100+       | ✅        | Free             |

## Benefits

✅ **Easy Switching** - Change providers with 1 environment variable
✅ **No Code Changes** - Generators work with any provider
✅ **Future-Proof** - Add new providers without touching generators
✅ **Testing** - Mock providers for unit tests
✅ **Reliability** - Fallback to different provider if one fails
✅ **Cost Optimization** - Use free providers or switch based on needs

## Standard Data Format

All providers return data in the same format:

### Candles
```python
pd.DataFrame({
    "timestamp": [datetime, ...],
    "open": [float, ...],
    "high": [float, ...],
    "low": [float, ...],
    "close": [float, ...],
    "volume": [int, ...]
})
```

### Indicators
```python
{
    "timestamps": [datetime, ...],
    "values": {
        "rsi": [float, ...],
        "macd": [float, ...],
        "macd_signal": [float, ...]
    },
    "ohlcv": {  # Optional
        "open": [float, ...],
        "high": [float, ...],
        # ...
    }
}
```

## Next Steps

1. ✅ Finnhub provider implemented
2. 🚧 Add Yahoo Finance provider (free, unlimited)
3. 🚧 Add Alpha Vantage provider (backup option)
4. 🚧 Add provider health checks
5. 🚧 Add automatic fallback if provider fails
6. 🚧 Add caching layer to reduce API calls

## Questions?

See:
- `app/utils/market_data_provider.py` - Abstract base class
- `app/utils/providers/finnhub_provider.py` - Example implementation
- `app/utils/market_data_factory.py` - Provider factory

