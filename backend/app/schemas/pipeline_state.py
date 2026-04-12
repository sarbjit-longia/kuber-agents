"""
Pipeline State Schema

This module defines the PipelineState which is the data structure passed between
agents during pipeline execution. It contains all the data needed for agents to
make trading decisions.
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import UUID
from pydantic import BaseModel, Field


class TimeframeData(BaseModel):
    """Data for a specific timeframe."""
    model_config = {"populate_by_name": True}

    timeframe: str = ""  # e.g., "5m", "1h", "4h", "1d"
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    # Data plane returns "time", agents use "timestamp" — accept both
    timestamp: datetime = Field(default_factory=datetime.utcnow, validation_alias="time")
    
    # Technical indicators (calculated by Market Data Agent)
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_middle: Optional[float] = None
    bollinger_lower: Optional[float] = None


class MarketData(BaseModel):
    """Market data for a symbol across multiple timeframes."""
    symbol: str
    current_price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    
    # Timeframe data
    timeframes: Dict[str, List[TimeframeData]] = Field(default_factory=dict)
    
    # Market info
    market_status: Optional[str] = None  # "open", "closed", "pre_market", "after_hours"
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class BiasResult(BaseModel):
    """Result from Bias Agent analysis."""
    bias: str  # "BULLISH", "BEARISH", "NEUTRAL"
    confidence: float  # 0.0 to 1.0
    timeframe: str  # Which timeframe this bias is for
    reasoning: str
    key_factors: List[str] = Field(default_factory=list)


class RegimeContext(BaseModel):
    """Deterministic market regime classification produced before LLM strategy generation."""
    trend: str = "unknown"           # "uptrend" | "downtrend" | "sideways" | "unknown"
    volatility: str = "normal"       # "low" | "normal" | "high"
    session: str = "regular"         # "pre_market" | "regular" | "lunch" | "power_hour" | "after_hours"
    adr_pct: Optional[float] = None  # Average daily range as % of price
    above_vwap: Optional[bool] = None
    sma_alignment: Optional[str] = None  # "bullish" | "bearish" | "mixed"
    regime_score: float = 0.0        # -1.0 (strong bear) to +1.0 (strong bull)
    details: Dict[str, Any] = Field(default_factory=dict)


class StrategySpec(BaseModel):
    """
    Machine-valid deterministic strategy specification.

    Produced by the deterministic setup evaluators.  The LLM may refine
    entry_reasoning / exit_reasoning but must not change the numeric levels.
    """
    strategy_family: str              # "orb" | "vwap_pullback" | "first_pullback" | "range_fade"
                                      # | "breakout_retest" | "swing_continuation" | "mean_reversion"
    timeframe: str                    # Execution timeframe e.g. "5m"
    action: str                       # "BUY" | "SELL" | "HOLD"
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    take_profit_2: Optional[float] = None    # Optional second target
    stop_type: str = "fixed"          # "fixed" | "atr_trail" | "breakeven_trail"
    valid_until: Optional[datetime] = None   # Time-based invalidation
    regime_required: Optional[str] = None    # Required regime for entry
    confidence: float = 0.0
    entry_reason: str = ""
    exit_reason: str = ""
    invalidation_reason: str = ""     # Why this setup is NOT valid
    source: str = "deterministic"     # "deterministic" | "llm_assisted"


class StrategyResult(BaseModel):
    """Result from Strategy Agent."""
    action: str  # "BUY", "SELL", "HOLD", "CLOSE"
    confidence: float  # 0.0 to 1.0
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size: Optional[float] = None  # Number of shares/contracts
    reasoning: str
    pattern_detected: Optional[str] = None
    # Deterministic strategy spec — populated when a setup evaluator fires
    strategy_spec: Optional[StrategySpec] = None
    regime: Optional[RegimeContext] = None


class RiskAssessment(BaseModel):
    """Risk assessment from Risk Manager Agent."""
    approved: bool
    risk_score: float  # 0.0 to 1.0 (higher = riskier)
    position_size: float  # Approved position size
    max_loss_amount: float
    risk_reward_ratio: float
    warnings: List[str] = Field(default_factory=list)
    reasoning: str


class AgentReportMetric(BaseModel):
    """Metric/value pair for agent reports."""
    name: str
    value: Any
    unit: Optional[str] = None
    description: Optional[str] = None


class AgentReport(BaseModel):
    """Human-readable report for what an agent did."""
    agent_id: str
    agent_type: str
    title: str
    summary: str
    details: Optional[str] = None
    status: str = "completed"
    metrics: List[AgentReportMetric] = Field(default_factory=list)
    data: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BracketLeg(BaseModel):
    """Individual leg of a bracket (OTOCO) order for tracking."""
    leg_id: str  # Broker-assigned leg order ID
    role: str  # "entry", "take_profit", "stop_loss"
    type: str  # "market", "limit", "stop"
    side: str  # "buy" or "sell"
    status: str  # "pending", "open", "filled", "cancelled", "expired"
    quantity: float = 0.0
    price: Optional[float] = None  # Limit price or stop price
    avg_fill_price: Optional[float] = None  # Filled price (once filled)


class TradeExecution(BaseModel):
    """Trade execution details from Trade Manager Agent."""
    order_id: Optional[str] = None
    trade_id: Optional[str] = None  # Broker trade ID (may differ from order_id, esp. OANDA)
    status: str  # "pending", "filled", "partially_filled", "rejected", "cancelled"
    filled_price: Optional[float] = None
    filled_quantity: Optional[float] = None
    commission: Optional[float] = None
    execution_time: Optional[datetime] = None
    broker_response: Optional[Dict[str, Any]] = None

    # Bracket order leg tracking (Tradier OTOCO, etc.)
    bracket_legs: Optional[List[BracketLeg]] = None  # SL/TP leg IDs for monitoring
    
    # Monitoring metadata
    api_error_count: int = 0  # Count of consecutive API failures during monitoring
    last_api_error: Optional[str] = None  # Last API error message
    last_successful_check: Optional[datetime] = None  # Last time we successfully checked broker

    # Trailing-stop and break-even tracking (TP-020)
    high_water_pnl: float = 0.0    # Highest unrealized P&L seen — used for trailing stop
    break_even_armed: bool = False  # True once position has reached the break-even threshold


class Position(BaseModel):
    """Current position information."""
    symbol: str
    side: str  # "long", "short"
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    opened_at: datetime


class SignalData(BaseModel):
    """
    Signal data that triggered the pipeline execution.
    
    This is populated when a pipeline is triggered by a signal (from signal-generator).
    Contains the original signal information including metadata and market data.
    """
    signal_id: str
    signal_type: str  # e.g., "rsi_oversold", "golden_cross", "mock"
    source: str  # e.g., "rsi_signal_generator", "mock_generator"
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    
    # Ticker(s) that triggered the signal
    tickers: List[str]
    
    # Signal-specific data (e.g., RSI value, MACD values, etc.)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Market data at time of signal (optional - can be used by agents)
    market_data: Optional[Dict[str, Any]] = None


class TradeReview(BaseModel):
    """Final trade review from the Senior Trader Review Agent."""
    decision: str  # "APPROVED", "REJECTED", "HOLD"
    confidence: float  # 0.0-1.0
    reasoning: str
    key_concerns: List[str] = Field(default_factory=list)
    key_strengths: List[str] = Field(default_factory=list)
    trader_notes: Optional[str] = None


class TradeOutcome(BaseModel):
    """Final outcome of a trade with P&L information."""
    status: str  # "executed" (filled+closed), "cancelled" (limit never filled), "pending" (limit waiting), "failed" (broker error)
    pnl: Optional[float] = None  # Profit/Loss in dollars
    pnl_percent: Optional[float] = None  # Profit/Loss percentage
    exit_reason: Optional[str] = None  # Why the position closed
    exit_price: Optional[float] = None
    entry_price: Optional[float] = None
    closed_at: Optional[datetime] = None


class PipelineState(BaseModel):
    """
    The complete state object passed between agents in a pipeline.
    
    This is the core data structure that agents read from and write to.
    Each agent receives this state, processes it, and returns an updated state.
    """
    # Execution context
    pipeline_id: UUID
    execution_id: UUID
    user_id: UUID
    
    # Trading context
    symbol: str
    mode: str = "paper"  # "live", "paper", "simulation", "validation"
    backtest_run_id: Optional[str] = None
    backtest_ts: Optional[datetime] = None
    timeframes: List[str] = Field(default_factory=list)  # Timeframes required by this pipeline (e.g., ["5m", "1h", "1d"])
    
    # Signal context (populated when triggered by signal)
    signal_data: Optional[SignalData] = None
    
    # Market data (populated by tools or from signal)
    market_data: Optional[MarketData] = None
    
    # Agent outputs
    biases: Dict[str, BiasResult] = Field(default_factory=dict)  # keyed by timeframe
    strategy: Optional[StrategyResult] = None
    risk_assessment: Optional[RiskAssessment] = None
    trade_review: Optional[TradeReview] = None  # Senior trader review (optional quality gate)
    trade_execution: Optional[TradeExecution] = None
    trade_outcome: Optional[TradeOutcome] = None  # Final P&L when position closes
    
    # Position management
    current_position: Optional[Position] = None
    
    # Execution artifacts (charts, visualizations, etc.)
    execution_artifacts: Dict[str, Any] = Field(default_factory=dict)
    
    # Trigger status
    trigger_met: bool = False
    trigger_reason: Optional[str] = None
    
    # Cost tracking
    total_cost: float = 0.0
    agent_costs: Dict[str, float] = Field(default_factory=dict)  # keyed by agent_id
    
    # Errors and warnings
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    
    # Position monitoring (Trade Manager)
    execution_phase: str = "execute"  # "execute" or "monitoring"
    should_complete: bool = False  # Signal from agent to complete monitoring
    monitor_interval_minutes: float = 5.0  # Polling frequency for position monitoring (supports sub-minute like 0.25 = 15s)
    
    # Communication error tracking (for API failures during monitoring)
    communication_error: bool = False  # Set to True when broker API is unreachable
    communication_error_message: Optional[str] = None  # Last API error message
    
    # Metadata
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    # Agent execution log (for debugging and reporting)
    execution_log: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Agent execution states (for UI progress tracking)
    agent_execution_states: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Structured agent reports
    agent_reports: Dict[str, AgentReport] = Field(default_factory=dict)
    
    def add_log(self, agent_id: str, message: str, level: str = "info"):
        """Add a log entry to the execution log."""
        self.execution_log.append({
            "timestamp": datetime.utcnow(),
            "agent_id": agent_id,
            "level": level,
            "message": message
        })
    
    def add_cost(self, agent_id: str, cost: float):
        """Add cost for an agent."""
        self.agent_costs[agent_id] = self.agent_costs.get(agent_id, 0.0) + cost
        self.total_cost += cost
    
    def get_timeframe_data(self, timeframe: str) -> Optional[List[TimeframeData]]:
        """Get data for a specific timeframe."""
        if not self.market_data:
            return None
        return self.market_data.timeframes.get(timeframe)
    
    def get_latest_candle(self, timeframe: str) -> Optional[TimeframeData]:
        """Get the most recent candle for a timeframe."""
        data = self.get_timeframe_data(timeframe)
        if data and len(data) > 0:
            return data[-1]
        return None
    
    def add_report(
        self,
        agent_id: str,
        agent_type: str,
        title: str,
        summary: str,
        *,
        details: Optional[str] = None,
        status: str = "completed",
        metrics: Optional[List[AgentReportMetric]] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        """Add or update the structured report for an agent."""
        report = AgentReport(
            agent_id=agent_id,
            agent_type=agent_type,
            title=title,
            summary=summary,
            details=details,
            status=status,
            metrics=metrics or [],
            data=data or {},
        )
        self.agent_reports[agent_id] = report


class AgentConfigSchema(BaseModel):
    """
    JSON Schema definition for agent configuration.
    
    This is used by the frontend to dynamically generate configuration forms.
    """
    type: str = "object"
    title: str
    description: Optional[str] = None
    properties: Dict[str, Dict[str, Any]]
    required: List[str] = Field(default_factory=list)
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "object",
                "title": "Time Trigger Configuration",
                "properties": {
                    "interval": {
                        "type": "string",
                        "title": "Interval",
                        "description": "How often to check (e.g., '5m', '1h')",
                        "default": "5m"
                    }
                },
                "required": ["interval"]
            }
        }


class AgentMetadata(BaseModel):
    """
    Metadata about an agent for discovery and configuration.
    
    This is returned by agents to describe themselves to the UI.
    """
    agent_type: str  # Unique identifier (e.g., "market_data_agent", "bias_agent")
    name: str  # Display name
    description: str  # Detailed description
    category: str  # "trigger", "data", "analysis", "risk", "execution", "reporting"
    version: str
    icon: str  # Icon name for UI
    
    # Pricing
    pricing_rate: float = 0.0  # Cost per hour, 0.0 for free agents
    is_free: bool = True
    
    # Requirements
    requires_timeframes: List[str] = Field(default_factory=list)  # e.g., ["5m", "1h"]
    requires_market_data: bool = False
    requires_position: bool = False
    
    # Configuration
    config_schema: AgentConfigSchema
    
    # Tools Support
    supported_tools: List[str] = Field(default_factory=list)  # e.g., ["alpaca_broker", "webhook_notifier"]
    default_tools: List[str] = Field(default_factory=list)  # CrewAI tools loaded at runtime (e.g., ["fvg_detector", "rsi_calculator"])

    # Capabilities
    can_initiate_trades: bool = False
    can_close_positions: bool = False
    
    class Config:
        json_schema_extra = {
            "example": {
                "agent_type": "market_data_agent",
                "name": "Market Data Agent",
                "description": "Fetches OHLCV candles and indicators from the Data Plane",
                "category": "data",
                "version": "1.0.0",
                "icon": "bar_chart",
                "pricing_rate": 0.0,
                "is_free": True,
                "requires_timeframes": ["5m", "1h"],
                "config_schema": {
                    "type": "object",
                    "title": "Market Data Configuration",
                    "properties": {
                        "timeframes": {
                            "type": "array",
                            "title": "Timeframes",
                            "items": {"type": "string"}
                        }
                    }
                }
            }
        }
