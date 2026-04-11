"""
Test complete agent pipeline execution.

Pipelines are triggered by the signal/scanner architecture (Kafka + Trigger Dispatcher)
or by Celery Beat for periodic execution. There is no TimeTriggerAgent node.

Pipeline execution order: MarketData → Bias → Strategy → Risk → TradeReview → TradeManager
"""
import pytest
from uuid import uuid4

from app.agents import (
    MarketDataAgent,
    BiasAgent,
    StrategyAgent,
    RiskManagerAgent,
    TradeManagerAgent,
    TradeReviewAgent,
)
from app.schemas.pipeline_state import PipelineState


@pytest.fixture
def initial_state():
    """Create initial pipeline state."""
    return PipelineState(
        pipeline_id=uuid4(),
        execution_id=uuid4(),
        user_id=uuid4(),
        symbol="AAPL",
        mode="paper"
    )


class TestAgentPipeline:
    """Test complete agent pipeline execution."""

    def test_pipeline_market_data_to_risk(self, initial_state):
        """
        Test a partial pipeline from market data through risk assessment.

        Pipeline flow:
        1. Market Data — fetch OHLCV candles (mock)
        2. Strategy — set manually (skip expensive LLM agents in unit test)
        3. Risk Manager — validate and size trade
        """
        state = initial_state

        # Step 1: Market Data
        market_data = MarketDataAgent(
            "market-1",
            {
                "timeframes": ["5m", "1h"],
                "lookback_periods": 50,
                "use_mock_data": True
            }
        )
        state = market_data.process(state)

        assert state.market_data is not None
        assert state.market_data.current_price > 0
        assert "5m" in state.market_data.timeframes

        # Step 2: Inject strategy manually (avoids slow/expensive LLM calls in tests)
        from app.schemas.pipeline_state import StrategyResult
        state.strategy = StrategyResult(
            action="BUY",
            confidence=0.75,
            entry_price=state.market_data.current_price,
            stop_loss=state.market_data.current_price * 0.98,
            take_profit=state.market_data.current_price * 1.04,
            position_size=None,
            reasoning="Test strategy for pipeline simulation",
            pattern_detected="Bull flag"
        )

        # Step 3: Risk Manager
        risk_manager = RiskManagerAgent(
            "risk-1",
            {
                "account_size": 10000,
                "risk_per_trade_percent": 1.0,
                "min_risk_reward_ratio": 2.0
            }
        )
        state = risk_manager.process(state)

        assert state.risk_assessment is not None

    def test_pipeline_with_hold_signal(self, initial_state):
        """Test pipeline when strategy signals HOLD."""
        state = initial_state

        market_data = MarketDataAgent(
            "market-1",
            {"timeframes": ["5m"], "use_mock_data": True}
        )
        state = market_data.process(state)

        from app.schemas.pipeline_state import StrategyResult
        state.strategy = StrategyResult(
            action="HOLD",
            confidence=0.6,
            entry_price=None,
            stop_loss=None,
            take_profit=None,
            position_size=None,
            reasoning="No clear opportunity",
            pattern_detected=None
        )

        risk_manager = RiskManagerAgent(
            "risk-1",
            {"account_size": 10000}
        )
        state = risk_manager.process(state)

        assert state.risk_assessment.approved is True
        assert state.risk_assessment.position_size == 0

        trade_manager = TradeManagerAgent(
            "trade-1",
            {"enable_execution": False}
        )
        state = trade_manager.process(state)

        assert state.trade_execution.status in ["no_action", "filled"]

    def test_pipeline_with_risk_rejection(self, initial_state):
        """Test pipeline when risk manager rejects a trade with poor R/R."""
        state = initial_state

        market_data = MarketDataAgent(
            "market-1",
            {"timeframes": ["5m"], "use_mock_data": True}
        )
        state = market_data.process(state)

        from app.schemas.pipeline_state import StrategyResult
        state.strategy = StrategyResult(
            action="BUY",
            confidence=0.5,
            entry_price=100.0,
            stop_loss=98.0,    # $2 risk
            take_profit=101.0, # $1 reward — 0.5:1 R/R, should be rejected
            position_size=None,
            reasoning="Poor R/R for testing",
            pattern_detected=None
        )

        risk_manager = RiskManagerAgent(
            "risk-1",
            {
                "account_size": 10000,
                "min_risk_reward_ratio": 2.0
            }
        )
        state = risk_manager.process(state)

        assert state.risk_assessment.approved is False
        assert len(state.risk_assessment.warnings) > 0

        trade_manager = TradeManagerAgent(
            "trade-1",
            {"enable_execution": False}
        )
        state = trade_manager.process(state)

        assert state.trade_execution.status == "rejected"


def test_agent_categories_complete():
    """Test that we have agents in all required pipeline categories."""
    from app.agents import get_registry

    registry = get_registry()
    agents = registry.list_all_metadata()
    categories = {agent.category for agent in agents}

    assert "data" in categories, "Missing data agents"
    assert "analysis" in categories, "Missing analysis agents"
    assert "risk" in categories, "Missing risk agents"
    assert "execution" in categories, "Missing execution agents"


def test_cost_tracking_in_pipeline(initial_state):
    """Test that costs are tracked correctly through free agents."""
    state = initial_state

    market_data = MarketDataAgent(
        "market-1",
        {"timeframes": ["5m"], "use_mock_data": True}
    )
    state = market_data.process(state)

    assert state.total_cost == 0.0
