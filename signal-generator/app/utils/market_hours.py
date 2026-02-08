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
    
    Example:
        from app.utils.market_hours import MarketHoursChecker, MarketType
        
        # Check specific market
        if MarketHoursChecker.is_market_open(MarketType.US_STOCKS):
            pass
        
        # Check if any ticker from list is tradeable
        tickers = ["AAPL", "EUR_USD", "BTC-USD"]
        if MarketHoursChecker.any_ticker_tradeable(tickers):
            pass
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
        """
        Auto-detect asset type from ticker format.
        
        Args:
            ticker: Ticker symbol (e.g., "AAPL", "EUR_USD", "BTC-USD")
            
        Returns:
            Detected MarketType
            
        Rules:
            - Forex: Contains underscore (EUR_USD, GBP_USD)
            - Crypto: Contains hyphen (BTC-USD, ETH-USD)
            - Stock: Everything else (AAPL, MSFT, GOOGL)
        """
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
        """
        Check if a specific ticker is currently tradeable based on its market hours.
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            True if the ticker's market is open, False otherwise
        """
        asset_type = cls.detect_asset_type(ticker)
        return cls.is_market_open(asset_type)
    
    @classmethod
    def any_ticker_tradeable(cls, tickers: List[str]) -> bool:
        """
        Check if ANY ticker from the list is currently tradeable.
        
        Useful for generators monitoring mixed assets (stocks + forex + crypto).
        If at least one market is open, we should run the generator.
        
        Args:
            tickers: List of ticker symbols
            
        Returns:
            True if any ticker's market is open, False if all markets are closed
        """
        if not tickers:
            return False
        
        # Group tickers by asset type
        asset_types_present: Set[MarketType] = set()
        for ticker in tickers:
            asset_type = cls.detect_asset_type(ticker)
            asset_types_present.add(asset_type)
        
        # Check if any of the asset types are currently open
        for asset_type in asset_types_present:
            if cls.is_market_open(asset_type):
                logger.debug(
                    "market_open_for_asset_type",
                    asset_type=asset_type.value,
                    open=True
                )
                return True
        
        logger.debug(
            "all_markets_closed",
            asset_types_checked=[at.value for at in asset_types_present]
        )
        return False
    
    @classmethod
    def get_tradeable_tickers(cls, tickers: List[str]) -> List[str]:
        """
        Filter tickers to only those currently tradeable.
        
        Args:
            tickers: List of ticker symbols
            
        Returns:
            List of tickers whose markets are currently open
        """
        return [ticker for ticker in tickers if cls.is_ticker_tradeable(ticker)]
    
    @classmethod
    def is_market_open(cls, market_type: MarketType = MarketType.US_STOCKS) -> bool:
        """
        Check if the specified market is currently open.
        
        Args:
            market_type: Type of market to check
            
        Returns:
            True if market is open, False otherwise
            
        Example:
            >>> MarketHoursChecker.is_market_open(MarketType.US_STOCKS)
            True  # If called during market hours
            
            >>> MarketHoursChecker.is_market_open(MarketType.FOREX)
            True  # If called during forex hours
        """
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
        """
        Check if US stock market is currently open.
        
        Market hours: Monday-Friday, 9:30 AM - 4:00 PM ET
        
        Args:
            now_et: Current datetime in US Eastern timezone
            
        Returns:
            True if US stock market is open, False otherwise
        """
        # Weekend check (Saturday=5, Sunday=6)
        if now_et.weekday() in (5, 6):
            logger.debug(
                "us_stock_market_closed_weekend",
                day_of_week=now_et.strftime("%A")
            )
            return False
        
        # Time check (9:30 AM - 4:00 PM ET)
        current_time = now_et.time()
        if cls.STOCK_OPEN <= current_time <= cls.STOCK_CLOSE:
            return True
        
        logger.debug(
            "us_stock_market_closed_outside_hours",
            current_time_et=current_time.strftime("%H:%M:%S"),
            market_open=cls.STOCK_OPEN.strftime("%H:%M:%S"),
            market_close=cls.STOCK_CLOSE.strftime("%H:%M:%S")
        )
        return False
    
    @classmethod
    def _is_forex_market_open(cls, now_et: datetime) -> bool:
        """
        Check if Forex market is currently open.
        
        Market hours: Sunday 5:00 PM - Friday 5:00 PM ET (24/5)
        
        Args:
            now_et: Current datetime in US Eastern timezone
            
        Returns:
            True if Forex market is open, False otherwise
        """
        day_of_week = now_et.weekday()
        current_hour = now_et.hour
        
        # Friday after 5 PM ET - Closed
        if day_of_week == cls.FOREX_WEEK_CLOSE_DAY and current_hour >= cls.FOREX_WEEK_CLOSE_HOUR:
            logger.debug(
                "forex_market_closed_friday_evening",
                current_time_et=now_et.strftime("%A %H:%M:%S")
            )
            return False
        
        # Saturday - Closed
        if day_of_week == 5:
            logger.debug("forex_market_closed_saturday")
            return False
        
        # Sunday before 5 PM ET - Closed
        if day_of_week == cls.FOREX_WEEK_OPEN_DAY and current_hour < cls.FOREX_WEEK_OPEN_HOUR:
            logger.debug(
                "forex_market_closed_sunday_before_5pm",
                current_time_et=now_et.strftime("%A %H:%M:%S")
            )
            return False
        
        # All other times - Open (Mon-Fri all day, Sun after 5pm)
        return True
    
    @classmethod
    def get_market_status_message(cls, market_type: MarketType = MarketType.US_STOCKS) -> str:
        """
        Get a human-readable market status message.
        
        Args:
            market_type: Type of market to check
            
        Returns:
            Human-readable status message
            
        Example:
            >>> MarketHoursChecker.get_market_status_message(MarketType.US_STOCKS)
            "US Stock market is OPEN (9:30 AM - 4:00 PM ET)"
        """
        now_et = datetime.now(cls.ET)
        is_open = cls.is_market_open(market_type)
        status = "OPEN" if is_open else "CLOSED"
        
        if market_type == MarketType.US_STOCKS:
            return (
                f"US Stock market is {status} "
                f"(Hours: Mon-Fri 9:30 AM - 4:00 PM ET, "
                f"Current: {now_et.strftime('%A %I:%M %p ET')})"
            )
        elif market_type == MarketType.FOREX:
            return (
                f"Forex market is {status} "
                f"(Hours: Sun 5 PM - Fri 5 PM ET, "
                f"Current: {now_et.strftime('%A %I:%M %p ET')})"
            )
        elif market_type == MarketType.CRYPTO:
            return (
                f"Crypto market is {status} (24/7, "
                f"Current: {now_et.strftime('%A %I:%M %p ET')})"
            )
        else:
            return f"Market status unknown for type: {market_type}"
