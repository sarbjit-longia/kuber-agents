"""
Market Data Provider Registry

Multi-provider architecture supporting:
- Finnhub (stocks)
- OANDA (forex)
- Alpha Vantage (backup/multi-asset)
- Future: Crypto providers
"""
from .base import BaseProvider, ProviderType
from .finnhub import FinnhubProvider
from .oanda import OANDAProvider

__all__ = [
    "BaseProvider",
    "ProviderType", 
    "FinnhubProvider",
    "OANDAProvider",
    "get_provider"
]


def get_provider(provider_type: ProviderType, **kwargs) -> BaseProvider:
    """
    Factory function to get the appropriate provider.
    
    Args:
        provider_type: Type of provider (FINNHUB, OANDA, etc.)
        **kwargs: Provider-specific configuration
    
    Returns:
        Configured provider instance
    """
    providers = {
        ProviderType.FINNHUB: FinnhubProvider,
        ProviderType.OANDA: OANDAProvider,
    }
    
    provider_class = providers.get(provider_type)
    if not provider_class:
        raise ValueError(f"Unknown provider type: {provider_type}")
    
    return provider_class(**kwargs)
