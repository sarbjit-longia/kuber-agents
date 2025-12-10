# Project Context Document

## Purpose

This document provides high-level context about the Trading Platform project. It's designed to help new developers (or AI assistants like Cursor) quickly understand the project's architecture, key decisions, and development patterns.

---

## Project Overview

**What are we building?**

An agent-based trading pipeline platform (similar to n8n) where retail traders can visually connect AI agents to create automated trading strategies. Users drag-and-drop agents, configure them through forms, and deploy pipelines that analyze markets and execute trades.

**Key Differentiator**: Modular agent architecture where agents are products. Users can mix and match agents (some free, some paid) to create custom strategies. Future: Agent marketplace where developers can sell custom agents.

**Tech Stack**:
- **Frontend**: Angular 17+ with Angular Material
- **Backend**: Python 3.11+ with FastAPI
- **Agent Framework**: CrewAI for multi-agent orchestration
- **LLM**: OpenAI (MVP), local models (future)
- **Task Queue**: Celery with Redis
- **Database**: PostgreSQL with JSONB for flexible storage
- **Cache**: Redis
- **Message Bus**: Apache Kafka for signal distribution
- **Monitoring**: OpenTelemetry + Prometheus + Grafana
- **Infrastructure**: AWS (ECS Fargate, RDS, ElastiCache, MSK, S3, CloudFront)
- **IaC**: Terraform (future)
- **CI/CD**: GitHub Actions (future)

---

## Core Concepts

### 1. Agent

An **Agent** is a self-contained AI-powered component that performs a specific task in the trading pipeline.

**Types of Agents** (by category):
- **Trigger Agents**: Pause pipeline until condition met (time, price, indicators, news)
- **Data Agents**: Fetch market data, news, alternative data
- **Analysis Agents**: Analyze market bias, generate trading signals
- **Risk Agents**: Validate trades, calculate position sizing
- **Execution Agents**: Execute trades via brokers
- **Reporting Agents**: Collect reasoning and create reports

**Key Properties**:
- Each agent has **metadata** (name, description, pricing, config schema)
- Agents declare their **input/output schemas**
- Agents declare **required timeframes** (e.g., bias needs 1h/4h/1d, strategy needs 5m)
- Agents can be **free or paid** (hourly rental model)
- Agents can internally be **CrewAI crews** (multi-agent collaboration)

**Example**: Strategy Agent analyzes market data and outputs a complete trade plan:
```python
StrategySignal(
    action="BUY",
    entry_price=150.50,
    stop_loss=148.00,
    target_1=154.25,
    target_2=158.00,
    reasoning="Golden cross forming..."
)
```

### 2. Pipeline

A **Pipeline** is a connected sequence of agents that work together.

**Storage**: Pipelines are stored as JSON in PostgreSQL:
```json
{
  "nodes": [
    {"id": "node-1", "agent_type": "time_trigger", "config": {...}},
    {"id": "node-2", "agent_type": "market_data_agent", "config": {...}}
  ],
  "edges": [{"from": "node-1", "to": "node-2"}]
}
```

**Execution**: When a pipeline runs:
1. CrewAI Flow orchestrates agent execution
2. Agents pass state object between each other
3. State accumulates outputs (market data → bias → strategy → risk → trade)
4. Celery workers execute pipelines asynchronously

### 3. Pipeline State

The **PipelineState** is the data object passed between agents:

```python
class PipelineState(BaseModel):
    pipeline_id: str
    execution_id: str
    user_id: str
    symbol: str
    
    # Multiple timeframe support
    timeframes: Dict[str, TimeframeData]  # {"1h": ..., "4h": ..., "5m": ...}
    primary_timeframe: str  # "5m" for execution
    
    # Agent outputs
    trigger_condition: Optional[str]
    market_data: Optional[MarketData]
    bias: Optional[BiasSignal]
    strategy: Optional[StrategySignal]
    risk: Optional[RiskDecision]
    trade: Optional[TradeExecution]
    
    # Cost tracking
    tokens_used: Dict[str, int]
    agent_runtime: Dict[str, float]
```

Each agent:
1. Receives `PipelineState`
2. Validates required inputs exist
3. Performs its task
4. Updates state with its output
5. Returns updated state

### 4. Timeframe Management

**Problem**: Different agents need different timeframes.
- Bias Agent: Analyzes multiple timeframes (1h, 4h, 1d) for overall market direction
- Strategy Agent: Works on single timeframe (5m) for precise entry
- Risk Manager: Uses strategy's timeframe

**Solution**: 
- Market Data Agent fetches all required timeframes
- Stores in `state.timeframes` dict
- Each agent accesses its required timeframe(s)
- `state.primary_timeframe` defines execution timeframe

### 5. Position Management & Exit Strategy

**Problem**: Who tracks positions and executes stop loss / targets after trade is placed?

**Solution**: Enhanced Trade Manager Agent

**Trade Manager** is not just an execution agent - it's the complete position lifecycle manager:

1. **Pre-Trade Position Check**
   - Queries broker for existing positions
   - Prevents duplicate positions (configurable)
   - Rejects conflicting trades

2. **Trade Execution with Exits**
   - Places bracket orders (stop + targets) if broker supports
   - Falls back to individual orders

3. **Position Monitoring** (Celery Task every 60 seconds)
   - Monitors for stop loss hit → closes position
   - Monitors for Target 1 hit → closes partial (50%), moves stop to breakeven
   - Monitors for Target 2 hit → closes remaining position

4. **Manual Intervention**
   - Emergency close position API endpoint
   - Emergency close all positions
   - Stops monitoring on manual close
   - Audit log of manual interventions

**Broker as Source of Truth**: No separate position tracking database. Trade Manager queries broker directly for current positions.

**Example**:
```python
# Strategy Agent outputs complete trade plan
strategy = StrategySignal(
    entry=150.50,
    stop_loss=148.00,    # Downside protection
    target_1=154.25,     # First profit take (50%)
    target_2=158.00      # Final profit take (50%)
)

# Trade Manager
1. Checks broker: "Do we already have AAPL position?" → No
2. Executes: Places bracket order
3. Monitors: Every 60s checks if stop/targets hit
4. Exits: Automatically closes when levels reached
```

### 6. Pipeline Trigger Modes (Event-Driven Architecture)

**Problem**: How should pipelines know when to execute? Polling is inefficient and costly.

**Solution**: Two trigger modes - Signal-based and Periodic

#### 6.1 Signal-Based Pipelines (`trigger_mode = SIGNAL`)

**How it works**:
1. User creates a **Scanner** (ticker list, e.g., "Tech Stocks" = [AAPL, GOOGL, MSFT])
2. User creates a **Pipeline** and links to scanner
3. User subscribes to **Signals** (e.g., golden_cross, news_sentiment)
4. **Signal Generators** continuously monitor markets, emit signals to Kafka
5. **Trigger Dispatcher** matches signals to pipelines:
   - Does ticker match scanner?
   - Does signal type match subscriptions?
   - Is confidence above threshold?
   - Is pipeline already running? (skip if yes)
6. If match, enqueue pipeline to Celery

**Example**:
```json
{
  "trigger_mode": "signal",
  "scanner_id": "uuid-tech-stocks",
  "signal_subscriptions": [
    {"signal_type": "golden_cross", "min_confidence": 80},
    {"signal_type": "news_sentiment", "min_confidence": 70}
  ]
}
```

**What Happens**:
- Signal Generator detects golden cross on AAPL (confidence: 85%)
- Kafka message: `{"signal_type": "golden_cross", "tickers": [{"ticker": "AAPL", "confidence": 85}]}`
- Trigger Dispatcher: Matches to pipeline (AAPL in scanner, confidence ≥ 80)
- Celery: Executes pipeline for AAPL

#### 6.2 Periodic Pipelines (`trigger_mode = PERIODIC`)

**How it works**:
1. User creates a pipeline without scanner
2. **Celery Beat** checks every 5 minutes for active periodic pipelines
3. For each pipeline, check if already PENDING or RUNNING
4. If not running, enqueue to Celery

**Example**:
```json
{
  "trigger_mode": "periodic",
  "symbol": "AAPL"
}
```

**What Happens**:
- Every 5 minutes: Celery Beat checks if pipeline is running
- If not running: Enqueue to Celery
- Pipeline executes for AAPL

#### 6.3 Key Benefits

**Signal-Based**:
- Low latency (< 1 second from signal to execution)
- Event-driven (not polling)
- Scalable (centralized signal generation)
- Multi-ticker support via scanners

**Periodic**:
- Simple to configure
- Predictable execution
- No scanner required

### 7. Cost Estimation & Transparency

**Problem**: Users don't know how much pipeline will cost until AFTER running. This leads to unexpected bills and budget overruns.

**Solution**: Pre-execution cost estimation + real-time tracking

**Cost Estimation Components**:

1. **Agent Rental Costs**: Based on hourly rate × estimated duration
   - Time Trigger: $0.00/hour (free)
   - Market Data: $0.00/hour (free)
   - Bias Agent: $0.08/hour (~6 min avg)
   - Strategy Agent: $0.10/hour (~6 min avg)
   - Risk Manager: $0.05/hour (~3 min avg)

2. **LLM Token Costs**: Based on model and estimated tokens
   - Bias Agent: GPT-4, ~2K input, ~500 output → ~$0.008
   - Strategy Agent: GPT-4, ~1.5K input, ~600 output → ~$0.005
   - Risk Manager: GPT-3.5-turbo, ~1K input, ~300 output → ~$0.002

3. **Daily/Monthly Projections**: Based on execution mode and schedule
   - Run Continuous (6 hr window): Estimated 6-12 executions/day
   - Run Scheduled (every 30 min): Exact count known
   - Compare against user's budget limits

**Before Starting Pipeline**:
```
┌─ Estimated Costs ─────────────────────────────┐
│                                                │
│  Cost per Execution: $0.23                    │
│                                                │
│  Daily Estimate:                               │
│    8-12 executions → $1.84 - $2.76 / day      │
│                                                │
│  Monthly Estimate (21 trading days):          │
│    $55.20 - $82.80 / month                    │
│                                                │
│  Your budget: $100/month                       │
│  ✓ Estimated usage: 55-83% of budget          │
│                                                │
│  Confidence: Medium ⚠️                         │
│    (Based on average execution times)          │
└────────────────────────────────────────────────┘
```

**Features**:
- **Pre-execution estimates**: See cost before starting
- **Budget comparison**: Warnings if > 80% of budget
- **Detailed breakdown**: Cost per agent, LLM tokens, duration
- **Real-time tracking**: Actual vs estimated during execution
- **Historical accuracy**: System learns from user's patterns
- **Confidence levels**: High (historical data), Medium (averages), Low (variable triggers)

**Improves Over Time**:
- Tracks estimated vs actual costs per execution
- Learns user's specific agent execution patterns
- Adjusts estimates based on historical data
- Shows accuracy percentage (e.g., "Our estimates are typically within ±15%")

### 8. Agent Configuration & UI Generation

**Problem**: How to create UI forms for agent config without coupling UI to each agent?

**Solution**: JSON Schema + Dynamic Forms

1. Each agent defines `AgentConfigSchema` (JSON Schema format):
```python
config_schema=AgentConfigSchema(
    properties={
        "timeframe": {
            "type": "string",
            "enum": ["1m", "5m", "15m", "1h"],
            "title": "Trading Timeframe"
        },
        "creativity": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "title": "Creativity"
        }
    }
)
```

2. Frontend fetches agent metadata from `/api/v1/agents`
3. Uses `@ajsf/core` (Angular JSON Schema Form) to render forms dynamically
4. User fills form → values stored in pipeline config JSON
5. **Result**: Add new agents without touching frontend code

### 9. Multi-Symbol Support & Stock Picker Agent

**Problem**: Pipelines are limited to one symbol. Users can't scan multiple stocks or run portfolio strategies.

**Solution**: Stock Picker Agent + Multi-Symbol Pipeline Execution

**Pipeline Flow**:
```
Trigger → Stock Picker → Market Data → Bias → Strategy → Risk → Trade
          (Picks N symbols) (Fetches all)  (Filters)  (Generates signals)
```

**Stock Picker Agent**:
1. Runs saved screener (user-defined filters: price, volume, sector, technicals)
2. Returns top N symbols (e.g., top 10 from 50 matches)
3. Adds symbols to `state.symbols` list
4. **FREE** - no cost for Stock Picker itself

**Multi-Symbol Execution**:
- Market Data Agent fetches data for ALL symbols in parallel
- Bias Agent analyzes ALL symbols, filters by score
- Strategy Agent generates signals for qualified symbols
- Trade Manager executes trades for all valid signals

**Cost Model - Per-Symbol Pricing**:
```
Single Symbol Pipeline:
  Bias Agent: $0.08/hr × 6 min × 1 symbol = $0.008
  Total: $0.02

10 Symbol Pipeline:
  Stock Picker: $0.00 (free)
  Bias Agent: $0.08/hr × 6 min × 10 symbols = $0.08
  Total: $0.20 (10x multiplier)
```

**Budget Protection**:
- Stock Picker checks budget BEFORE analyzing N symbols
- Blocks execution if cost would exceed remaining budget
- Transparent per-symbol cost breakdown in estimates

### 10. Pipeline Manager Agent (The Brain)

**Problem**: Need coordinator for budget, positions, and inter-agent communication. Business logic should be in agents, not backend services.

**Solution**: Pipeline Manager Agent - one per pipeline, auto-injected, handles everything

**Architecture**:
```
Pipeline 1 (AAPL Day Trading):
┌──────────────────────────────────────┐
│ Pipeline Manager Agent (Pipeline 1)  │ ← Owns $5/day budget
│  • Tracks this pipeline's budget     │
│  • Monitors this pipeline's positions│
│  • Coordinates pipeline agents       │
└──────────────────────────────────────┘
         ↓ manages
  Trigger → Market Data → Bias → Strategy → Trade Manager
```

**Pipeline Manager Agent** (Auto-injected as first agent):

1. **Budget Tracking** (for THIS pipeline only):
   - Loads pipeline's budget allocation ($5/day, $100/month)
   - Checks budget before pipeline starts
   - Receives cost reports from all agents after execution
   - Accumulates cumulative cost
   - Detects budget exhaustion

2. **Position Registry** (for THIS pipeline only):
   - Trade Manager registers positions with Pipeline Manager
   - Tracks open positions: `manager.open_positions`
   - Unregisters when positions close

3. **Inter-Agent Communication**:
   - Agents access manager via `state.pipeline_manager`
   - Stock Picker asks: "Can I analyze 10 symbols?"
   - Agents report: "I cost $0.08"
   - Manager commands Trade Manager: "Emergency close all positions"

4. **Intervention Logic**:
   - If budget exhausted → send close command to Trade Manager
   - Trade Manager closes all positions at market
   - Manager logs intervention
   - Raises `BudgetExceededException` to stop pipeline

**Budget Exhaustion Flow**:
```
1. Bias Agent completes → reports $0.08 cost to Manager
2. Manager: cumulative = $4.95 + $0.08 = $5.03
3. Manager: $5.03 >= $5.00 daily limit → EXHAUSTED
4. Manager → Trade Manager: "Emergency close positions"
5. Trade Manager closes 2 positions at market
6. Manager logs intervention, raises exception
7. Pipeline stops
8. User notified: "Budget exhausted, 2 positions closed"
```

**Pipeline Budget Allocation**:
```
User total budget: $50/day

Pipeline allocations:
  Pipeline 1 (AAPL Day):   $5/day
  Pipeline 2 (Tech Scan):  $10/day
  Pipeline 3 (Swing):      $20/day
  ────────────────────────────────
  Total allocated: $35/day
  Unallocated:     $15/day
```

**Example - Inter-Agent Communication**:
```python
# Stock Picker asks Pipeline Manager
class StockPickerAgent:
    async def process(self, state):
        estimated_cost = 0.25  # For 10 symbols
        
        # Ask Pipeline Manager
        allowed, reason = state.pipeline_manager.check_budget(estimated_cost)
        
        if not allowed:
            raise BudgetExceededException(f"Manager blocked: {reason}")
        
        # Approved - continue

# Bias Agent (cost reported by orchestrator automatically)
class BiasAgent:
    async def process(self, state):
        result = self.analyze()
        return state
        # Orchestrator reports cost to manager after this

# Trade Manager registers positions
class TradeManagerAgent:
    async def process(self, state):
        position = self.execute_trade()
        
        # Register with Pipeline Manager
        await state.pipeline_manager.register_position(position)
```

**Key Benefits**:
- ✅ **Agent-first** - All logic in Pipeline Manager Agent, not services
- ✅ **Isolated budgets** - Each pipeline has own allocation
- ✅ **Inter-agent communication** - Agents coordinate via manager
- ✅ **Thin orchestrator** - Just calls agents, no business logic
- ✅ **System agent** - Auto-injected, hidden from UI, free

### 11. Cost Tracking

**Why**: Control OpenAI costs and bill users fairly.

**What we track**:
- LLM tokens (input + output) per agent
- API calls (market data, broker)
- Agent runtime (for hourly rental charges)

**How**:
- Decorator/middleware wraps agent execution
- Tracks tokens using `tiktoken`
- Calculates cost: `token_cost + agent_rental_cost + api_cost`
- Stores in `cost_tracking` table
- Enforces budget limits (pause pipeline if exceeded)

**Optimization**:
- Free agents don't use LLM (Time Trigger, Market Data)
- Simple agents use GPT-3.5-turbo (Risk Manager, Reporting)
- Complex agents use GPT-4 (Bias, Strategy)
- Future: Migrate simple tasks to local models (Llama)

---

### 12. Performance Analytics

**Why**: Users need to see if their strategies are working and where to optimize.

**What we provide**:
- **Key Metrics**: Total P&L, Win Rate, Win/Loss Ratio, Sharpe Ratio, Max Drawdown, Profit Factor, ROI
- **Multi-Dimensional Analysis**: Performance breakdown by symbol, day of week, time of day
- **Visual Charts**: Equity curve showing cumulative P&L over time
- **Period Selection**: Analyze last 7/30/90 days or all time
- **Pipeline Comparison**: Side-by-side comparison of multiple pipelines
- **Best/Worst Tracking**: Largest win and largest loss with details

**Implementation**:

**Backend** (`app/services/performance_analytics.py`):
```python
class PerformanceAnalytics:
    async def get_pipeline_performance(pipeline_id, start_date, end_date):
        # Fetch all closed trades in period
        # Calculate metrics (P&L, win rate, Sharpe, drawdown)
        # Analyze by symbol/day/time
        # Generate equity curve
        # Return comprehensive performance report
```

**Frontend** (`analytics/performance-dashboard.component.ts`):
- Angular Material cards for metrics
- Chart.js/ngx-charts for equity curve and breakdowns
- Period selector (7D, 30D, 90D, All)
- Export functionality (PDF/CSV)

**Key Calculations**:
- **Sharpe Ratio**: Risk-adjusted return = (avg_return / std_return) * sqrt(252)
- **Max Drawdown**: Peak-to-trough decline in cumulative P&L
- **Profit Factor**: Gross profit / Gross loss
- **Win Rate**: (Winning trades / Total trades) * 100
- **ROI**: (Total P&L / Total cost) - includes agent fees and LLM costs

**User Benefits**:
1. **See what works**: Identify best-performing symbols, days, times
2. **Optimize strategies**: Adjust pipeline based on patterns
3. **Compare pipelines**: Allocate budget to winners
4. **Track improvement**: Monitor performance over time
5. **Cost awareness**: Net P&L includes all costs (agents + LLM)

**Example Insights**:
> "Your pipeline has 62.5% win rate on NVDA vs 45% on TSLA → Focus on NVDA"
> 
> "You perform better on Thursdays (9:30-11:00 AM) → Adjust schedule"
> 
> "Pipeline A: 2.1x ROI, Pipeline B: 0.8x ROI → Pause Pipeline B"

---

### 13. Testing & Dry Run Mode

**Why**: Allow users to safely test strategies before risking real money.

**Four Execution Modes**:

1. **🟢 Live Mode** - Real trades, real money
   - Uses live broker API
   - Requires verified broker connection
   - Full cost tracking (agent + LLM + broker fees)
   - **Risk: HIGH**

2. **🔵 Paper Trading Mode** - Realistic testing
   - Uses broker's paper trading API (Alpaca Paper, etc.)
   - Real market data, simulated fills
   - Requires broker paper account
   - **Risk: LOW (no real money)**

3. **🟡 Simulation Mode** - Fast testing
   - Fully simulated, no broker API calls
   - Instant fills with configurable slippage/commission
   - No broker connection needed
   - **Risk: NONE**

4. **⚪ Validation Mode** - Logic testing only
   - Runs all agents except Trade Manager
   - No trades executed
   - Generates "what would have happened" reports
   - **Risk: NONE**

**Implementation**:

**Backend** - Mode-Aware Trade Executors:
```python
class TradeManagerAgent:
    def __init__(self, pipeline):
        if pipeline.execution_mode == ExecutionMode.LIVE:
            self.executor = LiveTradeExecutor()
        elif pipeline.execution_mode == ExecutionMode.PAPER:
            self.executor = PaperTradeExecutor()
        elif pipeline.execution_mode == ExecutionMode.SIMULATION:
            self.executor = SimulatedTradeExecutor()
        else:  # VALIDATION
            self.executor = ValidationExecutor()  # No-op
```

**Frontend** - Mode Selection & Indicators:
- Mode selection during pipeline creation
- Large visual badges everywhere (color-coded)
- Confirmation dialogs for live mode
- Warning banners in test modes
- "Clone as Live" button for tested pipelines

**Simulation Features**:
- Configurable slippage (default 0.1%)
- Configurable commission (default $0.005/share)
- Simulate partial fills (20% chance)
- Simulate rejections (5% chance)
- Initial balance setting (default $100k)

**Safe Testing Workflow**:
```
New User → SIMULATION (unlocked)
            │
            ├─> 10+ successful trades
            └─> ✅ Unlock PAPER TRADING
                     │
                     ├─> 25+ paper trades
                     ├─> Positive P&L
                     └─> ✅ Unlock LIVE TRADING
                              │
                              ├─> Verify broker
                              ├─> Confirm risks
                              └─> 🟢 Real trading enabled
```

**Safety Features**:
1. **Visual Indicators**: Color-coded badges everywhere (Green/Blue/Yellow/Gray)
2. **Confirmation Dialogs**: Required for live mode activation
3. **Broker Validation**: Live mode requires verified connection
4. **Audit Trail**: All mode changes logged with reason
5. **Progressive Unlock**: Must succeed in test modes first
6. **Cost Isolation**: Different cost tracking per mode
7. **Performance Separation**: Separate analytics for test vs live
8. **Clone Feature**: Clone and test before modifying live pipelines

**User Benefits**:
- **Risk-Free Testing**: Try strategies without risking money
- **Fast Iteration**: Simulation mode for rapid testing
- **Realistic Validation**: Paper trading with real market data
- **Confidence Building**: Progress through modes builds competence
- **Safe Experimentation**: Clone live pipelines to test modifications

**Example Flow**:
> Day 1-3: Build strategy in SIMULATION → 15 wins, 5 losses (75% win rate)
> 
> Day 4-14: Test in PAPER TRADING → 30 trades, +$1,200 paper P&L
> 
> Day 15+: Deploy to LIVE → Confident, tested, ready for real trading

---

## Architecture Patterns

### Agent-First Architecture

**Philosophy**: All business logic lives in agents. Backend is just orchestration.

**Why?**
- **Portable**: Agents can run anywhere
- **Testable**: Mock state, test agents independently
- **Marketplace-ready**: Agents are products
- **Scalable**: Add workers to scale

**Backend responsibilities**:
- Store pipeline configs
- Schedule executions (Celery)
- Provide APIs (CRUD operations)
- Manage users and billing
- Stream real-time updates (WebSocket)

### CrewAI Integration

**CrewAI** is a multi-agent framework. We use it two ways:

1. **Pipeline-level**: CrewAI Flow orchestrates the entire pipeline
   ```python
   class TradingPipelineFlow(Flow):
       @start()
       def trigger_wait(self): ...
       
       @listen(trigger_wait)
       def fetch_market_data(self): ...
       
       @listen(fetch_market_data)
       def analyze_bias(self): ...
   ```

2. **Agent-level**: Individual agents can be CrewAI crews
   ```python
   class BiasAgent(BaseAgent):
       def process(self, state):
           crew = Crew(
               agents=[market_analyst, sentiment_analyst, synthesizer],
               tasks=[analyze_task, sentiment_task, synthesize_task]
           )
           result = crew.kickoff()
           state.bias = BiasSignal(**result)
           return state
   ```

### Celery Task Queue

**Why Celery?**
- Async pipeline execution (don't block API)
- Retry logic built-in
- Scheduled tasks (Celery Beat for triggers)
- Scalable (add more workers)

**Key Tasks**:
- `execute_pipeline(pipeline_id, user_id)`: Main execution task
- `check_trigger_condition(execution_id)`: Periodic trigger checks
- `cleanup_old_executions()`: Scheduled cleanup

**Non-blocking Triggers**:
- Trigger agent raises `TriggerNotMetException`
- Celery retries task after delay (exponential backoff)
- Worker is freed during wait
- User not charged during wait

### WebSocket for Real-time Updates

**Why?** Better UX than polling.

**Events**:
- `execution_started`
- `agent_started`, `agent_completed`
- `trade_executed`
- `error`

**Fallback**: If WebSocket fails, fall back to polling every 5 seconds.

---

## Key Design Decisions

### 1. Why PostgreSQL with JSONB?

- **Relational data**: Users, trades, costs (SQL queries)
- **Flexible data**: Pipeline configs (JSONB)
- **Best of both worlds**: ACID + schemaless configs
- **Performance**: Indexes on JSONB fields

### 2. Why FastAPI over Flask?

- **Performance**: ASGI + async/await
- **Type safety**: Pydantic validation
- **Auto docs**: Swagger UI built-in
- **Modern**: WebSocket support, async everywhere

### 3. Why Angular over React?

- **Project requirement**: User prefers Angular
- **Enterprise-ready**: Strong typing, opinionated structure
- **Material UI**: Excellent component library
- **RxJS**: Great for real-time updates

### 4. Why Terraform over CloudFormation?

- **Multi-cloud**: Could migrate off AWS
- **Readable**: HCL cleaner than YAML/JSON
- **State management**: Better than CF
- **Modules**: Reusable components

### 5. Why ECS Fargate over EC2?

- **Serverless**: No server management
- **Auto-scaling**: Built-in
- **Cost**: Pay per task execution
- **Simple**: Easier than K8s for our scale

### 6. Deployment: Docker Compose (dev) vs ECS (prod)

- **Dev**: `docker-compose.yml` in root - hot reload, easy debugging
- **Prod**: `deploy/Dockerfile.prod` - optimized, multi-stage build

---

## Development Workflow

### Adding a New Agent

1. **Create agent class** in `backend/app/agents/`:
   ```python
   class MyNewAgent(BaseAgent):
       @classmethod
       def get_metadata(cls) -> AgentMetadata:
           return AgentMetadata(
               agent_type="my_new_agent",
               name="My New Agent",
               config_schema=AgentConfigSchema(...)
           )
       
       def process(self, state: PipelineState) -> PipelineState:
           # Your logic here
           return state
   ```

2. **Register agent** in `backend/app/agents/__init__.py`:
   ```python
   AGENT_REGISTRY["my_new_agent"] = MyNewAgent
   ```

3. **Add to database** (seed data or migration):
   ```sql
   INSERT INTO agent_registry (agent_type, name, ...)
   VALUES ('my_new_agent', 'My New Agent', ...);
   ```

4. **Test**:
   ```python
   def test_my_new_agent():
       agent = MyNewAgent(agent_id="test", config={})
       state = PipelineState(...)
       result = agent.process(state)
       assert result.something == expected
   ```

5. **Frontend automatically picks it up** from `/api/v1/agents` endpoint!

### Local Development

```bash
# 1. Copy environment file
cp docs/env.development.template .env
# Edit .env with your API keys

# 2. Start services
docker-compose up

# 3. Run migrations
docker exec -it trading-backend bash
alembic upgrade head

# 4. Access services
# API: http://localhost:8000
# Swagger: http://localhost:8000/docs
# Flower (Celery UI): http://localhost:5555
# Frontend: http://localhost:4200
# Postgres: localhost:5432
# Redis: localhost:6379

# 5. Run tests
docker exec -it trading-backend pytest
```

### Deployment to Production

```bash
cd deploy

# 1. Select AWS profile
./run.sh profile

# 2. Deploy (builds, pushes, deploys)
./run.sh deploy

# Or step by step:
./run.sh build        # Build Docker images
./run.sh push         # Push to ECR
./run.sh deploy-ecs   # Update ECS services

# 3. Monitor
./run.sh status       # Get service status
./run.sh logs api     # Tail logs
```

---

## Common Patterns

### Testing Agents

```python
import pytest
from app.agents import StrategyAgent
from app.schemas.state import PipelineState, MarketData

def test_strategy_agent_generates_signal():
    # Arrange
    agent = StrategyAgent(
        agent_id="test-strategy",
        config={"timeframe": "5m", "risk_reward_min": 1.5}
    )
    
    state = PipelineState(
        pipeline_id="test",
        execution_id="test-exec",
        user_id="test-user",
        symbol="AAPL",
        market_data=MarketData(
            symbol="AAPL",
            current_price=150.0,
            # ... more data
        ),
        bias=BiasSignal(bias="bullish", confidence=85)
    )
    
    # Act
    result = agent.process(state)
    
    # Assert
    assert result.strategy is not None
    assert result.strategy.action == "BUY"
    assert result.strategy.stop_loss < result.strategy.entry_price
    assert result.strategy.target_1 > result.strategy.entry_price
```

### Mocking External APIs

```python
import pytest
from unittest.mock import patch

@patch('app.tools.market_data_tool.FinnhubClient')
def test_market_data_agent(mock_finnhub):
    # Mock API response
    mock_finnhub.return_value.get_quote.return_value = {
        'c': 150.0,  # current price
        'h': 151.0,  # high
        'l': 149.0,  # low
        # ...
    }
    
    agent = MarketDataAgent(agent_id="test", config={})
    state = PipelineState(...)
    result = agent.process(state)
    
    assert result.market_data.current_price == 150.0
```

### Error Handling

```python
class StrategyAgent(BaseAgent):
    def process(self, state: PipelineState) -> PipelineState:
        try:
            # Agent logic
            signal = self._generate_signal(state)
            state.strategy = signal
            
        except InsufficientDataError as e:
            state.errors.append(f"Strategy Agent: {str(e)}")
            logger.error(f"Strategy agent failed: {e}")
            raise  # Will trigger retry
            
        except Exception as e:
            state.errors.append(f"Strategy Agent: Unexpected error")
            logger.exception(f"Unexpected error in strategy agent")
            raise
        
        return state
```

---

## Troubleshooting Guide

### Common Issues

**1. Pipeline execution stuck in "waiting_trigger"**
- Check Celery Beat is running (`docker ps`)
- Check trigger condition in pipeline config
- View logs: `./run.sh logs beat`

**2. Agent fails with "Insufficient tokens"**
- Check OpenAI API key in `.env`
- Check user budget not exceeded
- View cost tracking table

**3. WebSocket not connecting**
- Check CORS settings in FastAPI
- Verify WebSocket URL in frontend config
- Check browser console for errors
- Fallback to polling should work

**4. Database migration failed**
- Check migration file for errors
- Rollback: `alembic downgrade -1`
- Fix migration, try again: `alembic upgrade head`

**5. "Agent type not found" error**
- Check agent registered in `AGENT_REGISTRY`
- Check `agent_registry` table has entry
- Verify agent_type spelling in pipeline config

### Debugging Tips

**View pipeline state**:
```bash
# In Redis
redis-cli
> GET pipeline:state:{execution_id}
```

**Check Celery queue**:
```bash
# View pending tasks
celery -A app.orchestration.executor inspect active
celery -A app.orchestration.executor inspect scheduled
```

**Check CloudWatch logs** (production):
```bash
aws logs tail /ecs/trading-api --follow
```

---

## Project Structure

```
kuber-agents/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── main.py            # FastAPI app
│   │   ├── config.py          # Configuration
│   │   ├── agents/            # Agent implementations
│   │   ├── tools/             # Agent tools
│   │   ├── orchestration/     # CrewAI flows, Celery tasks
│   │   ├── api/               # REST endpoints
│   │   ├── models/            # SQLAlchemy models
│   │   ├── schemas/           # Pydantic schemas
│   │   └── services/          # Business logic services
│   ├── tests/
│   ├── requirements.txt
│   └── alembic/               # DB migrations
│
├── frontend/                   # Angular frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── core/          # Auth, services
│   │   │   ├── shared/        # Shared components
│   │   │   └── features/      # Feature modules
│   │   │       ├── dashboard/
│   │   │       ├── pipeline-builder/
│   │   │       ├── monitoring/
│   │   │       └── reports/
│   │   └── environments/
│   ├── package.json
│   └── angular.json
│
├── deploy/                     # Deployment files
│   ├── terraform/             # Infrastructure as Code
│   ├── Dockerfile.prod        # Production Dockerfile
│   ├── run.sh                 # Deployment script
│   └── README.md
│
├── docs/                       # Documentation
│   ├── requirements.md        # Product requirements
│   ├── design.md              # Technical design
│   ├── roadmap.md             # Development roadmap
│   ├── context.md             # This file
│   ├── env.development.template
│   └── env.production.template
│
├── .github/
│   └── workflows/
│       └── deploy.yml         # CI/CD pipeline
│
├── docker-compose.yml         # Local development
├── Dockerfile                 # Development Dockerfile
└── README.md                  # Project README
```

---

## New Systems (Added December 2025)

### Scanner System

**What**: Reusable ticker lists for pipelines

**Why**: Avoid duplicating ticker lists across pipelines. One scanner can be used by multiple pipelines.

**Example**:
```
Scanner: "Tech Stocks" [AAPL, GOOGL, MSFT, NVDA]
  ├─ Pipeline 1: Golden Cross Strategy
  ├─ Pipeline 2: News Sentiment
  └─ Pipeline 3: RSI Mean Reversion
```

**Types**:
- **Manual** (Phase 1): User manually enters tickers
- **Filter-Based** (Phase 2): User defines filters, system evaluates universe
- **API-Based** (Phase 3): User provides webhook/API endpoint

**Database**: `scanners` table with `tickers` JSONB column

**API**: `/api/v1/scanners` (CRUD operations)

**Frontend**: `/scanners` page for management

---

### Signal System

**What**: Event-driven architecture for triggering pipelines based on market conditions

**Components**:
1. **Signal Generators**: Monitor markets, emit signals to Kafka
2. **Kafka**: Message bus for signal distribution
3. **Trigger Dispatcher**: Matches signals to pipelines
4. **Celery Workers**: Execute matched pipelines

**Signal Schema**:
```json
{
  "timestamp": 1702234567,
  "source": "golden_cross",
  "signal_type": "golden_cross",
  "tickers": [
    {"ticker": "AAPL", "signal": "BULLISH", "confidence": 85}
  ]
}
```

**Current Generators**:
- Mock (random test signals)
- Golden Cross (SMA 50/200 crossover)

**Future Generators**:
- News Sentiment (AI-powered)
- RSI, MACD, Volume Spike
- Custom user-defined

**Why Kafka?**
- Decouples signal generation from pipeline execution
- Horizontal scalability (add more generators/dispatchers)
- Low latency (< 1 second from signal to execution)
- Future: External signal providers can publish to Kafka

---

### Subscription & Billing Model

**What**: Dual revenue model - subscriptions + pay-per-use

#### Subscription Tiers (Signal Buckets)

Users subscribe to **Signal Buckets** that determine which signals they can access:

- **FREE** ($0/month): External signals only, 2 pipelines
- **BASIC** ($29/month): 5 signals (Golden Cross, RSI, etc.), 5 pipelines
- **PRO** ($99/month): 9 signals (+ News Sentiment), 20 pipelines
- **ENTERPRISE** ($299/month): All signals, unlimited pipelines

#### Agent Usage Fees

Agents charge per-second when pipelines execute:
- **Free Agents**: $0/hour (Market Data, Time Trigger)
- **Basic Agents**: $0.05/hour (Risk Manager)
- **Premium Agents**: $0.10/hour (Bias, Strategy)

#### Enforcement

- **Dev Mode** (`ENFORCE_SUBSCRIPTION_LIMITS=false`): All users get `DEFAULT_SUBSCRIPTION_TIER` (default: `enterprise`)
- **Production Mode** (`ENFORCE_SUBSCRIPTION_LIMITS=true`): Hard limits enforced, Stripe integration

**Database**: `users.subscription_tier`, `users.max_active_pipelines`

**API**: `/api/v1/users/me/subscription`

---

### Monitoring & Observability

**What**: Production-grade monitoring using OpenTelemetry + Prometheus + Grafana

**Why OpenTelemetry?**
- Vendor-neutral (no lock-in)
- Auto-instrumentation (FastAPI, SQLAlchemy, Redis, Celery)
- Future-proof (can switch to CloudWatch, Datadog, etc.)

**Metrics Exposed**:
- **System Health**: Active pipelines, users, success rate
- **Pipeline Execution**: Executions by status, duration, cost
- **Signal System**: Signals generated, matched, enqueued
- **Auto-Instrumented**: HTTP requests, DB queries, Redis ops

**Prometheus**: Scrapes `/metrics` endpoints every 15 seconds

**Grafana**: "Trading Platform Overview" dashboard with 30+ panels

**Future**: Distributed tracing (Jaeger/X-Ray), log aggregation (Loki/CloudWatch), alerting

---

## Glossary

- **Agent**: AI-powered component that performs specific task
- **Pipeline**: Sequence of connected agents
- **Scanner**: Reusable ticker list for pipelines
- **Signal**: Market event/condition that triggers pipeline execution
- **Signal Generator**: Service that monitors markets and emits signals
- **Trigger Dispatcher**: Service that matches signals to pipelines
- **Pipeline State**: Data object passed between agents
- **Trigger Mode**: SIGNAL (event-driven) or PERIODIC (scheduled)
- **Subscription Tier**: FREE, BASIC, PRO, ENTERPRISE
- **Timeframe**: Chart timeframe (1m, 5m, 1h, 4h, 1d, etc.)
- **CrewAI**: Multi-agent orchestration framework
- **Celery**: Distributed task queue
- **Kafka**: Message bus for signal distribution
- **OpenTelemetry**: Vendor-neutral observability framework
- **Prometheus**: Time-series metrics database
- **Grafana**: Visualization and dashboards
- **ECS**: Elastic Container Service (AWS)
- **Fargate**: Serverless container execution
- **MSK**: Managed Streaming for Kafka (AWS)
- **RDS**: Relational Database Service (PostgreSQL)
- **ElastiCache**: Managed Redis service
- **ALB**: Application Load Balancer
- **Terraform**: Infrastructure as Code tool
- **Alembic**: Database migration tool

---

## Useful Links

- **Documentation**: `./docs/`
- **API Docs (local)**: http://localhost:8000/docs
- **Celery Monitoring (local)**: http://localhost:5555
- **Terraform Docs**: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- **CrewAI Docs**: https://docs.crewai.com/
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Angular Docs**: https://angular.io/docs

---

**Document Version**: 1.0  
**Last Updated**: October 2025  
**Maintained By**: Engineering Team

**For New Developers**: Read this, then `requirements.md`, then `design.md`. Then start coding!

