"""
Base Signal Generator

Abstract base class that all signal generators must inherit from.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import structlog

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
    
    @property
    def generator_type(self) -> str:
        """Get the generator type identifier."""
        return self.__class__.__name__.replace("Generator", "").lower()
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"

