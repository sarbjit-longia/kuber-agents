"""
Market Data Utilities

Helper functions for fetching and processing market data.
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import structlog
import httpx
import pandas as pd

from app.config import settings


logger = structlog.get_logger()


class MarketDataFetcher:
    """Fetches market data from external APIs."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize market data fetcher.
        
        Args:
            api_key: Finnhub API key (defaults to settings.FINNHUB_API_KEY)
        """
        self.api_key = api_key or settings.FINNHUB_API_KEY
        self.base_url = "https://finnhub.io/api/v1"
    
    async def fetch_candles(
        self,
        symbol: str,
        resolution: str = "D",
        lookback_days: int = 365
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical candle data for a symbol.
        
        Args:
            symbol: Stock symbol
            resolution: Candle resolution (D=daily, W=weekly, M=monthly)
            lookback_days: Number of days to look back
            
        Returns:
            DataFrame with OHLCV data or None if fetch fails
        """
        if not self.api_key:
            logger.warning(
                "market_data_fetch_skipped",
                reason="No Finnhub API key configured"
            )
            return None
        
        end_ts = int(datetime.utcnow().timestamp())
        start_ts = int((datetime.utcnow() - timedelta(days=lookback_days)).timestamp())
        
        url = f"{self.base_url}/stock/candle"
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "from": start_ts,
            "to": end_ts,
            "token": self.api_key
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
            
            if data.get("s") != "ok":
                logger.warning(
                    "market_data_fetch_failed",
                    symbol=symbol,
                    status=data.get("s"),
                    resolution=resolution
                )
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame({
                "timestamp": pd.to_datetime(data["t"], unit="s"),
                "open": data["o"],
                "high": data["h"],
                "low": data["l"],
                "close": data["c"],
                "volume": data["v"]
            })
            
            df = df.sort_values("timestamp").reset_index(drop=True)
            
            logger.info(
                "market_data_fetched",
                symbol=symbol,
                resolution=resolution,
                candles=len(df)
            )
            
            return df
        
        except Exception as e:
            logger.error(
                "market_data_fetch_error",
                symbol=symbol,
                error=str(e),
                exc_info=True
            )
            return None
    
    def calculate_sma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """
        Calculate Simple Moving Average.
        
        Args:
            df: DataFrame with 'close' column
            period: SMA period
            
        Returns:
            Series with SMA values
        """
        return df["close"].rolling(window=period).mean()
    
    def detect_golden_cross(
        self,
        df: pd.DataFrame,
        short_period: int = 50,
        long_period: int = 200,
        lookback_days: int = 5
    ) -> bool:
        """
        Detect if a golden cross occurred recently.
        
        A golden cross is when the short-term SMA crosses above the long-term SMA.
        
        Args:
            df: DataFrame with price data
            short_period: Short SMA period (default 50)
            long_period: Long SMA period (default 200)
            lookback_days: How many recent days to check for crossover
            
        Returns:
            True if golden cross detected, False otherwise
        """
        if len(df) < long_period:
            return False
        
        # Calculate SMAs
        df = df.copy()
        df["sma_short"] = self.calculate_sma(df, short_period)
        df["sma_long"] = self.calculate_sma(df, long_period)
        
        # Drop NaN values
        df = df.dropna()
        
        if len(df) < lookback_days:
            return False
        
        # Check recent days for crossover
        recent_df = df.tail(lookback_days)
        
        for i in range(1, len(recent_df)):
            prev_idx = recent_df.index[i - 1]
            curr_idx = recent_df.index[i]
            
            prev_short = recent_df.loc[prev_idx, "sma_short"]
            prev_long = recent_df.loc[prev_idx, "sma_long"]
            curr_short = recent_df.loc[curr_idx, "sma_short"]
            curr_long = recent_df.loc[curr_idx, "sma_long"]
            
            # Check for crossover: short was below, now above
            if prev_short <= prev_long and curr_short > curr_long:
                logger.info(
                    "golden_cross_detected",
                    short_period=short_period,
                    long_period=long_period,
                    prev_short=prev_short,
                    prev_long=prev_long,
                    curr_short=curr_short,
                    curr_long=curr_long
                )
                return True
        
        return False

