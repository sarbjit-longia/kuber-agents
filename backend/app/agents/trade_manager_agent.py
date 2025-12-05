"""
Trade Manager Agent

Executes trades through broker API (Alpaca).
Handles order placement, fill confirmation, and error handling.
"""
from typing import Dict, Any
from datetime import datetime

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema, TradeExecution
from app.config import settings


class TradeManagerAgent(BaseAgent):
    """
    Trade execution agent using Alpaca API.
    
    This is a FREE agent (no AI needed, just API calls).
    
    Executes:
    - Market orders
    - Limit orders  
    - Bracket orders (entry + stop + target)
    - Order status tracking
    
    Configuration:
        - order_type: "market" or "limit" (default: "market")
        - use_paper_trading: Use paper trading account (default: True)
        - time_in_force: "day", "gtc", "ioc" (default: "day")
    
    Example config:
        {
            "order_type": "market",
            "use_paper_trading": true,
            "time_in_force": "day"
        }
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="trade_manager_agent",
            name="Trade Manager Agent",
            description="Executes trades through broker API. Supports multiple brokers via attached tools. Free to use.",
            category="execution",
            version="1.0.0",
            icon="swap_horiz",
            pricing_rate=0.0,
            is_free=True,
            requires_timeframes=[],
            requires_market_data=True,
            requires_position=False,
            supported_tools=["alpaca_broker", "webhook_notifier", "email_notifier"],  # Added
            config_schema=AgentConfigSchema(
                type="object",
                title="Trade Manager Configuration",
                description="Configure trade execution settings",
                properties={
                    "order_type": {
                        "type": "string",
                        "title": "Order Type",
                        "description": "Type of order to place",
                        "enum": ["market", "limit", "bracket"],
                        "default": "market"
                    },
                    "use_paper_trading": {
                        "type": "boolean",
                        "title": "Use Paper Trading",
                        "description": "Execute in paper trading account (recommended for testing)",
                        "default": True
                    },
                    "time_in_force": {
                        "type": "string",
                        "title": "Time in Force",
                        "description": "How long order remains active",
                        "enum": ["day", "gtc", "ioc", "fok"],
                        "default": "day"
                    },
                    "enable_execution": {
                        "type": "boolean",
                        "title": "Enable Execution",
                        "description": "Actually execute trades (false = simulation only)",
                        "default": False
                    }
                },
                required=[]
            ),
            can_initiate_trades=True,
            can_close_positions=True
        )
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        super().__init__(agent_id, config)
        self.paper_trading = config.get("use_paper_trading", True)
        self.execution_enabled = config.get("enable_execution", False)
        
        # Initialize Alpaca client (if API keys available)
        self._init_alpaca_client()
    
    def _init_alpaca_client(self):
        """Initialize Alpaca trading client."""
        # TODO: Implement actual Alpaca client initialization
        # For now, we'll simulate trades
        self.alpaca_client = None
        
        if settings.ALPACA_API_KEY and settings.ALPACA_SECRET_KEY:
            try:
                # from alpaca.trading.client import TradingClient
                # self.alpaca_client = TradingClient(
                #     api_key=settings.ALPACA_API_KEY,
                #     secret_key=settings.ALPACA_SECRET_KEY,
                #     paper=self.paper_trading
                # )
                pass
            except Exception as e:
                self.alpaca_client = None
    
    def process(self, state: PipelineState) -> PipelineState:
        """
        Execute trade based on risk assessment.
        
        Args:
            state: Current pipeline state with approved trade
            
        Returns:
            Updated pipeline state with execution details
            
        Raises:
            InsufficientDataError: If risk assessment missing
            AgentProcessingError: If execution fails
        """
        self.log(state, "Processing trade execution")
        
        # Validate we have risk assessment
        if not state.risk_assessment:
            raise InsufficientDataError("No risk assessment available for trade execution")
        
        risk = state.risk_assessment
        strategy = state.strategy
        
        # If trade not approved, record rejection
        if not risk.approved or not strategy:
            state.trade_execution = TradeExecution(
                order_id=None,
                status="rejected",
                filled_price=None,
                filled_quantity=None,
                commission=None,
                execution_time=None,
                broker_response={"reason": "Trade not approved by risk manager"}
            )
            self.log(state, "Trade not approved - execution skipped")
            self.record_report(
                state,
                title="Trade execution skipped",
                summary="Risk manager did not approve trade",
                status="skipped",
                data={"reason": "Trade not approved by risk manager"},
            )
            return state
        
        # If strategy is HOLD, no execution needed
        if strategy.action == "HOLD":
            state.trade_execution = TradeExecution(
                order_id=None,
                status="no_action",
                filled_price=None,
                filled_quantity=None,
                commission=None,
                execution_time=None,
                broker_response={"reason": "HOLD signal - no trade to execute"}
            )
            self.log(state, "HOLD signal - no execution needed")
            self.record_report(
                state,
                title="No execution (HOLD)",
                summary="Strategy advised HOLD so no trade executed",
                status="skipped",
                data={"reason": "Strategy HOLD"},
            )
            return state
        
        try:
            # Check if execution is enabled
            if not self.execution_enabled:
                # Simulation mode
                state.trade_execution = self._simulate_execution(state, strategy, risk)
                self.log(state, "⚠️ SIMULATED execution (enable_execution=false)")
                self.record_report(
                    state,
                    title="Simulated trade execution",
                    summary=f"{strategy.action} {risk.position_size:.0f} units @ {strategy.entry_price}",
                    data={
                        "mode": "simulation",
                        "order_type": self.config.get("order_type", "market"),
                        "position_size": risk.position_size,
                        "entry_price": strategy.entry_price,
                    },
                )
                return state
            
            # Real execution
            order_type = self.config.get("order_type", "market")
            
            if order_type == "bracket":
                execution = self._execute_bracket_order(state, strategy, risk)
            elif order_type == "limit":
                execution = self._execute_limit_order(state, strategy, risk)
            else:  # market
                execution = self._execute_market_order(state, strategy, risk)
            
            state.trade_execution = execution
            
            if execution.status == "filled":
                self.log(
                    state,
                    f"✓ Trade EXECUTED: {strategy.action} {execution.filled_quantity} shares "
                    f"@ ${execution.filled_price:.2f}"
                )
            else:
                self.log(
                    state,
                    f"⚠️ Trade status: {execution.status}",
                    level="warning"
                )
            
            self.record_report(
                state,
                title="Trade execution result",
                summary=f"{execution.status.upper()} - {strategy.action} {execution.filled_quantity} units",
                status="completed" if execution.status == "filled" else execution.status,
                data={
                    "filled_price": execution.filled_price,
                    "filled_quantity": execution.filled_quantity,
                    "order_type": self.config.get("order_type", "market"),
                    "execution_mode": "live" if self.execution_enabled else "simulation",
                    "broker_response": execution.broker_response,
                },
            )
            
            # No cost for this agent
            self.track_cost(state, 0.0)
            
            return state
        
        except Exception as e:
            error_msg = f"Trade execution failed: {str(e)}"
            self.add_error(state, error_msg)
            
            # Record failed execution
            state.trade_execution = TradeExecution(
                order_id=None,
                status="failed",
                filled_price=None,
                filled_quantity=None,
                commission=None,
                execution_time=None,
                broker_response={"error": str(e)}
            )
            
            raise AgentProcessingError(error_msg) from e
    
    def _simulate_execution(
        self,
        state: PipelineState,
        strategy,
        risk
    ) -> TradeExecution:
        """Simulate trade execution for testing."""
        return TradeExecution(
            order_id=f"SIM-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            status="filled",
            filled_price=strategy.entry_price,
            filled_quantity=risk.position_size,
            commission=0.0,  # Simulated trades have no commission
            execution_time=datetime.utcnow(),
            broker_response={
                "simulated": True,
                "action": strategy.action,
                "symbol": state.symbol,
                "mode": "simulation"
            }
        )
    
    def _execute_market_order(
        self,
        state: PipelineState,
        strategy,
        risk
    ) -> TradeExecution:
        """Execute a market order."""
        # TODO: Implement actual Alpaca market order
        # For now, return simulated execution
        return self._simulate_execution(state, strategy, risk)
    
    def _execute_limit_order(
        self,
        state: PipelineState,
        strategy,
        risk
    ) -> TradeExecution:
        """Execute a limit order."""
        # TODO: Implement actual Alpaca limit order
        return self._simulate_execution(state, strategy, risk)
    
    def _execute_bracket_order(
        self,
        state: PipelineState,
        strategy,
        risk
    ) -> TradeExecution:
        """Execute a bracket order (entry + stop + target)."""
        # TODO: Implement actual Alpaca bracket order
        # Bracket orders include entry, stop loss, and take profit in one order
        return self._simulate_execution(state, strategy, risk)

