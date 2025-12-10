# System Design Document

## 1. System Architecture Overview

### 1.1 High-Level Architecture (Updated Dec 2025)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         User Browser (Angular SPA)                          │
│                     Authentication • Pipeline Builder                       │
│                     Scanner Management • Monitoring                         │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ HTTPS/WSS
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                         FastAPI Backend API                                 │
│   Auth • Pipelines • Scanners • Executions • Signals • Billing             │
└────────┬────────────────────────────────────────────────────┬───────────────┘
         │                                                    │
         │                                                    │ Enqueue Tasks
┌────────▼────────────────────────────────────────────────────▼───────────────┐
│                         Redis (Queue + Cache)                               │
└────────┬────────────────────────────────────────────────────────────────────┘
         │
         │                                       ┌─────────────────────────────┐
         │                                       │   Signal Generators         │
         │                                       │  ┌───────────────────────┐ │
         │                                       │  │ Mock Signal Gen       │ │
         │                                       │  │ Golden Cross Gen      │ │
         │                                       │  │ News Sentiment Gen    │ │
         │                                       │  └──────────┬────────────┘ │
         │                                       └─────────────┼──────────────┘
         │                                                     │ Publish
         │                                              ┌──────▼──────────┐
         │                                              │     Kafka       │
         │                                              │ trading-signals │
         │                                              └──────┬──────────┘
         │                                                     │ Subscribe
         │                                              ┌──────▼──────────────┐
         │                                              │ Trigger Dispatcher  │
         │                                              │ • Cache Pipelines   │
         │                                              │ • Match Signals     │
         │                                              │ • Enqueue Tasks     │
         │                                              └──────┬──────────────┘
         │                                                     │ Enqueue
         │                                                     │
┌────────▼─────────────────────────────────────────────────────▼───────────────┐
│                      Celery Workers (Pipeline Execution)                     │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    CrewAI Agent Flow Orchestration                    │  │
│  │  ┌────────┐  ┌────────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌────────┐  │  │
│  │  │Market  │→│  Bias  │→│Strat │→│ Risk │→│ Order│→│Reports │  │  │
│  │  │ Data   │  │ Agent  │  │Agent │  │ Mgr  │  │ Mgr  │  │        │  │  │
│  │  └────────┘  └────────┘  └──────┘  └──────┘  └──────┘  └────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└───┬─────────────┬──────────────┬──────────────┬────────────────┬────────────┘
    │             │              │              │                │
┌───▼────┐  ┌─────▼──────┐  ┌───▼───────┐  ┌───▼──────┐  ┌─────▼─────────┐
│  PG    │  │  OpenAI    │  │ Finnhub   │  │ Alpaca   │  │  Prometheus   │
│  RDS   │  │  API (LLM) │  │(Mkt Data) │  │ (Broker) │  │  + Grafana    │
└────────┘  └────────────┘  └───────────┘  └──────────┘  └───────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                      Periodic Trigger (Celery Beat)                         │
│  Checks for periodic-mode pipelines every 5 minutes                         │
│  Enqueues to Celery if not already running                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Responsibilities

**Frontend (Angular)**
- Visual pipeline builder (drag-drop interface)
- Scanner management (create/edit ticker lists)
- Signal subscription configuration
- Real-time monitoring dashboard
- User authentication & profile management
- Cost tracking & subscription management

**Backend API (FastAPI)**
- REST endpoints for CRUD operations (Pipelines, Scanners, Executions, Users)
- WebSocket server for real-time execution updates
- Authentication & authorization (JWT)
- Subscription tier enforcement
- Request validation & rate limiting
- OpenTelemetry metrics exposure

**Signal Generators (Independent Services)**
- Monitor market conditions (technical indicators, news, custom)
- Generate structured trading signals
- Publish signals to Kafka topic (`trading-signals`)
- Expose Prometheus metrics (generation rate, latency)

**Trigger Dispatcher (Independent Service)**
- Subscribe to Kafka signal topic
- Maintain in-memory cache of active signal-based pipelines
- Match signals to pipelines based on scanner tickers and subscriptions
- Enqueue matched pipelines to Celery (if not already running)
- Handle duplicate signal filtering

**Periodic Scheduler (Celery Beat)**
- Check for active periodic-mode pipelines every 5 minutes
- Enqueue periodic pipelines if not already running
- No polling per-pipeline (centralized scheduling)

**Pipeline Orchestrator (Celery Workers + CrewAI)**
- Execute pipeline workflows (agent DAG)
- Manage agent lifecycle
- Track execution costs (LLM tokens, agent runtime)
- Generate structured reports per agent
- Handle retries & failures

**Data Layer**
- **PostgreSQL (RDS)**: Users, pipelines, scanners, trades, executions, subscriptions
- **Redis (ElastiCache)**: Celery task queue, caching
- **Kafka**: Signal message bus
- **Prometheus**: Metrics time-series database
- **Grafana**: Monitoring dashboards
- **S3** (future): Detailed reports, logs, archives

**Monitoring & Observability (OpenTelemetry + Prometheus + Grafana)**
- Application metrics (HTTP requests, DB queries, Celery tasks)
- Business metrics (pipelines, executions, signals, system health)
- Dashboards for real-time visualization
- Future: Distributed tracing, log aggregation, alerting

---

## 2. Backend Architecture

### 2.1 FastAPI Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI app initialization
│   ├── config.py               # Configuration management
│   ├── dependencies.py         # Dependency injection
│   │
│   ├── api/
│   │   ├── v1/
│   │   │   ├── auth.py         # Authentication endpoints
│   │   │   ├── pipelines.py    # Pipeline CRUD
│   │   │   ├── executions.py   # Execution control
│   │   │   ├── trades.py       # Trade history
│   │   │   ├── reports.py      # Report viewing
│   │   │   ├── billing.py      # Cost tracking
│   │   │   └── agents.py       # Agent registry
│   │   └── websocket.py        # WebSocket handlers
│   │
│   ├── models/
│   │   ├── user.py             # SQLAlchemy models
│   │   ├── pipeline.py
│   │   ├── execution.py
│   │   ├── trade.py
│   │   ├── report.py
│   │   └── billing.py
│   │
│   ├── schemas/
│   │   ├── pipeline.py         # Pydantic schemas
│   │   ├── agent.py
│   │   └── state.py
│   │
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── pipeline_service.py
│   │   ├── billing_service.py
│   │   └── notification_service.py
│   │
│   ├── agents/                 # Agent implementations
│   │   ├── base.py             # Base agent interface
│   │   ├── triggers/
│   │   │   ├── time_trigger.py
│   │   │   ├── technical_trigger.py
│   │   │   ├── price_trigger.py
│   │   │   └── news_trigger.py
│   │   ├── market_data_agent.py
│   │   ├── bias_agent.py
│   │   ├── strategy_agent.py
│   │   ├── risk_manager_agent.py
│   │   ├── trade_manager_agent.py
│   │   └── reporting_agent.py
│   │
│   ├── tools/                  # Agent tools
│   │   ├── market_data_tool.py
│   │   ├── broker_tool.py
│   │   ├── database_tool.py
│   │   └── notification_tool.py
│   │
│   ├── orchestration/
│   │   ├── flow.py             # CrewAI flow definition
│   │   ├── state.py            # Pipeline state management
│   │   └── executor.py         # Celery tasks
│   │
│   ├── llm/
│   │   ├── provider.py         # LLM abstraction
│   │   ├── openai_provider.py
│   │   └── token_counter.py
│   │
│   └── utils/
│       ├── encryption.py
│       ├── validators.py
│       └── constants.py
│
├── tests/
├── migrations/                 # Alembic migrations
├── requirements.txt
└── docker-compose.yml
```

### 2.2 Key Design Patterns

**Repository Pattern**: Database access abstraction
**Factory Pattern**: Agent instantiation based on type
**Strategy Pattern**: LLM provider switching
**Observer Pattern**: WebSocket event broadcasting
**Decorator Pattern**: Cost tracking, retry logic

---

## 3. Agent Framework Design

### 3.1 Pipeline State Schema

```python
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from datetime import datetime
from enum import Enum

class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

class BiasType(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

class MarketData(BaseModel):
    symbol: str
    current_price: float
    bid: float
    ask: float
    volume: int
    ohlcv: Dict[str, float]
    indicators: Dict[str, float]  # RSI, SMA, EMA, MACD, etc.
    timestamp: datetime

class BiasSignal(BaseModel):
    bias: BiasType
    confidence: float  # 0-100
    reasoning: str
    factors: List[str]
    timestamp: datetime

class StrategySignal(BaseModel):
    action: TradeSide
    conviction: float  # 0-100
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward_ratio: float
    reasoning: str
    technical_factors: List[str]
    timestamp: datetime

class RiskDecision(BaseModel):
    approved: bool
    adjusted: bool
    position_size: int  # shares
    account_risk_pct: float
    position_risk_amount: float
    adjustments_made: Optional[str]
    reasoning: str
    timestamp: datetime

class TradeExecution(BaseModel):
    order_id: str
    broker_order_id: str
    symbol: str
    action: TradeSide
    quantity: int
    requested_price: float
    filled_price: float
    slippage: float
    commission: float
    status: str
    timestamp: datetime

class TimeframeData(BaseModel):
    """Market data for a specific timeframe"""
    timeframe: str  # "1m", "5m", "15m", "1h", "4h", "1d"
    ohlcv: Dict[str, float]
    indicators: Dict[str, float]
    candles: List[Dict]  # Recent candles for this timeframe

class PipelineState(BaseModel):
    # Metadata
    pipeline_id: str
    execution_id: str
    user_id: str
    symbol: str
    start_time: datetime
    current_agent: str
    
    # Timeframe context
    timeframes: Dict[str, TimeframeData] = {}  # {timeframe: data}
    primary_timeframe: str = "5m"  # Default execution timeframe
    
    # Agent outputs
    trigger_condition: Optional[str] = None
    market_data: Optional[MarketData] = None
    bias: Optional[BiasSignal] = None
    strategy: Optional[StrategySignal] = None
    risk: Optional[RiskDecision] = None
    trade: Optional[TradeExecution] = None
    
    # Cost tracking
    tokens_used: Dict[str, int] = {}  # {agent_id: tokens}
    api_calls: Dict[str, int] = {}    # {service: count}
    agent_runtime: Dict[str, float] = {}  # {agent_id: seconds}
    
    # Metadata
    errors: List[str] = []
    warnings: List[str] = []
    metadata: Dict[str, Any] = {}
    
    def get_timeframe_data(self, timeframe: str) -> Optional[TimeframeData]:
        """Get market data for specific timeframe"""
        return self.timeframes.get(timeframe)
```

### 3.2 Base Agent Interface

```python
from abc import ABC, abstractmethod
from typing import Type, Dict, Any, List
from pydantic import BaseModel
from crewai import Agent, Crew, Task

class AgentConfigSchema(BaseModel):
    """JSON Schema definition for agent configuration"""
    type: str  # "object", "string", "number", etc.
    properties: Dict[str, Any]
    required: List[str]
    title: str
    description: str

class AgentMetadata(BaseModel):
    """Metadata for agent registry and UI generation"""
    agent_type: str
    name: str
    description: str
    category: str  # "trigger", "data", "analysis", "risk", "execution", "reporting"
    version: str
    icon: str  # Icon identifier for UI
    pricing_rate: float
    is_free: bool
    requires_timeframes: List[str]  # e.g., ["1h", "4h", "1d"] or ["5m"]
    config_schema: AgentConfigSchema  # JSON Schema for configuration UI

class BaseAgent(ABC):
    """Base class for all agents in the system"""
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        self.agent_id = agent_id  # Unique ID in pipeline
        self.config = config
        self.agent_type = self.__class__.__name__
        self.pricing_rate = self.get_metadata().pricing_rate
    
    @classmethod
    @abstractmethod
    def get_metadata(cls) -> AgentMetadata:
        """Return agent metadata for registry and UI generation"""
        pass
    
    @abstractmethod
    def process(self, state: PipelineState) -> PipelineState:
        """
        Process the pipeline state and return updated state.
        This is the main entry point for agent execution.
        """
        pass
    
    @abstractmethod
    def get_input_schema(self) -> Type[BaseModel]:
        """Return the expected input schema"""
        pass
    
    @abstractmethod
    def get_output_schema(self) -> Type[BaseModel]:
        """Return the output schema this agent produces"""
        pass
    
    def validate_input(self, state: PipelineState) -> bool:
        """Validate that state contains required inputs"""
        pass
    
    def validate_config(self) -> bool:
        """Validate agent configuration against schema"""
        schema = self.get_metadata().config_schema
        # Validate self.config against schema
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize agent for storage"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "config": self.config,
            "metadata": self.get_metadata().dict()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseAgent":
        """Deserialize agent from storage"""
        return cls(agent_id=data["agent_id"], config=data["config"])
    
    def track_cost(self, state: PipelineState, tokens: int, runtime: float):
        """Track cost metrics for this agent execution"""
        state.tokens_used[self.agent_id] = tokens
        state.agent_runtime[self.agent_id] = runtime
```

**Example Agent Implementation**:
```python
class StrategyAgent(BaseAgent):
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="strategy_agent",
            name="Strategy Agent",
            description="Generates complete trading signals with entry, stops, and targets",
            category="analysis",
            version="1.0.0",
            icon="strategy",
            pricing_rate=0.10,  # $0.10/hour
            is_free=False,
            requires_timeframes=["5m"],  # Works on single timeframe
            config_schema=AgentConfigSchema(
                type="object",
                title="Strategy Agent Configuration",
                description="Configure strategy generation parameters",
                properties={
                    "timeframe": {
                        "type": "string",
                        "enum": ["1m", "5m", "15m", "1h", "4h", "1d"],
                        "default": "5m",
                        "title": "Trading Timeframe",
                        "description": "Primary timeframe for strategy signals"
                    },
                    "risk_reward_min": {
                        "type": "number",
                        "minimum": 1.0,
                        "maximum": 5.0,
                        "default": 1.5,
                        "title": "Minimum Risk/Reward Ratio",
                        "description": "Minimum acceptable risk/reward for trades"
                    },
                    "creativity": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 0.7,
                        "title": "Creativity (Temperature)",
                        "description": "Higher values = more creative strategies"
                    }
                },
                required=["timeframe", "risk_reward_min"]
            )
        )
```

### 3.3 CrewAI Flow Integration

```python
from crewai.flow.flow import Flow, listen, start
from typing import Dict

class TradingPipelineFlow(Flow):
    """CrewAI flow for orchestrating trading pipeline"""
    
    def __init__(self, pipeline_config: Dict, user_id: str):
        super().__init__()
        self.pipeline_config = pipeline_config
        self.user_id = user_id
        self.state = PipelineState(
            pipeline_id=pipeline_config['id'],
            execution_id=generate_execution_id(),
            user_id=user_id,
            symbol=pipeline_config['symbol'],
            start_time=datetime.utcnow(),
            current_agent="trigger"
        )
    
    @start()
    def trigger_wait(self):
        """First step: Wait for trigger condition"""
        agent = create_agent_from_config(
            self.pipeline_config['agents']['trigger']
        )
        self.state = agent.process(self.state)
        return self.state
    
    @listen(trigger_wait)
    def fetch_market_data(self, state: PipelineState):
        """Fetch current market data"""
        agent = MarketDataAgent(self.pipeline_config['agents']['market_data'])
        self.state = agent.process(state)
        return self.state
    
    @listen(fetch_market_data)
    def analyze_bias(self, state: PipelineState):
        """Determine market bias"""
        agent = BiasAgent(self.pipeline_config['agents']['bias'])
        self.state = agent.process(state)
        return self.state
    
    @listen(analyze_bias)
    def generate_strategy(self, state: PipelineState):
        """Generate trading signal with stops/targets"""
        agent = StrategyAgent(self.pipeline_config['agents']['strategy'])
        self.state = agent.process(state)
        return self.state
    
    @listen(generate_strategy)
    def validate_risk(self, state: PipelineState):
        """Validate and adjust for risk"""
        agent = RiskManagerAgent(self.pipeline_config['agents']['risk'])
        self.state = agent.process(state)
        return self.state
    
    @listen(validate_risk)
    def execute_trade(self, state: PipelineState):
        """Execute approved trade"""
        if state.risk and state.risk.approved:
            agent = TradeManagerAgent(self.pipeline_config['agents']['trade'])
            self.state = agent.process(state)
        return self.state
    
    @listen(execute_trade)
    def generate_report(self, state: PipelineState):
        """Create execution report"""
        agent = ReportingAgent(self.pipeline_config['agents']['reporting'])
        self.state = agent.process(state)
        return self.state
```

---

## 4. Individual Agent Designs

### 4.1 Time-Based Trigger Agent (FREE)

**Purpose**: Pause pipeline execution until specific time conditions met

**Input Requirements**: None (uses config)

**Configuration**:
```python
{
    "type": "time_trigger",
    "schedule": {
        "type": "market_hours",  # or "specific_time", "cron"
        "market": "US",
        "offset_minutes": 5  # start 5 min after market open
    }
}
```

**Output**: Updates `state.trigger_condition`

**Implementation**:
- Check if current time matches schedule
- If not met, raise `TriggerNotMetException` (handled by orchestrator)
- Celery retries task with exponential backoff
- No LLM calls required (free agent)

### 4.2 Technical Indicator Trigger Agent

**Purpose**: Trigger based on technical analysis conditions

**Input Requirements**: Market data (fetches itself)

**Configuration**:
```python
{
    "type": "technical_trigger",
    "conditions": [
        {"indicator": "RSI", "operator": ">", "value": 70},
        {"indicator": "MACD", "signal": "bullish_crossover"}
    ],
    "logic": "AND"  # or "OR"
}
```

**Tools Used**:
- MarketDataTool: Fetch indicators
- LLM (light): Interpret complex conditions

**Output**: Updates `state.trigger_condition`

### 4.3 Market Data Agent

**Purpose**: Fetch current market data and calculate indicators

**Input Requirements**: symbol (from config)

**Tools Used**:
- FinnhubTool: Real-time quotes, candles
- IndicatorTool: Calculate SMA, EMA, RSI, MACD, Bollinger Bands

**Process**:
1. Fetch current quote and recent candles
2. Calculate technical indicators
3. Format into MarketData object
4. No LLM required (data fetching only)

**Output**: Updates `state.market_data`

### 4.4 Bias Agent

**Purpose**: Determine overall market sentiment/direction

**Input Requirements**: `state.market_data`

**CrewAI Crew**:
- **Market Analyst Agent**: Analyzes technical indicators
- **Sentiment Analyst Agent**: Considers broader market context
- **Bias Synthesizer Agent**: Combines inputs into final bias

**Tasks**:
1. Technical Analysis Task: Review indicators for trend
2. Sentiment Task: Assess market sentiment
3. Bias Decision Task: Synthesize into bullish/bearish/neutral

**LLM Usage**: GPT-4 (requires reasoning)

**Output**: Updates `state.bias`

### 4.5 Strategy Agent

**Purpose**: Generate complete trading signal with entry, stops, and targets

**Input Requirements**: `state.market_data`, `state.bias`

**CrewAI Crew**:
- **Pattern Recognition Agent**: Identify chart patterns
- **Entry Analyst Agent**: Determine optimal entry price
- **Risk Analyst Agent**: Calculate stop loss based on volatility/support
- **Target Analyst Agent**: Identify profit targets based on resistance/reward ratio

**Process**:
1. Analyze current market structure
2. Align strategy with bias (don't fight the trend)
3. Determine entry price
4. Calculate stop loss (ATR-based or support/resistance)
5. Calculate Target 1 (conservative, 1.5:1 R:R)
6. Calculate Target 2 (aggressive, 3:1 R:R)
7. Provide detailed reasoning for each level

**LLM Usage**: GPT-4 (complex reasoning required)

**Output**: Updates `state.strategy` with complete trade plan

**Example Output**:
```python
StrategySignal(
    action="BUY",
    conviction=85,
    entry_price=150.50,
    stop_loss=148.00,  # -$2.50 risk
    target_1=154.25,   # +$3.75 (1.5:1 R:R)
    target_2=158.00,   # +$7.50 (3:1 R:R)
    risk_reward_ratio=1.5,
    reasoning="Golden cross forming, RSI oversold recovery...",
    technical_factors=["Golden Cross", "Support at 148", "Volume surge"]
)
```

### 4.6 Risk Manager Agent

**Purpose**: Validate trade proposal and calculate position sizing

**Input Requirements**: `state.strategy`, user account info

**Process**:
1. Retrieve user account balance and positions
2. Calculate risk per share: `entry_price - stop_loss`
3. Calculate position size: `(account_balance * risk_pct) / risk_per_share`
4. Check against risk rules:
   - Max position size per trade
   - Max portfolio exposure to symbol
   - Minimum risk/reward ratio (e.g., 1:1.5)
   - Buying power availability
5. Approve, reject, or adjust position size

**LLM Usage**: GPT-3.5-turbo (calculation + rules application)

**Output**: Updates `state.risk`

**Example**:
```python
# Account: $100,000, Max risk per trade: 2%
# Strategy: Entry $150.50, Stop $148.00, risk = $2.50/share
# Position size = ($100,000 * 0.02) / $2.50 = 800 shares
# Total position = $120,400 (exceeds 10% max position size)
# ADJUST: Reduce to 600 shares ($90,300, 9% of account)

RiskDecision(
    approved=True,
    adjusted=True,
    position_size=600,
    account_risk_pct=1.5,  # actual risk after adjustment
    position_risk_amount=1500,  # $2.50 * 600
    adjustments_made="Reduced from 800 to 600 shares to comply with 10% max position rule",
    reasoning="..."
)
```

### 4.7 Trade Manager Agent (Enhanced)

**Purpose**: Execute trades, manage positions, monitor exits, provide manual controls

**Input Requirements**: `state.risk` (approved), `state.strategy`

**Tools Used**:
- BrokerTool (Enhanced): Submit orders, query positions, manage exits

**Configuration**:
```python
{
    "type": "trade_manager_agent",
    "allow_pyramiding": False,  # Allow multiple positions same symbol
    "partial_exit_split": [50, 50],  # [T1%, T2%]
    "move_stop_to_breakeven": True,
    "monitoring_enabled": True
}
```

**Process**:
1. **Pre-Trade Position Check**
   - Query broker for existing open positions
   - Check if position already exists for symbol
   - Reject if conflict (configurable)
   
2. **Execute Trade**
   - Check if trade approved by risk manager
   - Construct order payload with stops/targets
   - Submit bracket order (if broker supports)
   - Or submit main order + stop/target orders separately
   - Poll for fill confirmation
   - Calculate slippage

3. **Start Position Monitoring**
   - Store position details in monitoring system
   - Schedule periodic checks (every 60 seconds)
   - Monitor for stop loss hit, target hits

4. **Position Monitoring Loop** (Celery Task)
   - Query broker for current position status
   - Check current price vs stop/targets
   - If stop hit: Close position, create report
   - If Target 1 hit: Close partial (configurable %), move stop to breakeven
   - If Target 2 hit: Close remaining position
   - Schedule next check if position still open

5. **Manual Controls**
   - Expose emergency close via API
   - Stop monitoring when manually closed
   - Log manual intervention for audit

**LLM Usage**: None (execution and monitoring logic only)

**Output**: Updates `state.trade` with execution details

**Example Flow**:
```python
# Approved trade from Risk Manager
approved_trade = RiskDecision(
    approved=True,
    position_size=600,  # shares
    ...
)

# Strategy details
strategy = StrategySignal(
    entry_price=150.50,
    stop_loss=148.00,
    target_1=154.25,
    target_2=158.00
)

# Trade Manager checks broker
existing_positions = broker_tool.get_open_positions()
if "AAPL" in [p.symbol for p in existing_positions]:
    return TradeExecution(status="REJECTED", reason="Position exists")

# Execute
order = broker_tool.place_bracket_order(
    symbol="AAPL",
    side="BUY",
    quantity=600,
    stop_loss=148.00,
    take_profit_1=154.25,
    take_profit_2=158.00
)

# Start monitoring
monitor_position_task.apply_async(args=[position_data])
```

**Broker Tool Enhancement**:
```python
class BrokerTool:
    def get_open_positions(self) -> List[Position]:
        """Query broker for all open positions"""
        
    def place_bracket_order(self, ...):
        """Place order with attached stop/targets"""
        
    def emergency_close_position(self, symbol: str):
        """Immediately close at market"""
        
    def close_partial_position(self, symbol: str, quantity: int):
        """Close partial position"""
        
    def modify_stop_loss(self, symbol: str, new_stop: float):
        """Move stop to breakeven"""
```

### 4.8 Reporting Agent

**Purpose**: Collect reasoning chain and create comprehensive report

**Input Requirements**: All previous agent outputs in state

**Process**:
1. Collect outputs from all agents
2. Create structured JSON report
3. Generate executive summary using LLM
4. Store in database and S3
5. Trigger notification

**LLM Usage**: GPT-3.5-turbo (summarization)

**Output**: Report created, stored, user notified

---

## 5. Pipeline Storage & Serialization

### 5.1 Pipeline Configuration Format

Pipelines are stored as JSON in the database `config` column:

```json
{
  "id": "pipeline-uuid",
  "name": "My Day Trading Bot",
  "symbol": "AAPL",
  "primary_timeframe": "5m",
  "nodes": [
    {
      "id": "node-1",
      "agent_type": "time_trigger",
      "position": {"x": 100, "y": 100},
      "config": {
        "schedule": {
          "type": "market_hours",
          "market": "US",
          "offset_minutes": 5
        }
      }
    },
    {
      "id": "node-2",
      "agent_type": "market_data_agent",
      "position": {"x": 300, "y": 100},
      "config": {
        "timeframes": ["1h", "4h", "1d", "5m"],
        "indicators": ["SMA_20", "SMA_50", "RSI", "MACD"]
      }
    },
    {
      "id": "node-3",
      "agent_type": "bias_agent",
      "position": {"x": 500, "y": 100},
      "config": {
        "analysis_timeframes": ["1h", "4h", "1d"],
        "confidence_threshold": 70
      }
    },
    {
      "id": "node-4",
      "agent_type": "strategy_agent",
      "position": {"x": 700, "y": 100},
      "config": {
        "timeframe": "5m",
        "risk_reward_min": 1.5,
        "creativity": 0.7
      }
    }
  ],
  "edges": [
    {"from": "node-1", "to": "node-2"},
    {"from": "node-2", "to": "node-3"},
    {"from": "node-3", "to": "node-4"}
  ],
  "settings": {
    "max_retries": 3,
    "retry_delay": 60
  }
}
```

### 5.2 Agent Instantiation from Config

```python
def create_agent_from_node(node: Dict[str, Any]) -> BaseAgent:
    """Factory function to create agent from pipeline node"""
    agent_type = node["agent_type"]
    agent_id = node["id"]
    config = node["config"]
    
    # Get agent class from registry
    agent_class = AGENT_REGISTRY.get(agent_type)
    if not agent_class:
        raise ValueError(f"Unknown agent type: {agent_type}")
    
    # Instantiate agent
    agent = agent_class(agent_id=agent_id, config=config)
    
    # Validate configuration
    if not agent.validate_config():
        raise ValueError(f"Invalid config for {agent_type}")
    
    return agent

def create_flow_from_pipeline(pipeline_config: Dict) -> TradingPipelineFlow:
    """Create executable CrewAI flow from pipeline configuration"""
    # Parse nodes and edges
    # Create agent instances
    # Build flow graph dynamically
    pass
```

### 5.3 Agent Registry

```python
# Global registry mapping agent types to classes
AGENT_REGISTRY = {
    "time_trigger": TimeTriggerAgent,
    "technical_trigger": TechnicalTriggerAgent,
    "price_trigger": PriceTriggerAgent,
    "news_trigger": NewsTriggerAgent,
    "market_data_agent": MarketDataAgent,
    "bias_agent": BiasAgent,
    "strategy_agent": StrategyAgent,
    "risk_manager_agent": RiskManagerAgent,
    "trade_manager_agent": TradeManagerAgent,
    "reporting_agent": ReportingAgent,
}

def get_all_agent_metadata() -> List[AgentMetadata]:
    """Get metadata for all registered agents (for UI)"""
    return [agent_class.get_metadata() for agent_class in AGENT_REGISTRY.values()]
```

---

## 6. Dynamic UI Generation

### 6.1 JSON Schema Forms in Angular

**Library**: `@ajsf/core` (Angular JSON Schema Form) or `ngx-schema-form`

**Flow**:
1. Frontend fetches agent metadata from `/api/v1/agents`
2. For each agent type, receives `config_schema` (JSON Schema)
3. Dynamically renders form using JSON Schema Form library
4. User fills form, values saved in pipeline config

**Example Component**:
```typescript
// agent-config.component.ts
import { Component, Input } from '@angular/core';
import { JsonSchemaFormModule } from '@ajsf/core';

@Component({
  selector: 'app-agent-config',
  template: `
    <json-schema-form
      [schema]="configSchema"
      [data]="configData"
      (onChanges)="onConfigChange($event)">
    </json-schema-form>
  `
})
export class AgentConfigComponent {
  @Input() agentMetadata: AgentMetadata;
  configSchema: any;
  configData: any = {};
  
  ngOnInit() {
    // Convert our AgentConfigSchema to JSON Schema format
    this.configSchema = this.agentMetadata.config_schema;
  }
  
  onConfigChange(data: any) {
    // Emit config changes to parent (pipeline builder)
    this.configData = data;
  }
}
```

### 6.2 Pipeline Builder UI Architecture

**Visual Editor**: Use `@angular/cdk/drag-drop` or integrate with a library like:
- `@swimlane/ngx-graph` (graph visualization)
- Or custom canvas with D3.js/Konva.js

**Components**:
```
pipeline-builder/
├── agent-palette.component.ts      # Left sidebar: Available agents
├── pipeline-canvas.component.ts    # Center: Drag-drop canvas
├── agent-config-panel.component.ts # Right sidebar: Selected agent config
└── pipeline-toolbar.component.ts   # Top: Save, Run, etc.
```

**State Management**:
```typescript
interface PipelineBuilderState {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  selectedNode: string | null;
  agentMetadata: AgentMetadata[];
}
```

### 6.3 Timeframe Selection UI

Since agents require different timeframes:

1. **Market Data Agent Config**:
   - Multi-select dropdown for timeframes
   - Fetches all selected timeframes

2. **Bias Agent Config**:
   - Multi-select for analysis timeframes (e.g., 1h, 4h, 1d)

3. **Strategy Agent Config**:
   - Single select for execution timeframe (e.g., 5m)

**UI ensures**:
- Market Data Agent fetches all timeframes needed by downstream agents
- Clear labeling: "Analysis Timeframes" vs "Execution Timeframe"

---

## 7. WebSocket Design

### 7.1 Purpose & Events

**Purpose**: Real-time updates to frontend during pipeline execution

**Events Emitted**:
```python
# Backend emits these events
{
    "event": "execution_started",
    "execution_id": "uuid",
    "pipeline_id": "uuid",
    "timestamp": "2025-10-23T10:00:00Z"
}

{
    "event": "agent_started",
    "execution_id": "uuid",
    "agent_id": "node-3",
    "agent_type": "bias_agent",
    "timestamp": "2025-10-23T10:00:15Z"
}

{
    "event": "agent_completed",
    "execution_id": "uuid",
    "agent_id": "node-3",
    "output_summary": "Bias: Bullish (85% confidence)",
    "cost_increment": 0.002,
    "timestamp": "2025-10-23T10:00:25Z"
}

{
    "event": "trade_executed",
    "execution_id": "uuid",
    "trade": {
        "symbol": "AAPL",
        "action": "BUY",
        "quantity": 100,
        "price": 150.50
    },
    "timestamp": "2025-10-23T10:01:00Z"
}

{
    "event": "execution_completed",
    "execution_id": "uuid",
    "status": "completed",
    "total_cost": 0.05,
    "report_id": "uuid",
    "timestamp": "2025-10-23T10:01:30Z"
}

{
    "event": "error",
    "execution_id": "uuid",
    "agent_id": "node-4",
    "error_message": "Risk check failed: Insufficient buying power",
    "timestamp": "2025-10-23T10:00:50Z"
}
```

### 7.2 Implementation

**Backend (FastAPI)**:
```python
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        self.active_connections[user_id].remove(websocket)
    
    async def send_to_user(self, user_id: str, message: dict):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                await connection.send_json(message)

manager = ConnectionManager()

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)

# Emit events from agents
async def emit_agent_event(user_id: str, event_type: str, data: dict):
    await manager.send_to_user(user_id, {
        "event": event_type,
        **data
    })
```

**Frontend (Angular)**:
```typescript
// websocket.service.ts
import { Injectable } from '@angular/core';
import { Observable, Subject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private socket: WebSocket;
  private subject: Subject<any> = new Subject();
  
  connect(userId: string): Observable<any> {
    this.socket = new WebSocket(`wss://api.example.com/ws/${userId}`);
    
    this.socket.onmessage = (event) => {
      this.subject.next(JSON.parse(event.data));
    };
    
    this.socket.onerror = (error) => {
      console.error('WebSocket error:', error);
      // Fallback to polling
      this.fallbackToPolling();
    };
    
    return this.subject.asObservable();
  }
  
  private fallbackToPolling() {
    // Implement polling as fallback
  }
}
```

### 7.3 Is WebSocket Necessary?

**Pros**:
- Instant updates (< 100ms latency)
- Better UX for monitoring
- Lower server load than frequent polling

**Cons**:
- More complex infrastructure
- Connection management overhead

**Decision**: **Include for MVP** but with polling fallback. Critical for:
- Live monitoring dashboard
- Real-time cost tracking
- Trade execution notifications

**Alternative**: Server-Sent Events (SSE) - simpler than WebSockets, one-way only

---

## 8. Pipeline Scheduling & Execution Modes

### 8.1 Execution Modes

Pipelines support four execution modes to handle different trading strategies:

**1. RUN_ONCE** (Default - Safest)
- Pipeline runs once when manually started
- After completion, status = "completed", stops
- User must manually start again
- Use case: Test a strategy, one-time scan

**2. RUN_CONTINUOUS**
- Pipeline runs indefinitely until manually stopped
- After completing one cycle, immediately restarts
- Checks time windows and daily limits before restart
- Use case: Day trading, continuous monitoring

**3. RUN_SCHEDULED**
- Pipeline runs on a schedule (cron, intervals, market hours)
- Celery Beat manages scheduling
- Use case: Daily analysis at market open, hourly scans

**4. RUN_ON_SIGNAL**
- Runs continuously but position-aware
- Won't restart if position still open
- Once position closes, automatically restarts
- Use case: One position at a time, wait for exit before next entry

### 8.2 Schedule Configuration Schema

```python
from enum import Enum
from pydantic import BaseModel
from typing import Optional, List

class ExecutionMode(str, Enum):
    RUN_ONCE = "run_once"
    RUN_CONTINUOUS = "run_continuous"
    RUN_SCHEDULED = "run_scheduled"
    RUN_ON_SIGNAL = "run_on_signal"

class ScheduleConfig(BaseModel):
    """Complete schedule configuration for pipeline execution"""
    
    # Schedule type
    schedule_type: str  # "cron", "market_open", "interval", "time_window"
    
    # For cron scheduling
    cron_expression: Optional[str] = None  # "0 9 * * 1-5" (9 AM weekdays)
    
    # For market-based scheduling
    market: Optional[str] = "US"
    offset_minutes: Optional[int] = 5  # Start N minutes after market open
    
    # For interval scheduling
    interval_minutes: Optional[int] = None  # Run every X minutes
    active_during: Optional[str] = "market_hours"  # or "24/7"
    
    # Time window control (NEW)
    start_time: Optional[str] = None  # "09:35" (HH:MM format)
    end_time: Optional[str] = None    # "15:30" (HH:MM format)
    timezone: str = "America/New_York"
    
    # Active days (0=Monday, 6=Sunday)
    active_days: List[int] = [0, 1, 2, 3, 4]  # Default: weekdays
    
    # End-of-day position management (NEW)
    flatten_positions_at_end: bool = False  # Auto-close at end_time
    stop_pipeline_at_end: bool = True       # Stop pipeline at end_time
    
    # Trading limits
    max_trades_per_day: Optional[int] = None
    max_executions_per_day: Optional[int] = None
    
    # Auto-stop conditions
    stop_on_daily_loss: Optional[float] = None  # Stop if lose $X
    stop_on_drawdown: Optional[float] = None    # Stop if drawdown X%

class PipelineConfig(BaseModel):
    """Pipeline configuration including execution mode"""
    id: str
    name: str
    symbol: str
    nodes: List[Node]
    edges: List[Edge]
    
    # Execution configuration
    execution_mode: ExecutionMode = ExecutionMode.RUN_ONCE
    schedule_config: Optional[ScheduleConfig] = None
```

### 8.3 Time Window Management

```python
# app/orchestration/time_window.py

from datetime import datetime, time
import pytz

class TimeWindowChecker:
    """Check if current time is within configured trading window"""
    
    def __init__(self, schedule_config: ScheduleConfig):
        self.config = schedule_config
        self.tz = pytz.timezone(schedule_config.timezone)
    
    def is_within_window(self) -> bool:
        """Check if current time is within start_time and end_time"""
        
        if not self.config.start_time or not self.config.end_time:
            return True  # No time restriction
        
        now = datetime.now(self.tz)
        
        # Check day of week
        if now.weekday() not in self.config.active_days:
            return False
        
        # Parse times
        start = datetime.strptime(self.config.start_time, "%H:%M").time()
        end = datetime.strptime(self.config.end_time, "%H:%M").time()
        current = now.time()
        
        # Check if within window
        if start <= end:
            return start <= current <= end
        else:
            # Crosses midnight: 22:00 - 02:00
            return current >= start or current <= end
    
    def is_past_end_time(self) -> bool:
        """Check if current time is past end_time"""
        if not self.config.end_time:
            return False
        
        now = datetime.now(self.tz)
        end = datetime.strptime(self.config.end_time, "%H:%M").time()
        return now.time() > end
    
    def seconds_until_end(self) -> Optional[int]:
        """Calculate seconds until end_time"""
        if not self.config.end_time:
            return None
        
        now = datetime.now(self.tz)
        end_time = datetime.strptime(self.config.end_time, "%H:%M").time()
        end_datetime = datetime.combine(now.date(), end_time, tzinfo=self.tz)
        
        if end_datetime < now:
            return 0
        
        return int((end_datetime - now).total_seconds())
```

### 8.4 Pipeline Execution with Time Windows

```python
# app/orchestration/executor.py

@celery_app.task
def execute_pipeline(pipeline_id: str, user_id: str):
    """
    Main pipeline execution task with time window and mode handling
    """
    pipeline = load_pipeline(pipeline_id)
    
    # Check if within trading window
    time_checker = TimeWindowChecker(pipeline.schedule_config)
    
    if not time_checker.is_within_window():
        logger.info(f"Pipeline {pipeline_id} outside trading window")
        
        if time_checker.is_past_end_time():
            handle_end_of_day(pipeline, user_id)
        
        return
    
    # Execute the pipeline flow
    flow = TradingPipelineFlow(pipeline.config, user_id)
    result = flow.run()
    
    # Determine if should restart based on execution mode
    if should_restart_pipeline(pipeline, result):
        seconds_until_end = time_checker.seconds_until_end()
        
        # Don't restart if less than 5 minutes until end time
        if seconds_until_end and seconds_until_end < 300:
            logger.info(f"Pipeline {pipeline_id} near end time, scheduling EOD")
            schedule_end_of_day_task(pipeline_id, user_id, seconds_until_end)
        else:
            schedule_pipeline_restart(pipeline_id, user_id, pipeline.execution_mode)
    else:
        mark_pipeline_completed(pipeline_id)

def should_restart_pipeline(pipeline: Pipeline, result: ExecutionResult) -> bool:
    """Determine if pipeline should restart after execution"""
    
    mode = pipeline.execution_mode
    
    if mode == ExecutionMode.RUN_ONCE:
        return False
    
    if mode == ExecutionMode.RUN_CONTINUOUS:
        # Check trading limits
        if exceeded_daily_limits(pipeline):
            logger.info(f"Pipeline {pipeline.id} hit daily limit")
            return False
        return True
    
    if mode == ExecutionMode.RUN_ON_SIGNAL:
        # Check if position is open
        position = check_open_position(pipeline.user_id, pipeline.symbol)
        if position:
            # Wait for position to close
            schedule_restart_after_position_close(pipeline.id, pipeline.symbol)
            return False
        return True
    
    if mode == ExecutionMode.RUN_SCHEDULED:
        # Celery Beat handles scheduling
        return False
    
    return False

def exceeded_daily_limits(pipeline: Pipeline) -> bool:
    """Check if pipeline has hit daily limits"""
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
    
    # Check max trades
    if pipeline.schedule_config.max_trades_per_day:
        trades_today = count_trades_today(pipeline.id, today_start)
        if trades_today >= pipeline.schedule_config.max_trades_per_day:
            notify_user(pipeline.user_id, "Pipeline stopped: Max trades per day reached")
            return True
    
    # Check max executions
    if pipeline.schedule_config.max_executions_per_day:
        executions_today = count_executions_today(pipeline.id, today_start)
        if executions_today >= pipeline.schedule_config.max_executions_per_day:
            return True
    
    # Check daily loss limit
    if pipeline.schedule_config.stop_on_daily_loss:
        daily_pnl = calculate_daily_pnl(pipeline.id, today_start)
        if daily_pnl < -pipeline.schedule_config.stop_on_daily_loss:
            logger.warning(f"Pipeline {pipeline.id} hit daily loss limit: ${daily_pnl}")
            notify_user(
                pipeline.user_id, 
                f"Pipeline stopped: Daily loss limit of ${pipeline.schedule_config.stop_on_daily_loss} exceeded"
            )
            return True
    
    return False
```

### 8.5 End-of-Day Position Management

```python
def handle_end_of_day(pipeline: Pipeline, user_id: str):
    """Handle end-of-day actions when pipeline reaches end_time"""
    
    logger.info(f"Pipeline {pipeline.id} reached end time")
    
    # Flatten positions if configured
    if pipeline.schedule_config.flatten_positions_at_end:
        logger.info(f"Flattening all positions for pipeline {pipeline.id}")
        flatten_all_positions(user_id, pipeline.id, reason="End of trading window")
    
    # Stop pipeline if configured
    if pipeline.schedule_config.stop_pipeline_at_end:
        logger.info(f"Stopping pipeline {pipeline.id} at end of window")
        update_pipeline_status(pipeline.id, "stopped")
        
        notify_user(
            user_id,
            f"Pipeline '{pipeline.name}' stopped at end of trading window ({pipeline.schedule_config.end_time})"
        )

@celery_app.task
def flatten_all_positions(user_id: str, pipeline_id: str, reason: str):
    """Close all open positions for a pipeline at market price"""
    
    broker_tool = BrokerTool(user_id=user_id)
    positions = broker_tool.get_open_positions()
    
    if not positions:
        logger.info(f"No positions to flatten for pipeline {pipeline_id}")
        return
    
    closed_positions = []
    failed_positions = []
    total_pnl = 0.0
    
    for position in positions:
        try:
            # Check if position created by this pipeline
            trade = get_trade_by_symbol_and_pipeline(user_id, position.symbol, pipeline_id)
            if not trade:
                continue
            
            logger.info(f"Closing position {position.symbol} for pipeline {pipeline_id}")
            result = broker_tool.emergency_close_position(position.symbol)
            
            # Stop monitoring
            stop_position_monitoring(user_id, position.symbol)
            
            # Log the flatten
            log_position_flatten(
                user_id=user_id,
                pipeline_id=pipeline_id,
                symbol=position.symbol,
                reason=reason,
                fill_price=result.fill_price,
                pnl=position.unrealized_pnl
            )
            
            closed_positions.append(position.symbol)
            total_pnl += position.unrealized_pnl
            
        except Exception as e:
            logger.error(f"Failed to close {position.symbol}: {e}")
            failed_positions.append(position.symbol)
    
    # Log EOD action
    log_eod_action(
        pipeline_id=pipeline_id,
        user_id=user_id,
        positions_closed=len(closed_positions),
        total_pnl=total_pnl,
        reason=reason
    )
    
    # Notify user
    if closed_positions:
        notify_user(
            user_id,
            f"Pipeline '{pipeline_id}' closed {len(closed_positions)} positions at end of trading window: {', '.join(closed_positions)}. Total P&L: ${total_pnl:.2f}"
        )
    
    if failed_positions:
        notify_user(
            user_id,
            f"Warning: Failed to close positions: {', '.join(failed_positions)}",
            level="warning"
        )
    
    return {
        "closed": closed_positions,
        "failed": failed_positions,
        "total_pnl": total_pnl
    }

# Periodic task to check time windows (runs every minute)
@celery_app.task
def check_pipeline_time_windows():
    """Check if any active pipelines have passed their end_time"""
    
    active_pipelines = get_active_pipelines_with_time_windows()
    
    for pipeline in active_pipelines:
        time_checker = TimeWindowChecker(pipeline.schedule_config)
        
        if time_checker.is_past_end_time():
            logger.info(f"Pipeline {pipeline.id} past end time, triggering EOD")
            handle_end_of_day(pipeline, pipeline.user_id)
```

### 8.6 Celery Beat Scheduled Tasks

```python
# app/orchestration/beat_schedule.py

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Register scheduled pipelines with Celery Beat"""
    
    # Time window checker - runs every minute
    sender.add_periodic_task(
        60.0,
        check_pipeline_time_windows.s(),
        name='check-pipeline-time-windows'
    )
    
    # Load all RUN_SCHEDULED pipelines
    scheduled_pipelines = get_scheduled_pipelines()
    
    for pipeline in scheduled_pipelines:
        schedule = create_schedule(pipeline.schedule_config)
        
        sender.add_periodic_task(
            schedule,
            execute_pipeline.s(pipeline.id, pipeline.user_id),
            name=f'scheduled-pipeline-{pipeline.id}'
        )

def create_schedule(config: ScheduleConfig):
    """Convert schedule config to Celery schedule"""
    from celery.schedules import crontab
    
    if config.schedule_type == "cron":
        return crontab(config.cron_expression)
    
    elif config.schedule_type == "interval":
        return config.interval_minutes * 60  # seconds
    
    elif config.schedule_type == "market_open":
        # Market open: 9:30 AM ET on weekdays
        hour = 9
        minute = 30 + config.offset_minutes
        return crontab(hour=hour, minute=minute, day_of_week='1-5')
    
    elif config.schedule_type == "time_window":
        # Uses start_time
        start = datetime.strptime(config.start_time, "%H:%M")
        return crontab(hour=start.hour, minute=start.minute, day_of_week='1-5')
```

### 8.7 Database Schema Updates

```sql
-- Add execution mode and schedule config to pipelines table
ALTER TABLE pipelines ADD COLUMN execution_mode VARCHAR(50) DEFAULT 'run_once';
ALTER TABLE pipelines ADD COLUMN schedule_config JSONB;
ALTER TABLE pipelines ADD COLUMN current_status VARCHAR(50) DEFAULT 'stopped';
ALTER TABLE pipelines ADD COLUMN last_execution_at TIMESTAMP;
ALTER TABLE pipelines ADD COLUMN next_scheduled_at TIMESTAMP;

-- Track daily pipeline statistics
CREATE TABLE pipeline_daily_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id UUID REFERENCES pipelines(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    executions_count INTEGER DEFAULT 0,
    trades_count INTEGER DEFAULT 0,
    daily_pnl DECIMAL(10, 2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pipeline_id, date)
);

CREATE INDEX idx_pipeline_daily_stats ON pipeline_daily_stats(pipeline_id, date DESC);

-- Track end-of-day actions
CREATE TABLE eod_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id UUID REFERENCES pipelines(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    action_date DATE NOT NULL,
    action_time TIME NOT NULL,
    positions_closed INTEGER DEFAULT 0,
    total_pnl DECIMAL(10, 2),
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_eod_actions ON eod_actions(pipeline_id, action_date DESC);
```

---

## 9. Cost Estimation System

### 9.1 Pre-Execution Cost Estimation

**Purpose**: Provide users with accurate cost estimates BEFORE starting pipeline to enable budget planning and cost optimization.

### 9.2 Cost Estimator Service

```python
# app/services/cost_estimator.py

from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from pydantic import BaseModel

class CostEstimate(BaseModel):
    """Complete cost estimate for a pipeline"""
    cost_per_execution: float
    agent_costs: Dict[str, Dict]  # {agent_type: {rate, duration, cost}}
    token_costs: Dict[str, Dict]  # {agent_type: {model, tokens, cost}}
    total_agent_cost: float
    total_token_cost: float
    estimated_duration_minutes: float
    daily_cost_range: Tuple[float, float]  # (min, max)
    monthly_cost_range: Tuple[float, float]
    daily_executions_range: Tuple[int, int]
    confidence: str  # "low", "medium", "high"

class BudgetComparison(BaseModel):
    """Comparison of estimate against user budget"""
    within_budget: bool
    warnings: List[str]
    daily_usage_pct: float = None
    monthly_usage_pct: float = None

class CostEstimator:
    """Estimate pipeline execution costs before running"""
    
    # Agent hourly rates ($/hour)
    AGENT_HOURLY_RATES = {
        "time_trigger": 0.0,
        "technical_trigger": 0.03,
        "price_trigger": 0.02,
        "news_trigger": 0.05,
        "market_data_agent": 0.0,
        "bias_agent": 0.08,
        "strategy_agent": 0.10,
        "risk_manager_agent": 0.05,
        "trade_manager_agent": 0.0,
        "reporting_agent": 0.0,
    }
    
    # Average execution time per agent (minutes)
    AGENT_AVG_DURATION = {
        "time_trigger": 0.5,
        "technical_trigger": 1.0,
        "price_trigger": 0.5,
        "news_trigger": 2.0,
        "market_data_agent": 1.0,
        "bias_agent": 6.0,  # Uses LLM, slower
        "strategy_agent": 6.0,
        "risk_manager_agent": 3.0,
        "trade_manager_agent": 2.0,
        "reporting_agent": 2.0,
    }
    
    # Average token usage per agent
    AGENT_AVG_TOKENS = {
        "bias_agent": {
            "model": "gpt-4",
            "input": 2000,
            "output": 500
        },
        "strategy_agent": {
            "model": "gpt-4",
            "input": 1500,
            "output": 600
        },
        "risk_manager_agent": {
            "model": "gpt-3.5-turbo",
            "input": 1000,
            "output": 300
        },
        "reporting_agent": {
            "model": "gpt-3.5-turbo",
            "input": 3000,
            "output": 500
        },
    }
    
    # Token costs (per 1K tokens) - update these based on OpenAI pricing
    TOKEN_COSTS = {
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    }
    
    def estimate_pipeline_cost(
        self, 
        pipeline_config: Dict,
        user_history: Dict = None
    ) -> CostEstimate:
        """
        Estimate costs for a pipeline configuration
        
        Args:
            pipeline_config: Pipeline configuration dict
            user_history: Optional historical execution data for this user
        
        Returns:
            Detailed cost breakdown and estimates
        """
        
        # 1. Get agents in pipeline
        agents = self._get_agents_in_pipeline(pipeline_config)
        
        # 2. Calculate agent rental costs
        agent_costs = {}
        total_agent_cost = 0.0
        total_duration_minutes = 0.0
        
        for agent_type in agents:
            hourly_rate = self.AGENT_HOURLY_RATES.get(agent_type, 0.0)
            
            # Use historical data if available
            if user_history and agent_type in user_history:
                duration_minutes = user_history[agent_type]["avg_duration"]
            else:
                duration_minutes = self.AGENT_AVG_DURATION.get(agent_type, 2.0)
            
            # Calculate cost: (hourly_rate / 60) * duration_minutes
            agent_cost = (hourly_rate / 60) * duration_minutes
            
            agent_costs[agent_type] = {
                "hourly_rate": hourly_rate,
                "duration_minutes": duration_minutes,
                "cost": agent_cost
            }
            
            total_agent_cost += agent_cost
            total_duration_minutes += duration_minutes
        
        # 3. Calculate LLM token costs
        token_costs = {}
        total_token_cost = 0.0
        
        for agent_type in agents:
            if agent_type in self.AGENT_AVG_TOKENS:
                token_info = self.AGENT_AVG_TOKENS[agent_type]
                
                # Use historical data if available
                if user_history and agent_type in user_history:
                    input_tokens = user_history[agent_type]["avg_input_tokens"]
                    output_tokens = user_history[agent_type]["avg_output_tokens"]
                else:
                    input_tokens = token_info["input"]
                    output_tokens = token_info["output"]
                
                model = token_info["model"]
                
                # Calculate cost
                input_cost = (input_tokens / 1000) * self.TOKEN_COSTS[model]["input"]
                output_cost = (output_tokens / 1000) * self.TOKEN_COSTS[model]["output"]
                total_cost = input_cost + output_cost
                
                token_costs[agent_type] = {
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": total_cost
                }
                
                total_token_cost += total_cost
        
        # 4. Calculate per-execution cost
        cost_per_execution = total_agent_cost + total_token_cost
        
        # 5. Estimate daily/monthly costs based on schedule
        schedule_config = pipeline_config.get("schedule_config", {})
        execution_mode = pipeline_config.get("execution_mode", "run_once")
        
        daily_estimate = self._estimate_daily_executions(
            execution_mode,
            schedule_config
        )
        
        cost_per_day_low = cost_per_execution * daily_estimate["executions_min"]
        cost_per_day_high = cost_per_execution * daily_estimate["executions_max"]
        
        # 21 trading days per month average
        cost_per_month_low = cost_per_day_low * 21
        cost_per_month_high = cost_per_day_high * 21
        
        # 6. Determine confidence level
        confidence = "medium"
        if user_history:
            confidence = "high"  # Have historical data
        elif execution_mode == "run_once":
            confidence = "high"  # Predictable
        elif execution_mode == "run_continuous":
            confidence = "low"  # Depends on trigger frequency
        
        return CostEstimate(
            cost_per_execution=cost_per_execution,
            agent_costs=agent_costs,
            token_costs=token_costs,
            total_agent_cost=total_agent_cost,
            total_token_cost=total_token_cost,
            estimated_duration_minutes=total_duration_minutes,
            daily_cost_range=(cost_per_day_low, cost_per_day_high),
            monthly_cost_range=(cost_per_month_low, cost_per_month_high),
            daily_executions_range=(
                daily_estimate["executions_min"],
                daily_estimate["executions_max"]
            ),
            confidence=confidence
        )
    
    def _get_agents_in_pipeline(self, pipeline_config: Dict) -> List[str]:
        """Extract agent types from pipeline configuration"""
        agents = []
        for node in pipeline_config.get("nodes", []):
            agent_type = node.get("agent_type")
            if agent_type:
                agents.append(agent_type)
        return agents
    
    def _estimate_daily_executions(
        self,
        execution_mode: str,
        schedule_config: Dict
    ) -> Dict[str, int]:
        """
        Estimate how many times pipeline will execute per day
        
        Returns: {"executions_min": int, "executions_max": int}
        """
        
        if execution_mode == "run_once":
            return {"executions_min": 1, "executions_max": 1}
        
        elif execution_mode == "run_scheduled":
            if schedule_config.get("schedule_type") == "interval":
                interval_minutes = schedule_config.get("interval_minutes", 60)
                
                # Get trading window duration
                start_time = schedule_config.get("start_time", "09:35")
                end_time = schedule_config.get("end_time", "15:30")
                
                start_dt = datetime.strptime(start_time, "%H:%M")
                end_dt = datetime.strptime(end_time, "%H:%M")
                window_minutes = (end_dt - start_dt).seconds / 60
                
                executions = int(window_minutes / interval_minutes)
                return {"executions_min": executions, "executions_max": executions}
            
            elif schedule_config.get("schedule_type") == "market_open":
                return {"executions_min": 1, "executions_max": 1}
        
        elif execution_mode == "run_continuous":
            # Depends on trigger frequency - estimate conservatively
            start_time = schedule_config.get("start_time", "09:35")
            end_time = schedule_config.get("end_time", "15:30")
            
            start_dt = datetime.strptime(start_time, "%H:%M")
            end_dt = datetime.strptime(end_time, "%H:%M")
            window_hours = (end_dt - start_dt).seconds / 3600
            
            # Conservative: 1 per hour, Aggressive: 2 per hour
            executions_min = max(1, int(window_hours))
            executions_max = int(window_hours * 2)
            
            # Cap by max_trades_per_day
            max_trades = schedule_config.get("max_trades_per_day")
            if max_trades:
                executions_max = min(executions_max, max_trades)
            
            return {"executions_min": executions_min, "executions_max": executions_max}
        
        elif execution_mode == "run_on_signal":
            max_trades = schedule_config.get("max_trades_per_day", 3)
            return {"executions_min": 1, "executions_max": max_trades}
        
        return {"executions_min": 1, "executions_max": 5}
    
    def compare_budget(
        self,
        estimate: CostEstimate,
        user_budget: Dict
    ) -> BudgetComparison:
        """
        Compare estimated costs against user's budget
        
        Returns warnings if approaching or exceeding budget
        """
        
        daily_budget = user_budget.get("daily_limit")
        monthly_budget = user_budget.get("monthly_limit")
        
        warnings = []
        daily_pct = None
        monthly_pct = None
        
        # Check daily budget
        if daily_budget:
            daily_pct = (estimate.daily_cost_range[1] / daily_budget) * 100
            
            if estimate.daily_cost_range[1] > daily_budget:
                warnings.append(
                    f"Estimated daily cost (${estimate.daily_cost_range[1]:.2f}) "
                    f"may exceed daily budget (${daily_budget:.2f})"
                )
            elif estimate.daily_cost_range[1] > daily_budget * 0.8:
                warnings.append(
                    f"Estimated daily cost will use ~{daily_pct:.0f}% of daily budget"
                )
        
        # Check monthly budget
        if monthly_budget:
            monthly_pct = (estimate.monthly_cost_range[1] / monthly_budget) * 100
            
            if estimate.monthly_cost_range[1] > monthly_budget:
                warnings.append(
                    f"Estimated monthly cost (${estimate.monthly_cost_range[1]:.2f}) "
                    f"may exceed monthly budget (${monthly_budget:.2f})"
                )
            elif estimate.monthly_cost_range[1] > monthly_budget * 0.8:
                warnings.append(
                    f"Estimated monthly cost will use ~{monthly_pct:.0f}% of budget"
                )
        
        return BudgetComparison(
            within_budget=len(warnings) == 0,
            warnings=warnings,
            daily_usage_pct=daily_pct,
            monthly_usage_pct=monthly_pct
        )
```

### 9.3 Cost Estimation API Endpoints

```python
# app/api/v1/cost.py

from fastapi import APIRouter, Depends, HTTPException
from app.models.user import User
from app.dependencies import get_current_user
from app.services.cost_estimator import CostEstimator

router = APIRouter(prefix="/api/v1", tags=["cost"])

@router.post("/pipelines/estimate-cost", response_model=CostEstimateResponse)
async def estimate_pipeline_cost(
    pipeline_config: Dict,
    current_user: User = Depends(get_current_user)
):
    """
    Estimate costs for a pipeline configuration before running
    
    Returns detailed cost breakdown and budget comparison
    """
    
    estimator = CostEstimator()
    
    # Get user's historical execution data for more accurate estimates
    user_history = await get_user_execution_history(current_user.id)
    
    # Get cost estimate
    estimate = estimator.estimate_pipeline_cost(pipeline_config, user_history)
    
    # Get user's budget settings
    user_budget = await get_user_budget(current_user.id)
    
    # Compare against budget
    budget_comparison = estimator.compare_budget(estimate, user_budget)
    
    return CostEstimateResponse(
        estimate=estimate,
        budget_comparison=budget_comparison,
        timestamp=datetime.utcnow()
    )

@router.get("/pipelines/{pipeline_id}/cost-estimate")
async def get_pipeline_cost_estimate(
    pipeline_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get cost estimate for an existing pipeline"""
    
    pipeline = await get_pipeline(pipeline_id, current_user.id)
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    
    estimator = CostEstimator()
    user_history = await get_user_execution_history(current_user.id)
    estimate = estimator.estimate_pipeline_cost(pipeline.config, user_history)
    
    user_budget = await get_user_budget(current_user.id)
    budget_comparison = estimator.compare_budget(estimate, user_budget)
    
    return CostEstimateResponse(
        estimate=estimate,
        budget_comparison=budget_comparison,
        timestamp=datetime.utcnow()
    )

@router.get("/cost/historical-accuracy")
async def get_estimation_accuracy(
    current_user: User = Depends(get_current_user),
    days: int = 30
):
    """
    Get historical accuracy of cost estimates vs actual costs
    
    Helps users understand confidence level of estimates
    """
    
    accuracy_data = await calculate_estimation_accuracy(
        current_user.id,
        days=days
    )
    
    return {
        "avg_accuracy_pct": accuracy_data["avg_accuracy"],
        "total_estimated": accuracy_data["total_estimated"],
        "total_actual": accuracy_data["total_actual"],
        "sample_size": accuracy_data["executions_count"],
        "confidence": accuracy_data["confidence_level"]
    }
```

### 9.4 Database Schema for Estimate Tracking

```sql
-- Track estimate vs actual for improving accuracy
CREATE TABLE cost_estimate_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID REFERENCES pipeline_executions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    pipeline_id UUID REFERENCES pipelines(id) ON DELETE CASCADE,
    
    -- Estimates
    estimated_cost DECIMAL(10, 4),
    estimated_duration_minutes DECIMAL(10, 2),
    confidence_level VARCHAR(20),
    
    -- Actuals
    actual_cost DECIMAL(10, 4),
    actual_duration_minutes DECIMAL(10, 2),
    
    -- Accuracy
    cost_accuracy_pct DECIMAL(5, 2),  -- (actual/estimated * 100)
    duration_accuracy_pct DECIMAL(5, 2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cost_estimate_tracking_user ON cost_estimate_tracking(user_id, created_at DESC);
CREATE INDEX idx_cost_estimate_tracking_pipeline ON cost_estimate_tracking(pipeline_id, created_at DESC);
```

### 9.5 Frontend Cost Display Component

```typescript
// frontend/src/app/features/pipeline-builder/cost-estimator/cost-estimator.component.ts

import { Component, OnInit, Input } from '@angular/core';
import { CostEstimatorService } from './cost-estimator.service';

@Component({
  selector: 'app-cost-estimator',
  templateUrl: './cost-estimator.component.html',
  styleUrls: ['./cost-estimator.component.scss']
})
export class CostEstimatorComponent implements OnInit {
  @Input() pipelineConfig: PipelineConfig;
  
  costEstimate: CostEstimate | null = null;
  budgetComparison: BudgetComparison | null = null;
  loading = false;
  showDetailedBreakdown = false;
  
  constructor(
    private costService: CostEstimatorService
  ) {}
  
  ngOnInit() {
    this.estimateCosts();
  }
  
  ngOnChanges(changes: SimpleChanges) {
    // Recalculate when pipeline config changes
    if (changes['pipelineConfig']) {
      this.estimateCosts();
    }
  }
  
  estimateCosts() {
    this.loading = true;
    
    this.costService.estimatePipelineCost(this.pipelineConfig)
      .subscribe({
        next: (response) => {
          this.costEstimate = response.estimate;
          this.budgetComparison = response.budget_comparison;
          this.loading = false;
        },
        error: (error) => {
          console.error('Failed to estimate costs:', error);
          this.loading = false;
        }
      });
  }
  
  getBudgetStatus(): 'safe' | 'warning' | 'danger' {
    if (!this.budgetComparison) return 'safe';
    
    const pct = this.budgetComparison.monthly_usage_pct || 0;
    
    if (pct > 100) return 'danger';
    if (pct > 80) return 'warning';
    return 'safe';
  }
  
  getConfidenceColor(confidence: string): string {
    switch (confidence) {
      case 'high': return 'green';
      case 'medium': return 'yellow';
      case 'low': return 'orange';
      default: return 'gray';
    }
  }
  
  toggleDetailedBreakdown() {
    this.showDetailedBreakdown = !this.showDetailedBreakdown;
  }
}
```

---

## 10. Position Management System

### 10.1 Position Monitoring (Celery Task)

```python
# app/orchestration/executor.py

@celery_app.task(name="monitor_position")
def monitor_position_task(position_data: dict):
    """
    Periodic task to monitor open position for exit conditions
    Runs every 60 seconds while position is open
    """
    broker_tool = BrokerTool(user_id=position_data['user_id'])
    
    # Get current position from broker (source of truth)
    position = broker_tool.get_position(position_data['symbol'])
    
    if not position:
        logger.info(f"Position {position_data['symbol']} already closed")
        return  # Position closed, stop monitoring
    
    current_price = position.current_price
    symbol = position_data['symbol']
    side = position_data['side']
    
    # Check exit conditions based on side
    if side == 'LONG':
        # Check stop loss
        if current_price <= position_data['stop_loss']:
            logger.info(f"Stop loss hit for {symbol} at ${current_price}")
            broker_tool.close_position(symbol, reason="Stop loss hit")
            trigger_reporting_agent(position_data['execution_id'])
            return
        
        # Check Target 2
        if current_price >= position_data['target_2']:
            logger.info(f"Target 2 hit for {symbol} at ${current_price}")
            broker_tool.close_position(symbol, reason="Target 2 hit")
            trigger_reporting_agent(position_data['execution_id'])
            return
        
        # Check Target 1
        if current_price >= position_data['target_1']:
            # Check if we've already taken partial profit
            if position.quantity == position_data['original_quantity']:
                # First time hitting T1, take partial profit
                partial_split = position_data.get('partial_exit_split', [50, 50])
                partial_qty = int(position.quantity * partial_split[0] / 100)
                
                logger.info(f"Target 1 hit for {symbol}, closing {partial_qty} shares")
                broker_tool.close_partial_position(symbol, partial_qty)
                
                # Move stop to breakeven if configured
                if position_data.get('move_stop_to_breakeven', True):
                    broker_tool.modify_stop_loss(symbol, position_data['entry_price'])
                    logger.info(f"Moved stop to breakeven for {symbol}")
    
    elif side == 'SHORT':
        # Check stop loss (inverse for short)
        if current_price >= position_data['stop_loss']:
            logger.info(f"Stop loss hit for SHORT {symbol} at ${current_price}")
            broker_tool.close_position(symbol, reason="Stop loss hit")
            trigger_reporting_agent(position_data['execution_id'])
            return
        
        # Check Target 2 (inverse)
        if current_price <= position_data['target_2']:
            logger.info(f"Target 2 hit for SHORT {symbol} at ${current_price}")
            broker_tool.close_position(symbol, reason="Target 2 hit")
            trigger_reporting_agent(position_data['execution_id'])
            return
        
        # Check Target 1 (inverse)
        if current_price <= position_data['target_1']:
            if position.quantity == position_data['original_quantity']:
                partial_split = position_data.get('partial_exit_split', [50, 50])
                partial_qty = int(position.quantity * partial_split[0] / 100)
                
                logger.info(f"Target 1 hit for SHORT {symbol}, closing {partial_qty} shares")
                broker_tool.close_partial_position(symbol, partial_qty)
                
                if position_data.get('move_stop_to_breakeven', True):
                    broker_tool.modify_stop_loss(symbol, position_data['entry_price'])
    
    # Position still open, schedule next check
    monitor_position_task.apply_async(
        args=[position_data],
        countdown=60  # Check again in 60 seconds
    )
```

### 10.2 Position Management API Endpoints

```python
# app/api/v1/positions.py

from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.models.user import User
from app.dependencies import get_current_user
from app.tools.broker_tool import BrokerTool

router = APIRouter(prefix="/api/v1/positions", tags=["positions"])

@router.get("", response_model=List[PositionResponse])
async def get_open_positions(
    current_user: User = Depends(get_current_user)
):
    """
    Get all open positions for the current user
    
    Queries the broker for real-time position data
    """
    broker_tool = BrokerTool(user_id=current_user.id)
    positions = broker_tool.get_open_positions()
    
    # Enrich with pipeline information
    for position in positions:
        # Look up which pipeline created this position
        trade = await get_trade_by_symbol(current_user.id, position.symbol)
        if trade:
            position.pipeline_id = trade.pipeline_id
            position.pipeline_name = trade.pipeline_name
            position.created_by_execution = trade.execution_id
    
    return positions

@router.post("/{symbol}/close", response_model=ClosePositionResponse)
async def emergency_close_position(
    symbol: str,
    reason: str = "Manual emergency close",
    current_user: User = Depends(get_current_user)
):
    """
    Emergency close a specific position immediately at market price
    
    This stops all monitoring and closes the position
    """
    broker_tool = BrokerTool(user_id=current_user.id)
    
    # Verify position exists
    position = broker_tool.get_position(symbol)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    # Close at market
    result = broker_tool.emergency_close_position(symbol)
    
    # Stop monitoring task
    # Cancel any scheduled monitoring tasks for this position
    stop_position_monitoring(current_user.id, symbol)
    
    # Log manual intervention for audit
    await log_manual_intervention(
        user_id=current_user.id,
        symbol=symbol,
        action="emergency_close",
        reason=reason,
        fill_price=result.fill_price
    )
    
    logger.info(
        f"Manual emergency close: {symbol} by user {current_user.id}",
        extra={
            "user_id": current_user.id, 
            "symbol": symbol,
            "reason": reason
        }
    )
    
    return ClosePositionResponse(
        status="closed",
        symbol=symbol,
        closed_at=datetime.utcnow(),
        fill_price=result.fill_price,
        quantity=position.quantity
    )

@router.post("/close-all", response_model=List[ClosePositionResponse])
async def emergency_close_all_positions(
    reason: str = "Manual emergency close all",
    current_user: User = Depends(get_current_user)
):
    """
    Emergency close ALL open positions immediately
    
    Use with caution - closes everything at market price
    """
    broker_tool = BrokerTool(user_id=current_user.id)
    
    # Get all positions
    positions = broker_tool.get_open_positions()
    
    if not positions:
        return []
    
    results = []
    for position in positions:
        try:
            result = broker_tool.emergency_close_position(position.symbol)
            stop_position_monitoring(current_user.id, position.symbol)
            
            results.append(ClosePositionResponse(
                status="closed",
                symbol=position.symbol,
                closed_at=datetime.utcnow(),
                fill_price=result.fill_price,
                quantity=position.quantity
            ))
            
        except Exception as e:
            logger.error(f"Failed to close {position.symbol}: {e}")
            results.append(ClosePositionResponse(
                status="error",
                symbol=position.symbol,
                error=str(e)
            ))
    
    # Log bulk close
    await log_manual_intervention(
        user_id=current_user.id,
        action="emergency_close_all",
        reason=reason,
        positions_closed=len(results)
    )
    
    return results

@router.get("/{symbol}", response_model=PositionDetailResponse)
async def get_position_detail(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed information about a specific position
    
    Including monitoring status, exit levels, history
    """
    broker_tool = BrokerTool(user_id=current_user.id)
    
    position = broker_tool.get_position(symbol)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    # Get monitoring status
    monitoring_active = is_position_being_monitored(current_user.id, symbol)
    
    # Get exit levels from monitoring data
    exit_levels = get_exit_levels(current_user.id, symbol)
    
    return PositionDetailResponse(
        **position.dict(),
        monitoring_active=monitoring_active,
        stop_loss=exit_levels.get('stop_loss'),
        target_1=exit_levels.get('target_1'),
        target_2=exit_levels.get('target_2')
    )
```

### 10.3 Database Schema Updates

```sql
-- Add to trades table for monitoring status
ALTER TABLE trades ADD COLUMN monitoring_active BOOLEAN DEFAULT true;
ALTER TABLE trades ADD COLUMN partial_exit_at TIMESTAMP;
ALTER TABLE trades ADD COLUMN partial_exit_quantity INTEGER;
ALTER TABLE trades ADD COLUMN fully_closed_at TIMESTAMP;
ALTER TABLE trades ADD COLUMN close_reason VARCHAR(100);  -- 'stop_hit', 'target_hit', 'manual'

-- Manual interventions audit log
CREATE TABLE manual_interventions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(20),
    action VARCHAR(50),  -- 'emergency_close', 'emergency_close_all'
    reason TEXT,
    positions_affected INTEGER DEFAULT 1,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

CREATE INDEX idx_manual_interventions_user ON manual_interventions(user_id, timestamp DESC);
```

---

## 11. Multi-Symbol Support & Stock Picker Agent

### 11.1 Stock Picker Agent

**Purpose**: Select multiple symbols to analyze based on screening criteria, enabling portfolio strategies and stock scanning.

```python
# app/agents/stock_picker_agent.py

from app.agents.base import BaseAgent, AgentMetadata, AgentConfigSchema
from app.services.screener_service import ScreenerService
from typing import List, Dict

class StockPickerAgent(BaseAgent):
    """
    Stock Picker Agent
    
    Selects which stocks to analyze based on a saved screener.
    Runs the screener and adds top N symbols to pipeline state.
    
    Position in Pipeline:
      Trigger Agent → Stock Picker Agent → Market Data Agent → ...
    
    This agent is FREE (no cost) but downstream agents will charge
    per symbol analyzed.
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="stock_picker_agent",
            name="Stock Picker Agent",
            description=(
                "Selects stocks to analyze using a saved screener. "
                "Runs your screener filters and picks the top N stocks "
                "that match your criteria. Subsequent agents will analyze "
                "these stocks in parallel.\n\n"
                "⚠️ Cost Multiplier: Analyzing N symbols will multiply "
                "downstream agent costs by N."
            ),
            category="data",
            version="1.0.0",
            icon="filter_list",
            pricing_rate=0.0,  # FREE - just runs filters
            is_free=True,
            requires_timeframes=[],  # Doesn't need timeframe data
            config_schema=AgentConfigSchema(
                type="object",
                title="Stock Picker Configuration",
                properties={
                    "screener_id": {
                        "type": "string",
                        "title": "Screener",
                        "description": "Select a saved screener to use",
                        "format": "screener-select",  # Custom UI component
                    },
                    "top_n": {
                        "type": "integer",
                        "title": "Top N Stocks",
                        "description": "How many stocks to pick from screener results",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "refresh_on_each_run": {
                        "type": "boolean",
                        "title": "Refresh Screener on Each Run",
                        "description": (
                            "If true, runs screener fresh each time. "
                            "If false, uses cached results (faster but may be stale)."
                        ),
                        "default": True,
                    },
                    "fallback_to_previous": {
                        "type": "boolean",
                        "title": "Fallback to Previous Results",
                        "description": (
                            "If screener returns no results, use previous run's symbols"
                        ),
                        "default": False,
                    },
                },
                required=["screener_id"],
            ),
        )
    
    def __init__(self, agent_id: str, config: Dict):
        super().__init__(agent_id, config)
        self.screener_service = ScreenerService()
    
    async def process(self, state: PipelineState) -> PipelineState:
        """
        Run screener and add selected symbols to state
        
        Args:
            state: Current pipeline state
            
        Returns:
            Updated state with symbols list populated
            
        Raises:
            AgentProcessingError: If screener fails
            BudgetExceededException: If multi-symbol execution would exceed budget
        """
        
        screener_id = self.config.get("screener_id")
        top_n = self.config.get("top_n", 10)
        refresh = self.config.get("refresh_on_each_run", True)
        
        logger.info(f"Stock Picker: Running screener {screener_id} for top {top_n} symbols")
        
        try:
            # Get screener configuration
            screener = await self.get_screener(screener_id, state.user_id)
            
            if not screener:
                raise AgentProcessingError(f"Screener {screener_id} not found")
            
            # Run screener (or get cached results)
            if refresh:
                screener_results = await self.screener_service.run_screener(screener)
                # Cache results for 5 minutes
                await self.cache_screener_results(screener_id, screener_results)
            else:
                screener_results = await self.get_cached_screener_results(screener_id)
                if not screener_results:
                    # Cache miss, run fresh
                    screener_results = await self.screener_service.run_screener(screener)
            
            # Get top N symbols
            symbols = screener_results.symbols[:top_n]
            
            if not symbols:
                # No stocks matched screener
                logger.warning("Stock Picker: No symbols found in screener")
                
                if self.config.get("fallback_to_previous"):
                    # Try to get previous results
                    symbols = await self.get_previous_symbols(state.pipeline_id)
                
                if not symbols:
                    state.symbols = []
                    state.stock_picker_output = {
                        "screener_id": screener_id,
                        "symbols_found": 0,
                        "symbols_selected": [],
                        "status": "no_results",
                    }
                    # This will cause downstream agents to skip
                    return state
            
            # IMPORTANT: Check budget before proceeding with multi-symbol execution
            await self.check_multi_symbol_budget(state, len(symbols))
            
            # Add to state
            state.symbols = symbols
            state.stock_picker_output = {
                "screener_id": screener_id,
                "screener_name": screener.name,
                "total_matched": screener_results.total_matched,
                "symbols_found": len(screener_results.symbols),
                "symbols_selected": symbols,
                "executed_at": screener_results.executed_at,
                "status": "success",
            }
            
            logger.info(
                f"Stock Picker: Selected {len(symbols)} stocks from "
                f"{screener_results.total_matched} total matches: {symbols}"
            )
            
            return state
            
        except BudgetExceededException:
            # Re-raise budget exceptions
            raise
        except Exception as e:
            logger.exception(f"Stock Picker Agent failed: {str(e)}")
            state.errors.append(f"stock_picker_agent: {str(e)}")
            raise AgentProcessingError(f"Stock picker failed: {str(e)}")
    
    async def check_multi_symbol_budget(self, state: PipelineState, num_symbols: int):
        """
        Check if user has budget for analyzing N symbols
        
        Raises BudgetExceededException if insufficient budget
        """
        if num_symbols == 1:
            return  # Normal single-symbol budget check will happen later
        
        # Estimate cost for analyzing N symbols
        from app.services.cost_estimator import CostEstimator
        
        estimator = CostEstimator()
        pipeline = await get_pipeline(state.pipeline_id)
        
        # Calculate estimated cost with multi-symbol multiplier
        estimated_cost = await estimator.estimate_pipeline_cost_with_symbols(
            pipeline.config,
            num_symbols=num_symbols
        )
        
        # Check user's remaining budget
        user_budget = await get_user_budget(state.user_id)
        daily_spend = await get_daily_spend(state.user_id)
        remaining_budget = user_budget.daily_limit - daily_spend
        
        if estimated_cost.cost_per_execution > remaining_budget:
            raise BudgetExceededException(
                f"Analyzing {num_symbols} symbols would cost "
                f"${estimated_cost.cost_per_execution:.2f}, but you only have "
                f"${remaining_budget:.2f} remaining in your daily budget. "
                f"Either reduce top_n in Stock Picker config or increase budget."
            )
        
        logger.info(
            f"Budget check passed: ${estimated_cost.cost_per_execution:.2f} "
            f"cost for {num_symbols} symbols, ${remaining_budget:.2f} remaining"
        )
    
    async def get_screener(self, screener_id: str, user_id: str):
        """Fetch screener configuration from database"""
        from app.models.screener import Screener
        screener = await Screener.get(id=screener_id, user_id=user_id)
        return screener
    
    async def cache_screener_results(self, screener_id: str, results):
        """Cache screener results in Redis (5 minute TTL)"""
        import json
        cache_key = f"screener_results:{screener_id}"
        await redis_client.setex(
            cache_key,
            300,  # 5 minutes
            json.dumps(results.dict())
        )
    
    async def get_cached_screener_results(self, screener_id: str):
        """Get cached screener results"""
        import json
        cache_key = f"screener_results:{screener_id}"
        cached = await redis_client.get(cache_key)
        if cached:
            from app.services.screener_service import ScreenerResult
            return ScreenerResult(**json.loads(cached))
        return None
    
    async def get_previous_symbols(self, pipeline_id: str) -> List[str]:
        """Get symbols from previous successful execution"""
        # Query database for last execution's symbols
        last_execution = await get_last_successful_execution(pipeline_id)
        if last_execution and last_execution.stock_picker_output:
            return last_execution.stock_picker_output.get("symbols_selected", [])
        return []
```

### 11.2 Updated PipelineState (Multi-Symbol)

```python
# app/models/state.py

class PipelineState(BaseModel):
    """
    Enhanced pipeline state with multi-symbol support
    """
    
    # Existing fields
    pipeline_id: str
    execution_id: str
    user_id: str
    
    # Symbol selection (NEW - for multi-symbol support)
    symbols: List[str] = []  # List of symbols to analyze (from Stock Picker)
    symbol: str = None  # Deprecated - for backward compatibility with single-symbol
    
    # Stock Picker output
    stock_picker_output: Dict = None  # Screener execution details
    
    # Market data (enhanced for multi-symbol)
    market_data: MarketData = None  # Deprecated - single symbol
    market_data_multi: Dict[str, MarketData] = {}  # {symbol: MarketData}
    timeframes: Dict[str, TimeframeData] = {}  # For single symbol (backward compat)
    timeframes_multi: Dict[str, Dict[str, TimeframeData]] = {}  # {symbol: {tf: data}}
    
    # Analysis results per symbol
    bias_results: Dict[str, BiasOutput] = {}  # {symbol: BiasOutput}
    strategy_signals: Dict[str, StrategyOutput] = {}  # {symbol: StrategyOutput}
    risk_approvals: Dict[str, RiskOutput] = {}  # {symbol: RiskOutput}
    
    # Execution (can have multiple trades from multi-symbol)
    trades: List[TradeExecution] = []  # All executed trades
    
    # Reporting
    reports: Dict[str, Dict] = {}  # {symbol: report}
    
    # Errors and cost tracking
    errors: List[str] = []
    agent_costs: List[AgentCost] = []
    total_cost: float = 0.0
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### 11.3 Multi-Symbol Market Data Agent

```python
# app/agents/market_data_agent.py

class MarketDataAgent(BaseAgent):
    """
    Enhanced Market Data Agent with multi-symbol support
    
    Fetches market data for all symbols in state.symbols.
    Falls back to single symbol mode if state.symbol is set.
    """
    
    async def process(self, state: PipelineState) -> PipelineState:
        """Fetch market data for all symbols"""
        
        # Determine which symbols to fetch
        if state.symbols:
            # Multi-symbol mode (from Stock Picker Agent)
            symbols_to_fetch = state.symbols
            logger.info(f"Market Data: Multi-symbol mode - fetching {len(symbols_to_fetch)} symbols")
        elif state.symbol:
            # Single-symbol mode (backward compatibility)
            symbols_to_fetch = [state.symbol]
            logger.info(f"Market Data: Single-symbol mode - fetching {state.symbol}")
        else:
            raise InsufficientDataError("No symbols specified in state")
        
        timeframes = self.config.get("timeframes", ["5m"])
        
        # Fetch data for all symbols in parallel
        tasks = [
            self.fetch_symbol_data(symbol, timeframes)
            for symbol in symbols_to_fetch
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Store in state
        state.market_data_multi = {}
        state.timeframes_multi = {}
        
        for symbol, result in zip(symbols_to_fetch, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to fetch data for {symbol}: {result}")
                state.errors.append(f"market_data: Failed to fetch {symbol}")
                continue
            
            market_data, timeframe_data = result
            state.market_data_multi[symbol] = market_data
            state.timeframes_multi[symbol] = timeframe_data
        
        # Backward compatibility: If single symbol, also set state.market_data
        if len(symbols_to_fetch) == 1 and symbols_to_fetch[0] in state.market_data_multi:
            state.symbol = symbols_to_fetch[0]
            state.market_data = state.market_data_multi[symbols_to_fetch[0]]
            state.timeframes = state.timeframes_multi[symbols_to_fetch[0]]
        
        logger.info(
            f"Market Data: Successfully fetched data for "
            f"{len(state.market_data_multi)}/{len(symbols_to_fetch)} symbols"
        )
        
        # Remove symbols that failed data fetch from state.symbols
        state.symbols = list(state.market_data_multi.keys())
        
        return state
    
    async def fetch_symbol_data(
        self,
        symbol: str,
        timeframes: List[str]
    ) -> Tuple[MarketData, Dict[str, TimeframeData]]:
        """Fetch market data for a single symbol"""
        # Implementation (existing logic)
        pass
```

### 11.4 Multi-Symbol Bias/Strategy Agents

```python
# app/agents/bias_agent.py

class BiasAgent(BaseAgent):
    """
    Enhanced Bias Agent with multi-symbol support
    
    Analyzes bias for all symbols in state.market_data_multi.
    Filters symbols based on minimum bias score.
    """
    
    async def process(self, state: PipelineState) -> PipelineState:
        """Analyze bias for all symbols"""
        
        if not state.market_data_multi:
            raise InsufficientDataError("No market data available")
        
        logger.info(f"Bias Agent: Analyzing {len(state.market_data_multi)} symbols")
        
        # Analyze each symbol in parallel
        tasks = [
            self.analyze_symbol_bias(symbol, state.timeframes_multi[symbol])
            for symbol in state.market_data_multi.keys()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Store results
        state.bias_results = {}
        for symbol, result in zip(state.market_data_multi.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"Bias analysis failed for {symbol}: {result}")
                continue
            state.bias_results[symbol] = result
        
        # Filter symbols by minimum bias score
        min_bias_score = self.config.get("min_bias_score", 0.6)
        
        qualified_symbols = [
            symbol for symbol, bias in state.bias_results.items()
            if bias.bias_score >= min_bias_score
        ]
        
        logger.info(
            f"Bias Agent: {len(qualified_symbols)} of {len(state.bias_results)} "
            f"symbols passed bias filter (score >= {min_bias_score})"
        )
        
        # Update symbols list to only include qualified ones
        # This reduces cost for downstream agents
        state.symbols = qualified_symbols
        
        return state
    
    async def analyze_symbol_bias(
        self,
        symbol: str,
        timeframe_data: Dict[str, TimeframeData]
    ) -> BiasOutput:
        """Analyze bias for a single symbol"""
        # LLM call to analyze bias
        # (Existing implementation, but now called per symbol)
        pass
```

### 11.5 Pipeline Manager Agent (Coordinator)

**Purpose**: One manager per pipeline that coordinates execution, tracks budget, monitors positions, and handles interventions.

```python
# app/agents/pipeline_manager_agent.py

from typing import List, Dict, Tuple
from datetime import datetime
import asyncio

class PipelineManagerAgent(BaseAgent):
    """
    Pipeline Manager Agent (One per pipeline)
    
    Coordinates a single pipeline:
    - Tracks this pipeline's budget allocation
    - Monitors this pipeline's positions
    - Receives cost reports from pipeline agents
    - Commands Trade Manager when needed
    - Makes intervention decisions
    
    Auto-injected into every pipeline as first agent.
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="pipeline_manager_agent",
            name="Pipeline Manager Agent",
            description="Coordinates pipeline execution, tracks budget, monitors positions",
            category="system",
            version="1.0.0",
            icon="settings_applications",
            pricing_rate=0.0,  # FREE system agent
            is_free=True,
            is_system_agent=True,  # Hidden from UI
            requires_timeframes=[],
            config_schema=None
        )
    
    def __init__(self, agent_id: str, config: Dict):
        super().__init__(agent_id, config)
        
        # Pipeline context
        self.pipeline_id = None
        self.user_id = None
        self.execution_id = None
        
        # Budget tracking for THIS pipeline only
        self.budget_allocated = {"daily_limit": None, "monthly_limit": None}
        self.cumulative_cost = 0.0
        self.budget_exhausted = False
        
        # Position tracking for THIS pipeline only
        self.open_positions: List[Position] = []
        
        # Reference to Trade Manager (for commands)
        self.trade_manager_agent = None
    
    async def process(self, state: PipelineState) -> PipelineState:
        """
        Runs at START of pipeline
        
        1. Initializes manager for this execution
        2. Checks pipeline's budget allocation
        3. Blocks if insufficient budget
        """
        
        # Initialize
        self.pipeline_id = state.pipeline_id
        self.user_id = state.user_id
        self.execution_id = state.execution_id
        
        # Load pipeline's budget allocation
        pipeline = await get_pipeline(self.pipeline_id)
        self.budget_allocated = pipeline.budget_allocation or {}
        
        # Find Trade Manager in pipeline
        self.trade_manager_agent = await self.find_trade_manager_in_pipeline(pipeline)
        
        # Estimate cost
        estimated_cost = await self.estimate_pipeline_cost(state)
        
        logger.info(
            f"Pipeline Manager: Estimated cost ${estimated_cost:.4f} for pipeline "
            f"{self.pipeline_id}"
        )
        
        # Check pipeline's budget
        allowed, reason = self.check_budget(estimated_cost)
        
        if not allowed:
            logger.warning(f"Pipeline Manager: BLOCKED - {reason}")
            raise BudgetExceededException(
                f"Pipeline budget insufficient: {reason}\n"
                f"Remaining: ${self.get_remaining_budget():.2f}\n"
                f"Estimated cost: ${estimated_cost:.2f}"
            )
        
        # Store manager reference in state (so agents can talk to it)
        state.pipeline_manager = self
        state.budget_info = {
            "allocated_daily": self.budget_allocated.get("daily_limit"),
            "estimated_cost": estimated_cost,
            "cumulative_cost": 0.0
        }
        
        logger.info("Pipeline Manager: ✅ Budget check passed")
        
        return state
    
    def check_budget(self, estimated_cost: float) -> Tuple[bool, str]:
        """Check if pipeline has budget for this execution"""
        
        daily_spend = self.get_pipeline_daily_spend()
        daily_limit = self.budget_allocated.get("daily_limit")
        
        if not daily_limit:
            return (True, "No budget limits on this pipeline")
        
        remaining = daily_limit - daily_spend
        if estimated_cost > remaining:
            return (
                False,
                f"Daily allocation exhausted. Used ${daily_spend:.2f} of "
                f"${daily_limit:.2f}. Need ${estimated_cost:.2f} more."
            )
        
        return (True, "Within budget")
    
    async def report_cost(self, agent_type: str, cost: float, state: PipelineState):
        """
        Called by pipeline agents after execution
        
        Agents report their cost to Pipeline Manager
        """
        
        self.cumulative_cost += cost
        state.budget_info["cumulative_cost"] = self.cumulative_cost
        
        logger.info(
            f"Pipeline Manager: Cost from {agent_type}: ${cost:.4f}. "
            f"Cumulative: ${self.cumulative_cost:.4f}"
        )
        
        # Check if budget exhausted
        daily_spend = self.get_pipeline_daily_spend() + self.cumulative_cost
        daily_limit = self.budget_allocated.get("daily_limit")
        
        if daily_limit and daily_spend >= daily_limit:
            logger.critical(
                f"Pipeline Manager: ⛔ BUDGET EXHAUSTED! "
                f"${daily_spend:.2f} >= ${daily_limit:.2f}"
            )
            
            self.budget_exhausted = True
            
            # Close all THIS pipeline's positions
            await self.emergency_close_positions(
                reason="pipeline_budget_exhausted",
                state=state
            )
            
            raise BudgetExceededException(
                f"Pipeline budget exhausted. All positions closed."
            )
    
    async def emergency_close_positions(self, reason: str, state: PipelineState):
        """
        Emergency close all positions for THIS pipeline
        
        Sends command to Trade Manager agent
        """
        
        if not self.open_positions:
            logger.info("Pipeline Manager: No positions to close")
            return
        
        logger.warning(
            f"Pipeline Manager: Emergency closing {len(self.open_positions)} positions"
        )
        
        if not self.trade_manager_agent:
            logger.error("Pipeline Manager: No Trade Manager found!")
            return
        
        # Command Trade Manager to close positions
        close_command = {
            "type": "emergency_close",
            "from": "pipeline_manager",
            "positions": self.open_positions,
            "reason": reason,
            "priority": "critical"
        }
        
        # Trade Manager executes
        result = await self.trade_manager_agent.execute_command(close_command, state)
        
        # Log intervention
        await self.log_intervention(
            action="emergency_close_budget",
            reason=reason,
            positions_affected=len(self.open_positions),
            result=result,
            state=state
        )
        
        logger.info(
            f"Pipeline Manager: Closed {len(self.open_positions)} positions. "
            f"P&L: ${result.get('total_pnl', 0):.2f}"
        )
        
        self.open_positions = []
    
    async def register_position(self, position: Position):
        """Trade Manager registers positions with Pipeline Manager"""
        self.open_positions.append(position)
        logger.info(f"Pipeline Manager: Registered position {position.symbol}")
    
    async def unregister_position(self, position_id: str):
        """Trade Manager unregisters closed positions"""
        self.open_positions = [p for p in self.open_positions if p.id != position_id]
        logger.info(f"Pipeline Manager: Unregistered position {position_id}")
    
    # Helper methods
    def get_pipeline_daily_spend(self) -> float:
        """Get THIS pipeline's spend today (from database)"""
        # Query for today's executions for THIS pipeline only
        pass
    
    def get_remaining_budget(self) -> float:
        """Get remaining budget for THIS pipeline"""
        daily_spend = self.get_pipeline_daily_spend()
        daily_limit = self.budget_allocated.get("daily_limit", 0)
        return max(0, daily_limit - daily_spend)
    
    async def estimate_pipeline_cost(self, state: PipelineState) -> float:
        """Estimate cost for this pipeline execution"""
        # Call cost estimator
        pass
    
    async def find_trade_manager_in_pipeline(self, pipeline) -> BaseAgent:
        """Find Trade Manager agent in this pipeline"""
        # Look through pipeline agents
        pass
    
    async def log_intervention(self, action: str, reason: str, 
                               positions_affected: int, result: Dict, 
                               state: PipelineState):
        """Log intervention to manual_interventions table"""
        pass
```

### 11.6 Pipeline Orchestrator (Ultra-Thin)

```python
# app/orchestration/executor.py

async def execute_pipeline(pipeline_id: str, execution_id: str):
    """
    Ultra-thin orchestrator - just calls agents in sequence
    
    Pipeline Manager Agent (first agent) handles all budget logic.
    Other agents report costs to Pipeline Manager via state.pipeline_manager.
    """
    
    pipeline = await get_pipeline(pipeline_id)
    
    # Initialize state
    state = PipelineState(
        pipeline_id=pipeline_id,
        execution_id=execution_id,
        user_id=pipeline.user_id
    )
    
    try:
        # Execute agents (Pipeline Manager is first, auto-injected)
        for agent in pipeline.agents:
            logger.info(f"Executing: {agent.agent_type}")
            
            # Execute agent
            state = await agent.process(state)
            
            # If not Pipeline Manager, report cost
            if agent.agent_type != "pipeline_manager_agent" and state.pipeline_manager:
                agent_cost = calculate_agent_cost(agent, state)
                
                # Agent reports to Pipeline Manager
                await state.pipeline_manager.report_cost(
                    agent_type=agent.agent_type,
                    cost=agent_cost,
                    state=state
                )
                # Pipeline Manager will raise BudgetExceededException if exhausted
        
        # Pipeline completed successfully
        logger.info(f"Pipeline {pipeline_id} completed. Cost: ${state.budget_info['cumulative_cost']:.4f}")
        
    except BudgetExceededException as e:
        # Pipeline Manager blocked/stopped execution
        logger.warning(f"Pipeline stopped: {e}")
        await notify_user(state.user_id, "Pipeline Stopped", str(e))
        await pause_pipeline(pipeline_id, "budget_exhausted")
        
    except TriggerNotMetException:
        logger.info("Trigger not met, rescheduling")
        raise
        
    except Exception as e:
        logger.exception(f"Pipeline execution failed: {e}")
        raise
```

### 11.7 Inter-Agent Communication Examples

**Stock Picker Agent asks Pipeline Manager for budget approval**:

```python
class StockPickerAgent(BaseAgent):
    async def process(self, state: PipelineState) -> PipelineState:
        top_n = self.config.get("top_n", 10)
        estimated_cost = await self.estimate_multi_symbol_cost(top_n)
        
        # Ask Pipeline Manager
        if state.pipeline_manager:
            allowed, reason = state.pipeline_manager.check_budget(estimated_cost)
            
            if not allowed:
                raise BudgetExceededException(
                    f"Pipeline Manager blocked: {reason}"
                )
        
        # Approved - continue
        ...
```

**Bias Agent reports cost to Pipeline Manager**:

```python
class BiasAgent(BaseAgent):
    async def process(self, state: PipelineState) -> PipelineState:
        result = await self.analyze_bias(state)
        
        # Cost already reported by orchestrator after agent completes
        # (see execute_pipeline above)
        
        return state
```

**Trade Manager registers positions with Pipeline Manager**:

```python
class TradeManagerAgent(BaseAgent):
    async def process(self, state: PipelineState) -> PipelineState:
        for symbol, signal in state.strategy_signals.items():
            position = await self.execute_trade(signal, state)
            
            # Register with Pipeline Manager
            if state.pipeline_manager:
                await state.pipeline_manager.register_position(position)
        
        return state
    
    async def execute_command(self, command: Dict, state: PipelineState):
        """
        Execute command from Pipeline Manager
        
        Pipeline Manager sends emergency close commands here
        """
        if command["type"] == "emergency_close":
            logger.warning("Trade Manager: Executing emergency close")
            
            results = []
            for position in command["positions"]:
                result = await self.close_position_market(position, command["reason"])
                results.append(result)
                
                # Unregister with Pipeline Manager
                if state.pipeline_manager:
                    await state.pipeline_manager.unregister_position(position.id)
            
            return {
                "success": True,
                "positions_closed": len(results),
                "total_pnl": sum(r["pnl"] for r in results),
                "results": results
            }
```

---

## 12. Database Design

### 11.1 PostgreSQL Schema

#### Users Table
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    subscription_tier VARCHAR(50) DEFAULT 'free',
    status VARCHAR(50) DEFAULT 'active',
    budget_limit_daily DECIMAL(10, 2),
    budget_limit_monthly DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
```

#### Broker Connections Table
```sql
CREATE TABLE broker_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    broker_name VARCHAR(50) NOT NULL,  -- 'alpaca', 'ibkr'
    account_type VARCHAR(50),  -- 'paper', 'live'
    api_key_encrypted TEXT NOT NULL,
    api_secret_encrypted TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, broker_name, account_type)
);
```

#### Pipelines Table
```sql
CREATE TABLE pipelines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    symbol VARCHAR(20) NOT NULL,
    config JSONB NOT NULL,  -- Full pipeline configuration
    status VARCHAR(50) DEFAULT 'draft',  -- draft, active, paused, archived
    max_retries INTEGER DEFAULT 3,
    retry_delay_seconds INTEGER DEFAULT 60,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipelines_user_status ON pipelines(user_id, status);
CREATE INDEX idx_pipelines_config ON pipelines USING gin(config);
```

#### Pipeline Executions Table
```sql
CREATE TABLE pipeline_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id UUID REFERENCES pipelines(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL,  -- waiting_trigger, running, completed, failed
    current_agent VARCHAR(100),
    state JSONB NOT NULL,  -- Serialized PipelineState
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    duration_seconds INTEGER,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    total_cost DECIMAL(10, 4)
);

CREATE INDEX idx_executions_pipeline ON pipeline_executions(pipeline_id);
CREATE INDEX idx_executions_user_status ON pipeline_executions(user_id, status);
CREATE INDEX idx_executions_start_time ON pipeline_executions(start_time DESC);
```

#### Trades Table
```sql
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID REFERENCES pipeline_executions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    action VARCHAR(10) NOT NULL,  -- BUY, SELL
    quantity INTEGER NOT NULL,
    entry_price DECIMAL(10, 4),
    stop_loss DECIMAL(10, 4),
    target_1 DECIMAL(10, 4),
    target_2 DECIMAL(10, 4),
    filled_price DECIMAL(10, 4),
    slippage DECIMAL(10, 4),
    commission DECIMAL(10, 4),
    broker_order_id VARCHAR(255),
    status VARCHAR(50),  -- pending, filled, rejected, cancelled
    pnl DECIMAL(10, 2),  -- realized P&L when closed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    filled_at TIMESTAMP,
    closed_at TIMESTAMP
);

CREATE INDEX idx_trades_user_symbol ON trades(user_id, symbol);
CREATE INDEX idx_trades_execution ON trades(execution_id);
CREATE INDEX idx_trades_created_at ON trades(created_at DESC);
```

#### Reports Table
```sql
CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID REFERENCES pipeline_executions(id) ON DELETE CASCADE,
    trade_id UUID REFERENCES trades(id) ON DELETE SET NULL,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    report_type VARCHAR(50) DEFAULT 'trade_execution',
    summary TEXT,
    full_report JSONB NOT NULL,  -- Complete reasoning chain
    s3_url TEXT,  -- Detailed report in S3
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reports_execution ON reports(execution_id);
CREATE INDEX idx_reports_user_created ON reports(user_id, created_at DESC);
```

#### Cost Tracking Table
```sql
CREATE TABLE cost_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    execution_id UUID REFERENCES pipeline_executions(id) ON DELETE SET NULL,
    agent_name VARCHAR(100) NOT NULL,
    cost_type VARCHAR(50) NOT NULL,  -- 'llm_tokens', 'api_call', 'agent_rental'
    quantity INTEGER,  -- tokens or API calls
    unit_cost DECIMAL(10, 6),
    total_cost DECIMAL(10, 4),
    metadata JSONB,  -- model name, provider, etc.
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cost_user_timestamp ON cost_tracking(user_id, timestamp DESC);
CREATE INDEX idx_cost_execution ON cost_tracking(execution_id);
```

#### Agent Registry Table
```sql
CREATE TABLE agent_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    version VARCHAR(50) DEFAULT '1.0.0',
    input_schema JSONB NOT NULL,
    output_schema JSONB NOT NULL,
    pricing_rate DECIMAL(10, 4),  -- hourly rate, NULL for free agents
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_agent_registry_active ON agent_registry(is_active);
```

### 11.2 Redis Data Structures

**Pipeline State Cache**:
```
Key: pipeline:state:{execution_id}
Type: Hash
TTL: 24 hours
Data: Serialized PipelineState
```

**Active Pipeline Tracking**:
```
Key: user:active_pipelines:{user_id}
Type: Set
Data: Set of execution_ids
```

**Trigger Wait Queue**:
```
Key: trigger:waiting:{execution_id}
Type: Hash
Fields: {next_check_time, condition, retry_count}
```

**Cost Accumulator** (real-time tracking):
```
Key: cost:realtime:{execution_id}
Type: Hash
Fields: {tokens, api_calls, runtime}
TTL: 1 hour
```

---

## 11.8 Custom Strategy Agent (LLM-Generated User Strategies)

### Overview

The Custom Strategy Agent allows users to define their own trading strategies in plain English. The system uses LLM to generate Python code, performs multi-layered security review, requires admin approval (MVP), and executes in a sandboxed environment.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User Creates Strategy                   │
│  "Buy when 9-EMA crosses above 21-EMA, sell when it crosses │
│   back below. Only trade if volume > 1M shares."            │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │   LLM #1: Code Generator   │
         │   (GPT-4 / GPT-3.5-turbo)  │
         └─────────────┬─────────────┘
                       │
                       ▼
         ┌──────────────────────────────┐
         │   Generated Python Code      │
         │                              │
         │ # EMA Crossover Strategy     │
         │ fast_ema = indicators['ema_9']│
         │ slow_ema = indicators['ema_21']│
         │ volume = data['volume'][-1]  │
         │                              │
         │ if volume > 1_000_000:       │
         │   if fast_ema[-1] > slow_ema[-1] and \│
         │      fast_ema[-2] <= slow_ema[-2]:│
         │     signal = "BUY"           │
         │   elif fast_ema[-1] < slow_ema[-1] and \│
         │        fast_ema[-2] >= slow_ema[-2]:│
         │     signal = "SELL"          │
         │ else:                        │
         │   signal = "HOLD"            │
         └─────────────┬────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  Security Review (Multi-Layer) │
         │                           │
         │  Layer 1: LLM #2 Review   │
         │  Layer 2: Static Analysis │
         │  Layer 3: Sandbox Config  │
         └─────────────┬─────────────┘
                       │
                       ▼
                   Pass/Fail?
                       │
           ┌───────────┴───────────┐
           │                       │
          Pass                   Fail
           │                       │
           ▼                       ▼
  ┌────────────────┐      ┌──────────────┐
  │ PENDING_REVIEW │      │   REJECTED   │
  │ (Admin Queue)  │      │ (User Notified)│
  └───────┬────────┘      └──────────────┘
          │
    Admin Reviews
          │
    ┌─────┴─────┐
    │           │
  Approve     Reject
    │           │
    ▼           ▼
┌────────┐  ┌──────────┐
│ ACTIVE │  │ REJECTED │
└───┬────┘  └──────────┘
    │
    │ User adds to pipeline
    │
    ▼
┌──────────────────────┐
│  Sandboxed Execution │
│  - RestrictedPython  │
│  - 5 sec timeout     │
│  - 100MB memory      │
│  - No I/O access     │
└──────────────────────┘
```

### Database Schema

**custom_strategy_agents table**:

```sql
CREATE TABLE custom_strategy_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,  -- Plain English strategy description
    
    -- Generated code
    generated_code TEXT NOT NULL,
    code_hash VARCHAR(64) NOT NULL,  -- SHA256 of code for version tracking
    
    -- Security review results
    llm_security_review JSONB,  -- {approved, issues, risk_level, explanation}
    static_analysis_result JSONB,  -- {passed, issues}
    
    -- Status workflow
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
        -- DRAFT, PENDING_REVIEW, ACTIVE, REJECTED, ARCHIVED
    
    -- Admin approval
    reviewed_by UUID REFERENCES users(id),  -- Admin who reviewed
    reviewed_at TIMESTAMP,
    review_comments TEXT,
    
    -- Metadata
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMP,
    
    -- Usage tracking
    usage_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    
    -- Performance tracking
    total_trades INT DEFAULT 0,
    total_pnl DECIMAL(15, 2) DEFAULT 0.00,
    
    CONSTRAINT check_status CHECK (status IN ('DRAFT', 'PENDING_REVIEW', 'ACTIVE', 'REJECTED', 'ARCHIVED'))
);

CREATE INDEX idx_custom_agents_user ON custom_strategy_agents(user_id);
CREATE INDEX idx_custom_agents_status ON custom_strategy_agents(status);
CREATE INDEX idx_custom_agents_pending ON custom_strategy_agents(status) WHERE status = 'PENDING_REVIEW';
```

**custom_agent_execution_audit table**:

```sql
CREATE TABLE custom_agent_execution_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    custom_agent_id UUID NOT NULL REFERENCES custom_strategy_agents(id),
    user_id UUID NOT NULL REFERENCES users(id),
    pipeline_id UUID NOT NULL REFERENCES pipelines(id),
    execution_id UUID NOT NULL REFERENCES pipeline_executions(id),
    
    -- Execution details
    code_hash VARCHAR(64) NOT NULL,
    code_snippet TEXT,  -- First 500 chars for review
    execution_time_ms INT,
    memory_used_bytes BIGINT,
    
    -- Result
    result VARCHAR(10),  -- BUY, SELL, HOLD
    success BOOLEAN NOT NULL,
    error_message TEXT,
    
    -- Anomaly flags
    is_anomaly BOOLEAN DEFAULT FALSE,
    anomaly_reason TEXT,
    
    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_custom_agent ON custom_agent_execution_audit(custom_agent_id);
CREATE INDEX idx_audit_anomaly ON custom_agent_execution_audit(is_anomaly) WHERE is_anomaly = TRUE;
```

### Backend Implementation

**CustomStrategyAgent Class** (`app/agents/custom_strategy_agent.py`):

```python
from typing import Dict, Any
import hashlib
import ast
from RestrictedPython import compile_restricted, safe_builtins
import signal
from contextlib import contextmanager

from app.agents.base_agent import BaseAgent, AgentMetadata
from app.schemas.pipeline_state import PipelineState
from app.schemas.strategy import StrategyOutput
from app.services.llm_service import OpenAIService
from app.services.security_service import SecurityReviewService

class CustomStrategyAgent(BaseAgent):
    """
    User-defined strategy agent with LLM code generation and sandboxed execution
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="custom_strategy",
            name="Custom Strategy",
            description="Define your own strategy in plain English",
            category="analysis",
            version="1.0.0",
            icon="code",
            pricing_rate=0.20,  # Premium pricing (dual LLM calls)
            is_free=False,
            requires_timeframes=[],  # User specifies in description
            config_schema={
                "type": "object",
                "title": "Custom Strategy Configuration",
                "properties": {
                    "custom_agent_id": {
                        "type": "string",
                        "title": "Custom Agent ID",
                        "description": "ID of approved custom strategy agent",
                        "format": "uuid"
                    },
                    "strategy_description": {
                        "type": "string",
                        "title": "Strategy Description (Read-Only)",
                        "description": "Plain English description of strategy",
                        "readOnly": True
                    },
                    "generated_code": {
                        "type": "string",
                        "title": "Generated Code (Read-Only)",
                        "description": "Python code generated from description",
                        "format": "textarea",
                        "readOnly": True
                    }
                },
                "required": ["custom_agent_id"]
            }
        )
    
    async def process(self, state: PipelineState) -> PipelineState:
        """
        Execute custom user-defined strategy
        
        Steps:
        1. Load custom agent from database
        2. Verify it's approved (ACTIVE status)
        3. Execute in sandbox
        4. Audit log
        """
        
        custom_agent_id = self.config['custom_agent_id']
        
        # Load custom agent
        custom_agent = await self.load_custom_agent(custom_agent_id, state.user_id)
        
        if custom_agent.status != 'ACTIVE':
            raise AgentProcessingError(
                f"Custom agent not active. Status: {custom_agent.status}"
            )
        
        # Execute in sandbox
        try:
            result = await self.execute_in_sandbox(
                code=custom_agent.generated_code,
                context={
                    'data': state.market_data,
                    'indicators': self.calculate_indicators(state.market_data),
                    'timeframe_data': state.timeframes
                }
            )
            
            signal = result.get('signal', 'HOLD')
            confidence = result.get('confidence', 80)
            reasoning = result.get('reasoning', custom_agent.description[:200])
            
            # Update usage stats
            await self.update_usage_stats(custom_agent.id, success=True)
            
            # Audit log
            await self.audit_execution(
                custom_agent_id=custom_agent.id,
                state=state,
                code_hash=custom_agent.code_hash,
                result=signal,
                success=True,
                execution_time_ms=result.get('execution_time_ms', 0)
            )
            
            # Update state
            state.strategy_signal = StrategyOutput(
                action=signal,
                confidence=confidence,
                reasoning=f"Custom Strategy: {reasoning}",
                entry_price=state.market_data.close,
                # Additional fields can be set by custom code
            )
            
        except TimeoutError:
            logger.error(f"Custom agent {custom_agent_id} execution timeout")
            await self.update_usage_stats(custom_agent.id, success=False)
            raise AgentProcessingError("Strategy execution timeout (max 5 seconds)")
            
        except Exception as e:
            logger.exception(f"Custom agent {custom_agent_id} execution failed")
            await self.update_usage_stats(custom_agent.id, success=False)
            await self.audit_execution(
                custom_agent_id=custom_agent.id,
                state=state,
                code_hash=custom_agent.code_hash,
                result=None,
                success=False,
                error_message=str(e)
            )
            raise AgentProcessingError(f"Strategy execution failed: {str(e)}")
        
        return state
    
    async def execute_in_sandbox(self, code: str, context: Dict[str, Any]) -> Dict:
        """
        Execute user code in restricted sandbox
        
        Uses RestrictedPython for safety
        """
        import time
        start_time = time.time()
        
        # Compile with restrictions
        byte_code = compile_restricted(
            code,
            filename='<custom_strategy>',
            mode='exec'
        )
        
        # Create restricted globals
        restricted_globals = {
            '__builtins__': safe_builtins,
            # Math functions
            'abs': abs,
            'min': min,
            'max': max,
            'round': round,
            'len': len,
            'sum': sum,
            # Context
            'data': context['data'],
            'indicators': context['indicators'],
            'timeframe_data': context.get('timeframe_data', {}),
            # Required output variables
            'signal': 'HOLD',
            'confidence': 80,
            'reasoning': '',
        }
        
        # Execute with timeout
        with self.timeout(seconds=5):
            exec(byte_code, restricted_globals)
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        return {
            'signal': restricted_globals.get('signal', 'HOLD'),
            'confidence': restricted_globals.get('confidence', 80),
            'reasoning': restricted_globals.get('reasoning', ''),
            'execution_time_ms': execution_time_ms
        }
    
    @contextmanager
    def timeout(self, seconds: int):
        """Execution timeout context manager"""
        def handler(signum, frame):
            raise TimeoutError("Execution exceeded time limit")
        
        # Set alarm
        signal.signal(signal.SIGALRM, handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)  # Cancel alarm
    
    def calculate_indicators(self, market_data) -> Dict:
        """Pre-calculate common indicators for user code"""
        # This would use a technical indicators library
        # Return dict of indicator names -> values
        return {
            'ema_9': self.calc_ema(market_data.close, 9),
            'ema_21': self.calc_ema(market_data.close, 21),
            'rsi_14': self.calc_rsi(market_data.close, 14),
            'macd': self.calc_macd(market_data.close),
            # ... more indicators
        }
```

**Security Review Service** (`app/services/security_service.py`):

```python
class SecurityReviewService:
    """
    Multi-layered security review for custom code
    """
    
    async def review_code(self, code: str, description: str) -> SecurityReviewResult:
        """
        Perform comprehensive security review
        
        Returns: SecurityReviewResult with approval decision
        """
        
        # Layer 1: LLM Security Review
        llm_review = await self.llm_security_review(code, description)
        
        if llm_review.risk_level in ['high', 'critical']:
            return SecurityReviewResult(
                approved=False,
                reason=f"LLM identified {llm_review.risk_level} risk",
                llm_review=llm_review,
                static_analysis=None
            )
        
        # Layer 2: Static Analysis
        static_result = self.static_analysis(code)
        
        if not static_result.passed:
            return SecurityReviewResult(
                approved=False,
                reason=f"Static analysis failed: {static_result.reason}",
                llm_review=llm_review,
                static_analysis=static_result
            )
        
        # Both layers passed
        return SecurityReviewResult(
            approved=True,
            reason="Passed all security checks",
            llm_review=llm_review,
            static_analysis=static_result
        )
    
    async def llm_security_review(self, code: str, description: str) -> LLMSecurityReview:
        """LLM-based security analysis"""
        
        prompt = f"""
        You are a security expert reviewing trading strategy code for a sandboxed execution environment.
        
        Strategy Description: {description}
        
        Code to Review:
        ```python
        {code}
        ```
        
        Analyze for security issues:
        1. File system access (open, read, write, os.path)
        2. Network access (requests, urllib, socket, http)
        3. OS commands (os.system, subprocess, exec, eval)
        4. Dangerous imports (pickle, marshal, ctypes, sys, __import__)
        5. Resource exhaustion (infinite loops, recursion)
        6. Data exfiltration attempts
        7. Code injection (eval, exec, compile)
        
        Respond in JSON format:
        {{
            "approved": true/false,
            "risk_level": "none" | "low" | "medium" | "high" | "critical",
            "issues": ["list of specific issues found"],
            "explanation": "detailed explanation of decision"
        }}
        """
        
        response = await openai_service.call(prompt, model="gpt-4", response_format="json")
        return LLMSecurityReview(**json.loads(response))
    
    def static_analysis(self, code: str) -> StaticAnalysisResult:
        """Programmatic security checks using AST"""
        
        FORBIDDEN_IMPORTS = {
            'os', 'sys', 'subprocess', 'socket', 'urllib', 'requests',
            'http', 'pickle', 'marshal', 'ctypes', '__import__', 'importlib'
        }
        
        FORBIDDEN_BUILTINS = {
            'eval', 'exec', 'compile', '__import__', 'open',
            'input', 'raw_input', 'file', 'execfile'
        }
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return StaticAnalysisResult(
                passed=False,
                reason=f"Syntax error: {str(e)}"
            )
        
        # Check for forbidden imports
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
                if module and module.split('.')[0] in FORBIDDEN_IMPORTS:
                    return StaticAnalysisResult(
                        passed=False,
                        reason=f"Forbidden import: {module}"
                    )
            
            # Check for forbidden function calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_BUILTINS:
                    return StaticAnalysisResult(
                        passed=False,
                        reason=f"Forbidden function: {node.func.id}"
                    )
        
        return StaticAnalysisResult(passed=True)
```

**Admin Approval Workflow** (`app/api/v1/admin/custom_agents.py`):

```python
from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_current_admin_user

router = APIRouter(prefix="/api/v1/admin/custom-agents", tags=["admin"])

@router.get("/pending")
async def list_pending_agents(
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """List all custom agents pending review"""
    
    agents = await db.execute(
        """
        SELECT ca.*, u.email as user_email, u.name as user_name
        FROM custom_strategy_agents ca
        JOIN users u ON ca.user_id = u.id
        WHERE ca.status = 'PENDING_REVIEW'
        ORDER BY ca.created_at ASC
        """
    )
    
    return agents.fetchall()

@router.post("/{agent_id}/approve")
async def approve_custom_agent(
    agent_id: str,
    review_comments: str = None,
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Approve a custom strategy agent"""
    
    agent = await db.fetch_one(
        "SELECT * FROM custom_strategy_agents WHERE id = $1",
        agent_id
    )
    
    if not agent:
        raise HTTPException(404, "Agent not found")
    
    if agent.status != 'PENDING_REVIEW':
        raise HTTPException(400, f"Agent not pending review. Current status: {agent.status}")
    
    # Update status
    await db.execute(
        """
        UPDATE custom_strategy_agents
        SET status = 'ACTIVE',
            reviewed_by = $1,
            reviewed_at = NOW(),
            review_comments = $2,
            updated_at = NOW()
        WHERE id = $3
        """,
        admin_user.id, review_comments, agent_id
    )
    
    # Notify user
    await notification_service.send(
        user_id=agent.user_id,
        type="CUSTOM_AGENT_APPROVED",
        title="Custom Strategy Approved",
        message=f"Your custom strategy '{agent.name}' has been approved and is ready to use!",
        data={"agent_id": agent_id, "comments": review_comments}
    )
    
    return {"status": "approved"}

@router.post("/{agent_id}/reject")
async def reject_custom_agent(
    agent_id: str,
    review_comments: str,
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Reject a custom strategy agent"""
    
    agent = await db.fetch_one(
        "SELECT * FROM custom_strategy_agents WHERE id = $1",
        agent_id
    )
    
    if not agent:
        raise HTTPException(404, "Agent not found")
    
    # Update status
    await db.execute(
        """
        UPDATE custom_strategy_agents
        SET status = 'REJECTED',
            reviewed_by = $1,
            reviewed_at = NOW(),
            review_comments = $2,
            updated_at = NOW()
        WHERE id = $3
        """,
        admin_user.id, review_comments, agent_id
    )
    
    # Notify user
    await notification_service.send(
        user_id=agent.user_id,
        type="CUSTOM_AGENT_REJECTED",
        title="Custom Strategy Needs Revision",
        message=f"Your custom strategy '{agent.name}' needs revision. Reason: {review_comments}",
        data={"agent_id": agent_id, "comments": review_comments}
    )
    
    return {"status": "rejected"}
```

### Frontend Implementation

**Custom Agent Creation Form** (`custom-agent-form.component.html`):

```html
<form [formGroup]="customAgentForm" (ngSubmit)="createAgent()">
  <mat-card>
    <mat-card-header>
      <mat-card-title>Create Custom Strategy</mat-card-title>
      <mat-card-subtitle>Describe your strategy in plain English</mat-card-subtitle>
    </mat-card-header>

    <mat-card-content>
      <!-- Agent Name -->
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Strategy Name</mat-label>
        <input matInput formControlName="name" placeholder="My EMA Crossover Strategy">
      </mat-form-field>

      <!-- Strategy Description -->
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Strategy Description</mat-label>
        <textarea 
          matInput 
          formControlName="description" 
          rows="8"
          placeholder="Describe your strategy... 

Example: Buy when the 9-period EMA crosses above the 21-period EMA on the 5-minute chart. Sell when it crosses back below. Only trade if volume is above 1 million shares.">
        </textarea>
        <mat-hint>Be as specific as possible. Include entry rules, exit rules, and any conditions.</mat-hint>
      </mat-form-field>

      <!-- Generate Code Button -->
      <button 
        mat-raised-button 
        color="primary" 
        type="button"
        (click)="generateCode()"
        [disabled]="generating || !customAgentForm.get('description').value">
        <mat-icon *ngIf="generating">hourglass_empty</mat-icon>
        <mat-icon *ngIf="!generating">code</mat-icon>
        {{ generating ? 'Generating Code...' : 'Generate Strategy Code' }}
      </button>

      <!-- Generated Code Display -->
      <div *ngIf="generatedCode" class="code-preview">
        <h3>Generated Code</h3>
        <mat-card class="code-card">
          <mat-card-content>
            <pre><code [highlight]="generatedCode" [languages]="['python']"></code></pre>
          </mat-card-content>
        </mat-card>

        <!-- Security Review Results -->
        <mat-card *ngIf="securityReview" class="security-review">
          <mat-card-header>
            <mat-icon [color]="securityReview.approved ? 'primary' : 'warn'">
              {{ securityReview.approved ? 'verified' : 'warning' }}
            </mat-icon>
            <mat-card-title>
              Security Review: {{ securityReview.approved ? 'Passed' : 'Failed' }}
            </mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p>Risk Level: <strong>{{ securityReview.risk_level }}</strong></p>
            <p>{{ securityReview.explanation }}</p>
            <div *ngIf="securityReview.issues.length > 0">
              <p><strong>Issues Found:</strong></p>
              <ul>
                <li *ngFor="let issue of securityReview.issues">{{ issue }}</li>
              </ul>
            </div>
          </mat-card-content>
        </mat-card>

        <!-- Test in Simulation Button -->
        <button 
          mat-raised-button 
          color="accent"
          type="button"
          (click)="testInSimulation()"
          [disabled]="!securityReview?.approved">
          <mat-icon>science</mat-icon>
          Test in Simulation
        </button>
      </div>

      <!-- Approval Notice -->
      <mat-card *ngIf="generatedCode && securityReview?.approved" class="approval-notice">
        <mat-card-content>
          <mat-icon color="primary">info</mat-icon>
          <p>
            <strong>Manual Approval Required</strong><br>
            Your custom strategy will be reviewed by our team before you can use it in a pipeline.
            This typically takes 24-48 hours. You'll receive an email notification once it's approved.
          </p>
        </mat-card-content>
      </mat-card>

    </mat-card-content>

    <mat-card-actions>
      <button 
        mat-raised-button 
        color="primary" 
        type="submit"
        [disabled]="!customAgentForm.valid || !securityReview?.approved">
        Submit for Review
      </button>
      <button mat-button type="button" (click)="cancel()">
        Cancel
      </button>
    </mat-card-actions>
  </mat-card>
</form>
```

### Key Safety Features

1. **Multi-Layered Security**:
   - LLM security review (GPT-4)
   - Static code analysis (AST parsing)
   - Sandboxed execution (RestrictedPython)
   - Resource limits (time, memory)

2. **Admin Approval Workflow** (MVP):
   - All custom agents reviewed manually
   - Admin can test before approving
   - User notified of approval/rejection
   - Comments provided for rejected agents

3. **Audit Trail**:
   - Every execution logged
   - Code hash tracked
   - Performance metrics collected
   - Anomaly detection

4. **Progressive Enhancement** (Future):
   - Transition to AI-only approval
   - Confidence thresholds
   - Continuous learning from approvals
   - Community library and marketplace

---

## 12. Frontend Architecture

### 12.1 Angular Module Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── core/
│   │   │   ├── auth/
│   │   │   │   ├── auth.service.ts
│   │   │   │   ├── auth.guard.ts
│   │   │   │   └── jwt.interceptor.ts
│   │   │   ├── services/
│   │   │   │   ├── api.service.ts
│   │   │   │   ├── websocket.service.ts
│   │   │   │   └── notification.service.ts
│   │   │   └── models/
│   │   │       ├── pipeline.model.ts
│   │   │       ├── agent.model.ts
│   │   │       └── execution.model.ts
│   │   │
│   │   ├── shared/
│   │   │   ├── components/
│   │   │   ├── pipes/
│   │   │   └── directives/
│   │   │
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   │   ├── login/
│   │   │   │   └── register/
│   │   │   │
│   │   │   ├── dashboard/
│   │   │   │   ├── dashboard.component.ts
│   │   │   │   ├── dashboard.component.html
│   │   │   │   └── dashboard.component.scss
│   │   │   │
│   │   │   ├── pipeline-builder/
│   │   │   │   ├── pipeline-builder.component.ts
│   │   │   │   ├── pipeline-builder.component.html
│   │   │   │   ├── agent-palette/
│   │   │   │   ├── canvas/
│   │   │   │   └── config-panel/
│   │   │   │
│   │   │   ├── monitoring/
│   │   │   │   ├── execution-list/
│   │   │   │   ├── execution-detail/
│   │   │   │   └── real-time-logs/
│   │   │   │
│   │   │   ├── reports/
│   │   │   │   ├── report-list/
│   │   │   │   └── report-viewer/
│   │   │   │
│   │   │   ├── billing/
│   │   │   │   ├── cost-dashboard/
│   │   │   │   └── usage-history/
│   │   │   │
│   │   │   └── settings/
│   │   │       ├── profile/
│   │   │       └── broker-connections/
│   │   │
│   │   └── app-routing.module.ts
│   │
│   ├── assets/
│   ├── environments/
│   └── styles/
```

### 12.2 Key Frontend Components

**Pipeline Builder**
- Library: Consider Angular-based flow library or integrate with ReactFlow via wrapper
- Features: Drag-drop agents, connect nodes, validate connections, configure agents
- State Management: NgRx or RxJS BehaviorSubjects

**Real-time Monitoring**
- WebSocket connection to backend
- Display current agent, progress, logs
- Update dashboard on state changes

**Positions Dashboard** (NEW)
- Real-time view of all open positions
- Display: Symbol, Side (LONG/SHORT), Quantity, Entry Price, Current Price
- Show unrealized P&L (live updates)
- Display stop loss and target levels
- Show which pipeline created position
- Emergency close button per position (with confirmation)
- Emergency close all button
- Auto-refresh every 5-10 seconds or WebSocket updates
- Color coding: Green (profit), Red (loss), Yellow (at risk near stop)

**Cost Dashboard**
- Real-time cost display during execution
- Historical cost charts (Chart.js / ngx-charts)
- Budget alerts

---

## 12.3 Performance Analytics Dashboard

### Overview

The Performance Analytics Dashboard provides comprehensive insights into pipeline trading performance, helping users understand profitability, identify patterns, and optimize their strategies.

### Frontend Components

**Component Structure**:
```
frontend/src/app/features/analytics/
├── performance-dashboard/
│   ├── performance-dashboard.component.ts
│   ├── performance-dashboard.component.html
│   ├── performance-dashboard.component.scss
│   ├── performance-dashboard.component.spec.ts
│   └── components/
│       ├── metrics-card/
│       │   ├── metrics-card.component.ts
│       │   ├── metrics-card.component.html
│       │   └── metrics-card.component.scss
│       ├── equity-curve-chart/
│       │   ├── equity-curve-chart.component.ts
│       │   ├── equity-curve-chart.component.html
│       │   └── equity-curve-chart.component.scss
│       ├── breakdown-panel/
│       │   ├── breakdown-panel.component.ts
│       │   ├── breakdown-panel.component.html
│       │   └── breakdown-panel.component.scss
│       └── pipeline-comparison/
│           ├── pipeline-comparison.component.ts
│           ├── pipeline-comparison.component.html
│           └── pipeline-comparison.component.scss
├── services/
│   └── analytics.service.ts
└── models/
    └── performance.model.ts
```

**TypeScript Models** (`performance.model.ts`):

```typescript
export interface PerformanceMetrics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  breakeven_trades: number;
  win_rate: number;
  
  total_pnl: number;
  avg_win: number;
  avg_loss: number;
  win_loss_ratio: number;
  
  largest_win: TradeDetail | null;
  largest_loss: TradeDetail | null;
  
  avg_hold_time_hours: number;
  
  sharpe_ratio: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  profit_factor: number;
  
  total_cost: number;
  net_pnl: number;
  roi: number;
}

export interface TradeDetail {
  symbol: string;
  pnl: number;
  date: string;
  trade_id: string;
}

export interface SymbolPerformance {
  total_pnl: number;
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
}

export interface TimePerformance {
  total_pnl: number;
  trades: number;
  wins: number;
  losses: number;
}

export interface EquityCurvePoint {
  date: string;
  cumulative_pnl: number;
  trade_pnl: number;
  symbol: string;
}

export interface PipelinePerformance {
  pipeline_id: string;
  period_start: string;
  period_end: string;
  metrics: PerformanceMetrics;
  by_symbol: Record<string, SymbolPerformance>;
  by_day_of_week: Record<string, TimePerformance>;
  by_time_of_day: Record<string, TimePerformance>;
  equity_curve: EquityCurvePoint[];
}

export interface PipelineComparison {
  [pipelineId: string]: {
    name: string;
    performance: PipelinePerformance;
  };
}
```

**Analytics Service** (`analytics.service.ts`):

```typescript
import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '@environments/environment';
import { PipelinePerformance, PipelineComparison } from '../models/performance.model';

@Injectable({
  providedIn: 'root'
})
export class AnalyticsService {
  private baseUrl = `${environment.apiUrl}/api/v1/analytics`;

  constructor(private http: HttpClient) {}

  getPipelinePerformance(
    pipelineId: string,
    startDate?: string,
    endDate?: string
  ): Observable<PipelinePerformance> {
    let params = new HttpParams();
    if (startDate) params = params.set('start_date', startDate);
    if (endDate) params = params.set('end_date', endDate);

    return this.http.get<PipelinePerformance>(
      `${this.baseUrl}/pipelines/${pipelineId}/performance`,
      { params }
    );
  }

  comparePipelines(
    pipelineIds: string[],
    startDate?: string,
    endDate?: string
  ): Observable<PipelineComparison> {
    let params = new HttpParams();
    pipelineIds.forEach(id => {
      params = params.append('pipeline_ids', id);
    });
    if (startDate) params = params.set('start_date', startDate);
    if (endDate) params = params.set('end_date', endDate);

    return this.http.get<PipelineComparison>(
      `${this.baseUrl}/pipelines/compare`,
      { params }
    );
  }

  getUserPerformance(
    startDate?: string,
    endDate?: string
  ): Observable<any> {
    let params = new HttpParams();
    if (startDate) params = params.set('start_date', startDate);
    if (endDate) params = params.set('end_date', endDate);

    return this.http.get(`${this.baseUrl}/user/performance`, { params });
  }
}
```

**Performance Dashboard Component** (`performance-dashboard.component.ts`):

```typescript
import { Component, OnInit, OnDestroy } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { Subject, takeUntil } from 'rxjs';
import { AnalyticsService } from '../../services/analytics.service';
import { PipelinePerformance } from '../../models/performance.model';

@Component({
  selector: 'app-performance-dashboard',
  templateUrl: './performance-dashboard.component.html',
  styleUrls: ['./performance-dashboard.component.scss']
})
export class PerformanceDashboardComponent implements OnInit, OnDestroy {
  private destroy$ = new Subject<void>();
  
  pipelineId: string;
  performance: PipelinePerformance | null = null;
  selectedPeriod: string = '30d';
  loading = false;
  error: string | null = null;

  // Period options
  periodOptions = [
    { value: '7d', label: '7 Days' },
    { value: '30d', label: '30 Days' },
    { value: '90d', label: '90 Days' },
    { value: 'all', label: 'All Time' }
  ];

  constructor(
    private route: ActivatedRoute,
    private analyticsService: AnalyticsService
  ) {}

  ngOnInit(): void {
    this.pipelineId = this.route.snapshot.paramMap.get('id')!;
    this.loadPerformance();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadPerformance(): void {
    this.loading = true;
    this.error = null;

    const { startDate, endDate } = this.getDateRange(this.selectedPeriod);

    this.analyticsService
      .getPipelinePerformance(this.pipelineId, startDate, endDate)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (data) => {
          this.performance = data;
          this.loading = false;
        },
        error: (err) => {
          this.error = 'Failed to load performance data';
          this.loading = false;
          console.error(err);
        }
      });
  }

  onPeriodChange(period: string): void {
    this.selectedPeriod = period;
    this.loadPerformance();
  }

  getDateRange(period: string): { startDate?: string; endDate?: string } {
    const now = new Date();
    const endDate = now.toISOString();
    let startDate: string | undefined;

    switch (period) {
      case '7d':
        startDate = new Date(now.setDate(now.getDate() - 7)).toISOString();
        break;
      case '30d':
        startDate = new Date(now.setDate(now.getDate() - 30)).toISOString();
        break;
      case '90d':
        startDate = new Date(now.setDate(now.getDate() - 90)).toISOString();
        break;
      case 'all':
        startDate = undefined;
        break;
    }

    return { startDate, endDate };
  }

  exportReport(): void {
    // TODO: Implement export functionality
    console.log('Exporting report...');
  }

  getSymbolsArray(): Array<{ symbol: string; data: any }> {
    if (!this.performance) return [];
    return Object.entries(this.performance.by_symbol).map(([symbol, data]) => ({
      symbol,
      data
    }));
  }

  getDaysArray(): Array<{ day: string; data: any }> {
    if (!this.performance) return [];
    return Object.entries(this.performance.by_day_of_week).map(([day, data]) => ({
      day,
      data
    }));
  }

  getTimesArray(): Array<{ time: string; data: any }> {
    if (!this.performance) return [];
    return Object.entries(this.performance.by_time_of_day).map(([time, data]) => ({
      time,
      data
    }));
  }

  formatCurrency(value: number): string {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(value);
  }

  formatPercent(value: number): string {
    return `${value.toFixed(2)}%`;
  }
}
```

**Performance Dashboard Template** (`performance-dashboard.component.html`):

```html
<div class="performance-dashboard">
  <!-- Header -->
  <div class="dashboard-header">
    <h1>Performance Analytics</h1>
    
    <div class="header-controls">
      <!-- Period Selector -->
      <mat-button-toggle-group
        [(value)]="selectedPeriod"
        (change)="onPeriodChange($event.value)">
        <mat-button-toggle *ngFor="let option of periodOptions" [value]="option.value">
          {{ option.label }}
        </mat-button-toggle>
      </mat-button-toggle-group>

      <button mat-raised-button color="primary" (click)="exportReport()">
        <mat-icon>file_download</mat-icon>
        Export Report
      </button>
    </div>
  </div>

  <!-- Loading State -->
  <div *ngIf="loading" class="loading-container">
    <mat-spinner></mat-spinner>
  </div>

  <!-- Error State -->
  <div *ngIf="error" class="error-container">
    <mat-icon color="warn">error</mat-icon>
    <p>{{ error }}</p>
    <button mat-raised-button (click)="loadPerformance()">Retry</button>
  </div>

  <!-- Performance Content -->
  <div *ngIf="!loading && !error && performance" class="performance-content">
    
    <!-- Key Metrics Cards -->
    <div class="metrics-grid">
      <app-metrics-card
        title="Total P&L"
        [value]="formatCurrency(performance.metrics.total_pnl)"
        [trend]="performance.metrics.total_pnl > 0 ? 'up' : 'down'"
        icon="trending_up">
      </app-metrics-card>

      <app-metrics-card
        title="Win Rate"
        [value]="formatPercent(performance.metrics.win_rate)"
        [subtitle]="performance.metrics.winning_trades + 'W / ' + performance.metrics.losing_trades + 'L'"
        icon="pie_chart">
      </app-metrics-card>

      <app-metrics-card
        title="Total Trades"
        [value]="performance.metrics.total_trades.toString()"
        icon="receipt_long">
      </app-metrics-card>

      <app-metrics-card
        title="Win/Loss Ratio"
        [value]="performance.metrics.win_loss_ratio.toFixed(2)"
        icon="balance">
      </app-metrics-card>

      <app-metrics-card
        title="Sharpe Ratio"
        [value]="performance.metrics.sharpe_ratio.toFixed(2)"
        [subtitle]="'Risk-adjusted return'"
        icon="speed">
      </app-metrics-card>

      <app-metrics-card
        title="Max Drawdown"
        [value]="formatCurrency(performance.metrics.max_drawdown)"
        [subtitle]="'(' + formatPercent(performance.metrics.max_drawdown_pct) + ')'"
        [trend]="'down'"
        icon="trending_down">
      </app-metrics-card>

      <app-metrics-card
        title="Net P&L"
        [value]="formatCurrency(performance.metrics.net_pnl)"
        [subtitle]="'After ' + formatCurrency(performance.metrics.total_cost) + ' costs'"
        [trend]="performance.metrics.net_pnl > 0 ? 'up' : 'down'"
        icon="account_balance">
      </app-metrics-card>

      <app-metrics-card
        title="ROI"
        [value]="performance.metrics.roi.toFixed(2) + 'x'"
        [subtitle]="'Return on investment'"
        icon="insights">
      </app-metrics-card>
    </div>

    <!-- Equity Curve Chart -->
    <mat-card class="equity-curve-card">
      <mat-card-header>
        <mat-card-title>Equity Curve</mat-card-title>
        <mat-card-subtitle>Cumulative P&L Over Time</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <app-equity-curve-chart
          [data]="performance.equity_curve">
        </app-equity-curve-chart>
      </mat-card-content>
    </mat-card>

    <!-- Breakdown Panels -->
    <div class="breakdown-grid">
      <!-- By Symbol -->
      <mat-card class="breakdown-card">
        <mat-card-header>
          <mat-card-title>Performance by Symbol</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <app-breakdown-panel
            [data]="getSymbolsArray()"
            type="symbol">
          </app-breakdown-panel>
        </mat-card-content>
      </mat-card>

      <!-- By Day of Week -->
      <mat-card class="breakdown-card">
        <mat-card-header>
          <mat-card-title>Performance by Day</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <app-breakdown-panel
            [data]="getDaysArray()"
            type="day">
          </app-breakdown-panel>
        </mat-card-content>
      </mat-card>

      <!-- By Time of Day -->
      <mat-card class="breakdown-card">
        <mat-card-header>
          <mat-card-title>Performance by Time</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <app-breakdown-panel
            [data]="getTimesArray()"
            type="time">
          </app-breakdown-panel>
        </mat-card-content>
      </mat-card>
    </div>

    <!-- Best/Worst Trades -->
    <div class="trades-highlight">
      <mat-card class="trade-card best-trade">
        <mat-card-header>
          <mat-card-title>Largest Win</mat-card-title>
        </mat-card-header>
        <mat-card-content *ngIf="performance.metrics.largest_win">
          <div class="trade-details">
            <span class="symbol">{{ performance.metrics.largest_win.symbol }}</span>
            <span class="pnl positive">{{ formatCurrency(performance.metrics.largest_win.pnl) }}</span>
            <span class="date">{{ performance.metrics.largest_win.date | date }}</span>
          </div>
        </mat-card-content>
      </mat-card>

      <mat-card class="trade-card worst-trade">
        <mat-card-header>
          <mat-card-title>Largest Loss</mat-card-title>
        </mat-card-header>
        <mat-card-content *ngIf="performance.metrics.largest_loss">
          <div class="trade-details">
            <span class="symbol">{{ performance.metrics.largest_loss.symbol }}</span>
            <span class="pnl negative">{{ formatCurrency(performance.metrics.largest_loss.pnl) }}</span>
            <span class="date">{{ performance.metrics.largest_loss.date | date }}</span>
          </div>
        </mat-card-content>
      </mat-card>
    </div>
  </div>
</div>
```

### Backend Implementation

**Performance Analytics Service** (`app/services/performance_analytics.py`):

```python
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.trade import Trade
from app.models.cost_tracking import CostTracking
from app.schemas.performance import PipelinePerformance, PerformanceMetrics

class PerformanceAnalytics:
    """Calculate performance metrics for pipelines"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def get_pipeline_performance(
        self,
        pipeline_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> PipelinePerformance:
        """Calculate comprehensive performance metrics"""
        
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        # Get all closed trades for this pipeline in the period
        trades = self.db.query(Trade).filter(
            and_(
                Trade.pipeline_id == pipeline_id,
                Trade.status == "CLOSED",
                Trade.close_time >= start_date,
                Trade.close_time <= end_date
            )
        ).all()
        
        if not trades:
            return PipelinePerformance(
                pipeline_id=pipeline_id,
                period_start=start_date,
                period_end=end_date,
                metrics=PerformanceMetrics(),
                message="No trades in this period"
            )
        
        # Calculate metrics
        metrics = self._calculate_metrics(trades)
        
        # Get cost data
        total_cost = await self._get_total_cost(pipeline_id, start_date, end_date)
        metrics["total_cost"] = total_cost
        metrics["net_pnl"] = metrics["total_pnl"] - total_cost
        metrics["roi"] = (metrics["total_pnl"] / total_cost) if total_cost > 0 else 0
        
        # Calculate breakdowns
        by_symbol = self._analyze_by_symbol(trades)
        by_day_of_week = self._analyze_by_day_of_week(trades)
        by_time_of_day = self._analyze_by_time_of_day(trades)
        equity_curve = self._calculate_equity_curve(trades)
        
        return PipelinePerformance(
            pipeline_id=pipeline_id,
            period_start=start_date,
            period_end=end_date,
            metrics=metrics,
            by_symbol=by_symbol,
            by_day_of_week=by_day_of_week,
            by_time_of_day=by_time_of_day,
            equity_curve=equity_curve
        )
    
    def _calculate_metrics(self, trades: List[Trade]) -> Dict:
        """Calculate core performance metrics"""
        
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl < 0]
        breakeven_trades = [t for t in trades if t.pnl == 0]
        
        metrics = {
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "breakeven_trades": len(breakeven_trades),
            "win_rate": (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        }
        
        # P&L metrics
        total_pnl = sum(t.pnl for t in trades)
        winning_pnl = sum(t.pnl for t in winning_trades)
        losing_pnl = sum(t.pnl for t in losing_trades)
        
        metrics["total_pnl"] = round(total_pnl, 2)
        metrics["avg_win"] = round(winning_pnl / len(winning_trades), 2) if winning_trades else 0
        metrics["avg_loss"] = round(losing_pnl / len(losing_trades), 2) if losing_trades else 0
        metrics["win_loss_ratio"] = abs(metrics["avg_win"] / metrics["avg_loss"]) if metrics["avg_loss"] != 0 else float('inf')
        
        # Best/Worst
        metrics["largest_win"] = max(trades, key=lambda t: t.pnl) if trades else None
        metrics["largest_loss"] = min(trades, key=lambda t: t.pnl) if trades else None
        
        # Hold time
        hold_times = [(t.close_time - t.open_time).total_seconds() / 3600 
                      for t in trades if t.close_time]
        metrics["avg_hold_time_hours"] = round(np.mean(hold_times), 2) if hold_times else 0
        
        # Advanced metrics
        metrics["sharpe_ratio"] = self._calculate_sharpe_ratio(trades)
        drawdown_amt, drawdown_pct = self._calculate_max_drawdown(trades)
        metrics["max_drawdown"] = drawdown_amt
        metrics["max_drawdown_pct"] = drawdown_pct
        metrics["profit_factor"] = abs(winning_pnl / losing_pnl) if losing_pnl != 0 else float('inf')
        
        return metrics
    
    def _calculate_sharpe_ratio(self, trades: List[Trade]) -> float:
        """Calculate Sharpe Ratio"""
        if len(trades) < 2:
            return 0.0
        
        returns = [t.pnl for t in trades]
        avg_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0.0
        
        # Annualize (assuming ~252 trading days)
        sharpe = (avg_return / std_return) * np.sqrt(252)
        return round(sharpe, 2)
    
    def _calculate_max_drawdown(self, trades: List[Trade]) -> Tuple[float, float]:
        """Calculate maximum drawdown"""
        sorted_trades = sorted(trades, key=lambda t: t.close_time or t.open_time)
        
        cumulative_pnl = []
        total = 0.0
        for trade in sorted_trades:
            total += trade.pnl
            cumulative_pnl.append(total)
        
        peak = cumulative_pnl[0]
        max_dd = 0.0
        max_dd_pct = 0.0
        
        for pnl in cumulative_pnl:
            if pnl > peak:
                peak = pnl
            
            drawdown = peak - pnl
            if drawdown > max_dd:
                max_dd = drawdown
                max_dd_pct = (drawdown / peak * 100) if peak > 0 else 0.0
        
        return (round(max_dd, 2), round(max_dd_pct, 2))
    
    def _analyze_by_symbol(self, trades: List[Trade]) -> Dict:
        """Analyze performance by symbol"""
        by_symbol = {}
        
        for trade in trades:
            symbol = trade.symbol
            if symbol not in by_symbol:
                by_symbol[symbol] = {
                    "total_pnl": 0.0,
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "win_rate": 0.0
                }
            
            by_symbol[symbol]["total_pnl"] += trade.pnl
            by_symbol[symbol]["trades"] += 1
            
            if trade.pnl > 0:
                by_symbol[symbol]["wins"] += 1
            elif trade.pnl < 0:
                by_symbol[symbol]["losses"] += 1
        
        # Calculate win rate and round
        for symbol, stats in by_symbol.items():
            if stats["trades"] > 0:
                stats["win_rate"] = round((stats["wins"] / stats["trades"]) * 100, 2)
            stats["total_pnl"] = round(stats["total_pnl"], 2)
        
        # Sort by P&L descending
        return dict(sorted(by_symbol.items(), key=lambda x: x[1]["total_pnl"], reverse=True))
    
    def _analyze_by_day_of_week(self, trades: List[Trade]) -> Dict:
        """Analyze performance by day of week"""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        by_day = {day: {"total_pnl": 0.0, "trades": 0, "wins": 0, "losses": 0} for day in days}
        
        for trade in trades:
            day_name = trade.open_time.strftime("%A")
            if day_name in by_day:
                by_day[day_name]["total_pnl"] += trade.pnl
                by_day[day_name]["trades"] += 1
                if trade.pnl > 0:
                    by_day[day_name]["wins"] += 1
                elif trade.pnl < 0:
                    by_day[day_name]["losses"] += 1
        
        # Round P&L
        for day in by_day:
            by_day[day]["total_pnl"] = round(by_day[day]["total_pnl"], 2)
        
        return by_day
    
    def _analyze_by_time_of_day(self, trades: List[Trade]) -> Dict:
        """Analyze performance by time of day"""
        time_buckets = {
            "9:30-11:00": {"total_pnl": 0.0, "trades": 0, "wins": 0, "losses": 0},
            "11:00-13:00": {"total_pnl": 0.0, "trades": 0, "wins": 0, "losses": 0},
            "13:00-15:00": {"total_pnl": 0.0, "trades": 0, "wins": 0, "losses": 0},
            "15:00-16:00": {"total_pnl": 0.0, "trades": 0, "wins": 0, "losses": 0},
        }
        
        for trade in trades:
            hour = trade.open_time.hour
            minute = trade.open_time.minute
            time_decimal = hour + minute / 60.0
            
            if 9.5 <= time_decimal < 11.0:
                bucket = "9:30-11:00"
            elif 11.0 <= time_decimal < 13.0:
                bucket = "11:00-13:00"
            elif 13.0 <= time_decimal < 15.0:
                bucket = "13:00-15:00"
            elif 15.0 <= time_decimal < 16.0:
                bucket = "15:00-16:00"
            else:
                continue
            
            time_buckets[bucket]["total_pnl"] += trade.pnl
            time_buckets[bucket]["trades"] += 1
            if trade.pnl > 0:
                time_buckets[bucket]["wins"] += 1
            elif trade.pnl < 0:
                time_buckets[bucket]["losses"] += 1
        
        # Round P&L
        for bucket in time_buckets:
            time_buckets[bucket]["total_pnl"] = round(time_buckets[bucket]["total_pnl"], 2)
        
        return time_buckets
    
    def _calculate_equity_curve(self, trades: List[Trade]) -> List[Dict]:
        """Calculate equity curve over time"""
        sorted_trades = sorted(trades, key=lambda t: t.close_time or t.open_time)
        
        equity_curve = []
        cumulative_pnl = 0.0
        
        for trade in sorted_trades:
            cumulative_pnl += trade.pnl
            equity_curve.append({
                "date": (trade.close_time or trade.open_time).isoformat(),
                "cumulative_pnl": round(cumulative_pnl, 2),
                "trade_pnl": round(trade.pnl, 2),
                "symbol": trade.symbol
            })
        
        return equity_curve
    
    async def _get_total_cost(
        self,
        pipeline_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> float:
        """Get total cost for pipeline in period"""
        result = self.db.query(
            func.sum(CostTracking.total_cost)
        ).filter(
            and_(
                CostTracking.pipeline_id == pipeline_id,
                CostTracking.timestamp >= start_date,
                CostTracking.timestamp <= end_date
            )
        ).scalar()
        
        return round(result or 0.0, 2)
```

**API Endpoints** (`app/api/v1/analytics.py`):

```python
from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.services.performance_analytics import PerformanceAnalytics
from app.schemas.performance import PipelinePerformance, PipelineComparison

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

@router.get("/pipelines/{pipeline_id}/performance", response_model=PipelinePerformance)
async def get_pipeline_performance(
    pipeline_id: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get performance analytics for a pipeline"""
    
    # Verify user owns this pipeline
    pipeline = await get_pipeline(pipeline_id, db)
    if pipeline.user_id != current_user.id:
        raise HTTPException(403, "Access denied")
    
    analytics = PerformanceAnalytics(db)
    performance = await analytics.get_pipeline_performance(
        pipeline_id=pipeline_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return performance

@router.get("/pipelines/compare", response_model=PipelineComparison)
async def compare_pipelines(
    pipeline_ids: List[str] = Query(...),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Compare performance of multiple pipelines"""
    
    # Verify user owns all pipelines
    for pid in pipeline_ids:
        pipeline = await get_pipeline(pid, db)
        if pipeline.user_id != current_user.id:
            raise HTTPException(403, f"Access denied to pipeline {pid}")
    
    analytics = PerformanceAnalytics(db)
    
    comparisons = {}
    for pid in pipeline_ids:
        perf = await analytics.get_pipeline_performance(pid, start_date, end_date)
        pipeline = await get_pipeline(pid, db)
        comparisons[pid] = {
            "name": pipeline.name,
            "performance": perf
        }
    
    return comparisons

@router.get("/user/performance")
async def get_user_performance(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get aggregate performance across all user's pipelines"""
    
    # Get all user's pipelines
    pipelines = await get_user_pipelines(current_user.id, db)
    pipeline_ids = [p.id for p in pipelines]
    
    analytics = PerformanceAnalytics(db)
    
    # Get individual performance
    performances = {}
    for pid in pipeline_ids:
        perf = await analytics.get_pipeline_performance(pid, start_date, end_date)
        performances[pid] = perf
    
    # Aggregate metrics
    aggregate = {
        "total_pnl": sum(p.metrics["total_pnl"] for p in performances.values()),
        "total_trades": sum(p.metrics["total_trades"] for p in performances.values()),
        "total_cost": sum(p.metrics["total_cost"] for p in performances.values()),
        "pipelines": performances
    }
    
    return aggregate
```

### Key Features

1. **Comprehensive Metrics**: Total P&L, win rate, Sharpe ratio, max drawdown, profit factor, ROI
2. **Multi-Dimensional Analysis**: By symbol, day of week, time of day
3. **Visual Charts**: Equity curve, breakdowns with bar charts
4. **Period Selection**: 7D, 30D, 90D, All Time
5. **Pipeline Comparison**: Compare multiple pipelines side-by-side
6. **Export Functionality**: Export reports as PDF/CSV
7. **Real-time Updates**: Metrics update as new trades close

### UI Libraries

- **Angular Material**: UI components (cards, buttons, toggles)
- **Chart.js** or **ngx-charts**: For equity curve and breakdown charts
- **Angular CDK**: For responsive layouts

---

## 12.4 Testing & Dry Run Mode

### Overview

Testing & Dry Run Mode allows users to safely test their trading strategies without risking real money. The system supports four execution modes with clear visual indicators and strict isolation to prevent accidental real trades.

### Execution Modes

#### 1. Live Mode 🟢
- **Purpose**: Real trading with real money
- **Behavior**: Executes actual trades through broker API
- **Requirements**: Verified broker connection, sufficient account balance
- **Costs**: Full tracking (agent fees + LLM + broker commissions)
- **Risk**: HIGH - real money at stake

#### 2. Paper Trading Mode 🔵
- **Purpose**: Realistic testing with broker's paper account
- **Behavior**: Uses broker's paper trading API (Alpaca Paper, etc.)
- **Requirements**: Broker paper account connection
- **Costs**: Agent fees + LLM (no real broker fees)
- **Risk**: LOW - no real money, but realistic simulation

#### 3. Simulation Mode 🟡
- **Purpose**: Fast testing without broker API calls
- **Behavior**: Fully simulated trades with configurable parameters
- **Requirements**: None (no broker needed)
- **Costs**: Agent fees + LLM only
- **Risk**: NONE - completely simulated

#### 4. Validation Mode ⚪
- **Purpose**: Strategy logic testing only
- **Behavior**: Runs all agents except Trade Manager
- **Requirements**: None
- **Costs**: Agent fees + LLM only
- **Risk**: NONE - no trades executed

---

### Database Schema Updates

**Pipeline Model** (`app/models/pipeline.py`):

```python
from enum import Enum
from sqlalchemy import Column, String, Enum as SQLEnum, JSON, DateTime

class ExecutionMode(str, Enum):
    LIVE = "LIVE"
    PAPER = "PAPER"
    SIMULATION = "SIMULATION"
    VALIDATION = "VALIDATION"

class Pipeline(Base):
    __tablename__ = "pipelines"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    
    # Execution mode
    execution_mode = Column(SQLEnum(ExecutionMode), nullable=False, default=ExecutionMode.SIMULATION)
    
    # Mode-specific config
    mode_config = Column(JSON, nullable=True)  # Slippage, commission, etc.
    
    # Broker connection (required for LIVE and PAPER modes)
    broker_connection_id = Column(String, nullable=True)
    
    # Audit trail
    mode_changed_at = Column(DateTime, nullable=True)
    mode_changed_by = Column(String, nullable=True)
    mode_change_reason = Column(String, nullable=True)
    
    # ... other fields
```

**Mode Config Schema**:

```python
# For SIMULATION mode
{
    "slippage_pct": 0.1,          # 0.1% slippage
    "commission_per_share": 0.005, # $0.005 per share
    "simulate_partial_fills": True,
    "simulate_rejections": True,
    "initial_balance": 100000.0    # Starting balance for simulation
}

# For PAPER mode
{
    "paper_account_id": "alpaca_paper_123",
    "initial_balance": 100000.0
}
```

**Trade Model Updates** (`app/models/trade.py`):

```python
class Trade(Base):
    __tablename__ = "trades"
    
    # ... existing fields
    
    # Mode tracking
    execution_mode = Column(SQLEnum(ExecutionMode), nullable=False)
    
    # Simulation-specific fields
    simulated_slippage = Column(Float, nullable=True)
    simulated_commission = Column(Float, nullable=True)
    
    # Paper trading fields
    paper_account_id = Column(String, nullable=True)
    paper_order_id = Column(String, nullable=True)
```

---

### Backend Implementation

#### Trade Manager Agent - Mode-Aware Execution

**Updated Trade Manager** (`app/agents/trade_manager_agent.py`):

```python
class TradeManagerAgent(BaseAgent):
    """
    Trade Manager with multi-mode support
    """
    
    def __init__(self, agent_id: str, config: Dict, pipeline: Pipeline):
        super().__init__(agent_id, config)
        self.pipeline = pipeline
        self.execution_mode = pipeline.execution_mode
        self.mode_config = pipeline.mode_config or {}
        
        # Initialize appropriate executor
        if self.execution_mode == ExecutionMode.LIVE:
            self.executor = LiveTradeExecutor(pipeline.broker_connection_id)
        elif self.execution_mode == ExecutionMode.PAPER:
            self.executor = PaperTradeExecutor(pipeline.broker_connection_id)
        elif self.execution_mode == ExecutionMode.SIMULATION:
            self.executor = SimulatedTradeExecutor(self.mode_config)
        elif self.execution_mode == ExecutionMode.VALIDATION:
            self.executor = ValidationExecutor()  # No-op executor
    
    def process(self, state: PipelineState) -> PipelineState:
        """Execute trade based on pipeline mode"""
        
        # Get trade signal
        signal = state.strategy_signal
        risk_approval = state.risk_approval
        
        if not risk_approval.approved:
            logger.info(f"Trade rejected by risk manager: {risk_approval.reason}")
            return state
        
        # Validation mode: Skip execution
        if self.execution_mode == ExecutionMode.VALIDATION:
            logger.info(f"[VALIDATION MODE] Would execute: {signal.action} {signal.quantity} {signal.symbol}")
            state.validation_result = {
                "signal": signal.dict(),
                "would_execute": True,
                "estimated_entry": signal.entry_price,
                "estimated_stop": signal.stop_loss,
                "estimated_target": signal.take_profit
            }
            return state
        
        # Execute trade via appropriate executor
        try:
            execution_result = self.executor.execute_trade(
                symbol=signal.symbol,
                action=signal.action,
                quantity=signal.quantity,
                order_type=signal.order_type,
                price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit
            )
            
            # Store execution result
            trade = Trade(
                id=str(uuid.uuid4()),
                pipeline_id=self.pipeline.id,
                execution_id=state.execution_id,
                symbol=signal.symbol,
                action=signal.action,
                quantity=signal.quantity,
                entry_price=execution_result.fill_price,
                status="OPEN",
                execution_mode=self.execution_mode,
                open_time=datetime.utcnow(),
                # Mode-specific fields
                simulated_slippage=execution_result.slippage if hasattr(execution_result, 'slippage') else None,
                simulated_commission=execution_result.commission if hasattr(execution_result, 'commission') else None,
                paper_account_id=execution_result.paper_account_id if hasattr(execution_result, 'paper_account_id') else None
            )
            
            db.add(trade)
            db.commit()
            
            state.trade = trade
            
            # Log with mode indicator
            logger.info(f"[{self.execution_mode.value}] Trade executed: {trade.id}")
            
        except Exception as e:
            logger.exception(f"[{self.execution_mode.value}] Trade execution failed")
            state.errors.append(f"Trade execution failed: {str(e)}")
        
        return state
```

#### Trade Executors

**Live Trade Executor** (`app/services/executors/live_executor.py`):

```python
class LiveTradeExecutor:
    """Execute real trades through broker API"""
    
    def __init__(self, broker_connection_id: str):
        self.broker = get_broker_client(broker_connection_id)
    
    def execute_trade(self, symbol, action, quantity, order_type, price, stop_loss, take_profit):
        """Execute real trade"""
        
        # Validate buying power
        account = self.broker.get_account()
        if account.buying_power < (price * quantity):
            raise InsufficientFundsError("Insufficient buying power")
        
        # Place bracket order
        order = self.broker.place_bracket_order(
            symbol=symbol,
            qty=quantity,
            side=action,
            limit_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        
        # Wait for fill (with timeout)
        filled_order = self.broker.wait_for_fill(order.id, timeout=30)
        
        return ExecutionResult(
            order_id=filled_order.id,
            fill_price=filled_order.filled_avg_price,
            filled_qty=filled_order.filled_qty,
            commission=filled_order.commission,
            status="FILLED"
        )
```

**Paper Trade Executor** (`app/services/executors/paper_executor.py`):

```python
class PaperTradeExecutor:
    """Execute paper trades through broker's paper trading API"""
    
    def __init__(self, broker_connection_id: str):
        # Use paper trading endpoint
        self.broker = get_broker_client(broker_connection_id, paper=True)
    
    def execute_trade(self, symbol, action, quantity, order_type, price, stop_loss, take_profit):
        """Execute paper trade"""
        
        # Similar to live but uses paper account
        order = self.broker.place_bracket_order(
            symbol=symbol,
            qty=quantity,
            side=action,
            limit_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        
        filled_order = self.broker.wait_for_fill(order.id, timeout=30)
        
        return ExecutionResult(
            order_id=filled_order.id,
            fill_price=filled_order.filled_avg_price,
            filled_qty=filled_order.filled_qty,
            commission=0.0,  # No real commission in paper trading
            paper_account_id=filled_order.account_id,
            status="FILLED"
        )
```

**Simulated Trade Executor** (`app/services/executors/simulated_executor.py`):

```python
class SimulatedTradeExecutor:
    """Simulate trade execution without broker API"""
    
    def __init__(self, mode_config: Dict):
        self.slippage_pct = mode_config.get("slippage_pct", 0.1)
        self.commission_per_share = mode_config.get("commission_per_share", 0.005)
        self.simulate_partial_fills = mode_config.get("simulate_partial_fills", True)
        self.simulate_rejections = mode_config.get("simulate_rejections", True)
    
    def execute_trade(self, symbol, action, quantity, order_type, price, stop_loss, take_profit):
        """Simulate instant trade execution"""
        
        # Simulate rejection (5% chance)
        if self.simulate_rejections and random.random() < 0.05:
            rejection_reasons = [
                "Insufficient buying power",
                "Market closed",
                "Symbol not tradable",
                "Order size too large"
            ]
            raise TradeRejectionError(random.choice(rejection_reasons))
        
        # Apply slippage
        slippage = price * (self.slippage_pct / 100)
        if action in ["BUY", "COVER"]:
            fill_price = price + slippage  # Buy at higher price
        else:
            fill_price = price - slippage  # Sell at lower price
        
        # Simulate partial fill (20% chance)
        filled_qty = quantity
        if self.simulate_partial_fills and random.random() < 0.2:
            filled_qty = int(quantity * random.uniform(0.7, 0.95))
        
        # Calculate commission
        commission = filled_qty * self.commission_per_share
        
        # Instant "fill"
        return ExecutionResult(
            order_id=f"SIM_{uuid.uuid4().hex[:8]}",
            fill_price=round(fill_price, 2),
            filled_qty=filled_qty,
            commission=round(commission, 2),
            slippage=round(slippage, 2),
            status="FILLED"
        )
```

**Validation Executor** (`app/services/executors/validation_executor.py`):

```python
class ValidationExecutor:
    """No-op executor for validation mode"""
    
    def execute_trade(self, *args, **kwargs):
        """Don't execute, just validate"""
        
        # Return hypothetical execution result
        return ExecutionResult(
            order_id=f"VAL_{uuid.uuid4().hex[:8]}",
            fill_price=kwargs.get('price'),
            filled_qty=kwargs.get('quantity'),
            commission=0.0,
            status="VALIDATED"
        )
```

---

### Frontend Implementation

#### Mode Selection Component

**Pipeline Create/Edit Form** (`pipeline-form.component.ts`):

```typescript
import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';

export enum ExecutionMode {
  LIVE = 'LIVE',
  PAPER = 'PAPER',
  SIMULATION = 'SIMULATION',
  VALIDATION = 'VALIDATION'
}

@Component({
  selector: 'app-pipeline-form',
  templateUrl: './pipeline-form.component.html',
  styleUrls: ['./pipeline-form.component.scss']
})
export class PipelineFormComponent implements OnInit {
  pipelineForm: FormGroup;
  ExecutionMode = ExecutionMode;
  
  modeOptions = [
    {
      value: ExecutionMode.SIMULATION,
      label: 'Simulation',
      description: 'Fast testing, no broker needed',
      icon: 'science',
      color: 'accent',
      requiresBroker: false
    },
    {
      value: ExecutionMode.VALIDATION,
      label: 'Validation',
      description: 'Test logic only, no trades',
      icon: 'check_circle',
      color: 'basic',
      requiresBroker: false
    },
    {
      value: ExecutionMode.PAPER,
      label: 'Paper Trading',
      description: 'Realistic testing with paper account',
      icon: 'description',
      color: 'primary',
      requiresBroker: true
    },
    {
      value: ExecutionMode.LIVE,
      label: 'Live Trading',
      description: 'Real trades with real money',
      icon: 'attach_money',
      color: 'warn',
      requiresBroker: true,
      requiresConfirmation: true
    }
  ];

  constructor(
    private fb: FormBuilder,
    private pipelineService: PipelineService,
    private dialog: MatDialog
  ) {}

  ngOnInit(): void {
    this.pipelineForm = this.fb.group({
      name: ['', Validators.required],
      execution_mode: [ExecutionMode.SIMULATION, Validators.required],
      broker_connection_id: [null],
      mode_config: this.fb.group({
        slippage_pct: [0.1],
        commission_per_share: [0.005],
        simulate_partial_fills: [true],
        simulate_rejections: [true],
        initial_balance: [100000]
      })
    });

    // Watch mode changes
    this.pipelineForm.get('execution_mode').valueChanges.subscribe(mode => {
      this.onModeChange(mode);
    });
  }

  onModeChange(mode: ExecutionMode): void {
    const brokerField = this.pipelineForm.get('broker_connection_id');
    
    if (mode === ExecutionMode.LIVE || mode === ExecutionMode.PAPER) {
      brokerField.setValidators([Validators.required]);
      brokerField.updateValueAndValidity();
    } else {
      brokerField.clearValidators();
      brokerField.updateValueAndValidity();
    }

    // Show warning for live mode
    if (mode === ExecutionMode.LIVE) {
      this.showLiveModeWarning();
    }
  }

  showLiveModeWarning(): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: '⚠️ Live Trading Mode',
        message: 'You are about to enable LIVE TRADING with REAL MONEY. Are you sure?',
        confirmText: 'Yes, I understand the risks',
        cancelText: 'No, go back to test mode',
        dangerous: true
      }
    });

    dialogRef.afterClosed().subscribe(confirmed => {
      if (!confirmed) {
        this.pipelineForm.patchValue({ execution_mode: ExecutionMode.SIMULATION });
      }
    });
  }

  save(): void {
    if (this.pipelineForm.valid) {
      this.pipelineService.createPipeline(this.pipelineForm.value).subscribe({
        next: (pipeline) => {
          this.notificationService.success('Pipeline created successfully');
          this.router.navigate(['/pipelines', pipeline.id]);
        },
        error: (error) => {
          this.notificationService.error('Failed to create pipeline');
        }
      });
    }
  }
}
```

**Pipeline Form Template** (`pipeline-form.component.html`):

```html
<form [formGroup]="pipelineForm" (ngSubmit)="save()">
  <mat-card>
    <mat-card-header>
      <mat-card-title>Pipeline Configuration</mat-card-title>
    </mat-card-header>

    <mat-card-content>
      <!-- Pipeline Name -->
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Pipeline Name</mat-label>
        <input matInput formControlName="name" placeholder="My Trading Strategy">
      </mat-form-field>

      <!-- Execution Mode Selection -->
      <div class="mode-selection">
        <h3>Execution Mode</h3>
        <p class="hint">Choose how this pipeline will execute trades</p>

        <mat-radio-group formControlName="execution_mode" class="mode-radio-group">
          <mat-card 
            *ngFor="let mode of modeOptions" 
            class="mode-option"
            [class.selected]="pipelineForm.get('execution_mode').value === mode.value"
            [class.live-mode]="mode.value === ExecutionMode.LIVE">
            
            <mat-radio-button [value]="mode.value">
              <div class="mode-content">
                <div class="mode-header">
                  <mat-icon [color]="mode.color">{{ mode.icon }}</mat-icon>
                  <span class="mode-label">{{ mode.label }}</span>
                  <mat-chip 
                    *ngIf="mode.requiresBroker" 
                    class="broker-chip">
                    Requires Broker
                  </mat-chip>
                </div>
                <p class="mode-description">{{ mode.description }}</p>
              </div>
            </mat-radio-button>
          </mat-card>
        </mat-radio-group>
      </div>

      <!-- Broker Connection (conditional) -->
      <mat-form-field 
        *ngIf="pipelineForm.get('execution_mode').value === ExecutionMode.LIVE || 
               pipelineForm.get('execution_mode').value === ExecutionMode.PAPER"
        appearance="outline" 
        class="full-width">
        <mat-label>Broker Connection</mat-label>
        <mat-select formControlName="broker_connection_id">
          <mat-option *ngFor="let broker of userBrokers" [value]="broker.id">
            {{ broker.name }} ({{ broker.type }})
          </mat-option>
        </mat-select>
        <mat-hint>Select your {{ pipelineForm.get('execution_mode').value === ExecutionMode.LIVE ? 'live' : 'paper' }} broker account</mat-hint>
      </mat-form-field>

      <!-- Simulation Config (conditional) -->
      <div *ngIf="pipelineForm.get('execution_mode').value === ExecutionMode.SIMULATION" 
           formGroupName="mode_config"
           class="simulation-config">
        <h4>Simulation Settings</h4>

        <mat-form-field appearance="outline">
          <mat-label>Slippage %</mat-label>
          <input matInput type="number" formControlName="slippage_pct" step="0.05">
          <mat-hint>Simulated price slippage (default: 0.1%)</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Commission per Share ($)</mat-label>
          <input matInput type="number" formControlName="commission_per_share" step="0.001">
          <mat-hint>Simulated commission cost (default: $0.005)</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Initial Balance ($)</mat-label>
          <input matInput type="number" formControlName="initial_balance">
          <mat-hint>Starting balance for simulation (default: $100,000)</mat-hint>
        </mat-form-field>

        <mat-checkbox formControlName="simulate_partial_fills">
          Simulate partial fills
        </mat-checkbox>

        <mat-checkbox formControlName="simulate_rejections">
          Simulate order rejections
        </mat-checkbox>
      </div>

      <!-- Warning Banner for Live Mode -->
      <mat-card 
        *ngIf="pipelineForm.get('execution_mode').value === ExecutionMode.LIVE" 
        class="warning-banner live-mode-warning">
        <mat-icon color="warn">warning</mat-icon>
        <div>
          <strong>Live Trading Enabled</strong>
          <p>This pipeline will execute REAL TRADES with REAL MONEY. Ensure you have tested your strategy thoroughly in simulation and paper trading modes first.</p>
        </div>
      </mat-card>

    </mat-card-content>

    <mat-card-actions>
      <button mat-raised-button color="primary" type="submit" [disabled]="!pipelineForm.valid">
        Create Pipeline
      </button>
      <button mat-button type="button" (click)="cancel()">
        Cancel
      </button>
    </mat-card-actions>
  </mat-card>
</form>
```

#### Mode Indicator Component

**Mode Badge Component** (`mode-badge.component.ts`):

```typescript
import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-mode-badge',
  templateUrl: './mode-badge.component.html',
  styleUrls: ['./mode-badge.component.scss']
})
export class ModeBadgeComponent {
  @Input() mode: string;
  @Input() size: 'small' | 'medium' | 'large' = 'medium';

  getModeConfig() {
    const configs = {
      'LIVE': {
        label: 'LIVE',
        icon: 'radio_button_checked',
        color: '#4caf50',
        bgColor: '#e8f5e9',
        description: 'Real money trading'
      },
      'PAPER': {
        label: 'PAPER',
        icon: 'description',
        color: '#2196f3',
        bgColor: '#e3f2fd',
        description: 'Paper trading account'
      },
      'SIMULATION': {
        label: 'SIMULATION',
        icon: 'science',
        color: '#ff9800',
        bgColor: '#fff3e0',
        description: 'Simulated trades'
      },
      'VALIDATION': {
        label: 'VALIDATION',
        icon: 'check_circle',
        color: '#9e9e9e',
        bgColor: '#f5f5f5',
        description: 'Logic validation only'
      }
    };

    return configs[this.mode] || configs['SIMULATION'];
  }
}
```

**Mode Badge Template** (`mode-badge.component.html`):

```html
<div class="mode-badge" 
     [class.size-small]="size === 'small'"
     [class.size-medium]="size === 'medium'"
     [class.size-large]="size === 'large'"
     [style.background-color]="getModeConfig().bgColor"
     [style.color]="getModeConfig().color"
     [matTooltip]="getModeConfig().description">
  <mat-icon [style.color]="getModeConfig().color">{{ getModeConfig().icon }}</mat-icon>
  <span class="mode-label">{{ getModeConfig().label }}</span>
</div>
```

#### Pipeline List with Mode Indicators

**Updated Pipeline List** (`pipeline-list.component.html`):

```html
<mat-card *ngFor="let pipeline of pipelines" class="pipeline-card">
  <mat-card-header>
    <div class="header-content">
      <mat-card-title>{{ pipeline.name }}</mat-card-title>
      <app-mode-badge [mode]="pipeline.execution_mode" size="medium"></app-mode-badge>
    </div>
  </mat-card-header>

  <mat-card-content>
    <p>{{ pipeline.description }}</p>
    
    <div class="pipeline-stats">
      <span>Status: {{ pipeline.status }}</span>
      <span>Trades: {{ pipeline.trade_count }}</span>
      <span>P&L: {{ formatCurrency(pipeline.total_pnl) }}</span>
    </div>

    <!-- Warning for test modes -->
    <mat-chip-list *ngIf="pipeline.execution_mode !== 'LIVE'">
      <mat-chip class="test-mode-chip">
        <mat-icon>info</mat-icon>
        Test mode - Not using real money
      </mat-chip>
    </mat-chip-list>
  </mat-card-content>

  <mat-card-actions>
    <button mat-button (click)="viewPipeline(pipeline.id)">View</button>
    <button mat-button (click)="editPipeline(pipeline.id)">Edit</button>
    <button mat-button *ngIf="pipeline.execution_mode !== 'LIVE'" (click)="cloneAsLive(pipeline.id)">
      Clone as Live
    </button>
  </mat-card-actions>
</mat-card>
```

---

### Mode Transition Workflow

**Safe Testing Progression**:

```
New User
   │
   ├─> SIMULATION Mode (unlocked by default)
   │      │
   │      ├─> Complete demo pipeline
   │      ├─> 10+ successful simulated trades
   │      │
   │      └─> ✅ Unlock PAPER TRADING
   │
   ├─> PAPER TRADING Mode
   │      │
   │      ├─> Connect broker paper account
   │      ├─> 25+ successful paper trades
   │      ├─> Positive cumulative P&L
   │      │
   │      └─> ✅ Unlock LIVE TRADING
   │
   └─> LIVE TRADING Mode
          │
          ├─> Verify broker connection
          ├─> Confirm understanding of risks
          ├─> Set budget limits
          │
          └─> 🟢 Real trading enabled
```

---

### API Endpoints

**Mode Management** (`app/api/v1/pipelines.py`):

```python
@router.patch("/pipelines/{pipeline_id}/mode")
async def change_pipeline_mode(
    pipeline_id: str,
    mode_change: PipelineModeChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change pipeline execution mode
    
    Requires confirmation for live mode
    """
    
    pipeline = await get_pipeline(pipeline_id, db)
    
    if pipeline.user_id != current_user.id:
        raise HTTPException(403, "Access denied")
    
    # Validate mode transition
    if mode_change.new_mode == ExecutionMode.LIVE:
        # Check prerequisites
        if not await user_can_enable_live_mode(current_user.id, db):
            raise HTTPException(400, "Prerequisites not met for live trading")
        
        # Require confirmation
        if not mode_change.confirmed:
            raise HTTPException(400, "Confirmation required for live mode")
        
        # Validate broker connection
        if not pipeline.broker_connection_id:
            raise HTTPException(400, "Broker connection required for live mode")
    
    # Update mode
    pipeline.execution_mode = mode_change.new_mode
    pipeline.mode_changed_at = datetime.utcnow()
    pipeline.mode_changed_by = current_user.id
    pipeline.mode_change_reason = mode_change.reason
    
    db.commit()
    
    # Audit log
    await log_mode_change(
        pipeline_id=pipeline_id,
        user_id=current_user.id,
        old_mode=pipeline.execution_mode,
        new_mode=mode_change.new_mode,
        reason=mode_change.reason
    )
    
    return pipeline
```

---

### Key Safety Features

1. **Visual Indicators**: Large, prominent mode badges everywhere
2. **Confirmation Dialogs**: Required for switching to live mode
3. **Broker Validation**: Live mode requires verified broker connection
4. **Audit Trail**: All mode changes logged
5. **Progressive Unlock**: Users must progress through test modes first
6. **Cost Isolation**: Test modes have different cost structures
7. **Performance Separation**: Separate dashboards for test vs live
8. **Clone Feature**: Clone live pipelines as test for safe modification

---

## 13. Infrastructure Design

### 13.1 Local Development (Docker Compose)

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: trading_platform
      POSTGRES_USER: dev
      POSTGRES_PASSWORD: devpass
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  backend:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://dev:devpass@postgres:5432/trading_platform
      REDIS_URL: redis://redis:6379
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      FINNHUB_API_KEY: ${FINNHUB_API_KEY}
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app

  celery_worker:
    build: ./backend
    command: celery -A app.orchestration.executor worker --loglevel=info
    environment:
      DATABASE_URL: postgresql://dev:devpass@postgres:5432/trading_platform
      REDIS_URL: redis://redis:6379
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    depends_on:
      - postgres
      - redis

  celery_beat:
    build: ./backend
    command: celery -A app.orchestration.executor beat --loglevel=info
    environment:
      REDIS_URL: redis://redis:6379
    depends_on:
      - redis

  frontend:
    build: ./frontend
    command: npm start
    ports:
      - "4200:4200"
    volumes:
      - ./frontend:/app
      - /app/node_modules

volumes:
  postgres_data:
```

### 13.2 AWS Production Architecture

**Compute**:
- **ECS Fargate**: Run backend API and Celery workers
  - API Service: 2+ tasks, auto-scaling
  - Worker Service: 3+ tasks, auto-scaling based on queue depth
  - Beat Service: 1 task (singleton)

**Database**:
- **RDS PostgreSQL**: Multi-AZ, automated backups
  - Instance: db.t3.medium (scale up as needed)
  - Encryption at rest

**Cache**:
- **ElastiCache Redis**: Cluster mode
  - Node: cache.t3.medium

**Storage**:
- **S3**: Reports, logs, backups
  - Lifecycle policies for archival

**Networking**:
- **VPC**: Private subnets for ECS, RDS, Redis
- **ALB**: Route traffic to API tasks, SSL termination
- **CloudFront**: Serve Angular SPA from S3

**Security**:
- **Secrets Manager**: Store API keys, DB passwords
- **IAM Roles**: ECS task roles with least privilege
- **Security Groups**: Restrict access between components

**Monitoring**:
- **CloudWatch**: Logs, metrics, alarms
- **X-Ray**: Distributed tracing (future)

### 13.3 CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run backend tests
        run: |
          cd backend
          pip install -r requirements.txt
          pytest
      - name: Run frontend tests
        run: |
          cd frontend
          npm install
          npm test

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Build and push Docker images
        run: |
          docker build -t backend:latest ./backend
          docker push $ECR_REPO/backend:latest

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to ECS
        run: |
          aws ecs update-service --cluster prod --service api --force-new-deployment
```

---

## 14. Cost Tracking & Billing Design

### 14.1 Cost Metering Architecture

**Token Counting Middleware**:
```python
from functools import wraps

def track_llm_cost(func):
    @wraps(func)
    async def wrapper(self, state: PipelineState, *args, **kwargs):
        start_time = time.time()
        
        # Execute agent
        result = await func(self, state, *args, **kwargs)
        
        # Track costs
        tokens = self.llm_provider.get_last_token_count()
        runtime = time.time() - start_time
        
        # Calculate costs
        token_cost = calculate_token_cost(tokens, self.llm_provider.model)
        agent_cost = calculate_agent_rental(runtime, self.pricing_rate)
        
        # Store in DB
        await billing_service.record_cost(
            user_id=state.user_id,
            execution_id=state.execution_id,
            agent_name=self.agent_type,
            tokens=tokens,
            token_cost=token_cost,
            runtime=runtime,
            agent_cost=agent_cost
        )
        
        return result
    return wrapper
```

### 14.2 Budget Enforcement

```python
async def check_budget(user_id: str, estimated_cost: float):
    # Get user budget limits
    user = await get_user(user_id)
    
    # Get current spending
    daily_spend = await get_daily_spend(user_id)
    monthly_spend = await get_monthly_spend(user_id)
    
    # Check limits
    if user.budget_limit_daily:
        if daily_spend + estimated_cost > user.budget_limit_daily:
            raise BudgetExceededException("Daily budget exceeded")
    
    if user.budget_limit_monthly:
        if monthly_spend + estimated_cost > user.budget_limit_monthly:
            raise BudgetExceededException("Monthly budget exceeded")
```

---

## 15. Security Design

### 15.1 Authentication Flow

1. User submits email/password
2. Backend validates credentials
3. Generate JWT token (access + refresh)
4. Frontend stores token in httpOnly cookie
5. Include token in Authorization header for API requests
6. Backend validates JWT on each request

### 15.2 Broker Credential Encryption

```python
from cryptography.fernet import Fernet
import boto3

def encrypt_api_key(api_key: str, user_id: str) -> str:
    # Get encryption key from AWS KMS
    kms_client = boto3.client('kms')
    data_key = kms_client.generate_data_key(
        KeyId='alias/broker-credentials-key',
        KeySpec='AES_256'
    )
    
    # Encrypt API key
    f = Fernet(data_key['Plaintext'])
    encrypted = f.encrypt(api_key.encode())
    
    return encrypted.decode()

def decrypt_api_key(encrypted_key: str, user_id: str) -> str:
    # Retrieve and decrypt
    # (Similar process in reverse)
    pass
```

### 15.3 Rate Limiting

```python
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/v1/pipelines")
@limiter.limit("10/minute")
async def create_pipeline(request: Request, ...):
    pass
```

---

## 16. Key Design Decisions

### 16.1 Why CrewAI?

- Multi-agent orchestration built-in
- Flow-based execution model
- Easy to compose agents into crews
- Supports state passing between agents
- Active community and development

### 16.2 Why Celery?

- Mature, battle-tested task queue
- Supports async, retries, scheduling
- Redis backend for speed
- Flower UI for monitoring
- Easy to scale workers

### 16.3 Why PostgreSQL?
- JSONB for flexible config/state storage
- ACID compliance for financial data
- Excellent performance for relational queries
- TimescaleDB extension option for time-series

### 16.4 Agent-First Architecture

- All business logic in agents (portable, testable)
- Backend is thin orchestration layer
- Easy to add new agents without changing infrastructure
- Marketplace-ready (agents are products)

### 16.5 Event-Driven Triggers (Kafka)

- Push-based (not poll-based) for low latency
- Centralized signal generation (not per-pipeline)
- Horizontal scalability (add more generators/dispatchers)
- Clear separation: Signal Generation → Distribution → Matching → Execution

### 16.6 OpenTelemetry for Observability

- Vendor-neutral (no lock-in to AWS/Datadog/etc.)
- Auto-instrumentation for FastAPI, SQLAlchemy, Redis, Celery
- Easy migration from local (Prometheus) to cloud (CloudWatch)
- Future-proof for distributed tracing and log aggregation

---

## 17. Signal System Architecture

### 17.1 Overview

The Signal System is an **event-driven architecture** for triggering pipelines based on market conditions.

**Key Components**:
1. **Signal Generators**: Monitor markets, emit signals
2. **Kafka**: Message bus for signal distribution
3. **Trigger Dispatcher**: Matches signals to pipelines
4. **Celery Workers**: Execute matched pipelines

### 17.2 Signal Schema

```json
{
  "timestamp": 1702234567,
  "source": "golden_cross",
  "signal_id": "gc_1702234567_AAPL",
  "signal_type": "golden_cross",
  "tickers": [
    {"ticker": "AAPL", "signal": "BULLISH", "confidence": 85.5}
  ]
}
```

### 17.3 Signal Generators

Independent Docker containers that:
- Monitor market data/events
- Detect conditions (SMA crossover, news, RSI, etc.)
- Generate structured signals
- Publish to Kafka
- Expose Prometheus metrics

**Current**: Mock, Golden Cross  
**Future**: News Sentiment, RSI, MACD, Volume Spike, Custom

### 17.4 Trigger Dispatcher

Lightweight Python service that:
- Subscribes to Kafka `trading-signals` topic
- Caches active signal-based pipelines (in-memory, refreshed every 5 min)
- Matches signals to pipelines (ticker + signal type + confidence)
- Enqueues to Celery if not already running

**Matching Logic**:
1. Extract tickers from signal
2. Find pipelines with matching tickers in scanner
3. Check signal subscriptions (type + min confidence)
4. Check if already PENDING or RUNNING
5. Enqueue to Celery

---

## 18. Scanner System

### 18.1 Purpose

Scanners define reusable ticker lists for pipelines.

**Example**:
```
Scanner: "Tech Stocks" [AAPL, GOOGL, MSFT]
  ├─ Pipeline 1: Golden Cross Strategy
  ├─ Pipeline 2: News Sentiment
  └─ Pipeline 3: RSI Mean Reversion
```

### 18.2 Scanner Types

#### Phase 1: Manual (Current)
User manually enters tickers.

#### Phase 2: Filter-Based (Future)
User defines filters (market cap, sector, price, indicators), system evaluates universe.

#### Phase 3: API-Based (Future)
User provides webhook/API endpoint (e.g., TrendSpider, TradingView screener).

### 18.3 Database Schema

```python
class Scanner(Base):
    id = Column(UUID, primary_key=True)
    user_id = Column(UUID, ForeignKey("users.id"))
    name = Column(String(255))
    scanner_type = Column(Enum(ScannerType))
    tickers = Column(JSONB)  # For manual scanners
    filter_config = Column(JSONB)  # For filter scanners
    api_config = Column(JSONB)  # For API scanners

class Pipeline(Base):
    # ...
    scanner_id = Column(UUID, ForeignKey("scanners.id"))
    signal_subscriptions = Column(JSONB)
    # [{"signal_type": "golden_cross", "min_confidence": 80}]
```

### 18.4 API Endpoints

- `POST /api/v1/scanners` - Create scanner
- `GET /api/v1/scanners` - List user scanners
- `PUT /api/v1/scanners/{id}` - Update scanner
- `DELETE /api/v1/scanners/{id}` - Delete (fails if used by active pipelines)

---

## 19. Subscription & Billing Model

### 19.1 Dual Revenue Model

1. **Subscription Tiers**: Monthly fee for signal access + pipeline limits
2. **Agent Usage Fees**: Pay-per-use when pipelines execute

### 19.2 Subscription Tiers

**FREE** ($0/month): External signals only, 2 pipelines  
**BASIC** ($29/month): 5 signals (Golden Cross, RSI, etc.), 5 pipelines  
**PRO** ($99/month): 9 signals (+ News Sentiment), 20 pipelines  
**ENTERPRISE** ($299/month): All signals, unlimited pipelines

### 19.3 Agent Usage Fees

- **Free Agents**: $0/hour (Market Data, Time Trigger)
- **Basic Agents**: $0.05/hour (Risk Manager)
- **Premium Agents**: $0.10/hour (Bias, Strategy)

Charged per-second, only when pipelines running.

### 19.4 Database Schema

```python
class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class User(Base):
    subscription_tier = Column(SQLEnum(SubscriptionTier))
    max_active_pipelines = Column(Integer)
    subscription_expires_at = Column(DateTime)
```

**Signal Bucket Definitions**: `backend/app/subscriptions/signal_buckets.py`

### 19.5 Enforcement

**Dev Mode** (`ENFORCE_SUBSCRIPTION_LIMITS=false`):
- All users get `DEFAULT_SUBSCRIPTION_TIER` (default: `enterprise`)
- No enforcement, but UI still shows subscription status

**Production Mode** (`ENFORCE_SUBSCRIPTION_LIMITS=true`):
- Hard limits on pipelines and signal access
- Upgrade prompts
- Stripe integration (Phase 2)

---

## 20. Monitoring & Observability

### 20.1 Stack

**OpenTelemetry + Prometheus + Grafana**

**Why OpenTelemetry?**
- Vendor-neutral (can switch to CloudWatch, Datadog, etc.)
- Auto-instrumentation (FastAPI, SQLAlchemy, Redis, Celery)
- Future-proof for tracing and log aggregation

### 20.2 Metrics Exposed

Each service exposes `/metrics` on port `800X`:
- Backend API: `8001`
- Celery Worker: `8002`
- Signal Generator: `8003`
- Trigger Dispatcher: `8004`

Prometheus scrapes every 15 seconds.

### 20.3 Key Metrics

**System Health**:
- `system_active_pipelines`, `system_active_users`
- `system_executions_today_executions`, `system_success_rate_24h_percent`

**Pipeline Execution**:
- `pipeline_executions_total{status}`, `pipeline_execution_duration_seconds`

**Signal System**:
- `signals_generated_total{signal_type}`, `kafka_publish_success_total`
- `pipelines_matched_total`, `pipeline_cache_size`

**Auto-Instrumented** (via OpenTelemetry):
- `http_server_request_duration_seconds`, `db_client_operation_duration_seconds`

### 20.4 Grafana Dashboard

**Trading Platform Overview** dashboard:
- System Health (active pipelines, users, success rate)
- System Status (service UP/DOWN)
- Signal Generator metrics
- Trigger Dispatcher metrics
- Pipeline Execution metrics

**Dashboard Provisioning**: `monitoring/grafana/dashboards/trading-platform-overview.json`

### 20.5 Future

- Distributed tracing (Jaeger/X-Ray)
- Log aggregation (Loki/CloudWatch)
- Alerting (AlertManager/SNS)
- Anomaly detection

---

**Document Version**: 2.0  
**Last Updated**: December 10, 2025  
**Authors**: Engineering Team  
**Status**: Living Document

