#!/usr/bin/env python3
"""
Download Market Data Script

Downloads historical market data from Finnhub for testing purposes.
This data is used by MockMarketDataTool during development.

Usage:
    python scripts/download_market_data.py [--symbol AAPL] [--api-key YOUR_KEY]

Data downloaded:
- 5-minute candles for 1 trading day (~78 candles, 9:30 AM - 4:00 PM)
- Daily candles for 6 months (~120 trading days)
"""
import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import httpx
from app.config import settings


def get_finnhub_api_key():
    """Get Finnhub API key from environment or settings."""
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        api_key = getattr(settings, "FINNHUB_API_KEY", None)
    return api_key


def download_intraday_data(symbol: str, api_key: str, resolution: str = "5") -> dict:
    """
    Download 1 day of intraday data.
    
    Args:
        symbol: Stock symbol (e.g., AAPL)
        api_key: Finnhub API key
        resolution: Resolution (1, 5, 15, 30, 60, D, W, M)
        
    Returns:
        Dict with candle data
    """
    base_url = "https://finnhub.io/api/v1"
    
    # Get yesterday's market hours (to avoid incomplete today's data)
    # Market: 9:30 AM - 4:00 PM EST
    yesterday = datetime.now() - timedelta(days=1)
    
    # Find last weekday (skip weekends)
    while yesterday.weekday() >= 5:  # 5=Saturday, 6=Sunday
        yesterday -= timedelta(days=1)
    
    # Market hours in EST
    market_open = yesterday.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = yesterday.replace(hour=16, minute=0, second=0, microsecond=0)
    
    # Convert to Unix timestamps
    from_ts = int(market_open.timestamp())
    to_ts = int(market_close.timestamp())
    
    print(f"📥 Downloading {resolution}-minute data for {symbol}...")
    print(f"   Date: {yesterday.strftime('%Y-%m-%d')} (Market: 9:30 AM - 4:00 PM EST)")
    
    url = f"{base_url}/stock/candle"
    params = {
        "symbol": symbol,
        "resolution": resolution,
        "from": from_ts,
        "to": to_ts,
        "token": api_key
    }
    
    try:
        response = httpx.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("s") == "no_data":
            print(f"   ⚠️  No data available (might be holiday or weekend)")
            return None
        
        # Convert to our format
        candles = []
        for i in range(len(data.get("t", []))):
            candles.append({
                "timestamp": data["t"][i],
                "open": data["o"][i],
                "high": data["h"][i],
                "low": data["l"][i],
                "close": data["c"][i],
                "volume": data["v"][i]
            })
        
        print(f"   ✅ Downloaded {len(candles)} candles")
        
        return {
            "symbol": symbol,
            "resolution": resolution,
            "from": from_ts,
            "to": to_ts,
            "candles": candles,
            "downloaded_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"   ❌ Error downloading data: {e}")
        return None


def download_daily_data(symbol: str, api_key: str, months: int = 6) -> dict:
    """
    Download daily data for specified months.
    
    Args:
        symbol: Stock symbol
        api_key: Finnhub API key
        months: Number of months of data
        
    Returns:
        Dict with daily candle data
    """
    base_url = "https://finnhub.io/api/v1"
    
    # Get date range
    to_date = datetime.now()
    from_date = to_date - timedelta(days=months * 30)
    
    from_ts = int(from_date.timestamp())
    to_ts = int(to_date.timestamp())
    
    print(f"📥 Downloading daily data for {symbol}...")
    print(f"   Range: {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}")
    
    url = f"{base_url}/stock/candle"
    params = {
        "symbol": symbol,
        "resolution": "D",
        "from": from_ts,
        "to": to_ts,
        "token": api_key
    }
    
    try:
        response = httpx.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("s") == "no_data":
            print(f"   ⚠️  No data available")
            return None
        
        # Convert to our format
        candles = []
        for i in range(len(data.get("t", []))):
            candles.append({
                "timestamp": data["t"][i],
                "open": data["o"][i],
                "high": data["h"][i],
                "low": data["l"][i],
                "close": data["c"][i],
                "volume": data["v"][i]
            })
        
        print(f"   ✅ Downloaded {len(candles)} candles")
        
        return {
            "symbol": symbol,
            "resolution": "D",
            "from": from_ts,
            "to": to_ts,
            "candles": candles,
            "downloaded_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"   ❌ Error downloading data: {e}")
        return None


def aggregate_candles(candles: list, target_minutes: int, source_minutes: int) -> list:
    """
    Aggregate candles to larger timeframe.
    
    Args:
        candles: List of source candles
        target_minutes: Target timeframe in minutes (e.g., 60 for 1h)
        source_minutes: Source timeframe in minutes (e.g., 5 for 5m)
        
    Returns:
        List of aggregated candles
    """
    if not candles:
        return []
    
    aggregated = []
    ratio = target_minutes // source_minutes
    
    for i in range(0, len(candles), ratio):
        batch = candles[i:i+ratio]
        if not batch:
            continue
        
        aggregated.append({
            "timestamp": batch[0]["timestamp"],
            "open": batch[0]["open"],
            "high": max(c["high"] for c in batch),
            "low": min(c["low"] for c in batch),
            "close": batch[-1]["close"],
            "volume": sum(c["volume"] for c in batch)
        })
    
    return aggregated


def main():
    parser = argparse.ArgumentParser(description="Download market data for testing")
    parser.add_argument("--symbol", default="AAPL", help="Stock symbol to download")
    parser.add_argument("--api-key", help="Finnhub API key (optional, uses env var)")
    args = parser.parse_args()
    
    # Get API key
    api_key = args.api_key or get_finnhub_api_key()
    if not api_key:
        print("❌ Error: No Finnhub API key found!")
        print("   Set FINNHUB_API_KEY environment variable or pass --api-key")
        sys.exit(1)
    
    print(f"🚀 Downloading market data for {args.symbol}...")
    print()
    
    # Create data directory
    data_dir = backend_dir / "data" / "market_data" / args.symbol
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Download 5-minute data (1 day)
    data_5m = download_intraday_data(args.symbol, api_key, resolution="5")
    if data_5m:
        file_path = data_dir / "5m.json"
        with open(file_path, "w") as f:
            json.dump(data_5m, f, indent=2)
        print(f"   💾 Saved to {file_path}")
    
    print()
    
    # Generate other intraday timeframes by aggregation
    if data_5m and data_5m["candles"]:
        print("🔧 Aggregating to other timeframes...")
        
        # 15-minute (from 5m)
        candles_15m = aggregate_candles(data_5m["candles"], 15, 5)
        data_15m = {
            **data_5m,
            "resolution": "15",
            "candles": candles_15m
        }
        file_path = data_dir / "15m.json"
        with open(file_path, "w") as f:
            json.dump(data_15m, f, indent=2)
        print(f"   ✅ 15m: {len(candles_15m)} candles → {file_path}")
        
        # 1-hour (from 5m)
        candles_1h = aggregate_candles(data_5m["candles"], 60, 5)
        data_1h = {
            **data_5m,
            "resolution": "60",
            "candles": candles_1h
        }
        file_path = data_dir / "1h.json"
        with open(file_path, "w") as f:
            json.dump(data_1h, f, indent=2)
        print(f"   ✅ 1h: {len(candles_1h)} candles → {file_path}")
        
        print()
    
    # Download daily data (6 months)
    data_1d = download_daily_data(args.symbol, api_key, months=6)
    if data_1d:
        file_path = data_dir / "1d.json"
        with open(file_path, "w") as f:
            json.dump(data_1d, f, indent=2)
        print(f"   💾 Saved to {file_path}")
    
    print()
    
    # Generate 4-hour from daily if needed
    if data_1d and data_1d["candles"]:
        print("🔧 Generating 4h timeframe...")
        # For 4h, we'll just take daily data and split (simplified approach)
        # In reality, you'd need intraday data, but this is just for testing
        candles_4h = data_1d["candles"][-30:]  # Last 30 days as 4h proxies
        data_4h = {
            **data_1d,
            "resolution": "240",  # 4h in minutes
            "candles": candles_4h
        }
        file_path = data_dir / "4h.json"
        with open(file_path, "w") as f:
            json.dump(data_4h, f, indent=2)
        print(f"   ✅ 4h: {len(candles_4h)} candles → {file_path}")
        print()
    
    # Create metadata
    metadata = {
        "symbol": args.symbol,
        "downloaded_at": datetime.now().isoformat(),
        "timeframes": ["5m", "15m", "1h", "4h", "1d"],
        "description": "Market data for testing/development",
        "note": "This data is static and used by MockMarketDataTool"
    }
    
    metadata_path = data_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    
    print("✅ Done! Market data downloaded successfully")
    print(f"📁 Data saved to: {data_dir}")
    print()
    print("💡 To use mock data:")
    print("   1. In pipeline builder, attach 'Mock Market Data' tool to Market Data Agent")
    print("   2. Execute pipeline - it will use this local data")


if __name__ == "__main__":
    main()

