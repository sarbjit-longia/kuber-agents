"""
Signal Generator Registry

Centralized registry for discovering and managing signal generators.
"""
from typing import Dict, List, Optional, Type
import structlog

from app.generators.base import BaseSignalGenerator, GeneratorError


logger = structlog.get_logger()


class SignalGeneratorRegistry:
    """
    Singleton registry for managing signal generators.
    
    Provides methods to:
    - Register generator classes
    - Discover available generators
    - Create generator instances
    """
    
    _instance = None
    _registry: Dict[str, Type[BaseSignalGenerator]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SignalGeneratorRegistry, cls).__new__(cls)
        return cls._instance
    
    def register(self, generator_class: Type[BaseSignalGenerator]) -> None:
        """
        Register a signal generator class.
        
        Args:
            generator_class: Generator class to register
            
        Raises:
            ValueError: If generator_class is not a valid BaseSignalGenerator subclass
        """
        if not issubclass(generator_class, BaseSignalGenerator):
            raise ValueError(
                f"{generator_class.__name__} must inherit from BaseSignalGenerator"
            )
        
        generator_type = generator_class.__name__.replace("Generator", "").lower()
        
        if generator_type in self._registry:
            logger.warning(
                "generator_already_registered",
                generator_type=generator_type,
                overwriting=True
            )
        
        self._registry[generator_type] = generator_class
        logger.info(
            "generator_registered",
            generator_type=generator_type,
            class_name=generator_class.__name__
        )
    
    def list_generators(self) -> List[str]:
        """
        List all registered generator types.
        
        Returns:
            List of generator type identifiers
        """
        return list(self._registry.keys())
    
    def create_generator(
        self,
        generator_type: str,
        config: Optional[Dict] = None
    ) -> BaseSignalGenerator:
        """
        Create an instance of a generator.
        
        Args:
            generator_type: Generator type identifier
            config: Generator-specific configuration
            
        Returns:
            Initialized generator instance
            
        Raises:
            GeneratorError: If generator_type is not registered or instantiation fails
        """
        generator_class = self._registry.get(generator_type)
        
        if not generator_class:
            raise GeneratorError(f"Unknown generator type: {generator_type}")
        
        try:
            return generator_class(config=config)
        except Exception as e:
            logger.error(
                "generator_instantiation_failed",
                generator_type=generator_type,
                error=str(e),
                exc_info=True
            )
            raise GeneratorError(f"Failed to create generator {generator_type}: {e}")
    
    def is_registered(self, generator_type: str) -> bool:
        """
        Check if a generator type is registered.
        
        Args:
            generator_type: Generator type identifier
            
        Returns:
            True if registered, False otherwise
        """
        return generator_type in self._registry
    
    def clear(self) -> None:
        """Clear all registered generators (mainly for testing)."""
        self._registry.clear()
        logger.info("generator_registry_cleared")


# Singleton instance
_registry = SignalGeneratorRegistry()


def get_registry() -> SignalGeneratorRegistry:
    """Get the global signal generator registry instance."""
    return _registry


def register_generator(generator_class: Type[BaseSignalGenerator]) -> None:
    """
    Convenience function to register a generator.
    
    Args:
        generator_class: Generator class to register
    """
    _registry.register(generator_class)

