"""
Standalone agent tests (no database required).

Tests individual agents in isolation.
"""
from uuid import uuid4
from datetime import datetime

# Test agent registry
def test_agent_registry():
    """Test that all agents are registered."""
    from app.agents import get_registry
    
    registry = get_registry()
    agents = registry.list_all_metadata()
    
    print(f"\n✅ Agent Registry Test")
    print(f"   Total agents: {len(agents)}")
    
    # Check we have the expected agents
    agent_types = {agent.agent_type for agent in agents}
    
    expected = {
        "time_trigger",
        "market_data_agent", 
        "bias_agent",
        "strategy_agent",
        "risk_manager_agent",
        "trade_manager_agent"
    }
    
    assert expected.issubset(agent_types), f"Missing agents: {expected - agent_types}"
    
    # Check categories
    categories = {agent.category for agent in agents}
    print(f"   Categories: {', '.join(sorted(categories))}")
    
    assert "trigger" in categories
    assert "data" in categories
    assert "analysis" in categories
    assert "risk" in categories
    assert "execution" in categories
    
    # Show each agent
    for agent in sorted(agents, key=lambda x: (x.category, x.name)):
        cost_str = "FREE" if agent.is_free else f"${agent.pricing_rate:.2f}"
        print(f"   [{agent.category:10s}] {agent.name:35s} - {cost_str}")
    
    print("   ✓ All agents registered correctly\n")


def test_time_trigger_agent():
    """Test TimeTriggerAgent."""
    from app.agents import TimeTriggerAgent
    from app.schemas.pipeline_state import PipelineState
    
    print(f"\n✅ Time Trigger Agent Test")
    
    # Create agent
    agent = TimeTriggerAgent(
        "test-trigger",
        {"interval": "5m"}
    )
    
    # Create state
    state = PipelineState(
        pipeline_id=uuid4(),
        execution_id=uuid4(),
        user_id=uuid4(),
        symbol="AAPL",
        mode="paper"
    )
    
    # Process (should always trigger in test)
    result = agent.process(state)
    
    assert result.trigger_met is True
    assert result.trigger_reason is not None
    print(f"   Trigger Status: {result.trigger_met}")
    print(f"   Trigger Reason: {result.trigger_reason}")
    print("   ✓ Time trigger working\n")


def test_market_data_agent():
    """Test MarketDataAgent with mock data."""
    from app.agents import MarketDataAgent
    from app.schemas.pipeline_state import PipelineState
    
    print(f"\n✅ Market Data Agent Test")
    
    # Create agent with mock data
    agent = MarketDataAgent(
        "test-market",
        {
            "timeframes": ["5m", "1h"],
            "lookback_periods": 50,
            "use_mock_data": True
        }
    )
    
    # Create state
    state = PipelineState(
        pipeline_id=uuid4(),
        execution_id=uuid4(),
        user_id=uuid4(),
        symbol="AAPL",
        mode="paper"
    )
    
    # Process
    result = agent.process(state)
    
    assert result.market_data is not None
    assert result.market_data.current_price > 0
    assert "5m" in result.market_data.timeframes
    assert "1h" in result.market_data.timeframes
    
    print(f"   Symbol: {result.market_data.symbol}")
    print(f"   Current Price: ${result.market_data.current_price:.2f}")
    print(f"   Timeframes: {', '.join(result.market_data.timeframes.keys())}")
    print(f"   5m Data Points: {len(result.market_data.timeframes['5m'])}")
    print("   ✓ Market data fetched correctly\n")


def test_risk_manager_agent():
    """Test RiskManagerAgent."""
    from app.agents import RiskManagerAgent
    from app.schemas.pipeline_state import PipelineState, StrategyResult, MarketData, TimeframeData
    
    print(f"\n✅ Risk Manager Agent Test")
    
    # Create agent
    agent = RiskManagerAgent(
        "test-risk",
        {
            "account_size": 10000,
            "risk_per_trade_percent": 1.0,
            "min_risk_reward_ratio": 2.0
        }
    )
    
    # Create state with strategy
    state = PipelineState(
        pipeline_id=uuid4(),
        execution_id=uuid4(),
        user_id=uuid4(),
        symbol="AAPL",
        mode="paper"
    )
    
    # Add mock market data
    state.market_data = MarketData(
        symbol="AAPL",
        current_price=150.0,
        timeframes={
            "5m": [TimeframeData(
                timeframe="5m",
                open=150.0,
                high=151.0,
                low=149.0,
                close=150.0,
                volume=1000000,
                timestamp=datetime.utcnow()
            )]
        },
        last_updated=datetime.utcnow()
    )
    
    # Add strategy
    state.strategy = StrategyResult(
        action="BUY",
        confidence=0.75,
        entry_price=150.0,
        stop_loss=148.0,  # $2 risk
        take_profit=154.0,  # $4 reward (2:1 R/R)
        position_size=None,
        reasoning="Test strategy",
        pattern_detected="Bull flag"
    )
    
    # Process
    result = agent.process(state)
    
    assert result.risk_assessment is not None
    print(f"   Trade Approved: {result.risk_assessment.approved}")
    print(f"   Position Size: {result.risk_assessment.position_size:.0f} shares")
    print(f"   Max Loss: ${result.risk_assessment.max_loss_amount:.2f}")
    print(f"   Risk/Reward: {result.risk_assessment.risk_reward_ratio:.2f}:1")
    if not result.risk_assessment.approved:
        print(f"   Warnings: {', '.join(result.risk_assessment.warnings)}")
    print("   ✓ Risk assessment working\n")


def test_trade_manager_agent():
    """Test TradeManagerAgent."""
    from app.agents import TradeManagerAgent
    from app.schemas.pipeline_state import (
        PipelineState, StrategyResult, RiskAssessment,
        MarketData, TimeframeData
    )
    
    print(f"\n✅ Trade Manager Agent Test")
    
    # Create agent
    agent = TradeManagerAgent(
        "test-trade",
        {
            "order_type": "market",
            "enable_execution": False  # Simulation only
        }
    )
    
    # Create state with approved strategy
    state = PipelineState(
        pipeline_id=uuid4(),
        execution_id=uuid4(),
        user_id=uuid4(),
        symbol="AAPL",
        mode="paper"
    )
    
    # Add market data
    state.market_data = MarketData(
        symbol="AAPL",
        current_price=150.0,
        timeframes={
            "5m": [TimeframeData(
                timeframe="5m",
                open=150.0,
                high=151.0,
                low=149.0,
                close=150.0,
                volume=1000000,
                timestamp=datetime.utcnow()
            )]
        },
        last_updated=datetime.utcnow()
    )
    
    # Add strategy
    state.strategy = StrategyResult(
        action="BUY",
        confidence=0.75,
        entry_price=150.0,
        stop_loss=148.0,
        take_profit=154.0,
        position_size=50,
        reasoning="Test strategy",
        pattern_detected="Bull flag"
    )
    
    # Add risk assessment (approved)
    state.risk_assessment = RiskAssessment(
        approved=True,
        risk_score=0.15,
        position_size=50,
        max_loss_amount=100.0,
        risk_reward_ratio=2.0,
        warnings=[],
        reasoning="Trade approved - good R/R and position size"
    )
    
    # Process
    result = agent.process(state)
    
    assert result.trade_execution is not None
    print(f"   Execution Status: {result.trade_execution.status}")
    print(f"   Order ID: {result.trade_execution.order_id}")
    print(f"   Fill Price: ${result.trade_execution.filled_price:.2f}")
    print(f"   Quantity: {result.trade_execution.filled_quantity:.0f} shares")
    print(f"   Simulated: {result.trade_execution.broker_response.get('simulated', False)}")
    print("   ✓ Trade execution working\n")


def test_agent_cost_tracking():
    """Test that cost tracking works."""
    from app.agents import TimeTriggerAgent, MarketDataAgent
    from app.schemas.pipeline_state import PipelineState
    
    print(f"\n✅ Cost Tracking Test")
    
    state = PipelineState(
        pipeline_id=uuid4(),
        execution_id=uuid4(),
        user_id=uuid4(),
        symbol="AAPL",
        mode="paper"
    )
    
    # Run free agents
    trigger = TimeTriggerAgent("t1", {"interval": "5m"})
    state = trigger.process(state)
    
    market = MarketDataAgent("m1", {"timeframes": ["5m"], "use_mock_data": True})
    state = market.process(state)
    
    print(f"   Total Cost: ${state.total_cost:.2f}")
    print(f"   Agent Costs: {state.agent_costs}")
    
    assert state.total_cost == 0.0, "Free agents should have zero cost"
    
    print("   ✓ Cost tracking working\n")


if __name__ == "__main__":
    """Run tests manually."""
    test_agent_registry()
    test_time_trigger_agent()
    test_market_data_agent()
    test_risk_manager_agent()
    test_trade_manager_agent()
    test_agent_cost_tracking()
    
    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED!")
    print("="*60)

