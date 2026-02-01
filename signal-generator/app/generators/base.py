"""
Base Signal Generator

Abstract base class that all signal generators must inherit from.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import structlog
import pandas as pd

from app.schemas.signal import Signal


logger = structlog.get_logger()


class GeneratorError(Exception):
    """Base exception for generator errors."""
    pass


class BaseSignalGenerator(ABC):
    """
    Base class for all signal generators.
    
    Signal generators monitor market conditions and emit signals when
    conditions are met. They run continuously in the signal-generator service.
    
    Example:
        class MyGenerator(BaseSignalGenerator):
            def __init__(self, config: Dict[str, Any]):
                super().__init__(config)
                self.threshold = config.get("threshold", 0.5)
            
            async def generate(self) -> List[Signal]:
                # Check conditions
                if condition_met:
                    return [Signal(...)]
                return []
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the generator.
        
        Args:
            config: Generator-specific configuration
        """
        self.config = config or {}
        self.name = self.__class__.__name__
        self._validate_config()
        logger.info("generator_initialized", generator=self.name, config=self.config)
    
    @abstractmethod
    async def generate(self) -> List[Signal]:
        """
        Generate signals based on current market conditions.
        
        This method is called periodically by the generator service.
        It should check conditions and return a list of signals to emit.
        
        Returns:
            List of Signal objects to emit (empty list if no signals)
            
        Raises:
            GeneratorError: If signal generation fails
        """
        pass
    
    def _validate_config(self):
        """
        Validate generator configuration.
        
        Override this method to add custom validation.
        
        Raises:
            ValueError: If configuration is invalid
        """
        pass
    
    def _enrich_metadata(self, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Enrich signal metadata with generator information.
        
        Automatically adds timeframe info from config if available.
        This should be called when creating Signal objects to ensure
        timeframe info is consistently included.
        
        Args:
            metadata: Existing metadata dict (or None)
            
        Returns:
            Enriched metadata dict with timeframe info
            
        Example:
            signal = Signal(
                signal_type=SignalType.RSI_OVERSOLD,
                tickers=[ticker_signal],
                metadata=self._enrich_metadata({
                    "rsi": current_rsi,
                    "threshold": self.threshold
                })
            )
        """
        enriched = metadata.copy() if metadata else {}
        
        # Add primary timeframe from config if present and not already in metadata
        if "timeframe" in self.config and "timeframe" not in enriched:
            enriched["timeframe"] = self.config["timeframe"]
        
        # Add multiple timeframes if present (for HTF generators)
        if "htf_timeframes" in self.config and "timeframes" not in enriched:
            enriched["timeframes"] = self.config["htf_timeframes"]
        
        return enriched
    
    def _dataframe_to_candles(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Convert DataFrame to list of candle dicts with normalized column names.
        
        Handles both DataFrame and dict/list formats for compatibility.
        Normalizes column names to: o, h, l, c, v, t
        
        Args:
            df: DataFrame with columns like: open/o, high/h, low/l, close/c, volume/v, timestamp/t
            
        Returns:
            List of candle dicts: [{"o": ..., "h": ..., "l": ..., "c": ..., "v": ..., "t": ...}]
            Empty list if df is None or empty
        """
        # If None, return empty list
        if df is None:
            return []
        
        # If already a list, return as-is (assume already normalized)
        if isinstance(df, list):
            return df
        
        # If DataFrame, convert to list of dicts with normalized names
        if isinstance(df, pd.DataFrame):
            if df.empty:
                return []
            
            # Create a copy and rename columns to short names
            df_normalized = df.copy()
            
            # Map long names to short names
            column_mapping = {
                'open': 'o',
                'high': 'h',
                'low': 'l',
                'close': 'c',
                'volume': 'v',
                'timestamp': 't'
            }
            
            # Rename columns if they exist
            df_normalized.rename(columns=column_mapping, inplace=True)
            
            # Convert to records (list of dicts)
            candles = df_normalized.to_dict('records')
            return candles
        
        # If dict, wrap in list
        if isinstance(df, dict):
            return [df]
        
        # Unknown format
        logger.warning("unknown_candle_format", type=type(df).__name__)
        return []
    
    @property
    def generator_type(self) -> str:
        """Get the generator type identifier."""
        return self.__class__.__name__.replace("Generator", "").lower()
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"

