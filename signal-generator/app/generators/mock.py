"""
Mock Signal Generator

Generates random test signals for development and testing.
"""
import random
from typing import Dict, Any, List
import structlog

from app.generators.base import BaseSignalGenerator
from app.schemas.signal import Signal, TickerSignal, SignalType, BiasType


logger = structlog.get_logger()


class MockSignalGenerator(BaseSignalGenerator):
    """
    Mock signal generator for testing and development.
    
    Emits random signals for configured tickers to test the signal flow
    without requiring real market data or complex calculations.
    
    Configuration:
        - tickers: List of tickers to emit signals for
        - emission_probability: Probability (0-1) of emitting a signal each cycle
        - bias_options: List of bias types to randomly choose from
    
    Example config:
        {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "emission_probability": 0.3,
            "bias_options": ["BULLISH", "BEARISH"]
        }
    """
    
    def _validate_config(self):
        """Validate mock generator configuration."""
        emission_prob = self.config.get("emission_probability", 0.3)
        if not 0 <= emission_prob <= 1:
            raise ValueError("emission_probability must be between 0 and 1")
    
    async def generate(self) -> List[Signal]:
        """
        Generate random mock signals.
        
        Returns:
            List of Signal objects (may be empty if probability check fails)
        """
        tickers = self.config.get("tickers", ["AAPL", "MSFT"])
        emission_prob = self.config.get("emission_probability", 0.3)
        bias_options = self.config.get(
            "bias_options",
            [BiasType.BULLISH, BiasType.BEARISH]
        )
        
        # Randomly decide whether to emit a signal this cycle
        if random.random() > emission_prob:
            logger.debug(
                "mock_generator_no_emission",
                probability_check_failed=True
            )
            return []
        
        # Select random tickers (1-3 tickers per signal)
        num_tickers = random.randint(1, min(3, len(tickers)))
        selected_tickers = random.sample(tickers, num_tickers)
        
        # Generate signal for each ticker
        ticker_signals = []
        for ticker in selected_tickers:
            chosen_bias = random.choice(bias_options)
            confidence = round(random.uniform(60, 95), 0)  # 60-95% confidence
            
            ticker_signals.append(TickerSignal(
                ticker=ticker,
                signal=chosen_bias,
                confidence=confidence,
                reasoning=f"Mock signal with {chosen_bias.value} bias (test data)"
            ))
        
        signal = Signal(
            signal_type=SignalType.MOCK,
            source="mock_generator",
            tickers=ticker_signals,
            metadata={
                "generator": "mock",
                "emission_probability": emission_prob,
                "note": "This is test data for development"
            }
        )
        
        logger.info(
            "mock_signal_generated",
            signal_id=str(signal.signal_id),
            tickers=[ts.ticker for ts in ticker_signals],
            signals={ts.ticker: ts.signal.value for ts in ticker_signals}
        )
        
        return [signal]

