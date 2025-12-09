"""Signal Generators"""
from app.generators.base import BaseSignalGenerator, GeneratorError
from app.generators.registry import (
    SignalGeneratorRegistry,
    get_registry,
    register_generator
)
from app.generators.mock import MockSignalGenerator
from app.generators.golden_cross import GoldenCrossSignalGenerator


# Register all generators
def _initialize_registry():
    """Initialize the generator registry with all available generators."""
    registry = get_registry()
    
    registry.register(MockSignalGenerator)
    registry.register(GoldenCrossSignalGenerator)


# Initialize registry on import
_initialize_registry()


__all__ = [
    "BaseSignalGenerator",
    "GeneratorError",
    "SignalGeneratorRegistry",
    "get_registry",
    "register_generator",
    "MockSignalGenerator",
    "GoldenCrossSignalGenerator",
]

