"""
Market Data Provider - Abstract Base Class

This module defines the standard interface for all market data providers.
Generators use this interface, making it easy to switch providers without
changing any generator code.

Supported Providers:
- Finnhub (default)
- Alpha Vantage (future)
- Yahoo Finance (future)
- Polygon.io (future)
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, List
from datetime import datetime
import pandas as pd
from enum import Enum


class ProviderType(str, Enum):
    """Supported market data providers."""
    FINNHUB = "finnhub"
    ALPHA_VANTAGE = "alpha_vantage"
    YAHOO_FINANCE = "yahoo_finance"
    POLYGON = "polygon"


class MarketDataProvider(ABC):
    """
    Abstract base class for market data providers.
    
    All providers must implement these methods with consistent interfaces.
    This allows generators to be provider-agnostic.
    """
    
    @abstractmethod
    async def fetch_candles(
        self,
        symbol: str,
        resolution: str = "D",
        lookback_days: int = 365
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLCV candle data.
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            resolution: Timeframe - '1m', '5m', '15m', '1h', 'D', 'W', 'M'
            lookback_days: Number of days of historical data
            
        Returns:
            DataFrame with standardized columns:
            - timestamp: datetime
            - open: float
            - high: float
            - low: float
            - close: float
            - volume: int
            
            Returns None if fetch fails
        """
        pass
    
    @abstractmethod
    async def fetch_indicator(
        self,
        symbol: str,
        indicator: str,
        resolution: str = "D",
        lookback_days: int = 365,
        **indicator_params
    ) -> Optional[Dict]:
        """
        Fetch technical indicator data.
        
        Args:
            symbol: Stock symbol
            indicator: Indicator name (rsi, macd, bbands, sma, ema, etc.)
            resolution: Timeframe
            lookback_days: Number of days
            **indicator_params: Indicator-specific parameters
            
        Returns:
            Dict with standardized structure:
            {
                "timestamps": [datetime, ...],
                "values": {
                    "indicator_name": [float, ...],
                    "additional_fields": [float, ...]  # e.g., macd_signal, bbands_upper
                },
                "ohlcv": {  # Optional, if provider includes it
                    "open": [float, ...],
                    "high": [float, ...],
                    "low": [float, ...],
                    "close": [float, ...],
                    "volume": [int, ...]
                }
            }
            
            Returns None if fetch fails
        """
        pass
    
    @abstractmethod
    async def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get the current/latest price for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Current price as float, or None if unavailable
        """
        pass
    
    @abstractmethod
    async def search_symbol(self, query: str) -> List[Dict[str, str]]:
        """
        Search for symbols by company name or ticker.
        
        Args:
            query: Search query (company name or partial ticker)
            
        Returns:
            List of dicts with standardized structure:
            [
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "exchange": "NASDAQ",
                    "type": "Common Stock"
                },
                ...
            ]
        """
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider's name (e.g., 'Finnhub', 'Alpha Vantage')."""
        pass
    
    @property
    @abstractmethod
    def rate_limit_per_minute(self) -> int:
        """Return the API rate limit per minute."""
        pass
    
    @property
    @abstractmethod
    def supported_resolutions(self) -> List[str]:
        """
        Return list of supported timeframe resolutions.
        
        Should use standardized format:
        - '1m', '5m', '15m', '30m', '1h', '4h'
        - 'D' (daily), 'W' (weekly), 'M' (monthly)
        """
        pass
    
    @property
    @abstractmethod
    def supported_indicators(self) -> List[str]:
        """
        Return list of supported technical indicators.
        
        Use standardized names:
        - 'sma', 'ema', 'rsi', 'macd', 'bbands', 'stoch'
        - 'adx', 'cci', 'atr', 'obv', 'willr', 'mfi', 'sar', etc.
        """
        pass

