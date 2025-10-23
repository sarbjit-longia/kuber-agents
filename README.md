# Trading Platform - AI Agent-Based Trading Pipeline

> **Visual pipeline builder for creating automated trading strategies using AI agents**

An innovative platform that allows retail traders to create sophisticated trading bots by visually connecting AI agents—no coding required. Think n8n, but for algorithmic trading with intelligent agents.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Angular](https://img.shields.io/badge/angular-17+-red.svg)](https://angular.io/)
[![Status](https://img.shields.io/badge/status-in%20development-yellow.svg)](https://github.com/yourusername/kuber-agents)

---

## 🎯 Project Vision

Create a modular, agent-based trading platform where:
- **Traders** build strategies visually without code
- **Agents** are intelligent, reusable components
- **Strategies** are transparent with full reasoning trails
- **Marketplace** allows agent creators to monetize their work (future)

## ✨ Key Features

### MVP Features (10-week roadmap)
- ✅ **Visual Pipeline Builder** - Drag-and-drop agent connections
- ✅ **8+ Pre-built Agents** - Triggers, analysis, risk management, execution
- ✅ **Multi-Timeframe Analysis** - Analyze 1h/4h/1d, execute on 5m
- ✅ **Real-time Monitoring** - WebSocket updates during execution
- ✅ **Complete Reasoning** - See why each trade decision was made
- ✅ **Cost Tracking** - Token usage, API calls, agent rental fees
- ✅ **Demo Mode** - Try strategies risk-free with paper trading

### Future Features
- 🔮 Backtesting engine
- 🔮 Agent marketplace (buy/sell custom agents)
- 🔮 Multi-asset support (crypto, forex, options)
- 🔮 Custom agent uploads
- 🔮 Local LLM integration for cost reduction

## 🏗️ Architecture

```
User Browser (Angular)
    ↓
API Gateway / ALB
    ↓
FastAPI Backend ←→ Celery Workers (CrewAI Flow)
    ↓                      ↓
PostgreSQL            Redis Queue
                           ↓
                    [Market Data] [OpenAI] [Broker APIs]
```

**Key Technologies**:
- **Backend**: Python 3.11+, FastAPI, CrewAI, Celery, PostgreSQL, Redis
- **Frontend**: Angular 17+, Angular Material, TypeScript
- **Infrastructure**: AWS ECS Fargate, RDS, ElastiCache, S3, CloudFront
- **AI**: OpenAI API (GPT-4, GPT-3.5-turbo)
- **Data**: Finnhub (market data), Alpaca (broker)

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- AWS CLI (for deployment)
- API Keys: OpenAI, Finnhub, Alpaca (paper trading)

### Local Development

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/kuber-agents.git
cd kuber-agents

# 2. Copy environment template
cp docs/env.development.template .env

# 3. Edit .env with your API keys
vim .env

# 4. Start all services with Docker Compose
docker-compose up -d

# 5. Run database migrations
docker exec -it trading-backend alembic upgrade head

# 6. Access the application
# API: http://localhost:8000
# API Docs: http://localhost:8000/docs
# Frontend: http://localhost:4200
# Celery Monitor: http://localhost:5555
```

### Running Tests

```bash
# Backend tests
docker exec -it trading-backend pytest -v

# Frontend tests
cd frontend
npm test

# Coverage
docker exec -it trading-backend pytest --cov=app
```

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [requirements.md](docs/requirements.md) | Complete product requirements (business, functional, technical) |
| [design.md](docs/design.md) | System architecture, database schema, agent designs |
| [roadmap.md](docs/roadmap.md) | Development roadmap with milestones (10-week MVP) |
| [context.md](docs/context.md) | Quick start guide for developers, core concepts |
| [deploy/README.md](deploy/README.md) | Deployment guide for AWS production |

**Start here**: Read [context.md](docs/context.md) for an overview, then dive into specific docs as needed.

## 🤖 Example: Creating a Trading Pipeline

### 1. Visual Builder

Drag and connect agents in the UI:

```
[Time Trigger] → [Market Data] → [Bias] → [Strategy] → [Risk Manager] → [Trade Manager] → [Report]
```

### 2. Configure Each Agent

**Time Trigger Agent** (FREE):
- Trigger at: Market Open + 5 minutes
- Days: Monday-Friday

**Market Data Agent**:
- Timeframes: 1h, 4h, 1d, 5m
- Indicators: SMA 20/50, RSI, MACD

**Bias Agent** ($0.08/hour):
- Analysis timeframes: 1h, 4h, 1d
- Confidence threshold: 70%

**Strategy Agent** ($0.10/hour):
- Execution timeframe: 5m
- Min Risk/Reward: 1.5:1
- Creativity: 0.7

**Risk Manager Agent** ($0.05/hour):
- Max risk per trade: 2%
- Max position size: 10% of account

**Trade Manager Agent**:
- Broker: Alpaca (Paper Trading)
- Order type: Market

### 3. Run Pipeline

Click "Start" → Watch real-time execution → Review detailed report

### 4. Example Report Output

```
Pipeline: My Day Trading Bot
Symbol: AAPL
Executed: 2025-10-23 09:35:00

[Time Trigger] Market opened, condition met
[Market Data] Fetched data for 1h, 4h, 1d, 5m
[Bias] Bullish (85% confidence) - Golden cross forming on 4h
[Strategy] BUY signal
  - Entry: $150.50
  - Stop Loss: $148.00 (-1.66%)
  - Target 1: $154.25 (+2.49%, R:R 1.5:1)
  - Target 2: $158.00 (+4.98%, R:R 3:1)
[Risk Manager] APPROVED - 600 shares (9% of account, 1.5% risk)
[Trade Manager] Order filled at $150.48 (slippage: -$0.02)

Cost: $0.08 (tokens: 12,450, agents: 3, API calls: 8)
```

## 🧩 Agent Types

### Trigger Agents
- **Time-Based** (FREE) - Market hours, specific times, cron
- **Technical Indicator** - RSI, MACD, golden cross, etc.
- **Price-Based** - Breakouts, support/resistance
- **News-Based** (future) - Sentiment, earnings, SEC filings

### Data Agents
- **Market Data** - Real-time quotes, OHLCV, indicators

### Analysis Agents
- **Bias Agent** - Determine market direction (bullish/bearish/neutral)
- **Strategy Agent** - Generate complete trade plan with stops/targets

### Risk Agents
- **Risk Manager** - Position sizing, risk validation

### Execution Agents
- **Trade Manager** - Execute orders via broker APIs

### Reporting Agents
- **Reporting Agent** - Collect reasoning chain, create reports

## 💰 Pricing Model

- **Platform Subscription**: Base monthly fee (TBD)
- **Agent Rental**: Hourly rates when pipeline is active
  - Time Trigger: FREE
  - Market Data: FREE (API costs covered)
  - Bias Agent: $0.08/hour
  - Strategy Agent: $0.10/hour
  - Risk Manager: $0.05/hour
  - Trade Manager: FREE
  - Reporting: FREE
- **Future**: Agent marketplace with custom pricing

## 🛠️ Development

### Project Structure

```
kuber-agents/
├── backend/              # Python FastAPI backend
│   ├── app/
│   │   ├── agents/      # Agent implementations
│   │   ├── tools/       # Agent tools
│   │   ├── orchestration/ # CrewAI flows, Celery tasks
│   │   ├── api/         # REST endpoints
│   │   └── models/      # Database models
│   └── tests/           # Backend tests
│
├── frontend/            # Angular frontend
│   └── src/app/
│       └── features/
│           ├── pipeline-builder/
│           ├── monitoring/
│           └── reports/
│
├── deploy/              # Deployment files
│   ├── terraform/       # Infrastructure as Code
│   └── run.sh          # Deployment script
│
├── docs/                # Documentation
└── .cursorrules        # Cursor AI rules
```

### Adding a New Agent

See [.cursorrules](.cursorrules) for detailed guidelines.

```python
# 1. Create agent class
class MyNewAgent(BaseAgent):
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="my_new_agent",
            name="My New Agent",
            config_schema=AgentConfigSchema(...),
            pricing_rate=0.05
        )
    
    def process(self, state: PipelineState) -> PipelineState:
        # Your logic here
        return state

# 2. Register in AGENT_REGISTRY
AGENT_REGISTRY["my_new_agent"] = MyNewAgent

# 3. Write tests
def test_my_new_agent():
    # ...

# 4. UI automatically picks it up!
```

### Code Quality

```bash
# Backend
black backend/
pylint backend/app/
pytest backend/tests/ --cov=app

# Frontend
cd frontend
npm run lint
npm run test
npm run build:prod
```

## 🚢 Deployment

### AWS Production Deployment

```bash
cd deploy

# 1. Configure AWS profile
./run.sh profile

# 2. Initialize Terraform
./run.sh tf-init

# 3. Deploy infrastructure
./run.sh tf-plan
./run.sh tf-apply

# 4. Deploy application
./run.sh deploy

# 5. Monitor
./run.sh status
./run.sh logs api
```

### CI/CD

GitHub Actions automatically:
1. Runs tests on PR
2. Builds Docker images
3. Deploys to AWS on merge to `main`
4. Verifies deployment health

See [.github/workflows/deploy.yml](.github/workflows/deploy.yml)

## 🔒 Security

- ✅ Broker credentials encrypted (AWS KMS)
- ✅ JWT authentication
- ✅ Rate limiting per user
- ✅ Input validation (Pydantic)
- ✅ HTTPS only in production
- ✅ No secrets in code (environment variables)

## 📊 Monitoring

- **Logs**: CloudWatch (production), Docker logs (dev)
- **Metrics**: ECS service metrics, RDS performance
- **Celery**: Flower UI at http://localhost:5555
- **Errors**: Sentry integration (future)

## 🧪 Testing Strategy

- **Unit Tests**: Every agent, tool, service
- **Integration Tests**: Agent pipelines end-to-end
- **E2E Tests**: UI flows (Cypress/Playwright)
- **Load Tests**: Concurrent pipeline executions (Locust)
- **Coverage Goal**: >80%

## 🗺️ Roadmap

### Milestone 1-3: Foundation & Agents (Weeks 1-5) ✅
- [x] Project setup and documentation
- [ ] Authentication and core APIs
- [ ] Agent framework
- [ ] 8+ MVP agents implemented

### Milestone 4-5: UI & Monitoring (Weeks 6-7)
- [ ] Visual pipeline builder
- [ ] Real-time monitoring dashboard
- [ ] Cost tracking system

### Milestone 6-7: Polish & Demo (Week 8)
- [ ] Demo mode
- [ ] Testing and bug fixes
- [ ] Documentation

### Milestone 8: Production & Beta (Weeks 9-10)
- [ ] AWS deployment
- [ ] Beta user testing
- [ ] Feedback and iteration

See [roadmap.md](docs/roadmap.md) for detailed timeline.

## 🤝 Contributing

We welcome contributions! Please:

1. Read [.cursorrules](.cursorrules) for coding standards
2. Create a feature branch: `feature/my-new-agent`
3. Write tests for new code
4. Submit PR with clear description
5. Update relevant documentation

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details

## 🙏 Acknowledgments

- **CrewAI** for multi-agent orchestration
- **FastAPI** for modern Python web framework
- **Angular** for robust frontend framework
- **Alpaca** for broker API access
- **Finnhub** for market data

## 📞 Support

- **Documentation**: [docs/](docs/)
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Email**: support@tradingplatform.com (future)

---

**Built with ❤️ by traders, for traders**

**Status**: 🚧 In Active Development (Week 1 of 10-week MVP)

**Next Steps**: 
1. Set up local development environment
2. Read [docs/context.md](docs/context.md)
3. Start with Milestone 1 tasks in [roadmap.md](docs/roadmap.md)
