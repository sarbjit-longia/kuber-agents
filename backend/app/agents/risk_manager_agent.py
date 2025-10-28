"""
Risk Manager Agent

Validates and sizes trades based on risk parameters.
Mostly rule-based for cost efficiency, but can use AI for complex scenarios.
"""
from typing import Dict, Any

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema, RiskAssessment
from app.config import settings


class RiskManagerAgent(BaseAgent):
    """
    Risk management agent using rule-based validation.
    
    This is a FREE agent (uses rules, no AI needed).
    
    Validates:
    - Risk/reward ratios
    - Position sizing based on account risk
    - Maximum loss limits
    - Exposure limits
    
    Configuration:
        - account_size: Total account value (default: 10000)
        - risk_per_trade_percent: Max % of account to risk per trade (default: 1.0)
        - max_position_size_percent: Max % of account in single position (default: 10.0)
        - min_risk_reward_ratio: Minimum acceptable R/R (default: 2.0)
        - max_daily_loss_percent: Max % account loss per day (default: 3.0)
    
    Example config:
        {
            "account_size": 10000,
            "risk_per_trade_percent": 1.0,
            "max_position_size_percent": 10.0,
            "min_risk_reward_ratio": 2.0
        }
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="risk_manager_agent",
            name="Risk Manager Agent",
            description="Rule-based risk management and position sizing. Validates trades and calculates safe position sizes. Free to use.",
            category="risk",
            version="1.0.0",
            icon="shield",
            pricing_rate=0.0,
            is_free=True,
            requires_timeframes=[],
            requires_market_data=True,
            requires_position=False,
            config_schema=AgentConfigSchema(
                type="object",
                title="Risk Manager Configuration",
                description="Configure risk management parameters",
                properties={
                    "account_size": {
                        "type": "number",
                        "title": "Account Size",
                        "description": "Total account value in dollars",
                        "default": 10000,
                        "minimum": 100
                    },
                    "risk_per_trade_percent": {
                        "type": "number",
                        "title": "Risk Per Trade (%)",
                        "description": "Maximum percentage of account to risk on single trade",
                        "default": 1.0,
                        "minimum": 0.1,
                        "maximum": 5.0
                    },
                    "max_position_size_percent": {
                        "type": "number",
                        "title": "Max Position Size (%)",
                        "description": "Maximum percentage of account in single position",
                        "default": 10.0,
                        "minimum": 1.0,
                        "maximum": 100.0
                    },
                    "min_risk_reward_ratio": {
                        "type": "number",
                        "title": "Minimum Risk/Reward Ratio",
                        "description": "Minimum acceptable risk/reward ratio",
                        "default": 2.0,
                        "minimum": 1.0,
                        "maximum": 10.0
                    },
                    "max_daily_loss_percent": {
                        "type": "number",
                        "title": "Max Daily Loss (%)",
                        "description": "Maximum percentage account loss allowed per day",
                        "default": 3.0,
                        "minimum": 1.0,
                        "maximum": 10.0
                    }
                },
                required=["account_size"]
            ),
            can_initiate_trades=False,
            can_close_positions=False
        )
    
    def process(self, state: PipelineState) -> PipelineState:
        """
        Validate and size trade based on risk parameters.
        
        Args:
            state: Current pipeline state with strategy
            
        Returns:
            Updated pipeline state with risk assessment
            
        Raises:
            InsufficientDataError: If strategy missing
            AgentProcessingError: If risk assessment fails
        """
        self.log(state, "Performing risk assessment and position sizing")
        
        # Validate we have a strategy
        if not state.strategy:
            raise InsufficientDataError("No strategy available for risk assessment")
        
        strategy = state.strategy
        
        # If strategy is HOLD, approve with zero position
        if strategy.action == "HOLD":
            state.risk_assessment = RiskAssessment(
                approved=True,
                risk_score=0.0,
                position_size=0.0,
                max_loss_amount=0.0,
                risk_reward_ratio=0.0,
                warnings=[],
                reasoning="No trade proposed (HOLD signal)"
            )
            self.log(state, "✓ Risk assessment: HOLD signal approved")
            return state
        
        try:
            # Get configuration
            account_size = self.config["account_size"]
            risk_per_trade_pct = self.config.get("risk_per_trade_percent", 1.0)
            max_position_pct = self.config.get("max_position_size_percent", 10.0)
            min_rr_ratio = self.config.get("min_risk_reward_ratio", 2.0)
            
            # Validate strategy has required fields
            if not strategy.entry_price or not strategy.stop_loss or not strategy.take_profit:
                state.risk_assessment = RiskAssessment(
                    approved=False,
                    risk_score=1.0,
                    position_size=0.0,
                    max_loss_amount=0.0,
                    risk_reward_ratio=0.0,
                    warnings=["Incomplete trade plan: missing entry, stop, or target"],
                    reasoning="Trade rejected: incomplete price levels"
                )
                self.log(state, "✗ Trade rejected: incomplete price levels")
                return state
            
            # Calculate risk and reward
            entry = strategy.entry_price
            stop = strategy.stop_loss
            target = strategy.take_profit
            
            if strategy.action == "BUY":
                risk_per_share = abs(entry - stop)
                reward_per_share = abs(target - entry)
            else:  # SELL
                risk_per_share = abs(stop - entry)
                reward_per_share = abs(entry - target)
            
            # Calculate risk/reward ratio
            if risk_per_share == 0:
                rr_ratio = 0.0
            else:
                rr_ratio = reward_per_share / risk_per_share
            
            # Validate risk/reward ratio
            warnings = []
            if rr_ratio < min_rr_ratio:
                warnings.append(
                    f"Risk/reward ratio {rr_ratio:.2f}:1 is below minimum {min_rr_ratio}:1"
                )
            
            # Calculate position size based on risk
            max_risk_amount = account_size * (risk_per_trade_pct / 100)
            
            if risk_per_share > 0:
                position_size = max_risk_amount / risk_per_share
            else:
                position_size = 0
            
            # Validate position size doesn't exceed maximum
            max_position_value = account_size * (max_position_pct / 100)
            max_shares_by_value = max_position_value / entry
            
            if position_size > max_shares_by_value:
                warnings.append(
                    f"Position size limited by max position value: "
                    f"{position_size:.0f} reduced to {max_shares_by_value:.0f} shares"
                )
                position_size = max_shares_by_value
            
            # Calculate risk score (0.0 = low risk, 1.0 = high risk)
            risk_score = self._calculate_risk_score(
                rr_ratio=rr_ratio,
                min_rr=min_rr_ratio,
                risk_amount=max_risk_amount,
                account_size=account_size,
                confidence=strategy.confidence
            )
            
            # Determine approval
            approved = len(warnings) == 0 and risk_score < 0.8 and position_size > 0
            
            # Create risk assessment
            state.risk_assessment = RiskAssessment(
                approved=approved,
                risk_score=risk_score,
                position_size=round(position_size, 2),
                max_loss_amount=max_risk_amount,
                risk_reward_ratio=rr_ratio,
                warnings=warnings,
                reasoning=self._generate_reasoning(
                    approved=approved,
                    rr_ratio=rr_ratio,
                    risk_score=risk_score,
                    position_size=position_size,
                    max_risk=max_risk_amount,
                    warnings=warnings
                )
            )
            
            # Update strategy with position size
            strategy.position_size = position_size
            
            # Log result
            if approved:
                self.log(
                    state,
                    f"✓ Trade APPROVED: {position_size:.0f} shares, "
                    f"Risk: ${max_risk_amount:.2f} ({risk_per_trade_pct}%), "
                    f"R/R: {rr_ratio:.2f}:1"
                )
            else:
                self.log(
                    state,
                    f"✗ Trade REJECTED: {', '.join(warnings) if warnings else 'High risk score'}"
                )
            
            # No cost for this agent (rule-based)
            self.track_cost(state, 0.0)
            
            return state
        
        except Exception as e:
            error_msg = f"Risk assessment failed: {str(e)}"
            self.add_error(state, error_msg)
            raise AgentProcessingError(error_msg) from e
    
    def _calculate_risk_score(
        self,
        rr_ratio: float,
        min_rr: float,
        risk_amount: float,
        account_size: float,
        confidence: float
    ) -> float:
        """
        Calculate risk score (0.0 = low risk, 1.0 = high risk).
        
        Factors:
        - Risk/reward ratio
        - Risk amount relative to account
        - Strategy confidence
        """
        # R/R score (lower ratio = higher risk)
        rr_score = max(0, 1 - (rr_ratio / min_rr)) if min_rr > 0 else 0
        
        # Risk amount score
        risk_pct = (risk_amount / account_size) * 100
        risk_amount_score = min(1.0, risk_pct / 5.0)  # 5% = max risk
        
        # Confidence score (lower confidence = higher risk)
        confidence_score = 1 - confidence
        
        # Weighted average
        risk_score = (
            rr_score * 0.4 +
            risk_amount_score * 0.3 +
            confidence_score * 0.3
        )
        
        return round(risk_score, 2)
    
    def _generate_reasoning(
        self,
        approved: bool,
        rr_ratio: float,
        risk_score: float,
        position_size: float,
        max_risk: float,
        warnings: list
    ) -> str:
        """Generate human-readable reasoning for the risk assessment."""
        if approved:
            return (
                f"Trade approved with position size of {position_size:.0f} shares. "
                f"Risk/reward ratio of {rr_ratio:.2f}:1 meets requirements. "
                f"Maximum risk: ${max_risk:.2f}. "
                f"Risk score: {risk_score:.2f}/1.0."
            )
        else:
            reason_parts = []
            if warnings:
                reason_parts.append(f"Issues: {', '.join(warnings)}")
            if risk_score >= 0.8:
                reason_parts.append(f"Risk score too high: {risk_score:.2f}/1.0")
            if position_size <= 0:
                reason_parts.append("Position size invalid")
            
            return "Trade rejected. " + ". ".join(reason_parts) + "."

