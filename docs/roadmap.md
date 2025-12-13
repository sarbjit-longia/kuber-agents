# Product Roadmap

## Overview

This roadmap outlines the development plan for the Trading Platform from initial setup through MVP launch and beyond. The roadmap is divided into milestones with clear deliverables and timelines.

**Target MVP Launch**: 10 weeks from start  
**Target Beta Launch**: 12 weeks from start

---

## Milestone 0: Project Foundation ✅ COMPLETE
**Duration**: Week 1  
**Status**: ✅ **COMPLETED**

### Tasks

**Project Setup**
- [x] Create Git repository and branch structure
- [x] Create documentation (requirements, design, roadmap, context)
- [x] Define coding standards and conventions
- [x] Set up project management tools (TODOs, documentation)

**Infrastructure Setup**
- [x] Set up Docker development environment
- [x] Configure docker-compose.yml with all services
- [ ] Create AWS accounts (dev, staging, prod) - Deferred
- [ ] Set up Terraform for infrastructure as code - Deferred
- [ ] Configure CI/CD pipeline (GitHub Actions) - Deferred

**Backend Foundation**
- [x] Initialize FastAPI project structure
- [x] Set up PostgreSQL with Alembic migrations
- [x] Configure Redis connection
- [x] Implement basic health check endpoint
- [x] Set up logging and monitoring (structlog)

**Frontend Foundation**
- [x] Initialize Angular project
- [x] Set up Angular Material / UI framework
- [x] Configure routing and state management
- [x] Create base layout components (navbar, etc.)

### Deliverables
- ✅ Complete documentation suite
- ✅ Working Docker Compose environment
- ✅ Basic FastAPI app with health check
- ✅ Basic Angular app with routing

---

## Milestone 1: Authentication & Core APIs ✅ COMPLETE
**Duration**: Week 2  
**Status**: ✅ **COMPLETED**

### Tasks

**Authentication**
- [x] User registration and login endpoints
- [x] JWT token generation and validation
- [x] Password hashing (bcrypt)
- [x] JWT middleware for protected routes
- [x] Frontend login/register forms
- [x] Token storage and automatic refresh

**Database Models**
- [x] User model and table (with subscription fields)
- [x] Pipeline model and table
- [x] Execution model and table
- [x] Scanner model and table
- [x] Database migrations (Alembic)

**API Development**
- [x] User profile endpoints (GET, subscription info)
- [x] Pipeline CRUD endpoints
- [x] Scanner CRUD endpoints
- [x] Execution endpoints
- [x] Basic error handling
- [x] Request validation with Pydantic
- [x] API documentation (Swagger at /docs)

**Frontend**
- [x] Authentication service
- [x] Auth guard for protected routes
- [x] Login/register pages
- [x] Session management

### Deliverables
- ✅ Working authentication system
- ✅ User can register, login, and manage profile
- ✅ API documentation available at /docs
- ✅ Frontend authentication flow complete

---

## Milestone 2: Agent Framework & First Agents ✅ COMPLETE
**Duration**: Weeks 3-4  
**Status**: ✅ **COMPLETED**

### Week 3: Framework + Market Data + Trigger

**Agent Framework**
- [x] Define `BaseAgent` abstract class
- [x] Implement `PipelineState` schema
- [x] Create agent registry system (`AGENT_REGISTRY`)
- [x] Implement agent serialization (to_dict/from_dict)
- [x] Add agent metadata and config schema support
- [x] Factory pattern for agent instantiation

**LLM Integration**
- [x] OpenAI provider implementation
- [x] Token counting middleware (tiktoken)
- [x] Cost tracking for LLM calls (@track_llm_cost decorator)
- [x] Error handling and retries

**Tools Framework**
- [x] Base tool interface (`BaseTool`)
- [x] Tool registry system (`TOOL_REGISTRY`)
- [x] Market data tool (Finnhub + Mock implementations)
- [x] User-configurable tools (attach to agents)

**Agent Implementations**
- [x] Time-Based Trigger Agent (FREE) - Deprecated (replaced by signal system)
- [x] Market Data Agent
  - [x] Real-time quote fetching
  - [x] Multiple timeframe support
  - [x] Technical indicator calculation
  - [x] Accepts attached tools (market_data or mock_market_data)

### Week 4: Analysis Agents

**Agent Implementations**
- [x] Bias Agent (CrewAI crew)
  - [x] Multi-timeframe analysis (1h, 4h, 1d)
  - [x] Market analyst sub-agent
  - [x] Comprehensive bias reasoning
  - [x] LLM-powered tool detection from instructions
  - [x] Auto-detected tools integration
- [x] Strategy Agent (CrewAI crew + LLM Tools)
  - [x] Entry/stop/target calculation
  - [x] Complete trade plan generation
  - [x] Risk/reward analysis
  - [x] **ICT Strategy Tools** (FVG, Liquidity, Market Structure, Premium/Discount)
  - [x] **Indicator Tools** (RSI, SMA, MACD, Bollinger Bands)
  - [x] **Tool Executor** (dynamic tool invocation based on instructions)
  - [x] **Chart Data Generation** (TradingView annotations)
  - [x] **Instructions-based strategy** (plain English → tool detection)

**LLM-Powered Strategy System (NEW)** 🆕
- [x] Tool Detection Service (auto-detect tools from user instructions)
- [x] Strategy Tools Registry (OpenAI function calling format)
- [x] ICT Concepts Implementation:
  - [x] Fair Value Gap (FVG) Detector
  - [x] Liquidity Analyzer (pools, grabs, hunts)
  - [x] Market Structure (BOS/CHoCH, trends)
  - [x] Premium/Discount Zones
- [x] Indicator Tools (wrapper for Data Plane indicators)
- [x] Tool cost estimation and pricing model
- [x] Unsupported feature detection

**Testing**
- [x] Mock market data tool for development
- [x] Integration tests with full pipeline execution
- [ ] Unit test coverage > 70% - Deferred

### Deliverables
- ✅ 6+ working agents: Market Data, Bias, Strategy, Risk Manager, Order Manager, Reporting
- ✅ Agent framework with serialization and metadata
- ✅ Tools framework with user-configurable attachments
- ✅ Mock tools for development/testing
- ✅ **LLM-powered strategy system with ICT tools** 🆕
- ✅ **Instruction-based strategy creation** 🆕

---

## Milestone 3: Remaining Agents & Execution Engine ✅ COMPLETE
**Duration**: Week 5  
**Status**: ✅ **COMPLETED**

### Agent Implementations
- [x] Strategy Agent (CrewAI crew)
  - [x] Pattern recognition
  - [x] Entry/stop/target calculation
  - [x] Complete trade plan generation
- [x] Risk Manager Agent
  - [x] Position sizing
  - [x] Risk rules validation
  - [x] Trade approval logic
- [x] Order Manager Agent (Trade Manager)
  - [x] Broker tool (Alpaca integration)
  - [x] Order submission
  - [x] Fill confirmation
  - [x] Paper trading support
- [x] Reporting Agent
  - [x] Collect reasoning chain from all agents
  - [x] Generate structured reports (`AgentReport` schema)
  - [x] Store in execution artifacts (JSONB)
  - [ ] S3 storage - Deferred

### Celery Integration
- [x] Set up Celery with Redis
- [x] Create pipeline execution task (`execute_pipeline`)
- [x] Implement retry logic
- [x] Error handling and status tracking
- [x] Celery Beat for periodic scheduling

### Pipeline Orchestration
- [x] Implement pipeline executor (`backend/app/orchestration/executor.py`)
- [x] Agent-to-agent state passing (`PipelineState`)
- [x] Error handling and partial execution support
- [x] Dynamic agent instantiation from pipeline config
- [x] Cost tracking during execution
- [x] Metrics collection (OpenTelemetry)

### Deliverables
- ✅ All 6+ MVP agents implemented and working
- ✅ Working Celery task queue with Redis backend
- ✅ Pipeline orchestration (without CrewAI Flow - using sequential execution)
- ✅ End-to-end pipeline execution (signal → agents → order → report)

---

## Milestone 4: Pipeline Builder UI ✅ COMPLETE
**Duration**: Week 6  
**Status**: ✅ **COMPLETED**

### Pipeline Builder
- [x] Agent palette component (drag source)
- [x] Canvas component with drag-drop (Angular CDK)
- [x] Node rendering (agents as visual cards)
- [x] Edge rendering (connections/flow lines)
- [x] Node selection and highlighting
- [x] Node deletion
- [x] Tool attachment UI (attach tools to agents)
- [x] **Auto-detected tools visual representation** 🆕

### Agent Configuration
- [x] Fetch agent metadata from API (`/api/v1/agents`)
- [x] JSON Schema Form integration (@ajsf/core)
- [x] Dynamic form generation from agent config schemas
- [x] Config panel component (right sidebar)
- [x] Form validation
- [x] Save/Cancel buttons for config changes
- [x] Tool configuration panel
- [x] **Agent Instructions Component** (plain English input) 🆕
- [x] **PDF Strategy Document Upload** 🆕
- [x] **Tool Detection Integration** (frontend) 🆕
- [x] **Auto-detected tools display with cost** 🆕

### Pipeline Management
- [x] Pipeline list view (card-based)
- [x] Create new pipeline
- [x] Edit existing pipeline (load from database)
- [x] Delete pipeline
- [x] Activate/deactivate pipeline
- [x] Pipeline settings dialog (name, description, trigger mode, scanner, signals)
- [x] Pipeline validation (ensure all agents configured, tools attached)

### File Management (NEW) 🆕
- [x] Storage abstraction layer (LocalDisk for dev, S3 for prod)
- [x] PDF Parser (async with pdfplumber)
- [x] File Upload API (`/api/v1/files/upload`)
- [x] File Download API (`/api/v1/files/download`)
- [x] File Delete API (`/api/v1/files/delete`)
- [x] Strategy document storage and retrieval

### Deliverables
- ✅ Working visual pipeline builder with intuitive UX
- ✅ User can drag-drop agents onto canvas
- ✅ Dynamic config forms for each agent and tool
- ✅ Save/load pipelines from database
- ✅ Scanner and signal subscription configuration
- ✅ **Instructions-based agent configuration** 🆕
- ✅ **PDF strategy document support** 🆕
- ✅ **Visual tool detection and cost estimation** 🆕

---

## Milestone 5: Monitoring & Execution Control ✅ COMPLETE
**Duration**: Week 7  
**Status**: ✅ **COMPLETED**

### WebSocket Implementation
- [x] WebSocket server in FastAPI
- [x] Connection manager (`WebSocketManager`)
- [x] Event emitter from pipeline executor
- [x] WebSocket client in Angular (`WebSocketService`)
- [x] Polling fallback on WebSocket failure
- [x] Real-time execution updates (agent progress, status changes)

### Monitoring Dashboard
- [x] Active executions list (monitoring page `/monitoring`)
- [x] Pipeline execution detail view (per-execution drill-down)
- [x] Real-time agent progress (progress bar, current agent)
- [x] Live cost accumulation (running total)
- [x] Execution logs viewer (agent reports, errors)
- [x] Status indicators (pending, running, completed, failed)
- [x] Execution source display (periodic vs scanner name)
- [x] Local timezone formatting for timestamps
- [x] Filter by pipeline, status, date range

### Execution Control
- [x] Execute pipeline immediately (`/api/v1/executions`)
- [x] View execution history
- [x] Execution detail page with full agent breakdown
- [x] Real-time status updates via WebSocket
- [x] Pipeline activate/deactivate toggle
- [ ] Stop/cancel running execution - Future
- [ ] Pause/resume - Future

### Reports
- [x] Agent reports displayed in execution detail
- [x] Structured report schema (`AgentReport`)
- [x] Reasoning chain display per agent
- [x] Error display for failed agents
- [x] Execution artifacts stored in database (JSONB)
- [x] **Strategy Visualization** (interactive TradingView charts) 🆕
- [x] **Chart Annotation Builder** (convert tool results to chart data) 🆕
- [x] **Chart Component** (TradingView integration) 🆕
- [ ] Report list view (separate page) - Future
- [ ] Export reports (PDF/JSON) - Future

### Strategy Visualization (NEW) 🆕
- [x] Chart Annotation Builder Service
- [x] Convert FVG/Liquidity/Indicator data to chart annotations
- [x] TradingView Charting Library integration
- [x] Interactive chart rendering (candles + annotations)
- [x] Strategy decision visualization (entry/stop/target)
- [x] Agent reasoning display on charts
- [x] Chart data storage in execution_artifacts

### Deliverables
- ✅ Real-time monitoring dashboard with execution list
- ✅ WebSocket communication for live updates
- ✅ Execution detail view with agent reports
- ✅ Timezone-aware UI (local time display)
- ✅ Structured reporting system
- ✅ **Interactive strategy visualization with charts** 🆕

---

## Milestone 6.5: LLM-Powered Strategy System & Visualization ✅ COMPLETE 🆕
**Duration**: Recent sprint  
**Status**: ✅ **COMPLETED**

### LLM-Powered Tool Detection & Execution
- [x] Tool Detection Service (GPT-4 function calling)
  - [x] Auto-detect required tools from plain English instructions
  - [x] Parameter inference for each tool
  - [x] Cost estimation before execution
  - [x] Unsupported feature detection
  - [x] Confidence scoring
- [x] Strategy Tools Registry (OpenAI function calling format)
- [x] Tool pricing model (per-execution costs)
- [x] Tool Executor (dynamic tool invocation)

### ICT Strategy Tools Implementation
- [x] Fair Value Gap (FVG) Detector
  - [x] Bullish/Bearish FVG detection
  - [x] Gap size calculation
  - [x] Fill status tracking
  - [x] Historical FVG analysis
- [x] Liquidity Analyzer
  - [x] Swing high/low detection
  - [x] Liquidity pool identification
  - [x] Liquidity grab detection
  - [x] Hunt pattern recognition
- [x] Market Structure Tool
  - [x] BOS (Break of Structure) detection
  - [x] CHoCH (Change of Character) detection
  - [x] Trend identification (bullish/bearish)
  - [x] Structure level tracking
- [x] Premium/Discount Zones
  - [x] Daily range calculation
  - [x] Equilibrium identification
  - [x] Zone classification (premium/discount/equilibrium)

### Technical Indicator Tools
- [x] RSI Tool (Data Plane integration)
- [x] SMA Tool (multiple periods: 20, 50, 200)
- [x] MACD Tool (12/26/9)
- [x] Bollinger Bands Tool (period: 20)
- [x] Indicator data fetching from Data Plane
- [x] Caching and performance optimization

### Strategy Agent Enhancements
- [x] Instructions-based strategy configuration
- [x] PDF strategy document support
- [x] Auto-detected tool integration
- [x] Tool execution during agent processing
- [x] Chart data generation from tool results
- [x] Structured output with visualizations

### File Management & Storage
- [x] Storage Service abstraction layer
  - [x] LocalDiskStorage (development)
  - [x] S3Storage (production)
  - [x] Async file I/O with thread pools
- [x] PDF Parser
  - [x] Text extraction with pdfplumber
  - [x] Async processing
  - [x] Clean text output
- [x] File Upload API (`/api/v1/files/upload`)
- [x] File Download API (`/api/v1/files/download`)
- [x] File Delete API (`/api/v1/files/delete`)
- [x] Strategy document storage

### Strategy Visualization
- [x] Chart Annotation Builder Service
  - [x] FVG annotations (rectangles)
  - [x] Liquidity annotations (horizontal lines)
  - [x] Market structure annotations (BOS/CHoCH markers)
  - [x] Premium/Discount zones (filled areas)
  - [x] Indicator overlays (RSI, SMA, etc.)
  - [x] Entry/Stop/Target markers
- [x] TradingView Charting Library integration
- [x] Strategy Chart Component (Angular)
  - [x] Interactive candlestick charts
  - [x] Annotation rendering
  - [x] Decision summary display
  - [x] Reasoning steps visualization
  - [x] Trade details panel
- [x] Chart data storage in execution_artifacts

### Frontend Components
- [x] Agent Instructions Component
  - [x] Plain English instructions textarea
  - [x] PDF strategy document upload
  - [x] Tool detection trigger
  - [x] Auto-detected tools display
  - [x] Cost estimation display
  - [x] Error handling and validation
- [x] Tool Detection Service (Angular)
- [x] File Upload Service (Angular)
- [x] Strategy Chart Component
- [x] Auto-detected tools visual on canvas
  - [x] Tool nodes attached to agents
  - [x] Visual representation with metadata
  - [x] Tooltip information

### Backend API Enhancements
- [x] Tool Validation Endpoint (`/api/v1/agents/validate-instructions`)
- [x] Available Tools Endpoint (`/api/v1/agents/tools/available`)
- [x] User Profile Endpoint (`/api/v1/users/me`)
- [x] Fixed async/sync dependency issues
  - [x] Proper async/await patterns
  - [x] Thread pool for blocking I/O
  - [x] Consistent AsyncSession usage

### Bug Fixes & Code Quality
- [x] Fixed async PDF parsing (no event loop blocking)
- [x] Fixed async storage operations (LocalDisk & S3)
- [x] Fixed path construction in file downloads
- [x] Fixed inconsistent newline formatting in FVG output
- [x] Fixed async/sync dependency mismatch in user endpoints
- [x] Error handling improvements
- [x] Type safety enhancements

### Deliverables
- ✅ **LLM-powered strategy system** with automatic tool detection
- ✅ **ICT trading concepts** fully implemented (FVG, Liquidity, Market Structure)
- ✅ **Instruction-based strategy creation** (no coding required)
- ✅ **Interactive strategy visualization** with TradingView charts
- ✅ **PDF strategy document support** with text extraction
- ✅ **Tool-based pricing model** with pre-execution cost estimates
- ✅ **Production-ready async patterns** throughout the stack
- ✅ **Visual tool representation** on canvas with auto-detection

---

## Milestone 7: Cost Tracking & Billing ⚠️ PARTIAL
**Duration**: Week 7 (parallel with Milestone 5)  
**Status**: ⚠️ **PARTIALLY COMPLETE**

### Cost Tracking
- [x] Token counting for all LLM calls (tiktoken)
- [x] Agent runtime tracking (per-second)
- [x] Cost calculation formulas (agent pricing rates)
- [x] Real-time cost accumulation during execution
- [x] Total cost stored per execution
- [ ] API call metering - Deferred
- [ ] Database storage (cost_tracking table) - Deferred

### Billing System
- [x] Agent pricing configuration (metadata in agents)
- [x] Subscription tier enforcement (Phase 1 - soft)
- [x] Signal bucket definitions
- [x] Pipeline limits per tier
- [ ] Budget limit enforcement - Future
- [ ] Budget alert thresholds - Future
- [ ] Historical cost data queries - Future

### UI Components
- [x] Real-time cost display during execution (monitoring page)
- [x] Total cost in execution list
- [x] Subscription info API (`/api/v1/users/me/subscription`)
- [x] **User profile endpoint** (`/api/v1/users/me`) 🆕
- [x] **Tool-based cost estimation** (before execution) 🆕
- [ ] Cost dashboard page - Future
- [ ] Usage charts - Future
- [ ] Budget settings - Future
- [ ] Cost projections - Future

### API Enhancements (NEW) 🆕
- [x] Tool validation API (`/api/v1/agents/validate-instructions`)
- [x] Available tools API (`/api/v1/agents/tools/available`)
- [x] Async user endpoints (proper async/await patterns)
- [x] Fixed async/sync dependency issues in endpoints

### Deliverables
- ✅ Basic cost tracking (per execution total)
- ✅ Agent pricing configured
- ✅ Subscription tier data model (Phase 1)
- ✅ **Tool-based pricing with pre-execution estimates** 🆕
- ⚠️ Budget enforcement - Deferred
- ⚠️ Cost analytics dashboard - Deferred

---

## Milestone 8: Demo Mode & Polishing
**Duration**: Week 8  
**Goal**: Demo mode, testing, and bug fixes

### Demo Mode
- [ ] Pre-configured demo pipeline
- [ ] Demo data generation
- [ ] Paper trading integration
- [ ] Demo user account creation
- [ ] Onboarding flow for new users
- [ ] Guided tour of features

### Testing & QA
- [ ] End-to-end testing (Playwright/Cypress)
- [ ] Load testing (locust)
- [ ] Security testing
- [ ] Cross-browser testing
- [ ] Mobile responsiveness
- [ ] Bug fixes from testing

### Polish
- [ ] UI/UX improvements
- [ ] Loading states and spinners
- [ ] Empty states
- [ ] Error messages
- [ ] Success notifications
- [ ] Accessibility (WCAG 2.1)

### Documentation
- [ ] User documentation
- [ ] API documentation
- [ ] Deployment guide
- [ ] Troubleshooting guide

### Deliverables
- [ ] Working demo mode
- [ ] All critical bugs fixed
- [ ] Polished UI/UX
- [ ] Complete documentation

---

## Milestone 9: MVP Deployment & Beta Launch
**Duration**: Weeks 9-10  
**Goal**: Production deployment and beta user testing

### Week 9: Production Setup

**Infrastructure**
- [ ] Terraform apply to production
- [ ] RDS Multi-AZ setup
- [ ] ElastiCache cluster
- [ ] ECS Fargate services
- [ ] ALB with SSL certificate
- [ ] CloudFront for frontend
- [ ] Route53 domain configuration

**Security**
- [ ] Secrets Manager setup
- [ ] IAM roles and policies
- [ ] Security group configuration
- [ ] Enable encryption at rest
- [ ] SSL/TLS enforcement
- [ ] Rate limiting
- [ ] DDoS protection (AWS Shield)

**Monitoring**
- [ ] CloudWatch alarms
- [ ] Log aggregation
- [ ] Error tracking (Sentry)
- [ ] Performance monitoring
- [ ] Uptime monitoring

**CI/CD**
- [ ] GitHub Actions pipeline tested
- [ ] Automated deployments working
- [ ] Rollback procedure tested

### Week 10: Beta Launch

**Beta Preparation**
- [ ] Create beta user accounts (10-20 users)
- [ ] User onboarding emails
- [ ] Feedback collection system
- [ ] Support channel setup (Discord/Slack)

**Launch**
- [ ] Deploy to production
- [ ] Smoke tests
- [ ] Invite beta users
- [ ] Monitor system health
- [ ] Gather feedback
- [ ] Iterate on issues

**Metrics**
- [ ] User signup tracking
- [ ] Pipeline creation rate
- [ ] Execution success rate
- [ ] Average cost per user
- [ ] User engagement metrics

### Deliverables
- [ ] Production environment live
- [ ] 10+ beta users onboarded
- [ ] System stable and monitored
- [ ] Initial user feedback collected

---

## Scanner Feature Roadmap (Integrated into MVP)

### Phase 1: Manual Scanner ✅ COMPLETE
**Duration**: 1-2 days  
**Status**: ✅ **COMPLETED**

#### Backend Tasks
- [x] Scanner database model (`scanners` table)
- [x] Pipeline model update (add `scanner_id`, `signal_subscriptions`)
- [x] Scanner Pydantic schemas
- [x] Scanner CRUD API endpoints
- [x] Trigger Dispatcher integration (use scanner for matching)
- [x] Alembic migration
- [x] API endpoint: Get available signal types
- [x] Validation: Signal-based pipelines require scanner

#### Frontend Tasks
- [x] Scanner models and TypeScript interfaces
- [x] Scanner service (API calls)
- [x] Scanner management page (`/scanners`)
- [x] Scanner list component (cards view)
- [x] Create/Edit Scanner dialog (manual ticker input)
- [x] Pipeline Settings dialog (scanner selector + signal subscriptions)
- [x] Signal subscription selector
- [x] Integration in Pipeline Builder

#### Features
- [x] Create scanner with name + manual ticker list
- [x] Edit scanner (add/remove tickers)
- [x] Delete scanner (with usage validation)
- [x] List all user scanners
- [x] Select scanner in Pipeline Builder
- [x] Configure signal subscriptions per pipeline
- [x] Preview scanner tickers

#### Deliverables
- ✅ Scanners as reusable, first-class entities
- ✅ Users can create multi-ticker signal-based pipelines
- ✅ Signal filtering by type and confidence threshold
- ✅ Clean separation: Scanner → Signal → Pipeline

---

### Phase 2: Filter-Based Scanner (Future - Week 12+)
**Duration**: 1-2 weeks  
**Goal**: Dynamic scanners with market filters

#### Backend Tasks
- [ ] Ticker universe database table
- [ ] Ticker metadata ingestion (sector, market cap, etc.)
- [ ] Scanner execution engine (apply filters to universe)
- [ ] Scanner result caching (auto-refresh)
- [ ] Scanner scheduling (periodic refresh)
- [ ] Filter query builder

#### Frontend Tasks
- [ ] Visual filter builder UI
- [ ] Filter preview (real-time result count)
- [ ] Scanner result history viewer
- [ ] Filter templates (pre-built popular scanners)

#### Filter Categories
**Basic Filters**:
- Market Cap: Min/Max
- Price: Min/Max
- Volume: Min/Max
- Sector: Multi-select
- Industry: Multi-select

**Technical Filters**:
- RSI: Range
- Moving Averages: SMA/EMA crossovers
- Price vs SMA: Above/Below
- Volume: Above average
- 52-week High/Low: Percentage range

**Fundamental Filters** (if data available):
- P/E Ratio: Min/Max
- Dividend Yield: Min/Max
- EPS Growth: Min/Max

#### Data Source Options
- **Option A**: Pre-downloaded ticker universe (CSV/JSON)
  - Pros: Free, fast, offline-capable
  - Cons: Needs periodic updates, limited data
  
- **Option B**: Free API (Alpha Vantage, Polygon.io)
  - Pros: Real-time data
  - Cons: Rate limits, cost at scale
  
- **Option C**: Paid API (Finviz Elite, Finnhub)
  - Pros: Comprehensive data, fast
  - Cons: Monthly cost ($50-200/month)

**Recommendation**: Start with Option A, add Option B later

#### Deliverables
- Filter-based scanner creation
- Real-time filter preview
- Auto-refresh scanners on schedule
- Scanner result history

---

### Phase 3: Advanced Scanners (Future - Month 3+)
**Duration**: 2-3 weeks  
**Goal**: External integrations and advanced features

#### Features
- **Finviz Integration**: Import screener URLs
- **TradingView Integration**: Import scanner configurations
- **Custom API**: User provides webhook/REST endpoint
- **CSV Import**: Upload ticker lists
- **Scanner Backtesting**: Historical performance
- **Scanner Alerts**: Notify when ticker count changes
- **Shared Scanners**: Community marketplace
- **Scanner Templates**: Pre-built popular scanners
- **Scanner Versioning**: Track changes over time

#### Deliverables
- Multiple scanner integrations
- Scanner marketplace
- Advanced scanner analytics

---

## Subscription & Billing Roadmap

### Phase 1: Data Models & Structure (Current - Week 8)
**Duration**: 2-3 hours  
**Goal**: Add subscription tier infrastructure without enforcement

#### Backend Tasks
- [x] Add `SubscriptionTier` enum (FREE, BASIC, PRO, ENTERPRISE)
- [x] Add subscription fields to User model
- [x] Create signal bucket definitions
- [x] Add environment variable `ENFORCE_SUBSCRIPTION_LIMITS` (default: false)
- [x] Add helper functions for limit checking (soft enforcement)
- [x] Update User schema with subscription info
- [x] Add API endpoint to get user subscription details

#### Frontend Tasks
- [ ] Add subscription models/interfaces
- [ ] Display current tier in user profile
- [ ] Show subscription limits in UI (even if not enforced)
- [ ] Add "Dev Mode" badges where limits shown but not enforced

#### Signal Bucket Definitions
```
FREE: External signals (webhooks, TrendSpider, etc.)
BASIC ($29/month): 
  - External + Golden Cross, Death Cross, RSI, MACD, Volume Spike
  - Max 5 active pipelines
  
PRO ($99/month):
  - All BASIC + News Sentiment, Volatility, Support/Resistance
  - Max 20 active pipelines
  
ENTERPRISE ($299/month):
  - All signals + Custom signals
  - Unlimited pipelines
  - Priority processing
```

#### Deliverables
- ✅ Subscription tier architecture in place
- ✅ UI shows future state (tiers, limits)
- ✅ Zero friction in development (enforcement disabled)
- ✅ Ready to enable enforcement with single ENV variable

---

### Phase 2: Enforcement & Billing (Future - Week 12+)
**Duration**: 2-3 weeks  
**Goal**: Enforce subscription limits and integrate billing

#### Backend Tasks
- [ ] Set `ENFORCE_SUBSCRIPTION_LIMITS=true` in production
- [ ] Implement pipeline creation limit enforcement
- [ ] Implement signal access enforcement in trigger-dispatcher
- [ ] Add upgrade/downgrade logic
- [ ] Stripe integration for payment processing
- [ ] Subscription management API endpoints
- [ ] Webhook handlers for Stripe events
- [ ] Usage metering and invoicing
- [ ] Free tier rate limiting (100 external signals/day)
- [ ] Grace period handling (subscription expired)

#### Frontend Tasks
- [ ] Subscription management page
- [ ] Upgrade prompts when limits hit
- [ ] Payment form integration (Stripe Elements)
- [ ] Billing history page
- [ ] Usage dashboard (signals used, pipelines active)
- [ ] Subscription cancellation flow
- [ ] Plan comparison page

#### Billing Features
- [ ] Monthly recurring billing
- [ ] Pro-rated upgrades/downgrades
- [ ] Invoice generation
- [ ] Payment method management
- [ ] Failed payment handling
- [ ] Subscription renewal reminders
- [ ] Usage-based add-ons (extra pipelines: $5 per 5 pipelines)

#### Admin Features
- [ ] Admin panel for subscription management
- [ ] Override subscription limits
- [ ] Manual subscription adjustments
- [ ] Billing analytics dashboard
- [ ] Churn prevention features

#### Deliverables
- [ ] Full subscription enforcement active
- [ ] Stripe payment processing working
- [ ] Users can upgrade/downgrade
- [ ] Billing automation complete
- [ ] Revenue tracking in place

---

### Phase 3: Advanced Monetization (Future - Month 3+)
**Duration**: 2-3 weeks  
**Goal**: Advanced pricing and marketplace features

#### Features
- [ ] À la carte signal purchases ($15/month per Pro signal)
- [ ] Custom signal bucket creation
- [ ] Signal marketplace (buy/sell custom signals)
- [ ] Annual billing discount (20% off)
- [ ] Enterprise custom pricing
- [ ] Referral program
- [ ] Volume discounts for teams
- [ ] Academic/non-profit pricing

#### Deliverables
- [ ] Flexible monetization options
- [ ] Signal marketplace launched
- [ ] Referral program active

---

## Milestone 10: Signal Generator Service ✅ COMPLETE 🆕
**Duration**: Recent sprint  
**Status**: ✅ **COMPLETED**

### Signal Generation Infrastructure
- [x] Standalone signal-generator microservice
- [x] 18 technical indicator generators (RSI, MACD, Bollinger Bands, etc.)
- [x] Mock signal generator (for testing)
- [x] Kafka integration for signal publishing
- [x] OpenTelemetry metrics instrumentation
- [x] Prometheus metrics endpoint
- [x] Grafana dashboard (signal-specific metrics)

### Technical Indicator Generators Implemented
- [x] Golden Cross Signal Generator (SMA 50/200 crossover)
- [x] Death Cross Signal Generator (SMA 50/200 crossover)
- [x] RSI Signal Generator (oversold/overbought)
- [x] MACD Signal Generator (crossovers)
- [x] Volume Spike Signal Generator
- [x] Bollinger Bands Signal Generator (breakouts/squeezes)
- [x] Stochastic Signal Generator (%K/%D crossovers)
- [x] ADX Signal Generator (trend strength)
- [x] EMA Crossover Signal Generator (12/26 crossover)
- [x] ATR Signal Generator (volatility spikes)
- [x] CCI Signal Generator (overbought/oversold)
- [x] Stochastic RSI Signal Generator
- [x] Williams %R Signal Generator
- [x] Aroon Signal Generator (trend direction)
- [x] MFI Signal Generator (money flow)
- [x] OBV Signal Generator (on-balance volume)
- [x] SAR Signal Generator (parabolic SAR reversals)

### Market Data Provider Abstraction
- [x] Provider abstraction layer (Strategy pattern)
- [x] MarketDataProvider interface
- [x] FinnhubProvider implementation
  - [x] Official finnhub-python SDK integration
  - [x] Async/await patterns (thread pool for blocking calls)
  - [x] Proper resolution format (D/W/M instead of 1d/1w/1m)
  - [x] Comprehensive error handling
- [x] MarketDataFactory (singleton pattern)
- [x] Backward-compatible MarketDataFetcher wrapper
- [x] Environment-based provider selection
- [x] Easy provider switching (MARKET_DATA_PROVIDER env var)

### Provider Monitoring & Metrics
- [x] provider_api_calls_total (counter by endpoint, status)
- [x] provider_api_call_duration_seconds (histogram by endpoint)
- [x] provider_api_errors_total (counter by error type)
- [x] Rate limit tracking (timestamp-based calculation)
- [x] Grafana dashboard panels:
  - [x] Data Provider display
  - [x] Rate Limit Remaining gauge
  - [x] Rate Limit Usage gauge
  - [x] API Calls Rate timeseries
  - [x] API Call Duration (p50/p95)
  - [x] Rate Limit Usage Over Time

### Signal-Specific Metrics
- [x] signals_generated_total (by generator, type, source)
- [x] generator_scans_total (by generator)
- [x] generator_scan_errors_total (by generator)
- [x] generator_scan_duration_seconds (histogram)
- [x] Grafana dashboard panels:
  - [x] Signals by Generator (5min)
  - [x] Signals by Type (5min)
  - [x] Total Signals Distribution (pie charts)
  - [x] Generator Performance Summary (table)
  - [x] Generator Scan Duration (p50/p95)
  - [x] Generator Scan Errors

### Configuration & Deployment
- [x] Configurable scan intervals per generator (2-5 min)
- [x] Configurable timeframes (D, W, M)
- [x] Watchlist configuration (config/watchlist.json)
- [x] Docker containerization
- [x] Docker Compose integration
- [x] Health check endpoint
- [x] Graceful shutdown handling

### Documentation
- [x] Provider abstraction architecture document
- [x] Benefits and design rationale
- [x] Usage examples and migration guide
- [x] Configuration documentation
- [x] Supported resolutions and indicators
- [x] Future provider addition guide

### Bug Fixes & Improvements
- [x] Fixed Finnhub resolution format (1d → D, 1w → W, etc.)
- [x] Fixed rate limiting on startup (natural staggering)
- [x] Fixed 422 "Wrong resolution" errors
- [x] Improved error handling for API failures
- [x] Added retry logic with graceful degradation

### Deliverables
- ✅ **18 working signal generators** with technical indicators
- ✅ **Provider abstraction layer** for easy data source switching
- ✅ **Comprehensive monitoring** with Grafana dashboards
- ✅ **Kafka integration** for signal publishing
- ✅ **Rate limit tracking** with real-time metrics
- ✅ **Production-ready signal generation** microservice
- ✅ **Extensible architecture** ready for additional providers (Alpha Vantage, Yahoo Finance, etc.)

---

## Post-MVP Roadmap (Future Phases)

### Data Plane Service
**Status**: ✅ Phase 1 & 2 COMPLETE

#### Phase 1: Basic Caching (✅ Complete)
- [x] Universe discovery (hot/warm tickers)
- [x] Quote caching with smart TTL
- [x] On-demand candle fetching
- [x] Market Data Agent integration (v2.0 - FREE)
- [x] OpenTelemetry metrics
- [x] Grafana dashboard

#### Phase 2: Technical Indicators (✅ Complete)
- [x] Finnhub-based indicators (SMA, EMA, RSI, MACD, Bollinger Bands)
- [x] Indicator caching (5min TTL)
- [x] `/data/indicators/{ticker}` API endpoint
- [x] Pre-fetch task for universe tickers
- [x] Grafana indicator metrics (3 new panels)

#### Phase 3: TimescaleDB Storage (Future)
- [ ] Store historical OHLCV in TimescaleDB
- [ ] Continuous aggregates (5m from 1m candles)
- [ ] Data compression and retention policies
- [ ] Backfill 500 days of historical data

### Phase 2: Enhanced Features (Weeks 11-14)
- [ ] News-Based Trigger Agent
- [ ] Local LLM integration for simple tasks
- [ ] Backtesting engine
- [ ] Multi-symbol support (watchlists)
- [ ] SMS notifications
- [ ] Advanced charting
- [ ] Performance analytics
- [ ] Strategy templates

### Phase 3: Marketplace Foundation (Weeks 15-18)
- [ ] Agent versioning system
- [ ] Agent publishing workflow
- [ ] Agent approval/review process
- [ ] Marketplace UI
- [ ] Agent pricing and monetization
- [ ] Revenue sharing
- [ ] Agent ratings and reviews
- [ ] Community features

### Phase 4: Multi-Asset Support (Weeks 19-22)
- [ ] Cryptocurrency support
- [ ] Forex support
- [ ] Options trading
- [ ] Portfolio management
- [ ] Multi-account support
- [ ] Position tracking across accounts

### Phase 5: Enterprise Features (Weeks 23-26)
- [ ] Custom agent uploads
- [ ] Team collaboration
- [ ] White-label solution
- [ ] Advanced compliance features
- [ ] Audit trails
- [ ] Regulatory reporting
- [ ] SSO integration

---

## Success Metrics

### MVP Success Criteria
- **Technical**:
  - All 8+ agents working
  - < 60s average pipeline execution
  - > 95% uptime
  - < 5 critical bugs
  
- **Business**:
  - 10+ active beta users
  - 50+ pipelines created
  - 100+ trades executed
  - Average cost per user < $5/month
  - Positive user feedback (NPS > 40)

### Growth Targets (6 months post-MVP)
- 100+ paying users
- 1,000+ pipelines created
- 10,000+ trades executed
- 5+ community-contributed agents
- Break-even on infrastructure costs

---

## Risk Mitigation

### Technical Risks
- **LLM Cost Overruns**: Implement aggressive token optimization, migrate to local models
- **Scaling Issues**: Load testing, horizontal scaling, caching
- **API Rate Limits**: Caching, fallback providers, rate limiting

### Business Risks
- **Regulatory Compliance**: Legal review, disclaimers, user-brings-broker model
- **User Losses**: Demo mode, risk warnings, paper trading default
- **Competition**: Fast iteration, unique features, focus on UX

### Operational Risks
- **Downtime**: Multi-AZ deployment, automated failover, monitoring
- **Security Breach**: Regular security audits, pen testing, bug bounty
- **Data Loss**: Automated backups, point-in-time recovery

---

## Resource Requirements

### Team
- 1 Backend Engineer (Python/FastAPI)
- 1 Frontend Engineer (Angular)
- 1 DevOps Engineer (AWS/Terraform)
- 0.5 Designer (UI/UX)
- 0.5 QA Engineer

### Budget
- AWS: $300/month during development, $500-800/month in production
- OpenAI API: $200-500/month (depends on usage)
- Market Data: $100/month (Finnhub)
- Domain & SSL: $50/year
- Tools (GitHub, Sentry, etc.): $100/month

### Timeline
- MVP: 10 weeks
- Beta: 2 weeks
- Production Launch: Week 12

---

**Document Version**: 1.0  
**Last Updated**: October 2025  
**Status**: Active Development  
**Next Review**: End of Week 2

