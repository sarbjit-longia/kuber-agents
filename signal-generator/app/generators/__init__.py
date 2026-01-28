"""Signal Generators"""
from app.generators.base import BaseSignalGenerator, GeneratorError
from app.generators.registry import (
    SignalGeneratorRegistry,
    get_registry,
    register_generator
)
# Removed MockSignalGenerator import - not for production use
from app.generators.golden_cross import GoldenCrossSignalGenerator
from app.generators.death_cross import DeathCrossSignalGenerator
from app.generators.rsi import RSISignalGenerator
from app.generators.macd import MACDSignalGenerator
from app.generators.volume_spike import VolumeSpikeSignalGenerator
from app.generators.bollinger_bands import BollingerBandsSignalGenerator
from app.generators.stochastic import StochasticSignalGenerator
from app.generators.adx import ADXSignalGenerator
from app.generators.ema_crossover import EMACrossoverSignalGenerator
from app.generators.atr import ATRSignalGenerator
from app.generators.cci import CCISignalGenerator
from app.generators.stochrsi import StochRSISignalGenerator
from app.generators.williams_r import WilliamsRSignalGenerator
from app.generators.aroon import AroonSignalGenerator
from app.generators.mfi import MFISignalGenerator
from app.generators.obv import OBVSignalGenerator
from app.generators.sar import SARSignalGenerator


# Register all generators
def _initialize_registry():
    """Initialize the generator registry with all available generators."""
    registry = get_registry()
    
    # DO NOT register MockSignalGenerator in production
    # registry.register(MockSignalGenerator)
    registry.register(GoldenCrossSignalGenerator)
    registry.register(DeathCrossSignalGenerator)
    registry.register(RSISignalGenerator)
    registry.register(MACDSignalGenerator)
    registry.register(VolumeSpikeSignalGenerator)
    registry.register(BollingerBandsSignalGenerator)
    registry.register(StochasticSignalGenerator)
    registry.register(ADXSignalGenerator)
    registry.register(EMACrossoverSignalGenerator)
    registry.register(ATRSignalGenerator)
    registry.register(CCISignalGenerator)
    registry.register(StochRSISignalGenerator)
    registry.register(WilliamsRSignalGenerator)
    registry.register(AroonSignalGenerator)
    registry.register(MFISignalGenerator)
    registry.register(OBVSignalGenerator)
    registry.register(SARSignalGenerator)


# Initialize registry on import
_initialize_registry()


__all__ = [
    "BaseSignalGenerator",
    "GeneratorError",
    "SignalGeneratorRegistry",
    "get_registry",
    "register_generator",
    # "MockSignalGenerator",  # Removed from exports
    "GoldenCrossSignalGenerator",
    "DeathCrossSignalGenerator",
    "RSISignalGenerator",
    "MACDSignalGenerator",
    "VolumeSpikeSignalGenerator",
    "BollingerBandsSignalGenerator",
    "StochasticSignalGenerator",
    "ADXSignalGenerator",
    "EMACrossoverSignalGenerator",
    "ATRSignalGenerator",
    "CCISignalGenerator",
    "StochRSISignalGenerator",
    "WilliamsRSignalGenerator",
    "AroonSignalGenerator",
    "MFISignalGenerator",
    "OBVSignalGenerator",
    "SARSignalGenerator",
]


