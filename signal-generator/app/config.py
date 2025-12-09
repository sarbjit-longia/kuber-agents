"""
Signal Generator Configuration
"""
import json
import os
from pathlib import Path
from typing import Optional, List
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
    
    # Generator Settings
    MOCK_GENERATOR_INTERVAL_SECONDS: int = 60  # Emit every 60 seconds
    GOLDEN_CROSS_CHECK_INTERVAL_SECONDS: int = 300  # Check every 5 minutes
    GOLDEN_CROSS_SMA_SHORT: int = 50
    GOLDEN_CROSS_SMA_LONG: int = 200
    GOLDEN_CROSS_TIMEFRAME: str = "1d"
    
    # Config file paths
    WATCHLIST_CONFIG_PATH: str = "config/watchlist.json"
    
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

