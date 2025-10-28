# Development Environment Setup Guide

This guide will help you set up the trading platform for local development.

## Prerequisites

- Docker & Docker Compose (required)
- Python 3.11+ (optional, for local development)
- Node.js 18+ (optional, for local frontend development)
- Git

## Quick Start (Docker)

### 1. Clone and Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd kuber-agents

# The .env file is already created with default values
# Edit it to add your API keys (optional for basic testing)
```

### 2. Configure API Keys (Optional)

Edit the `.env` file in the project root and add your API keys:

```bash
# OpenAI (required for AI agents)
OPENAI_API_KEY=sk-your-actual-key

# Finnhub (required for market data)
FINNHUB_API_KEY=your-finnhub-key

# Alpaca (required for trading)
ALPACA_API_KEY=your-alpaca-key
ALPACA_SECRET_KEY=your-alpaca-secret
```

**Note**: Without API keys, you can still test the infrastructure, but agent functionality will be limited.

### 3. Start All Services

```bash
# Start all services (backend, frontend, database, redis, celery)
docker-compose up -d

# View logs
docker-compose logs -f

# Or view specific service logs
docker-compose logs -f backend
```

### 4. Initialize Database

```bash
# Run database migrations
docker exec -it trading-backend alembic upgrade head

# Verify migrations
docker exec -it trading-backend alembic current
```

### 5. Access the Application

Open your browser and navigate to:

- **Frontend**: http://localhost:4200
- **API Docs**: http://localhost:8000/docs
- **API Health**: http://localhost:8000/api/v1/health
- **Celery Monitor**: http://localhost:5555

## Verify Installation

### Check Backend

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Should return:
# {"status":"healthy","timestamp":"...","environment":"development","version":"0.1.0"}
```

### Check Frontend

Open http://localhost:4200 - you should see the dashboard with backend connection status.

### Check Database

```bash
# Connect to PostgreSQL
docker exec -it trading-postgres psql -U dev -d trading_platform

# List tables
\dt

# Exit
\q
```

### Check Redis

```bash
# Connect to Redis
docker exec -it trading-redis redis-cli

# Test connection
ping
# Should return: PONG

# Exit
exit
```

## Development Workflow

### Backend Development

```bash
# The backend automatically reloads on code changes (hot-reload)

# View backend logs
docker-compose logs -f backend

# Run tests
docker exec -it trading-backend pytest

# Run tests with coverage
docker exec -it trading-backend pytest --cov=app

# Access backend shell
docker exec -it trading-backend bash
```

### Frontend Development

```bash
# The frontend automatically reloads on code changes (hot-reload)

# View frontend logs
docker-compose logs -f frontend

# Or run frontend locally (alternative to Docker)
cd frontend
npm install
npm start
# Access at http://localhost:4200
```

### Database Migrations

```bash
# Create a new migration
docker exec -it trading-backend alembic revision --autogenerate -m "Description"

# Apply migrations
docker exec -it trading-backend alembic upgrade head

# Rollback last migration
docker exec -it trading-backend alembic downgrade -1

# View migration history
docker exec -it trading-backend alembic history
```

## Stopping Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (⚠️ this will delete all data)
docker-compose down -v
```

## Troubleshooting

### Backend won't start

```bash
# Check logs
docker-compose logs backend

# Common issue: PostgreSQL not ready
# Solution: Wait a few seconds and try again
docker-compose restart backend
```

### Frontend won't start

```bash
# Check logs
docker-compose logs frontend

# Try rebuilding
docker-compose up -d --build frontend
```

### Database connection issues

```bash
# Ensure PostgreSQL is healthy
docker-compose ps postgres

# Check if port 5432 is already in use
lsof -i :5432

# If needed, change port in docker-compose.yml
```

### "Module not found" errors

```bash
# Rebuild containers
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Next Steps

1. ✅ **Environment is running**
2. 📖 Read the documentation in `docs/`:
   - `context.md` - Understanding the system
   - `requirements.md` - What we're building
   - `design.md` - Technical architecture
3. 🚀 Start implementing features from `docs/roadmap.md`

## API Keys Setup

### OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Add to `.env`: `OPENAI_API_KEY=sk-...`

### Finnhub API Key

1. Go to https://finnhub.io/
2. Sign up for free tier
3. Get API key from dashboard
4. Add to `.env`: `FINNHUB_API_KEY=...`

### Alpaca API Key (Paper Trading)

1. Go to https://alpaca.markets/
2. Sign up for paper trading account
3. Generate API keys
4. Add to `.env`:
   ```
   ALPACA_API_KEY=...
   ALPACA_SECRET_KEY=...
   ALPACA_BASE_URL=https://paper-api.alpaca.markets
   ```

## Additional Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Angular Docs**: https://angular.io/docs
- **Docker Compose**: https://docs.docker.com/compose/
- **Alembic Docs**: https://alembic.sqlalchemy.org/

## Support

For issues, check:
1. Docker logs: `docker-compose logs`
2. GitHub Issues: [link]
3. Documentation: `docs/` folder

---

**Status**: ✅ Development environment ready!  
**Next**: Start building according to `docs/roadmap.md`

