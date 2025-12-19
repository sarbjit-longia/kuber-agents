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

---

## New Systems (Added December 2025)

### Instruction-Driven Agent Architecture

**What**: Agents configured with plain English instructions instead of hardcoded config schemas

**Why**: 
- Empowers non-technical users to create complex strategies
- Eliminates need for frontend form development per agent
- Enables LLM to interpret user intent dynamically
- Makes agents truly flexible and adaptable

**How It Works**:
1. User writes instructions in natural language (e.g., "Analyze market bias on 1h, 4h, and 1d timeframes using RSI and MACD")
2. Agent receives instructions in `process()`
3. LLM parses instructions and determines required actions
4. For tools: Tool Detection Service identifies needed tools
5. For timeframes: Regex parser extracts timeframes
6. For strategy rules: LLM interprets and applies logic

**Agents Using Instructions**:
- **Bias Agent**: Analyzes market bias based on user-defined indicators and timeframes
- **Strategy Agent**: Generates trade plans following user's strategy description
- **Risk Manager Agent**: Calculates position sizes and validates trades per user's risk rules

**Example Instructions**:

**Strategy Agent**:
```
Look for bullish Fair Value Gaps (FVG) on the 5-minute chart. 
Enter when price retests the FVG and shows confirmation with rising volume.
Set stop loss below the FVG low.
Target 2:1 risk-reward ratio.
```

**Risk Manager Agent**:
```
Keep 60% cash on the side.
Risk maximum 1% of account per trade.
Require minimum 2:1 risk-reward ratio.
Factor in today's market volatility when sizing positions.
```

**Key Benefits**:
- ✅ No JSON schemas or forms needed
- ✅ Natural language = lower barrier to entry
- ✅ Same agent works for infinite strategies
- ✅ LLM handles edge cases and variations
- ✅ Instructions stored in pipeline config

---

### LLM Model Registry

**What**: Database-backed system for managing LLM models with dynamic pricing

**Why**: 
- Enables accurate cost calculation based on actual model prices
- Allows easy addition of new models without code changes
- Supports environment-specific model visibility (dev vs prod)
- Provides flexibility for users to choose cost vs performance

**Database Schema**:
```sql
CREATE TABLE llm_models (
    id UUID PRIMARY KEY,
    provider VARCHAR(50),           -- openai, anthropic, lmstudio
    model_name VARCHAR(100),        -- gpt-4-turbo-preview, claude-3-opus
    display_name VARCHAR(200),      -- "GPT-4 Turbo (Latest)"
    input_cost_per_1k_tokens DECIMAL(10, 6),
    output_cost_per_1k_tokens DECIMAL(10, 6),
    context_window INTEGER,
    supports_function_calling BOOLEAN,
    environment VARCHAR(20),        -- all, development, production
    is_active BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**Seeded Models**:
- `gpt-4-turbo-preview` (GPT-4 Turbo)
- `gpt-3.5-turbo` (GPT-3.5 Turbo)
- `gpt-4` (GPT-4)
- `lmstudio-local` (LM Studio - dev only)

**Agent Configuration**:
```python
class BiasAgent(BaseAgent):
    def __init__(self, agent_id, config):
        # Model selection from config (defaults to gpt-4)
        model_name = config.get("model", "gpt-4")
        self.model = self._load_model(model_name)
```

**Cost Calculation**:
```python
# Before: Hardcoded
cost = 0.03 * (input_tokens / 1000) + 0.06 * (output_tokens / 1000)

# After: Dynamic from registry
model = get_model_by_name("gpt-4-turbo-preview")
cost = (
    model.input_cost_per_1k_tokens * (input_tokens / 1000) + 
    model.output_cost_per_1k_tokens * (output_tokens / 1000)
)
```

**API Endpoints**:
- `GET /api/v1/models` - List available models (filtered by environment)
- `GET /api/v1/models/{model_id}` - Get model details

---

### Multi-Broker Architecture

**What**: Abstraction layer supporting multiple brokerage platforms with unified interface

**Why**: 
- User choice - pick preferred broker
- Geographic flexibility - different brokers for different regions
- Redundancy - fallback if one broker has issues
- Future-proof - easy to add more brokers

**Broker Abstraction**:
```python
class BrokerService(ABC):
    """Abstract interface all brokers must implement"""
    
    @abstractmethod
    async def get_account_info(self) -> Dict[str, Any]:
        """Get account balance, buying power, etc."""
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Get all open positions"""
        pass
    
    @abstractmethod
    async def place_order(self, order: Order) -> str:
        """Place order, return order ID"""
        pass
    
    @abstractmethod
    async def close_position(self, symbol: str) -> bool:
        """Close position at market"""
        pass
```

**Supported Brokers**:

1. **Alpaca** (using `alpaca-py` SDK)
   - Paper trading account
   - Live trading account
   - US stocks and ETFs
   - Commission-free
   
2. **Oanda** (using REST API)
   - Practice account
   - Live account
   - Forex and CFDs
   - Popular in Europe/Asia
   
3. **Tradier** (using REST API)
   - Sandbox account
   - Live brokerage account
   - US stocks, options, ETFs
   - Developer-friendly

**Broker Configuration**:
```json
{
  "broker_type": "alpaca",
  "account_type": "paper",  // or "live"
  "api_key": "...",
  "api_secret": "...",
  "base_url": "https://paper-api.alpaca.markets"  // auto-set based on account_type
}
```

**Trade Manager Integration**:
```python
class TradeManagerAgent(BaseAgent):
    def __init__(self, config):
        broker_type = config.get("broker_type", "alpaca")
        self.broker = BrokerFactory.create(broker_type, config)
    
    async def process(self, state):
        # 1. Check existing positions
        positions = await self.broker.get_positions()
        
        # 2. Execute trade
        order_id = await self.broker.place_order(order)
        
        # 3. Monitor position
        # ...
```

---

### Position-Aware Trading System

**What**: Trade Manager checks broker for existing positions before executing new trades

**Why**: 
- Prevents duplicate positions on same symbol
- Prevents conflicting trades (e.g., buying when already short)
- Broker is source of truth (handles manual trades too)
- No separate position tracking database needed

**Pre-Trade Position Check**:
```python
# Trade Manager Agent
async def process(self, state):
    # 1. Query broker for existing positions
    positions = await self.broker.get_positions()
    existing_position = next(
        (p for p in positions if p.symbol == state.symbol), 
        None
    )
    
    # 2. Skip if position already exists (configurable)
    if existing_position and not self.config.get("allow_duplicate_positions"):
        self.record_report(
            state,
            title="Trade Skipped",
            summary=f"Existing position for {state.symbol} detected",
            data={"reason": "duplicate_position_prevention"}
        )
        return state
    
    # 3. Execute trade if no conflict
    order_id = await self.broker.place_order(...)
```

**Monitoring Phase**:
```python
# After trade execution, pipeline enters MONITORING status
# Celery task runs every 5 minutes to check position status

async def monitor_position(execution_id: str):
    # 1. Query broker for position
    position = await broker.get_position(symbol)
    
    # 2. Check exit conditions
    if position.unrealized_pl_percent <= -1.0:  # Stop loss
        await broker.close_position(symbol)
        # Update execution status to COMPLETED
    
    elif position.unrealized_pl_percent >= 2.0:  # Target
        await broker.close_position(symbol)
        # Update execution status to COMPLETED
    
    else:
        # Re-schedule check in 5 minutes
        monitor_position.apply_async(
            args=[execution_id], 
            countdown=300
        )
```

---

### Report Generation & Visualization

**What**: Comprehensive execution reports with charts, formatted reasoning, and management-ready presentation

**Why**: 
- Transparency - users see exactly what agents decided and why
- Debugging - identify issues in agent logic
- Compliance - audit trail for regulatory requirements
- Learning - understand what works and what doesn't

**Report Components**:

1. **Executive Summary** (LLM-generated)
   - High-level overview of execution
   - Key decision points
   - Final recommendation
   
2. **Agent Reports** (per agent)
   - Agent name and status
   - Structured data (metrics, decisions)
   - Formatted reasoning (markdown-style)
   - Charts and visualizations
   
3. **TradingView Charts**
   - Interactive candlestick charts
   - Annotations (FVG, support/resistance, entry/exit)
   - Trade levels visualization
   - Pattern highlights

4. **Execution Artifacts**
   - Full pipeline state
   - Cost breakdown
   - Error logs
   - Timing information

**Report Formatting Pipeline**:
```
LLM Output → _clean_reasoning() → _format_reasoning() → Markdown → HTML → UI/PDF
```

**Text Formatting**:
1. `_clean_reasoning()`: Remove artifacts, numbers, JSON blobs
2. `_format_reasoning()`: Add section headers (`**HEADER:**`), bullet points
3. Frontend pipe: Convert markdown to styled HTML
4. PDF generation: Render HTML with charts to professional PDF

**Example Formatted Output**:
```
**MARKET STRUCTURE:**
  • The 5-minute chart is in a clear bearish trend
  • Key support at $57.04 and resistance at $61.14
  • Current price ($59.11) is between these levels

**PATTERNS IDENTIFIED:**
  • No discernible Fair Value Gap (FVG)
  • Recent candles show minor consolidation

**TOOL ANALYSIS:**
  • MACD shows neutral bias with no strong crossover
  • Volume is 1.3x average
```

**PDF Generation**:
- Pre-generated on pipeline completion (not on-demand)
- Uses WeasyPrint for professional HTML-to-PDF conversion
- Includes all charts as embedded images
- Stored in S3 (or local disk for dev)
- Fast downloads via direct URL

---

### Multi-Timeframe Signal Generation

**What**: Signal generators monitor multiple timeframes simultaneously to catch signals at different granularities

**Why**: 
- Different strategies work on different timeframes
- More signal diversity = more opportunities
- Intraday (15m) vs swing (Daily) trading
- Users can subscribe to specific timeframes

**Configuration**:
```bash
# .env
PRIMARY_TIMEFRAME=D  # Daily (default)
ADDITIONAL_TIMEFRAMES=15,60  # Add 15-minute and 60-minute
```

**How It Works**:
1. Signal generator creates multiple instances per indicator
   - `golden_cross_D` (Daily)
   - `golden_cross_15` (15-minute)
   - `golden_cross_60` (Hourly)
   
2. Each instance monitors its assigned timeframe independently

3. Signals published to Kafka include timeframe metadata:
   ```json
   {
     "signal_type": "golden_cross",
     "timeframe": "15",
     "tickers": [{"ticker": "AAPL", "confidence": 85}]
   }
   ```

4. Trigger Dispatcher matches based on timeframe + signal type

**Benefits**:
- ✅ More signals generated across timeframes
- ✅ Day traders get intraday signals
- ✅ Swing traders get daily signals
- ✅ Same codebase, different configurations
- ✅ Kafka naturally handles high-frequency signals

---

### Monitoring & Observability Enhancements

**What**: Langfuse integration for LLM tracing and improved agent report formatting

**Langfuse Integration**:
- Trace every LLM call with full context
- Track token usage per agent
- Monitor cost in real-time
- Debug LLM failures with full conversation history
- Session-based tracing (group all agents in one execution)

**Agent Report Improvements**:
- Clean reasoning text (no LLM artifacts)
- Markdown-style formatting (bold headers, bullets)
- Line break preservation in UI
- Professional PDF generation
- Charts embedded in reports

---

## Updated Glossary

- **Instruction-Driven Agent**: Agent configured via natural language instead of JSON schema
- **LLM Model Registry**: Database of available LLM models with pricing
- **Broker Abstraction Layer**: Unified interface for multiple brokerages
- **Position-Aware Trading**: System that checks existing positions before trading
- **Dual-Phase Execution**: Pipeline runs in Execute phase, then Monitor phase
- **Pre-Generated PDF**: Report PDF created at pipeline completion, not on download
- **Multi-Timeframe Signals**: Signals generated across multiple timeframes (15m, 1h, 1d)
- **Langfuse**: LLM observability and tracing platform
- **WeasyPrint**: Python library for HTML-to-PDF conversion

---

**Document Version**: 1.1  
**Last Updated**: December 19, 2025  
**Maintained By**: Engineering Team

**For New Developers**: Read this, then `requirements.md`, then `design.md`. Then start coding!

