"""Deterministic strategy engine: regime detection and setup evaluation."""
from .regime import RegimeDetector
from .evaluators import SetupEvaluator

__all__ = ["RegimeDetector", "SetupEvaluator"]
