"""
Signal Generator Configuration
"""
import json
import os
from pathlib import Path
from typing import Optional, List
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import structlog


logger = structlog.get_logger()


class Settings(BaseSettings):
    """Signal generator settings."""
    
    # Service
    SERVICE_NAME: str = "signal-generator"
    LOG_LEVEL: str = "INFO"
    
    # Kafka (for Phase 2)
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_SIGNAL_TOPIC: str = "trading-signals"
    
    # Market Data
    FINNHUB_API_KEY: Optional[str] = None
    MARKET_DATA_PROVIDER: str = "data_plane"  # Options: data_plane, finnhub, alpha_vantage, yahoo_finance, polygon
    DATA_PLANE_URL: str = "http://data-plane:8000"  # Data Plane API URL
    
    # Generator Settings
    MOCK_GENERATOR_INTERVAL_SECONDS: int = 60  # Emit every 60 seconds
    GOLDEN_CROSS_CHECK_INTERVAL_SECONDS: int = 300  # Check every 5 minutes
    GOLDEN_CROSS_SMA_SHORT: int = 50
    GOLDEN_CROSS_SMA_LONG: int = 200
    GOLDEN_CROSS_TIMEFRAME: str = "D"  # Finnhub uses "D" for daily, not "1d"
    
    # Death Cross Settings
    DEATH_CROSS_CHECK_INTERVAL_SECONDS: int = 300  # Check every 5 minutes
    DEATH_CROSS_SMA_SHORT: int = 50
    DEATH_CROSS_SMA_LONG: int = 200
    DEATH_CROSS_TIMEFRAME: str = "D"
    
    # Global additional timeframes (comma-separated string like "5,15,60")
    # These will be added to each generator's primary timeframe
    ADDITIONAL_TIMEFRAMES: str = "5,15,60"
    
    # RSI Settings
    RSI_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    RSI_PERIOD: int = 14
    RSI_OVERSOLD_THRESHOLD: float = 30.0
    RSI_OVERBOUGHT_THRESHOLD: float = 70.0
    RSI_TIMEFRAME: str = "D"
    
    # MACD Settings
    MACD_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    MACD_FAST_PERIOD: int = 12
    MACD_SLOW_PERIOD: int = 26
    MACD_SIGNAL_PERIOD: int = 9
    MACD_TIMEFRAME: str = "D"
    
    # Volume Spike Settings
    VOLUME_SPIKE_CHECK_INTERVAL_SECONDS: int = 120  # Check every 2 minutes
    VOLUME_SPIKE_PERIOD: int = 20
    VOLUME_SPIKE_THRESHOLD: float = 2.0  # 2x average volume
    VOLUME_SPIKE_TIMEFRAME: str = "D"
    
    # Bollinger Bands Settings
    BBANDS_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    BBANDS_TIMEPERIOD: int = 20
    BBANDS_NBDEVUP: int = 2
    BBANDS_NBDEVDN: int = 2
    BBANDS_TIMEFRAME: str = "D"
    BBANDS_SIGNAL_TYPE: str = "breakout"  # "breakout" or "bounce"
    
    # Stochastic Settings
    STOCH_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    STOCH_FASTK_PERIOD: int = 14
    STOCH_SLOWK_PERIOD: int = 3
    STOCH_SLOWD_PERIOD: int = 3
    STOCH_OVERBOUGHT: float = 80
    STOCH_OVERSOLD: float = 20
    STOCH_TIMEFRAME: str = "D"
    
    # ADX Settings
    ADX_CHECK_INTERVAL_SECONDS: int = 240  # Check every 4 minutes
    ADX_TIMEPERIOD: int = 14
    ADX_STRONG_TREND: float = 25
    ADX_WEAK_TREND: float = 20
    ADX_TIMEFRAME: str = "D"
    
    # EMA Crossover Settings
    EMA_CHECK_INTERVAL_SECONDS: int = 300  # Check every 5 minutes
    EMA_FAST: int = 12
    EMA_SLOW: int = 26
    EMA_TIMEFRAME: str = "D"
    
    # ATR Settings
    ATR_CHECK_INTERVAL_SECONDS: int = 240  # Check every 4 minutes
    ATR_TIMEPERIOD: int = 14
    ATR_SPIKE_MULTIPLIER: float = 1.5
    ATR_COMPRESSION_MULTIPLIER: float = 0.7
    ATR_LOOKBACK_FOR_AVERAGE: int = 30
    ATR_TIMEFRAME: str = "D"
    
    # CCI Settings
    CCI_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    CCI_TIMEPERIOD: int = 20
    CCI_OVERBOUGHT: float = 100
    CCI_OVERSOLD: float = -100
    CCI_TIMEFRAME: str = "D"
    
    # Stochastic RSI Settings
    STOCHRSI_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    STOCHRSI_TIMEPERIOD: int = 14
    STOCHRSI_FASTK_PERIOD: int = 14
    STOCHRSI_FASTD_PERIOD: int = 3
    STOCHRSI_OVERBOUGHT: float = 80
    STOCHRSI_OVERSOLD: float = 20
    STOCHRSI_TIMEFRAME: str = "D"
    
    # Williams %R Settings
    WILLR_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    WILLR_TIMEPERIOD: int = 14
    WILLR_OVERBOUGHT: float = -20
    WILLR_OVERSOLD: float = -80
    WILLR_TIMEFRAME: str = "D"
    
    # AROON Settings
    AROON_CHECK_INTERVAL_SECONDS: int = 240  # Check every 4 minutes
    AROON_TIMEPERIOD: int = 25
    AROON_TREND_THRESHOLD: float = 70
    AROON_TIMEFRAME: str = "D"
    
    # MFI Settings
    MFI_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    MFI_TIMEPERIOD: int = 14
    MFI_OVERBOUGHT: float = 80
    MFI_OVERSOLD: float = 20
    MFI_TIMEFRAME: str = "D"
    
    # OBV Settings
    OBV_CHECK_INTERVAL_SECONDS: int = 240  # Check every 4 minutes
    OBV_SMA_PERIOD: int = 20
    OBV_DIVERGENCE_LOOKBACK: int = 10
    OBV_MIN_PRICE_CHANGE: float = 2.0
    OBV_TIMEFRAME: str = "D"
    
    # SAR Settings
    SAR_CHECK_INTERVAL_SECONDS: int = 300  # Check every 5 minutes
    SAR_ACCELERATION: float = 0.02
    SAR_MAXIMUM: float = 0.20
    SAR_TIMEFRAME: str = "D"
    
    # 200 EMA Crossover Settings
    EMA_200_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    EMA_200_PERIOD: int = 200
    EMA_200_TIMEFRAME: str = "D"
    
    # Swing Point Break Settings
    SWING_POINT_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    SWING_POINT_LOOKBACK_PERIODS: int = 20
    SWING_POINT_MIN_STRENGTH: int = 2
    SWING_POINT_TIMEFRAME: str = "D"
    
    # Momentum Divergence Settings
    DIVERGENCE_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    DIVERGENCE_INDICATOR: str = "rsi"  # "rsi" or "macd"
    DIVERGENCE_RSI_PERIOD: int = 14
    DIVERGENCE_LOOKBACK_PERIODS: int = 14
    DIVERGENCE_TIMEFRAME: str = "D"
    
    # Fair Value Gap Settings
    FVG_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    FVG_MIN_GAP_PIPS: int = 10
    FVG_TIMEFRAME: str = "D"
    
    # Liquidity Sweep Settings
    LIQUIDITY_SWEEP_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    LIQUIDITY_SWEEP_LOOKBACK_PERIODS: int = 20
    LIQUIDITY_SWEEP_TOLERANCE_PIPS: int = 5
    LIQUIDITY_SWEEP_TIMEFRAME: str = "D"
    
    # Break of Structure Settings
    BOS_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    BOS_LOOKBACK_PERIODS: int = 20
    BOS_MIN_SWING_STRENGTH: int = 3
    BOS_TIMEFRAME: str = "D"
    
    # Order Block Settings
    ORDER_BLOCK_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    ORDER_BLOCK_LOOKBACK_PERIODS: int = 30
    ORDER_BLOCK_MIN_MOVE_PIPS: int = 20
    ORDER_BLOCK_TIMEFRAME: str = "D"
    
    # Change of Character Settings
    CHOCH_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    CHOCH_LOOKBACK_PERIODS: int = 30
    CHOCH_MIN_SWING_STRENGTH: int = 3
    CHOCH_TIMEFRAME: str = "D"
    
    # Volume Profile POC Settings
    POC_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    POC_LOOKBACK_PERIODS: int = 20
    POC_TIMEFRAME: str = "D"
    
    # Accumulation/Distribution Settings
    ACCUM_DIST_CHECK_INTERVAL_SECONDS: int = 180  # Check every 3 minutes
    ACCUM_DIST_LOOKBACK_PERIODS: int = 14
    ACCUM_DIST_MIN_SLOPE: float = 0.001
    ACCUM_DIST_TIMEFRAME: str = "D"
    
    # HTF Trend Alignment Settings
    HTF_TREND_CHECK_INTERVAL_SECONDS: int = 240  # Check every 4 minutes
    HTF_TREND_EMA_PERIOD: int = 50
    HTF_TREND_TIMEFRAMES: str = "60,240,D"  # Comma-separated HTF timeframes
    HTF_TREND_MIN_ALIGNMENT: int = 2
    HTF_TREND_TIMEFRAME: str = "15"  # Current timeframe
    
    # Config file paths
    WATCHLIST_CONFIG_PATH: str = "config/watchlist.json"
    
    # Backend Database (for scanner discovery)
    BACKEND_DB_URL: Optional[str] = Field(
        default=None,
        description="PostgreSQL connection string for backend database (to query active scanners)"
    )
    
    # Universe refresh interval
    UNIVERSE_REFRESH_INTERVAL_SECONDS: int = Field(
        default=300,  # 5 minutes
        description="How often to refresh the ticker universe from active scanners"
    )
    
    # Market Hours Configuration
    # Auto-detects asset type from tickers (stocks/forex/crypto)
    ENABLE_MARKET_HOURS_CHECK: bool = Field(
        default=True,
        description="Enable market hours checking (skip generation when all markets closed)"
    )
    
    MARKET_HOURS_CHECK_INTERVAL_SECONDS: int = Field(
        default=60,
        description="How often to check if any market opened (when all previously closed)"
    )
    
    # Kafka configuration
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_SIGNAL_TOPIC: str = "trading-signals"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )
    
    def get_watchlist(self) -> List[str]:
        """
        Get watchlist tickers from config file.
        
        Returns:
            List of ticker symbols from watchlist.json
        """
        config_path = Path(self.WATCHLIST_CONFIG_PATH)
        
        # Try multiple possible locations
        search_paths = [
            config_path,  # Relative to current directory
            Path(__file__).parent.parent / config_path,  # Relative to app/
            Path("/app") / config_path,  # Docker container path
        ]
        
        for path in search_paths:
            if path.exists():
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                    
                    tickers = data.get("tickers", [])
                    
                    if not tickers:
                        logger.warning(
                            "watchlist_config_empty",
                            path=str(path),
                            using_default=True
                        )
                        return self._get_default_watchlist()
                    
                    # Normalize to uppercase
                    tickers = [t.strip().upper() for t in tickers]
                    
                    logger.info(
                        "watchlist_loaded",
                        path=str(path),
                        ticker_count=len(tickers)
                    )
                    
                    return tickers
                
                except Exception as e:
                    logger.error(
                        "watchlist_config_load_error",
                        path=str(path),
                        error=str(e),
                        using_default=True
                    )
                    return self._get_default_watchlist()
        
        # If no config file found, use default
        logger.warning(
            "watchlist_config_not_found",
            searched_paths=[str(p) for p in search_paths],
            using_default=True
        )
        return self._get_default_watchlist()
    
    def _get_default_watchlist(self) -> List[str]:
        """Get default watchlist if config file is not available."""
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]


settings = Settings()

