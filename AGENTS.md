# Repository Guidelines

## Project Structure & Module Organization

This repository is a multi-service trading platform. `backend/` contains the FastAPI API, Celery orchestration, migrations, and pytest suite in `backend/tests/`. `frontend/` is an Angular 17 standalone app under `frontend/src/app/`. `signal-generator/`, `data-plane/`, and `trigger-dispatcher/` are supporting Python services. `CloverCharts/` is the Swift client. Deployment and design material live in `deploy/`, `monitoring/`, and `docs/`.

## Architecture Overview

The system is agent-first: trading logic flows through Market Data → Bias → Strategy → Risk Manager → Trade Manager, with a shared `PipelineState` passed between agents. Pipelines are triggered either periodically by Celery Beat or by the event-driven signal stack (`signal-generator` → Kafka → `trigger-dispatcher`). Observability uses OpenTelemetry, Prometheus, and Grafana.

## Build, Test, and Development Commands

Start the local stack with `docker-compose up -d`. Apply migrations with `docker exec -it clovercharts-backend alembic upgrade head`, and seed base data with `docker exec clovercharts-backend python seed_database.py`. Run backend tests with `docker exec -it clovercharts-backend pytest -v` or `backend/run_agent_tests.sh quick`. Run the frontend locally: `cd frontend && npm install && npm start`. Use `npm run build` and `npm test` for Angular work.

## Coding Style & Naming Conventions

Python targets 3.11+ and uses 4-space indentation, `snake_case` modules, and explicit type hints. Keep routes under `backend/app/api/v1/`, domain logic in `services/`, and shared schemas in `schemas/`. Backend tooling includes `black --line-length 100`, `isort`, `flake8`, `pylint`, and `mypy`. Angular follows `.editorconfig`: 2-space indentation, UTF-8, trailing newline, and single quotes in TypeScript. Keep components standalone and match naming like `feature-name.component.ts`.

## Testing Guidelines

Python tests use pytest with `test_*.py` naming and markers such as `unit`, `integration`, `slow`, `accuracy`, and `report`. Add tests beside the affected service, for example `backend/tests/test_pipelines.py` or `signal-generator/tests/test_golden_cross.py`. Prefer deterministic fixtures and mocked market data. For agent code, return updated pipeline state instead of mutating shared state in place.

## Commit & Pull Request Guidelines

Recent history mixes concise imperative commits and Conventional Commit prefixes, but `CLAUDE.md` standardizes on conventional commits such as `feat:`, `fix:`, `docs:`, `refactor:`, and `test:`. Keep messages short and scoped. PRs should describe the user-visible change, list services touched, mention config or migration impact, link the issue, and include screenshots for frontend or Swift UI changes.

## Configuration & Security Tips

Copy `docs/env.development.template` to `.env` for local work and never commit real API keys. Review Docker Compose ports before exposing services. Read `docs/context.md` and `docs/design.md` before changing execution flow, signal matching, or service boundaries.
