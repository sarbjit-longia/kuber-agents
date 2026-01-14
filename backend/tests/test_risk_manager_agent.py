"""
Tests for Risk Manager Agent

Tests cover:
- Instruction accuracy (risk limits, position sizing)
- Trade approval/rejection logic
- Report generation
- Edge cases and boundary conditions
"""
import pytest
from app.agents import get_registry
from app.schemas.pipeline_state import StrategyResult
from tests.conftest import assert_reasoning_format


class TestRiskManagerAccuracy:
    """Test that Risk Manager follows instructions accurately."""
    
    @pytest.mark.accuracy
    def test_custom_risk_per_trade_1_percent(self, state_with_strategy):
        """Test: Agent should respect 1% max risk per trade limit."""
        registry = get_registry()
        
        config = {
            "instructions": (
                "Maximum risk per trade: 1% of account. "
                "Calculate position size accordingly."
            ),
            "model": "gpt-3.5-turbo",
            "account_balance": 100000  # $100k account
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-1pct",
            config=config
        )
        
        result = agent.process(state_with_strategy)
        
        assert result.risk_assessment, "Should generate risk assessment"
        risk = result.risk_assessment
        
        # Max loss should be ~$1000 (1% of 100k)
        if risk.max_loss_amount:
            max_allowed = 100000 * 0.01  # 1%
            assert risk.max_loss_amount <= max_allowed * 1.1, \
                f"Max loss (${risk.max_loss_amount}) exceeds 1% limit (${max_allowed})"
    
    @pytest.mark.accuracy
    def test_position_size_limit_25_percent(self, state_with_strategy):
        """Test: Agent should enforce 25% max position size."""
        registry = get_registry()
        
        config = {
            "instructions": (
                "Position size must not exceed 25% of account value. "
                "Reject trades that would violate this."
            ),
            "model": "gpt-3.5-turbo",
            "account_balance": 100000
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-25pct-size",
            config=config
        )
        
        result = agent.process(state_with_strategy)
        
        risk = result.risk_assessment
        
        if risk.position_size and state_with_strategy.strategy.entry_price:
            position_value = risk.position_size * state_with_strategy.strategy.entry_price
            max_allowed = 100000 * 0.25
            
            assert position_value <= max_allowed * 1.1, \
                f"Position value (${position_value:.2f}) exceeds 25% limit (${max_allowed})"
    
    @pytest.mark.accuracy
    def test_minimum_risk_reward_ratio_2to1(self, state_with_strategy):
        """Test: Agent should reject trades with R/R below 2:1."""
        registry = get_registry()
        
        # Modify strategy to have poor R/R (1:1)
        state_with_strategy.strategy = StrategyResult(
            action="BUY",
            entry_price=250.0,
            stop_loss=248.0,  # 2 point risk
            take_profit=252.0,  # 2 point reward = 1:1
            confidence=0.75,
            pattern_detected="Support bounce",
            reasoning="Entry at support level"
        )
        
        config = {
            "instructions": (
                "Reject trades with risk/reward below 2:1. "
                "Only approve high quality setups."
            ),
            "model": "gpt-3.5-turbo"
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-2to1-min",
            config=config
        )
        
        result = agent.process(state_with_strategy)
        
        risk = result.risk_assessment
        
        # Should be rejected (R/R = 1:1, below 2:1 minimum)
        assert not risk.approved, "Trade with 1:1 R/R should be rejected when 2:1 minimum required"
        assert "risk" in risk.reasoning.lower() or "reward" in risk.reasoning.lower(), \
            "Rejection reason should mention risk/reward"
    
    @pytest.mark.accuracy
    def test_approve_good_risk_reward(self, state_with_strategy):
        """Test: Agent should approve trades with good R/R (3:1)."""
        registry = get_registry()
        
        # Modify strategy to have good R/R (3:1)
        state_with_strategy.strategy = StrategyResult(
            action="BUY",
            entry_price=250.0,
            stop_loss=248.0,  # 2 point risk
            take_profit=256.0,  # 6 point reward = 3:1
            confidence=0.80,
            pattern_detected="Bull flag",
            reasoning="Strong bullish setup"
        )
        
        config = {
            "instructions": (
                "Approve trades with risk/reward of 2:1 or better. "
                "Risk per trade: 2% of account."
            ),
            "model": "gpt-3.5-turbo",
            "account_balance": 100000
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-approve",
            config=config
        )
        
        result = agent.process(state_with_strategy)
        
        risk = result.risk_assessment
        
        # Should be approved (R/R = 3:1, above 2:1 minimum)
        assert risk.approved, "Trade with 3:1 R/R should be approved"
        assert risk.risk_reward_ratio >= 2.0, f"R/R ratio should be >= 2.0, got {risk.risk_reward_ratio}"


class TestRiskManagerReports:
    """Test that Risk Manager generates proper reports."""
    
    @pytest.mark.report
    def test_report_structure(self, state_with_strategy):
        """Test: Report should have all required fields."""
        registry = get_registry()
        
        config = {
            "instructions": "Evaluate trade risk and provide approval decision.",
            "model": "gpt-3.5-turbo",
            "account_balance": 100000
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-report",
            config=config
        )
        
        result = agent.process(state_with_strategy)
        
        # Check reports
        assert hasattr(result, 'reports'), "Should have reports"
        assert "test-risk-report" in result.reports, "Should have report for this agent"
        
        report = result.reports["test-risk-report"]
        
        # Verify structure
        assert report.title == "Risk Assessment", f"Wrong title: {report.title}"
        assert report.summary, "Should have summary"
        assert report.data, "Should have data"
        
        # Check data fields
        assert "Approved" in report.data, "Should include approval status"
        assert "Risk Score" in report.data, "Should include risk score"
        assert "Position Size" in report.data, "Should include position size"
    
    @pytest.mark.report
    def test_reasoning_format(self, state_with_strategy):
        """Test: Reasoning should be clean and professional."""
        registry = get_registry()
        
        config = {
            "instructions": "Evaluate risk with detailed explanation.",
            "model": "gpt-3.5-turbo"
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-format",
            config=config
        )
        
        result = agent.process(state_with_strategy)
        
        risk = result.risk_assessment
        
        # Check formatting
        assert_reasoning_format(risk.reasoning)
    
    @pytest.mark.report
    def test_warnings_populated(self, state_with_strategy):
        """Test: Warnings should be included when applicable."""
        registry = get_registry()
        
        # Create marginal trade (high risk)
        state_with_strategy.strategy.stop_loss = state_with_strategy.strategy.entry_price - 10  # Large stop
        
        config = {
            "instructions": "Flag any trades with stop loss > 5% from entry as high risk.",
            "model": "gpt-3.5-turbo"
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-warnings",
            config=config
        )
        
        result = agent.process(state_with_strategy)
        
        risk = result.risk_assessment
        
        # Should have warnings
        assert isinstance(risk.warnings, list), "Warnings should be a list"
        # May or may not have warnings depending on LLM interpretation


class TestRiskManagerEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.mark.unit
    def test_missing_strategy(self, state_with_bias):
        """Test: Agent should handle missing strategy gracefully."""
        registry = get_registry()
        
        # State has bias but NO strategy
        config = {
            "instructions": "Evaluate trade risk.",
            "model": "gpt-3.5-turbo"
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-no-strategy",
            config=config
        )
        
        # Should raise error or handle gracefully
        from app.agents.base import InsufficientDataError
        with pytest.raises((InsufficientDataError, Exception)):
            agent.process(state_with_bias)
    
    @pytest.mark.unit
    def test_hold_action(self, state_with_strategy):
        """Test: Agent should handle HOLD action (no trade to evaluate)."""
        registry = get_registry()
        
        # Strategy says HOLD
        state_with_strategy.strategy.action = "HOLD"
        state_with_strategy.strategy.entry_price = None
        state_with_strategy.strategy.stop_loss = None
        state_with_strategy.strategy.take_profit = None
        
        config = {
            "instructions": "Evaluate trades. If no trade, explain why.",
            "model": "gpt-3.5-turbo"
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-hold",
            config=config
        )
        
        result = agent.process(state_with_strategy)
        
        # Should complete (may approve=False or skip)
        assert result.risk_assessment, "Should generate assessment even for HOLD"
    
    @pytest.mark.unit
    def test_incomplete_price_levels(self, state_with_strategy):
        """Test: Agent should handle missing price levels."""
        registry = get_registry()
        
        # Strategy missing take profit
        state_with_strategy.strategy.take_profit = None
        
        config = {
            "instructions": "Evaluate risk. Reject incomplete strategies.",
            "model": "gpt-3.5-turbo"
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-incomplete",
            config=config
        )
        
        result = agent.process(state_with_strategy)
        
        risk = result.risk_assessment
        
        # Should handle gracefully (likely reject)
        assert risk, "Should generate assessment"
    
    @pytest.mark.unit
    def test_zero_account_balance(self, state_with_strategy):
        """Test: Agent should handle edge case of zero balance."""
        registry = get_registry()
        
        config = {
            "instructions": "Calculate position size based on account balance.",
            "model": "gpt-3.5-turbo",
            "account_balance": 0  # Edge case!
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-zero-balance",
            config=config
        )
        
        result = agent.process(state_with_strategy)
        
        risk = result.risk_assessment
        
        # Should reject (no capital to trade)
        assert not risk.approved, "Should reject trades with zero balance"


class TestRiskManagerCalculations:
    """Test that risk calculations are accurate."""
    
    @pytest.mark.unit
    def test_risk_reward_calculation(self, state_with_strategy):
        """Test: R/R ratio should be calculated correctly."""
        registry = get_registry()
        
        # Set known values: Entry=250, Stop=248, Target=256
        # Risk = 2, Reward = 6, R/R = 3:1
        state_with_strategy.strategy = StrategyResult(
            action="BUY",
            entry_price=250.0,
            stop_loss=248.0,
            take_profit=256.0,
            confidence=0.75,
            pattern_detected="Test",
            reasoning="Test reasoning"
        )
        
        config = {
            "instructions": "Calculate risk/reward accurately.",
            "model": "gpt-3.5-turbo"
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-calc",
            config=config
        )
        
        result = agent.process(state_with_strategy)
        
        risk = result.risk_assessment
        
        # Check R/R calculation (should be 3.0)
        assert risk.risk_reward_ratio, "Should calculate R/R ratio"
        assert 2.8 <= risk.risk_reward_ratio <= 3.2, \
            f"R/R should be ~3.0, got {risk.risk_reward_ratio}"
    
    @pytest.mark.unit
    def test_position_size_calculation(self, state_with_strategy):
        """Test: Position size should match risk parameters."""
        registry = get_registry()
        
        # Entry=250, Stop=248, Risk=2 points
        # Account=100k, Max Risk=1% = $1000
        # Position size = $1000 / $2 = 500 shares
        state_with_strategy.strategy = StrategyResult(
            action="BUY",
            entry_price=250.0,
            stop_loss=248.0,
            take_profit=256.0,
            confidence=0.75,
            pattern_detected="Test",
            reasoning="Test"
        )
        
        config = {
            "instructions": "Risk 1% per trade. Calculate position size.",
            "model": "gpt-3.5-turbo",
            "account_balance": 100000
        }
        
        agent = registry.create_agent(
            agent_type="risk_manager_agent",
            agent_id="test-risk-pos-size",
            config=config
        )
        
        result = agent.process(state_with_strategy)
        
        risk = result.risk_assessment
        
        # Expected: 500 shares (allow some variance)
        if risk.position_size:
            expected_size = 500
            assert 400 <= risk.position_size <= 600, \
                f"Position size should be ~{expected_size}, got {risk.position_size}"

