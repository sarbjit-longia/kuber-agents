"""
Market Data Provider Registry

Multi-provider architecture supporting:
- Finnhub (stocks)
- Tiingo (stocks, crypto — recommended for stocks)
- OANDA (forex)
- Alpha Vantage (backup/multi-asset)
- Future: Crypto providers
"""
from .base import BaseProvider, ProviderType
from .finnhub import FinnhubProvider
from .oanda import OANDAProvider
from .tiingo import TiingoProvider

__all__ = [
    "BaseProvider",
    "ProviderType", 
    "FinnhubProvider",
    "OANDAProvider",
    "TiingoProvider",
    "get_provider"
]


def get_provider(provider_type: ProviderType, **kwargs) -> BaseProvider:
    """
    Factory function to get the appropriate provider.
    
    Args:
        provider_type: Type of provider (FINNHUB, OANDA, TIINGO, etc.)
        **kwargs: Provider-specific configuration
    
    Returns:
        Configured provider instance
    """
    providers = {
        ProviderType.FINNHUB: FinnhubProvider,
        ProviderType.OANDA: OANDAProvider,
        ProviderType.TIINGO: TiingoProvider,
    }
    
    provider_class = providers.get(provider_type)
    if not provider_class:
        raise ValueError(f"Unknown provider type: {provider_type}")
    
    return provider_class(**kwargs)
