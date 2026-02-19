"""
Market Hours Checker

Determines if a given market is currently open for trading.
Handles US Stock market hours and Forex market hours.
Auto-detects asset type from ticker format.
"""
from datetime import datetime, time
from enum import Enum
from zoneinfo import ZoneInfo
from typing import List, Set
import structlog


logger = structlog.get_logger()


class MarketType(str, Enum):
    """Supported market types."""
    US_STOCKS = "US_STOCKS"
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"  # Always open


class MarketHoursChecker:
    """
    Check if markets are currently open.
    
    Market Hours (US Eastern Time):
    - US Stocks: Monday-Friday, 9:30 AM - 4:00 PM ET
    - Forex: Sunday 5:00 PM - Friday 5:00 PM ET (24/5)
    - Crypto: 24/7 (always open)
    
    Auto-detects asset type from ticker format:
    - Forex: Contains underscore (EUR_USD, GBP_USD)
    - Crypto: Contains hyphen with USD (BTC-USD, ETH-USD)
    - Stock: Everything else (AAPL, MSFT, GOOGL)
    """
    
    # US Eastern timezone
    ET = ZoneInfo("America/New_York")
    
    # US Stock market hours (in ET)
    STOCK_OPEN = time(9, 30)   # 9:30 AM
    STOCK_CLOSE = time(16, 0)  # 4:00 PM
    
    # Forex market hours (Sunday 5 PM - Friday 5 PM ET)
    FOREX_WEEK_OPEN_DAY = 6  # Sunday (0=Monday, 6=Sunday)
    FOREX_WEEK_OPEN_HOUR = 17  # 5:00 PM
    FOREX_WEEK_CLOSE_DAY = 4  # Friday
    FOREX_WEEK_CLOSE_HOUR = 17  # 5:00 PM
    
    @classmethod
    def detect_asset_type(cls, ticker: str) -> MarketType:
        """Auto-detect asset type from ticker format."""
        ticker_upper = ticker.upper()
        
        # Forex: EUR_USD, GBP_USD, etc.
        if "_" in ticker_upper:
            return MarketType.FOREX
        
        # Crypto: BTC-USD, ETH-USD, etc.
        if "-" in ticker_upper and "USD" in ticker_upper:
            return MarketType.CRYPTO
        
        # Default to stocks
        return MarketType.US_STOCKS
    
    @classmethod
    def is_ticker_tradeable(cls, ticker: str) -> bool:
        """Check if a specific ticker is currently tradeable based on its market hours."""
        asset_type = cls.detect_asset_type(ticker)
        return cls.is_market_open(asset_type)
    
    @classmethod
    def is_market_open(cls, market_type: MarketType = MarketType.US_STOCKS) -> bool:
        """Check if the specified market is currently open."""
        now_et = datetime.now(cls.ET)
        
        if market_type == MarketType.CRYPTO:
            return True  # Crypto never sleeps
        
        elif market_type == MarketType.US_STOCKS:
            return cls._is_us_stock_market_open(now_et)
        
        elif market_type == MarketType.FOREX:
            return cls._is_forex_market_open(now_et)
        
        else:
            logger.warning("unknown_market_type", market_type=market_type)
            return True  # Default to open if unknown
    
    @classmethod
    def _is_us_stock_market_open(cls, now_et: datetime) -> bool:
        """Check if US stock market is currently open. Market hours: Monday-Friday, 9:30 AM - 4:00 PM ET"""
        # Weekend check (Saturday=5, Sunday=6)
        if now_et.weekday() in (5, 6):
            return False
        
        # Time check (9:30 AM - 4:00 PM ET)
        current_time = now_et.time()
        if cls.STOCK_OPEN <= current_time <= cls.STOCK_CLOSE:
            return True
        
        return False
    
    @classmethod
    def _is_forex_market_open(cls, now_et: datetime) -> bool:
        """Check if Forex market is currently open. Market hours: Sunday 5:00 PM - Friday 5:00 PM ET (24/5)"""
        day_of_week = now_et.weekday()
        current_hour = now_et.hour
        
        # Friday after 5 PM ET - Closed
        if day_of_week == cls.FOREX_WEEK_CLOSE_DAY and current_hour >= cls.FOREX_WEEK_CLOSE_HOUR:
            return False
        
        # Saturday - Closed
        if day_of_week == 5:
            return False
        
        # Sunday before 5 PM ET - Closed
        if day_of_week == cls.FOREX_WEEK_OPEN_DAY and current_hour < cls.FOREX_WEEK_OPEN_HOUR:
            return False
        
        # All other times - Open (Mon-Fri all day, Sun after 5pm)
        return True
