# Requirements Document

## Executive Summary

This document outlines the requirements for an agent-based trading pipeline platform that enables retail traders to create, configure, and deploy automated trading strategies through a visual interface. The platform uses AI agents orchestrated via CrewAI flows to analyze markets, generate signals, manage risk, and execute trades.

**Key Differentiators:**
- Visual pipeline builder similar to n8n for connecting AI agents
- Modular agent architecture with clean interfaces for extensibility
- Cost-efficient design with token tracking and hybrid LLM strategy
- Agent marketplace foundation for future monetization
- Multi-tenant architecture supporting concurrent pipeline executions

---

## 1. Business Requirements

### 1.1 Target Users
- **Primary**: Retail traders seeking to automate trading strategies
- **Experience Level**: Traders with basic to intermediate market knowledge
- **Technical Skill**: No coding required; visual pipeline builder interface

### 1.2 Value Proposition
- Create sophisticated trading bots without writing code
- Combine multiple AI agents to build custom trading strategies
- Transparent reasoning - see why each trade decision was made
- Cost-effective with pay-per-use pricing model
- Demo mode for risk-free learning

### 1.3 Revenue Model
- **Platform Subscription**: Base monthly fee for platform access
- **Agent Rental**: Hourly usage fees per agent (e.g., $0.10/hour for Strategy Agent)
  - Some agents are free (e.g., Time-Based Trigger Agent)
  - Premium agents have hourly rates
  - Different agent types may have different pricing tiers
- **Billing Granularity**: Charges only when pipelines are actively running (not during trigger wait states)
- **Future**: Agent marketplace with revenue sharing

### 1.4 Business Constraints
- Must support scalability to hundreds/thousands of users
- Cost per user must be optimized (token usage, API calls)
- Must be deployable on AWS for production
- Must support local development environment

---

## 2. Functional Requirements

### 2.1 User Management

**FR-2.1.1**: System shall support user registration and authentication
- Email/password authentication with JWT tokens
- Secure password storage (bcrypt/argon2)
- Password reset functionality

**FR-2.1.2**: System shall support user profile management
- Broker connection configuration (API keys, encrypted storage)
- Notification preferences (email, in-app)
- Budget limits and alerts

**FR-2.1.3**: System shall limit concurrent pipelines per user
- MVP: Maximum 1-3 concurrent active pipelines per user
- Configurable based on subscription tier

### 2.2 Pipeline Management

**FR-2.2.1**: Users shall be able to create custom agent pipelines
- Visual drag-and-drop interface for connecting agents
- Agent configuration through UI forms
- Pipeline naming and description
- Save pipeline as draft or publish to activate

**FR-2.2.2**: Users shall be able to manage pipeline lifecycle
- Start/Stop/Pause pipeline execution
- View pipeline status (waiting_trigger, running, paused, completed, failed)
- Delete pipelines
- Clone existing pipelines

**FR-2.2.3**: System shall validate pipeline configurations
- Ensure all required agents are connected
- Validate agent parameter values
- Check broker connections before starting
- Warn about estimated costs

**FR-2.2.4**: System shall support demo mode pipelines
- New users get access to pre-configured demo pipeline
- Demo pipelines use paper trading accounts
- Demo data clearly marked in UI

### 2.3 Agent Framework

**FR-2.3.1**: System shall support standard agent interface
- All agents receive standardized `PipelineState` object
- Agents output updated `PipelineState` with their results
- State includes: timestamp, symbol, user_id, pipeline_id, agent outputs, metadata

**FR-2.3.2**: System shall support agent composition
- Individual agents can be CrewAI crews internally
- Agents can use multiple tools
- Agent-to-agent communication via state object only

**FR-2.3.3**: System shall provide agent retry mechanism
- Configurable max retries per pipeline (default: 3)
- Configurable retry delay (default: exponential backoff)
- Log all retry attempts
- Fail pipeline after max retries exceeded

**FR-2.3.4**: System shall track agent execution metrics
- Execution time per agent
- Token usage (input/output) per agent
- API calls per agent
- Success/failure rates

### 2.4 MVP Agent Requirements

#### 2.4.1 Trigger Agents (Multiple Types)

**FR-2.4.1.0**: System shall support multiple trigger agent types
- Each trigger agent is a separate, specialized agent
- Users can connect any trigger agent type to their pipeline
- Multiple trigger agents can be chained if needed
- Each trigger type may have different pricing (some free, some paid)

**FR-2.4.1.1**: Time-Based Trigger Agent (FREE)
- Market open/close times
- Specific times of day (e.g., 10:00 AM EST)
- Days of week
- Cron-like scheduling
- **Pricing**: Free for all users

**FR-2.4.1.2**: Technical Indicator Trigger Agent
- RSI thresholds (e.g., RSI > 70)
- Moving average crossovers (golden cross, death cross)
- MACD signals
- Bollinger Band breakouts
- Volume spikes
- Custom indicator combinations

**FR-2.4.1.3**: Price-Based Trigger Agent
- Price above/below threshold
- Price percentage change
- Price range breakout
- Support/resistance levels

**FR-2.4.1.4**: News-Based Trigger Agent
- Monitors news feeds for specific keywords/topics
- Sentiment analysis on news
- Earnings announcement triggers
- SEC filing alerts

**FR-2.4.1.5**: All trigger agents shall pause pipeline efficiently
- Non-blocking wait (doesn't consume worker resources)
- Check conditions periodically (configurable interval)
- Resume pipeline execution when trigger condition met
- Users not charged for wait time

#### 2.4.2 Market Data Agent

**FR-2.4.2.1**: Market Data Agent shall provide real-time stock data
- Current price (bid/ask/last)
- OHLCV data
- Volume
- Basic technical indicators (SMA, EMA, RSI, MACD)

**FR-2.4.2.2**: Market Data Agent shall use pluggable data providers
- MVP: Finnhub API integration
- Architecture supports swapping providers (Alpha Vantage, Yahoo Finance, etc.)

**FR-2.4.2.3**: Market Data Agent shall handle data errors gracefully
- Retry on API failures
- Use cached data when appropriate
- Log data quality issues

#### 2.4.3 Bias Agent

**FR-2.4.3.1**: Bias Agent shall analyze overall market direction
- Determine market sentiment (bullish/bearish/neutral)
- Provide confidence score (0-100%)
- Consider multiple timeframes if configured

**FR-2.4.3.2**: Bias Agent shall provide reasoning
- Explain key factors influencing bias determination
- Reference specific data points used

#### 2.4.4 Strategy Agent

**FR-2.4.4.1**: Strategy Agent shall generate complete trading signals
- Output: BUY, SELL, HOLD
- Conviction level (0-100%)
- Entry price recommendation
- Stop loss price (risk management)
- Target 1 price (first profit target)
- Target 2 price (second profit target)
- Rationale for each price level

**FR-2.4.4.2**: Strategy Agent shall incorporate bias and risk constraints
- Use Bias Agent output in decision-making
- Align signals with market bias
- Consider risk management constraints while creating trade plan
- Coordinate with Risk Manager Agent to ensure trade feasibility

**FR-2.4.4.3**: Strategy Agent shall provide comprehensive reasoning
- Explain why signal was generated
- Reference technical/fundamental factors
- Justify stop loss and target price selections
- Explain risk/reward ratio

#### 2.4.5 Risk Manager Agent

**FR-2.4.5.1**: Risk Manager Agent shall validate complete trade proposals
- Receive trade plan from Strategy Agent (entry, stop loss, targets)
- Check portfolio exposure limits
- Verify sufficient buying power
- Check position concentration
- Validate stop loss placement
- Output: APPROVED / REJECTED / ADJUSTED

**FR-2.4.5.2**: Risk Manager Agent shall calculate and adjust position sizing
- Determine number of shares to trade based on strategy's stop loss
- Apply risk percentage per trade (e.g., max 2% account risk)
- Consider portfolio allocation
- May adjust position size if strategy's proposal exceeds risk limits

**FR-2.4.5.3**: Risk Manager Agent shall enforce risk rules
- Maximum drawdown limits
- Maximum position size per trade
- Maximum portfolio exposure per symbol
- Sector/symbol concentration limits
- Risk/reward ratio minimums

**FR-2.4.5.4**: Risk Manager Agent shall provide detailed reasoning
- Explain approval/rejection/adjustment decisions
- Show risk calculations (account risk, position risk)
- Justify any adjustments to Strategy Agent's proposal

#### 2.4.6 Trade Manager Agent

**FR-2.4.6.1**: Trade Manager Agent shall execute approved trades
- Submit orders to connected broker
- Support order types: Market, Limit
- Handle order confirmations and fills

**FR-2.4.6.2**: Trade Manager Agent shall support multiple brokers
- MVP: At least one broker (Alpaca recommended)
- Architecture supports multiple broker integrations via tools
- Users connect their own broker accounts

**FR-2.4.6.3**: Trade Manager Agent shall handle execution errors
- Retry failed orders (configurable)
- Log all execution attempts
- Notify user of failures

**FR-2.4.6.4**: Trade Manager Agent shall track execution details
- Order ID, fill price, fill time
- Slippage calculation
- Commission/fees

#### 2.4.7 Reporting Agent

**FR-2.4.7.1**: Reporting Agent shall collect reasoning from all agents
- Gather outputs from Trigger Agent(s), Market Data, Bias, Strategy, Risk Manager, Trade Manager
- Create structured report with full decision chain
- Capture complete trade plan (entry, stop loss, target 1, target 2)

**FR-2.4.7.2**: Reporting Agent shall generate comprehensive trade reports
- Executive summary of trade and outcome
- Trigger conditions that initiated the pipeline
- Market conditions at time of analysis
- Bias determination and confidence
- Complete strategy proposal (entry, stop, targets with reasoning)
- Risk management decision and position sizing calculation
- Trade execution details (fill prices, quantity, slippage, time)
- Cost breakdown (tokens used, API calls, agent fees)
- Final P&L when trade closes

**FR-2.4.7.3**: Reporting Agent shall store reports
- Save to database for historical access
- Archive detailed reports to S3
- Enable searching and filtering

**FR-2.4.7.4**: Reports shall be viewable in UI
- List all reports by pipeline
- Search/filter by date, symbol, outcome
- Export reports (PDF, JSON)

### 2.5 Cost Tracking & Billing

**FR-2.5.1**: System shall track LLM token usage
- Count input and output tokens per agent call
- Track by model (gpt-4, gpt-3.5-turbo, etc.)
- Accumulate per pipeline execution
- Store historical usage

**FR-2.5.2**: System shall track API call usage
- Market data API calls
- Broker API calls
- Other external service calls
- Associate with pipeline and user

**FR-2.5.3**: System shall calculate agent rental costs
- Track active time per agent (excluding trigger wait time)
- Apply per-agent hourly rates
- Aggregate costs per pipeline execution

**FR-2.5.4**: System shall enforce budget limits
- Users can set maximum spend per day/month
- Pause pipelines when budget exceeded
- Send alerts at threshold percentages (50%, 75%, 90%)

**FR-2.5.5**: System shall provide cost visibility
- Real-time cost accumulation during pipeline execution
- Cost breakdown by agent
- Historical cost reports
- Cost projections based on usage patterns

### 2.6 Monitoring & Observability

**FR-2.6.1**: Users shall see real-time pipeline status
- Current agent being executed
- Last agent output/decision
- Time in current state
- Errors/warnings

**FR-2.6.2**: System shall log all pipeline events
- Agent start/complete events
- State transitions
- Errors and retries
- Cost milestones

**FR-2.6.3**: System shall provide performance metrics
- Pipeline execution duration
- Agent execution times
- Success/failure rates
- P&L by pipeline

**FR-2.6.4**: System shall provide trade history
- List all trades executed by pipeline
- Show entry/exit prices
- Calculate realized P&L
- Link to detailed reports

### 2.7 Notification System

**FR-2.7.1**: System shall send email notifications
- Pipeline started/stopped/failed
- Trade executed
- Budget alerts
- Critical errors

**FR-2.7.2**: System shall provide in-app notifications
- Real-time notification center
- Notification history
- Mark as read/unread
- Configurable notification preferences

**FR-2.7.3**: Future: SMS notifications (post-MVP)

---

## 3. Non-Functional Requirements

### 3.1 Performance

**NFR-3.1.1**: Pipeline execution latency
- Trigger agent checks: < 5 seconds
- Agent-to-agent transition: < 2 seconds
- Complete pipeline execution (all agents): < 60 seconds under normal conditions

**NFR-3.1.2**: API response times
- Pipeline CRUD operations: < 500ms
- Status queries: < 200ms
- Historical data queries: < 2 seconds

**NFR-3.1.3**: Concurrent execution
- System shall support at least 100 concurrent pipeline executions
- Each user can have 1-3 concurrent pipelines (MVP)

### 3.2 Scalability

**NFR-3.2.1**: User scalability
- Architecture shall support scaling to 1,000+ users
- Horizontal scaling of workers (Celery)
- Database query optimization

**NFR-3.2.2**: Data scalability
- Efficient storage of historical trades (millions of records)
- Efficient storage of reports (S3 archival)
- Time-series optimization for market data

### 3.3 Reliability

**NFR-3.3.1**: System availability
- Target: 99% uptime during market hours
- Graceful degradation on dependency failures
- Automatic worker recovery

**NFR-3.3.2**: Data consistency
- Pipeline state must be consistent
- No lost trades due to system failures
- Audit trail for all financial transactions

**NFR-3.3.3**: Fault tolerance
- Retry mechanisms for transient failures
- Dead letter queues for failed tasks
- Alerting on system errors

### 3.4 Security

**NFR-3.4.1**: Authentication & Authorization
- JWT-based authentication
- Role-based access control (future multi-tier subscriptions)
- Session management

**NFR-3.4.2**: Data protection
- Broker API keys encrypted at rest (AWS Secrets Manager / KMS)
- Sensitive data encrypted in transit (TLS)
- No logging of API keys or credentials

**NFR-3.4.3**: Multi-tenancy isolation
- Complete isolation between user pipelines
- No access to other users' data
- Resource quotas per user

**NFR-3.4.4**: API security
- Rate limiting per user
- Input validation and sanitization
- Protection against common attacks (SQL injection, XSS, CSRF)

### 3.5 Cost Efficiency

**NFR-3.5.1**: LLM optimization
- MVP: Use OpenAI models
- Future: Migrate simple tasks to local models
- Prompt optimization to reduce tokens
- Caching of repeated queries

**NFR-3.5.2**: API call optimization
- Cache market data (respect rate limits)
- Batch API calls where possible
- Use WebSockets for real-time data to reduce polling

**NFR-3.5.3**: Infrastructure optimization
- Auto-scaling workers based on demand
- Serverless functions for infrequent tasks
- Efficient database indexing

### 3.6 Maintainability

**NFR-3.6.1**: Code quality
- Type hints in Python code
- Comprehensive unit tests (>80% coverage goal)
- Integration tests for critical flows
- Linting and formatting (black, pylint)

**NFR-3.6.2**: Documentation
- API documentation (OpenAPI/Swagger)
- Agent development guide
- Deployment runbooks
- Architecture decision records

**NFR-3.6.3**: Observability
- Structured logging
- Distributed tracing (future)
- Metrics dashboard (CloudWatch/Grafana)
- Error tracking (Sentry)

### 3.7 Usability

**NFR-3.7.1**: User interface
- Intuitive pipeline builder (minimal learning curve)
- Responsive design (desktop primary, mobile future)
- Real-time updates without page refresh
- Clear error messages and guidance

**NFR-3.7.2**: Onboarding
- Demo pipeline for new users
- Guided tour of pipeline builder
- Documentation and tutorials
- Sample strategies

---

## 4. Technical Requirements

### 4.1 Technology Stack

**Frontend:**
- Framework: Angular (latest stable version)
- UI Components: Angular Material or similar
- State Management: NgRx or RxJS
- Real-time: WebSocket client

**Backend:**
- Framework: FastAPI (Python 3.10+)
- Agent Framework: CrewAI
- LLM: OpenAI API (gpt-4, gpt-3.5-turbo)
- Task Queue: Celery with Redis backend
- Web Server: Uvicorn/Gunicorn

**Databases:**
- Primary: PostgreSQL (latest stable)
- Cache: Redis
- Object Storage: AWS S3 (reports, logs)

**Infrastructure:**
- Containerization: Docker
- Orchestration: Docker Compose (local), AWS ECS (production)
- CI/CD: GitHub Actions
- Cloud Provider: AWS

### 4.2 Development Environment

**TR-4.2.1**: Local development setup
- Docker Compose with all services
- Hot reload for frontend and backend
- Local PostgreSQL and Redis
- Environment variables configuration
- Sample data seeding script

**TR-4.2.2**: Development tools
- Python: Poetry or pip-tools for dependency management
- Node.js: npm for Angular dependencies
- Git hooks: Pre-commit linting and formatting
- VS Code / PyCharm configurations

### 4.3 Deployment Environment

**TR-4.3.1**: AWS production architecture
- ECS Fargate for containerized services (API, workers)
- RDS PostgreSQL (Multi-AZ for high availability)
- ElastiCache Redis
- Application Load Balancer for API
- CloudFront + S3 for Angular SPA
- Secrets Manager for API keys
- CloudWatch for logs and metrics

**TR-4.3.2**: Infrastructure as Code
- Terraform or AWS CDK for infrastructure provisioning
- Separate environments: dev, staging, production
- Automated deployments via CI/CD

### 4.4 External Integrations

**TR-4.4.1**: Market data providers
- Primary: Finnhub API (real-time stock data)
- Architecture supports swapping providers via abstraction layer

**TR-4.4.2**: Broker integrations
- Primary: Alpaca (paper and live trading)
- Architecture supports multiple brokers via tool abstraction

**TR-4.4.3**: LLM providers
- Primary: OpenAI API
- Architecture supports multiple providers (Anthropic, local models)

**TR-4.4.4**: Notification services
- Email: AWS SES or SendGrid
- Future: Twilio for SMS

---

## 5. Data Requirements

### 5.1 Core Entities

**Users**
- User ID, email, hashed password
- Subscription tier, status
- Created date, last login
- Broker connections (encrypted)

**Pipelines**
- Pipeline ID, user ID, name, description
- Configuration (JSON/YAML of agent graph)
- Status (draft, active, paused, archived)
- Created/updated timestamps

**Pipeline Executions**
- Execution ID, pipeline ID, user ID
- Start time, end time, duration
- Status (running, completed, failed)
- Current state (serialized PipelineState)
- Cost metrics (tokens, API calls, fees)

**Trades**
- Trade ID, execution ID, user ID
- Symbol, action (BUY/SELL), quantity
- Entry price, fill price, slippage
- Timestamp, broker order ID
- Status (pending, filled, rejected, cancelled)

**Reports**
- Report ID, execution ID, trade ID
- Full reasoning chain (JSON)
- Generated timestamp
- S3 URL for detailed report

**Cost Tracking**
- Record ID, user ID, execution ID
- Timestamp, agent name
- Token usage (input/output), cost
- API calls, cost
- Agent rental time, cost
- Total cost

**Agent Registry** (for marketplace foundation)
- Agent ID, name, version
- Description, author
- Input/output schema
- Pricing (hourly rate)
- Status (active, deprecated)

### 5.2 Data Retention

- **Trade history**: Indefinite retention
- **Pipeline executions**: 90 days detailed, then summarized
- **Reports**: 30 days in database, then S3 archival
- **Logs**: 14 days in CloudWatch, then S3 archival
- **Cost data**: Indefinite retention for billing

---

## 6. Out of Scope for MVP

The following features are explicitly **not** included in the MVP but may be considered for future phases:

**OS-6.1**: Backtesting engine
- Historical strategy simulation
- Performance metrics calculation
- Optimization tools

**OS-6.2**: Multi-asset support
- Cryptocurrency trading
- Forex trading
- Options/futures

**OS-6.3**: Advanced agent features
- Custom agent uploads by users
- Agent versioning and A/B testing
- Community-contributed agents

**OS-6.4**: Advanced notifications
- SMS notifications
- Webhook integrations
- Slack/Discord integrations

**OS-6.5**: Regulatory compliance
- FINRA reporting
- SEC compliance features
- Audit trails for regulators

**OS-6.6**: Advanced UI features
- Mobile applications
- Advanced charting
- Social features (sharing strategies)

**OS-6.7**: Agent marketplace
- Agent publishing workflow
- Revenue sharing
- Agent reviews and ratings

**OS-6.8**: Advanced analytics
- ML-powered performance insights
- Strategy optimization suggestions
- Competitive benchmarking

**OS-6.9**: Portfolio management
- Multi-account support
- Portfolio rebalancing
- Tax optimization

---

## 7. Success Criteria

The MVP will be considered successful when:

1. **Functional Completeness**
   - Core MVP agents implemented and working:
     - At least 2 trigger agent types (Time-Based free + one paid type)
     - Market Data Agent
     - Bias Agent
     - Strategy Agent (with stop loss & targets)
     - Risk Manager Agent
     - Trade Manager Agent
     - Reporting Agent
   - Pipeline builder allows creating and executing pipelines
   - At least 1 broker integration working (paper trading)
   - Demo mode fully functional

2. **Performance Targets**
   - Complete pipeline execution < 60 seconds
   - Support 100 concurrent pipeline executions
   - API response times meet NFR targets

3. **User Experience**
   - New user can create and run demo pipeline in < 10 minutes
   - Clear visibility into costs and trade reasoning
   - No critical bugs in core flows

4. **Business Validation**
   - 10+ beta users successfully running pipelines
   - Cost per user < $5/month (infrastructure + LLM)
   - Positive user feedback on core features

---

## 8. Assumptions & Dependencies

### 8.1 Assumptions

- Users have basic understanding of trading concepts
- Users have access to broker accounts (or willing to create paper trading accounts)
- Market data APIs (Finnhub) remain accessible and affordable
- OpenAI API remains available with current pricing
- AWS services remain available

### 8.2 Dependencies

- **External APIs**: Finnhub (market data), broker APIs (Alpaca)
- **Third-party services**: OpenAI, AWS
- **Open-source libraries**: CrewAI, FastAPI, Angular, Celery
- **Infrastructure**: Domain name, SSL certificates, AWS account

### 8.3 Risks

- **Cost Risk**: OpenAI token costs may be higher than projected
  - Mitigation: Aggressive prompt optimization, migrate to local models
  
- **Regulatory Risk**: Trading platform may require licenses
  - Mitigation: User brings own broker account; we're a tool, not a broker
  
- **API Risk**: External API rate limits or outages
  - Mitigation: Caching, fallback providers, graceful degradation
  
- **Market Risk**: Users may lose money on trades
  - Mitigation: Clear disclaimers, risk management agent, demo mode
  
- **Scalability Risk**: Architecture may not scale as expected
  - Mitigation: Load testing, incremental rollout, monitoring

---

## 9. Glossary

- **Agent**: An AI-powered component that performs a specific task in the trading pipeline
- **Pipeline**: A connected sequence of agents that work together to analyze markets and execute trades
- **Trigger Agent**: A specialized agent type that pauses pipeline execution until specific conditions are met (time, price, indicators, news). Multiple trigger agent types exist (time-based, technical, price, news).
- **CrewAI**: Python framework for orchestrating multi-agent systems
- **State**: The data object passed between agents containing all pipeline information
- **Tool**: A utility function that agents use to interact with external systems (APIs, databases)
- **Paper Trading**: Simulated trading with fake money for testing strategies
- **Stop Loss**: A price level where a trade is automatically closed to limit losses
- **Target Price**: A profit-taking price level; Strategy Agent provides Target 1 and Target 2 for staged exits
- **Position Sizing**: The number of shares/units to trade, calculated by Risk Manager based on account risk
- **P&L**: Profit and Loss
- **Token**: Unit of text processed by LLM models (roughly 4 characters per token)
- **Slippage**: The difference between expected trade price and actual execution price

---

**Document Version**: 1.0  
**Last Updated**: October 22, 2025  
**Authors**: Principal Engineering Team  
**Status**: Draft for Review

