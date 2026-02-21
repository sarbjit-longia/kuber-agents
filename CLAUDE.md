# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI agent-based trading pipeline platform where retail traders visually connect agents to create automated trading strategies. Agent-first architecture: all trading logic lives in agents, backend is orchestration.

## Development Commands

### Docker (primary development method)

```bash
# Start all services
docker-compose up -d

# Run database migrations
docker exec -it trading-backend alembic upgrade head

# Seed database (LLM models, idempotent)
docker exec trading-backend python seed_database.py

# Create a new migration
docker exec -it trading-backend alembic revision --autogenerate -m "description"

# Run backend tests
docker exec -it trading-backend pytest -v

# Run single test file
docker exec -it trading-backend pytest tests/test_strategy_agent.py -v

# Run tests with coverage
docker exec -it trading-backend pytest --cov=app

# View logs
docker-compose logs -f backend
docker-compose logs -f celery-worker
```

### Frontend (run locally, not in Docker)

```bash
cd frontend
npm install
npm start          # Dev server at http://localhost:4200
npm test           # Karma + Jasmine tests
npm run build      # Production build
```

### Backend local development (alternative to Docker)

```bash
# Always use the project virtual env
source .venv/bin/activate
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Code quality

```bash
# Backend
black backend/ --line-length 100
pylint backend/app/

# Frontend
cd frontend && npx ng generate component features/<name> --standalone
```

## Architecture

### System Overview

```
Frontend (Angular 17) → FastAPI Backend → Celery Workers (pipeline execution)
                                ↓                    ↓
                          PostgreSQL            Redis (broker/cache)
                                                     ↓
                                              [OpenAI] [Broker APIs]

Signal Generator → Kafka → Trigger Dispatcher → Celery (pipeline triggers)
Data Plane API (TimescaleDB) ← market data caching & historical storage
```

### Service Breakdown

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| Backend (FastAPI) | trading-backend | 8000 | REST API, WebSocket |
| Celery Worker | trading-celery-worker | — | Pipeline execution |
| Celery Beat | trading-celery-beat | — | Scheduled tasks |
| Flower | trading-flower | 5555 | Celery monitoring UI |
| Signal Generator | trading-signal-generator | 8007 | Market signal detection via Kafka |
| Trigger Dispatcher | trading-trigger-dispatcher | — | Matches signals to pipeline triggers |
| Data Plane | trading-data-plane | 8005 | Market data API + TimescaleDB storage |
| PostgreSQL | trading-postgres | 5433 | Main database |
| TimescaleDB | trading-timescaledb | 5434 | Time-series market data |
| Redis | trading-redis | 6380 | Celery broker + caching |
| Kafka | trading-kafka | 9092/9093 | Signal event streaming |
| Prometheus | trading-prometheus | 9090 | Metrics |
| Grafana | trading-grafana | 3000 | Dashboards |

### Backend Structure (`backend/app/`)

- **agents/**: Agent implementations. Each inherits `BaseAgent`, implements `get_metadata()` and `process(state) -> state`. Registered in `AgentRegistry` (`agents/registry.py`).
- **orchestration/**: `PipelineExecutor` runs agents in sequence. Celery tasks in `orchestration/tasks/` handle async execution, scheduling, monitoring, approvals, and reconciliation.
- **api/v1/**: REST endpoints. All routes prefixed `/api/v1/`.
- **models/**: SQLAlchemy ORM models (User, Pipeline, Execution, Scanner, CostTracking, LlmModel). UUIDs for PKs, JSONB for flexible config.
- **schemas/**: Pydantic schemas including `PipelineState` — the state object passed between agents.
- **services/**: Business logic layer including broker integrations (`services/brokers/`), PDF generation, approval workflows, notification (SMS/Telegram).
- **tools/**: Agent tools (market data, broker connectors, CrewAI tools). Tool registry pattern matching agents.
- **config.py**: Pydantic Settings loading from `.env`. Global `settings` singleton.

### Pipeline Execution Flow

1. User creates pipeline in UI (guided builder) with connected agents
2. Pipeline config stored as JSONB: `{nodes: [{agent_type, config}], edges: [{from, to}]}`
3. Trigger: manual start, scheduled (Celery Beat), or signal-based (Kafka → Trigger Dispatcher)
4. `PipelineExecutor` instantiates agents from registry, runs in sequence
5. Each agent receives `PipelineState`, processes it, returns updated state
6. Real-time updates via WebSocket to frontend
7. Execution results stored with full reasoning trail

### Agent System

Agents follow a strict contract:
- Inherit `BaseAgent` (in `agents/base.py`)
- Implement `get_metadata()` → `AgentMetadata` (type, category, config_schema, pricing)
- Implement `process(state: PipelineState) -> PipelineState`
- `config_schema` is JSON Schema — frontend dynamically generates config forms from it
- Register in `AgentRegistry` for discovery
- Categories: trigger, data, analysis, risk, execution, reporting

Error hierarchy: `AgentError` → `InsufficientDataError`, `TriggerNotMetException`, `BudgetExceededException`, `AgentProcessingError`

### Frontend Structure (`frontend/src/app/`)

See `frontend/CLAUDE.md` for detailed frontend guidance.

Key points:
- Angular 17 standalone components (no NgModules)
- Routes use `loadComponent()` lazy loading in `app.routes.ts`
- Service-based state management (RxJS BehaviorSubject, no NgRx)
- `ApiService` handles all HTTP calls to `/api/v1/*`
- JWT auth with functional guards/interceptors
- Angular Material dark theme with SCSS CSS custom properties
- Always use separate `.component.html` template files, never inline templates

### Microservices

- **signal-generator/**: Python service that monitors market data, detects signals (e.g., golden cross), publishes to Kafka topic `trading-signals`. Config-driven watchlist in `signal-generator/config/`.
- **trigger-dispatcher/**: Consumes Kafka signals, matches against active pipeline triggers in PostgreSQL, dispatches Celery tasks to execute matching pipelines.
- **data-plane/**: FastAPI service for market data. Abstracts providers (Finnhub, Tiingo, OANDA). Caches in Redis, stores historical data in TimescaleDB. Own Celery workers for background data collection.

## Key Conventions

- **Agent-first**: All trading logic in agents, not backend services
- **State immutability**: Agents receive state, return new state (don't mutate in-place)
- **Async-first**: Use `async/await` for all I/O in Python
- **Type hints everywhere** in Python; strict TypeScript in frontend
- **Pydantic** for all data validation and schemas
- **Alembic** for database migrations (naming: `YYYYMMDD_description`)
- **API versioning**: All endpoints under `/api/v1/`
- **Cost tracking**: Wrap LLM calls with cost tracking; token counting with tiktoken
- **Do not create documentation files** unless explicitly asked — update existing `docs/` files instead
- **Do not run frontend dev server** in chat; let user run it in their terminal
- **Backend formatting**: black (line-length 100), pylint
- **Git commits**: conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`)

## Docs Reference

Read docs in `docs/` folder before implementing features:
- `docs/requirements.md` — product requirements
- `docs/design.md` — system architecture and database schema
- `docs/context.md` — core concepts and quick-start for developers
- `docs/roadmap.md` — development phases and priorities

## Access Points (local dev)

- Frontend: http://localhost:4200
- API: http://localhost:8000
- API Docs (Swagger): http://localhost:8000/docs
- Celery Monitor (Flower): http://localhost:5555
- Grafana: http://localhost:3000
- Signal Monitor: http://localhost:8007
