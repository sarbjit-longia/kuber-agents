"""
Market Data Utilities - Compatibility Layer

This module provides backward compatibility with the old MarketDataFetcher interface.
It delegates to the provider abstraction layer.

New code should import from market_data_factory instead:
    from app.utils.market_data_factory import get_market_data_provider
    provider = get_market_data_provider()
"""
from typing import Optional, Dict
import pandas as pd
import structlog

from app.utils.market_data_factory import get_market_data_provider
from app.config import settings

logger = structlog.get_logger()


class MarketDataFetcher:
    """
    Legacy market data fetcher interface.
    
    This wraps the new provider abstraction layer for backward compatibility.
    Existing generators can continue using this class without changes.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize market data fetcher.
        
        Args:
            api_key: API key (optional, uses settings if not provided)
        """
        # Get provider from factory (uses configured provider)
        self._provider = get_market_data_provider()
        
        logger.info(
            "market_data_fetcher_initialized",
            provider=self._provider.provider_name,
            using_legacy_interface=True
        )
    
    async def fetch_candles(
        self,
        symbol: str,
        resolution: str = "D",
        lookback_days: int = 365
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical candle data.
        
        Delegates to the configured provider.
        """
        return await self._provider.fetch_candles(symbol, resolution, lookback_days)
    
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
        
        Delegates to the configured provider.
        """
        return await self._provider.fetch_indicator(
            symbol,
            indicator,
            resolution,
            lookback_days,
            **indicator_params
        )
    
    async def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get latest price.
        
        Delegates to the configured provider.
        """
        return await self._provider.get_latest_price(symbol)
