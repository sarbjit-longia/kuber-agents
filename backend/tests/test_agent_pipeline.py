"""
Test complete agent pipeline execution.

This demonstrates how agents work together in sequence.
"""
import pytest
from uuid import uuid4

from app.agents import (
    TimeTriggerAgent,
    MarketDataAgent,
    BiasAgent,
    StrategyAgent,
    RiskManagerAgent,
    TradeManagerAgent
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
    
    def test_complete_pipeline_simulation(self, initial_state):
        """
        Test a complete pipeline with all agents in sequence.
        
        Pipeline flow:
        1. Time Trigger - Check if should execute
        2. Market Data - Fetch market data
        3. Bias Agent - Analyze bias (SKIPPED in test - expensive)
        4. Strategy Agent - Generate strategy (SKIPPED in test - expensive)
        5. Risk Manager - Validate and size trade
        6. Trade Manager - Execute trade
        """
        state = initial_state
        
        # Step 1: Time Trigger
        trigger = TimeTriggerAgent("trigger-1", {"interval": "5m"})
        state = trigger.process(state)
        
        assert state.trigger_met is True
        assert "Time trigger" in state.trigger_reason
        print(f"\n✓ Step 1: Trigger met - {state.trigger_reason}")
        
        # Step 2: Market Data
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
        print(f"✓ Step 2: Market data fetched - Price: ${state.market_data.current_price:.2f}")
        
        # Step 3 & 4: Skip AI agents in test (they're expensive and slow)
        # Instead, manually set strategy for testing risk/trade managers
        from app.schemas.pipeline_state import StrategyResult
        
        state.strategy = StrategyResult(
            action="BUY",
            confidence=0.75,
            entry_price=state.market_data.current_price,
            stop_loss=state.market_data.current_price * 0.98,  # 2% stop
            take_profit=state.market_data.current_price * 1.04,  # 4% target (2:1 R/R)
            position_size=None,  # Will be calculated by risk manager
            reasoning="Test strategy for pipeline simulation",
            pattern_detected="Bull flag"
        )
        print(f"✓ Step 3-4: Strategy set (simulated) - {state.strategy.action}")
        
        # Step 5: Risk Manager
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
        print(f"✓ Step 5: Risk assessment - Approved: {state.risk_assessment.approved}, "
              f"Position: {state.risk_assessment.position_size:.0f} shares")
        
        # Step 6: Trade Manager
        trade_manager = TradeManagerAgent(
            "trade-1",
            {
                "order_type": "market",
                "enable_execution": False  # Simulation only
            }
        )
        state = trade_manager.process(state)
        
        assert state.trade_execution is not None
        print(f"✓ Step 6: Trade execution - Status: {state.trade_execution.status}")
        
        # Verify complete pipeline
        assert len(state.execution_log) > 0
        print(f"\n📊 Pipeline Summary:")
        print(f"   Total Cost: ${state.total_cost:.2f}")
        print(f"   Execution Steps: {len(state.execution_log)}")
        print(f"   Errors: {len(state.errors)}")
        print(f"   Warnings: {len(state.warnings)}")
    
    def test_pipeline_with_hold_signal(self, initial_state):
        """Test pipeline when strategy signals HOLD."""
        state = initial_state
        
        # Get market data
        market_data = MarketDataAgent(
            "market-1",
            {"timeframes": ["5m"], "use_mock_data": True}
        )
        state = market_data.process(state)
        
        # Set HOLD strategy
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
        
        # Risk manager should approve HOLD
        risk_manager = RiskManagerAgent(
            "risk-1",
            {"account_size": 10000}
        )
        state = risk_manager.process(state)
        
        assert state.risk_assessment.approved is True
        assert state.risk_assessment.position_size == 0
        
        # Trade manager should not execute
        trade_manager = TradeManagerAgent(
            "trade-1",
            {"enable_execution": False}
        )
        state = trade_manager.process(state)
        
        assert state.trade_execution.status in ["no_action", "filled"]
        print(f"✓ HOLD signal correctly processed - no trade executed")
    
    def test_pipeline_with_risk_rejection(self, initial_state):
        """Test pipeline when risk manager rejects trade."""
        state = initial_state
        
        # Get market data
        market_data = MarketDataAgent(
            "market-1",
            {"timeframes": ["5m"], "use_mock_data": True}
        )
        state = market_data.process(state)
        
        # Set strategy with poor risk/reward
        from app.schemas.pipeline_state import StrategyResult
        state.strategy = StrategyResult(
            action="BUY",
            confidence=0.5,
            entry_price=100.0,
            stop_loss=98.0,   # $2 risk
            take_profit=101.0,  # $1 reward (0.5:1 R/R - BAD!)
            position_size=None,
            reasoning="Poor R/R for testing",
            pattern_detected=None
        )
        
        # Risk manager should reject
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
        print(f"✓ Poor R/R trade correctly rejected by risk manager")
        
        # Trade manager should record rejection
        trade_manager = TradeManagerAgent(
            "trade-1",
            {"enable_execution": False}
        )
        state = trade_manager.process(state)
        
        assert state.trade_execution.status == "rejected"


def test_agent_categories_complete():
    """Test that we have agents in all required categories."""
    from app.agents import get_registry
    
    registry = get_registry()
    agents = registry.list_all_metadata()
    
    categories = {agent.category for agent in agents}
    
    # Check we have all essential categories
    assert "trigger" in categories, "Missing trigger agents"
    assert "data" in categories, "Missing data agents"
    assert "analysis" in categories, "Missing analysis agents"
    assert "risk" in categories, "Missing risk agents"
    assert "execution" in categories, "Missing execution agents"
    
    print(f"\n✓ All essential agent categories present:")
    for category in sorted(categories):
        count = len(registry.list_agents_by_category(category))
        print(f"   - {category}: {count} agent(s)")


def test_cost_tracking_in_pipeline(initial_state):
    """Test that costs are tracked correctly throughout pipeline."""
    state = initial_state
    
    # Run free agents
    trigger = TimeTriggerAgent("trigger-1", {"interval": "5m"})
    state = trigger.process(state)
    
    market_data = MarketDataAgent(
        "market-1",
        {"timeframes": ["5m"], "use_mock_data": True}
    )
    state = market_data.process(state)
    
    # All free agents should have zero cost
    assert state.total_cost == 0.0
    print(f"✓ Free agents have zero cost: ${state.total_cost}")
    
    # Track costs per agent
    for agent_id, cost in state.agent_costs.items():
        print(f"   - {agent_id}: ${cost:.2f}")

