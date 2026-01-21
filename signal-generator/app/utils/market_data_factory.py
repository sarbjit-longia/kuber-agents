"""
Market Data Provider Factory

Creates the appropriate provider instance based on configuration.
Makes it easy to switch between providers without changing generator code.

Usage:
    from app.utils.market_data_factory import get_market_data_provider
    
    provider = get_market_data_provider()
    candles = await provider.fetch_candles("AAPL", "D", 365)
"""
from typing import Optional
import structlog

from app.config import settings
from app.utils.market_data_provider import MarketDataProvider, ProviderType
from app.utils.providers.finnhub_provider import FinnhubProvider
from app.utils.providers.dataplane_provider import DataPlaneProvider
from app.telemetry import get_meter

logger = structlog.get_logger()


# Global provider instance (singleton pattern)
_provider_instance: Optional[MarketDataProvider] = None
_provider_info_gauge = None


def _setup_provider_info_metric():
    """Log provider info (OpenTelemetry Python doesn't support simple gauges)."""
    # Provider info will be shown in Grafana dashboard as a static annotation
    # Actual provider is logged at startup
    pass


def get_market_data_provider(
    provider_type: Optional[ProviderType] = None,
    force_new: bool = False
) -> MarketDataProvider:
    """
    Get or create a market data provider instance.
    
    This uses a singleton pattern by default to reuse API clients.
    Set force_new=True to create a fresh instance.
    
    Args:
        provider_type: Which provider to use (defaults to settings.MARKET_DATA_PROVIDER)
        force_new: If True, create a new instance instead of reusing cached one
        
    Returns:
        MarketDataProvider instance
        
    Raises:
        ValueError: If provider type is not supported
        RuntimeError: If provider initialization fails (e.g., missing API key)
    """
    global _provider_instance
    
    # Return cached instance if available and not forcing new
    if _provider_instance and not force_new:
        return _provider_instance
    
    # Determine which provider to use
    if provider_type is None:
        provider_str = getattr(settings, "MARKET_DATA_PROVIDER", "finnhub")
        # Convert string to ProviderType enum
        try:
            provider_type = ProviderType(provider_str)
        except ValueError:
            logger.warning(
                "invalid_provider_type",
                provider=provider_str,
                using_default="data_plane"
            )
            provider_type = ProviderType.DATA_PLANE
    
    logger.info("creating_market_data_provider", provider=provider_type)
    
    # Create provider instance based on type
    if provider_type == ProviderType.DATA_PLANE:
        # Use Data Plane API (supports stocks + forex + local indicators)
        data_plane_url = getattr(settings, "DATA_PLANE_URL", "http://data-plane:8000")
        provider = DataPlaneProvider(data_plane_url=data_plane_url)
    
    elif provider_type == ProviderType.FINNHUB:
        if not settings.FINNHUB_API_KEY:
            raise RuntimeError(
                "Finnhub API key not configured. "
                "Set FINNHUB_API_KEY environment variable."
            )
        provider = FinnhubProvider(api_key=settings.FINNHUB_API_KEY)
    
    elif provider_type == ProviderType.ALPHA_VANTAGE:
        # TODO: Implement Alpha Vantage provider
        raise NotImplementedError(
            "Alpha Vantage provider not yet implemented. "
            "Use ProviderType.FINNHUB or implement AlphaVantageProvider."
        )
    
    elif provider_type == ProviderType.YAHOO_FINANCE:
        # TODO: Implement Yahoo Finance provider
        raise NotImplementedError(
            "Yahoo Finance provider not yet implemented. "
            "Use ProviderType.FINNHUB or implement YahooFinanceProvider."
        )
    
    elif provider_type == ProviderType.POLYGON:
        # TODO: Implement Polygon.io provider
        raise NotImplementedError(
            "Polygon.io provider not yet implemented. "
            "Use ProviderType.FINNHUB or implement PolygonProvider."
        )
    
    else:
        raise ValueError(f"Unsupported provider type: {provider_type}")
    
    # Cache the instance
    _provider_instance = provider
    
    # Setup and update provider info metric
    info_gauge = _setup_provider_info_metric()
    if info_gauge:
        info_gauge.set(provider.rate_limit_per_minute, {
            "provider": provider.provider_name.lower(),
            "supported_resolutions": str(len(provider.supported_resolutions)),
            "supported_indicators": str(len(provider.supported_indicators))
        })
    
    logger.info(
        "market_data_provider_created",
        provider=provider.provider_name,
        rate_limit=provider.rate_limit_per_minute,
        resolutions=len(provider.supported_resolutions),
        indicators=len(provider.supported_indicators)
    )
    
    return provider


def reset_provider():
    """
    Reset the cached provider instance.
    
    Useful for testing or when switching providers at runtime.
    """
    global _provider_instance
    _provider_instance = None
    logger.info("market_data_provider_reset")

