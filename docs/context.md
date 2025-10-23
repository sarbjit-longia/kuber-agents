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
- **Infrastructure**: AWS (ECS Fargate, RDS, ElastiCache, S3, CloudFront)
- **IaC**: Terraform
- **CI/CD**: GitHub Actions

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

### 5. Agent Configuration & UI Generation

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

### 6. Cost Tracking

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

## Glossary

- **Agent**: AI-powered component that performs specific task
- **Pipeline**: Sequence of connected agents
- **Pipeline State**: Data object passed between agents
- **Trigger Agent**: Agent that pauses pipeline until condition met
- **Timeframe**: Chart timeframe (1m, 5m, 1h, 4h, 1d, etc.)
- **CrewAI**: Multi-agent orchestration framework
- **Celery**: Distributed task queue
- **ECS**: Elastic Container Service (AWS)
- **Fargate**: Serverless container execution
- **ECR**: Elastic Container Registry (Docker images)
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

