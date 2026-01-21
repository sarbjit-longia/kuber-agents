"""
Base Provider Interface

All market data providers must implement this interface.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Optional
from datetime import datetime


class ProviderType(str, Enum):
    """Supported provider types."""
    FINNHUB = "finnhub"
    OANDA = "oanda"
    ALPHA_VANTAGE = "alpha_vantage"
    TWELVE_DATA = "twelve_data"


class AssetClass(str, Enum):
    """Supported asset classes."""
    STOCKS = "stocks"
    FOREX = "forex"
    CRYPTO = "crypto"
    COMMODITIES = "commodities"


class BaseProvider(ABC):
    """
    Base class for all market data providers.
    
    Providers must implement:
    - Quote fetching (real-time prices)
    - Candle fetching (historical OHLCV)
    - Symbol normalization
    """
    
    def __init__(self, api_key: str, **kwargs):
        """
        Initialize provider.
        
        Args:
            api_key: API key for the provider
            **kwargs: Provider-specific configuration
        """
        self.api_key = api_key
        self.config = kwargs
    
    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Return the provider type."""
        pass
    
    @property
    @abstractmethod
    def supported_asset_classes(self) -> List[AssetClass]:
        """Return list of supported asset classes."""
        pass
    
    @abstractmethod
    async def get_quote(self, symbol: str, asset_class: AssetClass = AssetClass.STOCKS) -> Dict:
        """
        Get real-time quote for a symbol.
        
        Args:
            symbol: Ticker symbol
            asset_class: Asset class (stocks, forex, etc.)
        
        Returns:
            Dictionary with quote data:
            {
                "symbol": str,
                "current_price": float,
                "bid": float,
                "ask": float,
                "high": float,
                "low": float,
                "open": float,
                "previous_close": float,
                "volume": int,
                "timestamp": datetime
            }
        """
        pass
    
    @abstractmethod
    async def get_candles(
        self, 
        symbol: str, 
        timeframe: str,
        count: int = 100,
        asset_class: AssetClass = AssetClass.STOCKS
    ) -> List[Dict]:
        """
        Get historical candle data.
        
        Args:
            symbol: Ticker symbol
            timeframe: Timeframe (1m, 5m, 15m, 1h, 4h, D, W, M)
            count: Number of candles to fetch
            asset_class: Asset class (stocks, forex, etc.)
        
        Returns:
            List of candle dictionaries:
            [{
                "time": str (ISO 8601),
                "open": float,
                "high": float,
                "low": float,
                "close": float,
                "volume": int
            }]
        """
        pass
    
    @abstractmethod
    def normalize_symbol(self, symbol: str, asset_class: AssetClass) -> str:
        """
        Normalize symbol to provider-specific format.
        
        Args:
            symbol: User-provided symbol (e.g., "EUR/USD", "AAPL")
            asset_class: Asset class
        
        Returns:
            Provider-specific symbol format
            - Finnhub: "AAPL", "OANDA:EUR_USD"
            - OANDA: "EUR_USD"
        """
        pass
    
    def normalize_timeframe(self, timeframe: str) -> str:
        """
        Normalize timeframe to provider-specific format.
        
        Default implementation handles common formats.
        Override if provider uses different format.
        
        Args:
            timeframe: Standard format (1m, 5m, 15m, 1h, 4h, D, W, M)
        
        Returns:
            Provider-specific timeframe
        """
        # Default: return as-is
        return timeframe
