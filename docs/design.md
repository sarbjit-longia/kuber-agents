# System Design Document

## 1. System Architecture Overview

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Browser                            │
│                    (Angular SPA + WebSocket)                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS/WSS
┌──────────────────────────▼──────────────────────────────────────┐
│                      API Gateway / ALB                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    FastAPI Backend                              │
│  ┌────────────┬────────────┬──────────────┬──────────────┐    │
│  │  Auth API  │Pipeline API│ Monitor API  │  Billing API │    │
│  └────────────┴────────────┴──────────────┴──────────────┘    │
└──────────┬──────────────────┬────────────────────┬─────────────┘
           │                  │                    │
           │         ┌────────▼────────┐          │
           │         │  Celery Beat    │          │
           │         │  (Scheduling)   │          │
           │         └────────┬────────┘          │
           │                  │                    │
┌──────────▼──────────────────▼────────────────────▼─────────────┐
│                    Redis (State + Queue)                        │
└──────────┬──────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────┐
│              Celery Workers (Pipeline Executors)                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │          CrewAI Flow Orchestration                       │  │
│  │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐      │  │
│  │  │Trigger│→│Market│→│ Bias │→│Strat │→│ Risk │→...   │  │
│  │  │ Agent│  │ Data │  │Agent │  │Agent │  │ Mgr  │      │  │
│  │  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘      │  │
│  └──────────────────────────────────────────────────────────┘  │
└───┬─────────────────┬─────────────────┬──────────────────┬────┘
    │                 │                 │                  │
┌───▼────┐    ┌───────▼────────┐  ┌────▼─────┐    ┌──────▼──────┐
│  RDS   │    │  OpenAI API    │  │Finnhub   │    │Broker APIs  │
│  PG    │    │  (LLM)         │  │(Mkt Data)│    │ (Alpaca)    │
└────────┘    └────────────────┘  └──────────┘    └─────────────┘
```

### 1.2 Component Responsibilities

**Frontend (Angular)**
- Visual pipeline builder (drag-drop interface)
- Real-time monitoring dashboard
- User authentication & profile management
- Cost tracking & reports viewer

**Backend API (FastAPI)**
- REST endpoints for CRUD operations
- WebSocket server for real-time updates
- Authentication & authorization (JWT)
- Request validation & rate limiting

**Pipeline Orchestrator (Celery + CrewAI)**
- Execute pipeline workflows
- Manage agent lifecycle
- Handle retries & failures
- Non-blocking trigger waits

**Data Layer**
- PostgreSQL: Users, pipelines, trades, reports, billing
- Redis: Pipeline state, task queue, caching
- S3: Detailed reports, logs, archives

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

### 4.7 Trade Manager Agent

**Purpose**: Execute approved trades via broker

**Input Requirements**: `state.risk` (approved), `state.strategy`

**Tools Used**:
- BrokerTool: Submit orders to Alpaca/IBKR

**Process**:
1. Check if trade approved by risk manager
2. Construct order payload
3. Submit order to broker
4. Poll for fill confirmation
5. Calculate slippage
6. Submit stop loss and target orders (bracket order or separate)

**LLM Usage**: None (order execution logic only)

**Output**: Updates `state.trade`

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

## 8. Database Design

### 5.1 PostgreSQL Schema

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

### 5.2 Redis Data Structures

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

## 6. Frontend Architecture

### 6.1 Angular Module Structure

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

### 6.2 Key Frontend Components

**Pipeline Builder**
- Library: Consider Angular-based flow library or integrate with ReactFlow via wrapper
- Features: Drag-drop agents, connect nodes, validate connections, configure agents
- State Management: NgRx or RxJS BehaviorSubjects

**Real-time Monitoring**
- WebSocket connection to backend
- Display current agent, progress, logs
- Update dashboard on state changes

**Cost Dashboard**
- Real-time cost display during execution
- Historical cost charts (Chart.js / ngx-charts)
- Budget alerts

---

## 7. Infrastructure Design

### 7.1 Local Development (Docker Compose)

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

### 7.2 AWS Production Architecture

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

### 7.3 CI/CD Pipeline (GitHub Actions)

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

## 8. Cost Tracking & Billing Design

### 8.1 Cost Metering Architecture

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

### 8.2 Budget Enforcement

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

## 9. Security Design

### 9.1 Authentication Flow

1. User submits email/password
2. Backend validates credentials
3. Generate JWT token (access + refresh)
4. Frontend stores token in httpOnly cookie
5. Include token in Authorization header for API requests
6. Backend validates JWT on each request

### 9.2 Broker Credential Encryption

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

### 9.3 Rate Limiting

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

## 10. Key Design Decisions

### 10.1 Why CrewAI?

- Multi-agent orchestration built-in
- Flow-based execution model
- Easy to compose agents into crews
- Supports state passing between agents
- Active community and development

### 10.2 Why Celery?

- Mature, battle-tested task queue
- Supports async, retries, scheduling
- Redis backend for speed
- Flower UI for monitoring
- Easy to scale workers

### 10.3 Why PostgreSQL?

- JSONB for flexible config/state storage
- ACID compliance for financial data
- Excellent performance for relational queries
- TimescaleDB extension option for time-series

### 10.4 Agent-First Architecture

- All business logic in agents (portable, testable)
- Backend is thin orchestration layer
- Easy to add new agents without changing infrastructure
- Marketplace-ready (agents are products)

---

**Document Version**: 1.0  
**Last Updated**: October 22, 2025  
**Authors**: Principal Engineering Team  
**Status**: Draft for Review

