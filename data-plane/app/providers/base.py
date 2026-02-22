"""
Base Provider Interface

All market data providers must implement this interface.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Optional
from datetime import datetime
import time
import structlog

logger = structlog.get_logger()


class ProviderType(str, Enum):
    """Supported provider types."""
    FINNHUB = "finnhub"
    OANDA = "oanda"
    TIINGO = "tiingo"
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
        self.rate_limit_remaining = None
        self.rate_limit_total = None
        self.rate_limit_reset_time = None
    
    def _track_rate_limit(self, remaining: Optional[int], total: Optional[int], reset_time: Optional[int] = None):
        """
        Track rate limit information from API response headers.
        
        Args:
            remaining: Remaining API calls
            total: Total API calls allowed
            reset_time: Unix timestamp when rate limit resets
        """
        self.rate_limit_remaining = remaining
        self.rate_limit_total = total
        self.rate_limit_reset_time = reset_time
        
        # Update Prometheus metrics
        if remaining is not None and total is not None:
            from app.telemetry import api_rate_limit_remaining, api_rate_limit_total
            api_rate_limit_remaining.labels(provider=self.provider_type.value).set(remaining)
            api_rate_limit_total.labels(provider=self.provider_type.value).set(total)
            
            logger.debug(
                "rate_limit_tracked",
                provider=self.provider_type.value,
                remaining=remaining,
                total=total,
                usage_pct=round((1 - remaining/total) * 100, 1) if total > 0 else 0
            )
    
    def _track_api_call(self, endpoint: str, duration: float, status: str = "success", response_bytes: int = 0):
        """
        Track API call metrics.

        Args:
            endpoint: API endpoint called (e.g., "quote", "candles")
            duration: Call duration in seconds
            status: "success" or "error"
            response_bytes: Size of response body in bytes
        """
        from app.telemetry import api_calls_total, api_call_duration_seconds, provider_bandwidth_bytes_total

        api_calls_total.labels(
            provider=self.provider_type.value,
            endpoint=endpoint,
            status=status
        ).inc()

        api_call_duration_seconds.labels(
            provider=self.provider_type.value,
            endpoint=endpoint
        ).observe(duration)

        if response_bytes > 0:
            provider_bandwidth_bytes_total.labels(
                provider=self.provider_type.value,
                endpoint=endpoint
            ).inc(response_bytes)
    
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
