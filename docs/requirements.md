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

The platform uses a **dual revenue model** combining subscriptions and pay-per-use:

#### 1.3.1 Subscription Tiers (Signal Access)

Users subscribe to **Signal Buckets** that determine which trading signals they can access:

**FREE Tier ($0/month)**:
- External signals only (webhooks, TrendSpider integration)
- 2 active pipelines maximum
- 100 external signal triggers/day
- Community support

**BASIC Tier ($29/month)**:
- Basic Signal Bucket: Golden Cross, Death Cross, RSI, MACD, Volume Spike (5 signals)
- Includes all FREE tier signals
- 5 active pipelines maximum
- Unlimited signal triggers
- Email support

**PRO Tier ($99/month)**:
- Pro Signal Bucket: All BASIC + News Sentiment, Volatility, Support/Resistance (9 signals)
- 20 active pipelines maximum
- Priority signal processing
- Chat support + API access

**ENTERPRISE Tier ($299/month or custom)**:
- Enterprise Signal Bucket: All signals + Dark Pool, Options Flow, Custom AI (15+ signals)
- Unlimited pipelines
- Custom signal development
- Dedicated support + SLA

**Add-ons**:
- Extra pipelines: $5/month per 5 pipelines
- Individual Pro signals à la carte: $15/month each
- Custom scanner feeds: $20/month

#### 1.3.2 Agent Usage Fees (Pay-Per-Use)

Agents charge based on actual usage when pipelines execute:

**Agent Rental Fees**:
- **Free Agents**: Market Data, Time Trigger ($0/hour)
- **Basic Agents**: Risk Manager, Reporting ($0.05/hour)
- **Premium Agents**: Bias Analysis, Strategy Generation ($0.10/hour)
- **Enterprise Agents**: Custom agents (variable pricing)

**Billing Granularity**:
- Charged only when pipelines actively running
- Not charged during trigger wait states
- Per-second billing, rounded to nearest minute
- Costs tracked in real-time during execution

**LLM API Costs** (pass-through + markup):
- OpenAI API costs + 20% markup
- Token counting and tracking per agent
- Budget limits and alerts

#### 1.3.3 Combined Example

**User on PRO tier ($99/month) running 1 pipeline**:
```
Monthly Subscription:        $99.00  (Pro tier)
Pipeline runs 10 times/day × 30 days = 300 executions
Average execution: 2 minutes, 3 agents (1 free, 2 premium)

Agent costs:
  Market Data Agent:  0 min × $0.00 = $0.00
  Bias Agent:       600 min × $0.10/hr = $1.00
  Strategy Agent:   600 min × $0.10/hr = $1.00
                                       -------
Total Monthly:                        $101.00
```

**Key Benefits**:
- Predictable base cost (subscription)
- Pay only for execution (usage fees)
- No surprise bills (budget limits)
- Scale usage independently of subscription

#### 1.3.4 Future Monetization

- **Agent Marketplace**: Community-contributed agents with revenue sharing
- **Strategy Templates**: Pre-built pipeline templates ($5-20 each)
- **Backtesting Credits**: Pay per backtest run
- **Premium Data Feeds**: Enhanced market data subscriptions
- **White-Label**: Enterprise custom branding

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

**FR-2.2.5**: Users shall be able to configure pipeline execution modes
- **RUN_ONCE**: Pipeline runs once when manually started, then stops
- **RUN_CONTINUOUS**: Pipeline runs indefinitely until manually stopped
- **RUN_SCHEDULED**: Pipeline runs on a schedule (cron, intervals, market hours)
- **RUN_ON_SIGNAL**: Pipeline runs continuously but waits for position to close before restarting
- Default mode: RUN_ONCE (safest for new users)

**FR-2.2.6**: Users shall be able to configure pipeline schedule settings
- Define active trading days (e.g., Monday-Friday)
- Set start time and end time for trading window (e.g., 9:35 AM - 3:30 PM)
- Configure timezone for schedule (e.g., America/New_York)
- Set schedule type: cron expression, market open + offset, or interval
- Configure maximum trades per day
- Configure maximum executions per day

**FR-2.2.7**: System shall enforce trading time windows
- Only execute pipeline during configured time window
- Check time window before each pipeline restart
- Stop pipeline automatically at end time if configured
- Send notifications before and at end of trading window

**FR-2.2.8**: System shall support end-of-day position management
- Option to flatten (close) all positions at end of trading window
- Close positions at market price regardless of P&L
- Log all end-of-day closures for audit trail
- Notify user when positions are auto-closed
- Warning in UI when this feature is enabled

**FR-2.2.9**: System shall support auto-stop conditions
- Stop if daily loss exceeds configured amount
- Stop if drawdown exceeds configured percentage
- Stop after reaching max trades per day
- Stop after reaching max executions per day
- Notify user when auto-stop triggered

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

#### 2.4.6 Trade Manager Agent (Enhanced)

**FR-2.4.6.1**: Trade Manager Agent shall manage complete trade lifecycle
- Execute approved trades
- Monitor open positions
- Execute exit strategies (stop loss, targets)
- Provide manual intervention controls

**FR-2.4.6.2**: Trade Manager Agent shall check for position conflicts before execution
- Query broker for existing open positions
- Check if position already exists for symbol
- Reject trades that would create duplicate positions (configurable)
- Prevent conflicting direction trades (long vs short)

**FR-2.4.6.3**: Trade Manager Agent shall execute trades with exit orders
- Submit main order to broker
- Place bracket orders (stop loss + take profit) if broker supports
- Place individual stop/target orders as fallback
- Support configurable partial exits (e.g., 50% at T1, 50% at T2)

**FR-2.4.6.4**: Trade Manager Agent shall monitor open positions
- Check position status every 60 seconds
- Monitor for stop loss hit
- Monitor for target price hits
- Execute partial exits when Target 1 reached
- Move stop to breakeven after Target 1 (configurable)
- Close remaining position when Target 2 reached

**FR-2.4.6.5**: Trade Manager Agent shall support multiple brokers
- MVP: Alpaca (supports bracket orders)
- Architecture supports multiple broker integrations via tools
- Users connect their own broker accounts
- Prioritize brokers with bracket order support

**FR-2.4.6.6**: Trade Manager Agent shall handle execution errors
- Retry failed orders (configurable)
- Log all execution attempts
- Handle partial fills
- Notify user of failures

**FR-2.4.6.7**: Trade Manager Agent shall track execution details
- Order ID, fill price, fill time
- Slippage calculation
- Commission/fees
- Position monitoring status
- Partial exit timestamps
- Final P&L when position closed

**FR-2.4.6.8**: Trade Manager Agent shall be configurable
- Allow pyramiding (multiple positions same symbol): Yes/No
- Partial exit split: Configurable percentage (default 50%/50%)
- Move stop to breakeven: Yes/No
- Monitoring frequency: Default 60 seconds

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

#### 2.4.8 Pipeline Manager Agent

**FR-2.4.8.1**: Pipeline Manager Agent shall coordinate pipeline execution
- One manager agent per pipeline (auto-injected)
- Manages pipeline's budget allocation
- Tracks pipeline's positions
- Coordinates inter-agent communication
- Makes intervention decisions

**FR-2.4.8.2**: Pipeline Manager Agent shall track pipeline budget
- Load pipeline's budget allocation from configuration
- Track cumulative cost during execution
- Check budget before pipeline starts
- Monitor budget after each agent execution
- Stop pipeline if budget exhausted

**FR-2.4.8.3**: Pipeline Manager Agent shall receive cost reports from agents
- All pipeline agents report costs to their Pipeline Manager
- Manager accumulates costs in real-time
- Compares cumulative cost against budget allocation
- Triggers budget exhaustion protocol if limit reached

**FR-2.4.8.4**: Pipeline Manager Agent shall manage positions
- Track all positions opened by this pipeline
- Receive position registrations from Trade Manager
- Maintain position registry for this pipeline only
- Command Trade Manager to close positions when needed

**FR-2.4.8.5**: Pipeline Manager Agent shall handle budget exhaustion
- Detect when pipeline budget is exhausted (daily or monthly)
- Send emergency close command to Trade Manager
- Trade Manager closes all positions at market price
- Log all interventions in audit table
- Stop pipeline execution
- Notify user of budget exhaustion

**FR-2.4.8.6**: Pipeline Manager Agent shall be a system agent
- Auto-injected into every pipeline (first agent)
- Not visible in pipeline builder UI
- Free (no cost to user)
- Cannot be removed or configured by user

**FR-2.4.8.7**: Pipelines shall have budget allocations
- Each pipeline configured with daily budget limit (optional)
- Each pipeline configured with monthly budget limit (optional)
- Budget allocation is subset of user's total budget
- Multiple pipelines can have independent budget allocations

#### 2.4.9 Stock Picker Agent

**FR-2.4.9.1**: Stock Picker Agent shall select symbols from screener
- Execute saved screener to find matching stocks
- Apply user-defined filters (price, volume, sector, technical indicators)
- Return ordered list of symbols based on screening criteria
- Support top N selection (e.g., analyze top 10 stocks from screener)

**FR-2.4.8.2**: Stock Picker Agent shall support multiple symbol sources
- Saved screeners (user-created filters)
- CSV import (from external tools like Finviz, TradingView)
- Manual symbol lists
- Watchlists

**FR-2.4.8.3**: Stock Picker Agent shall add symbols to pipeline state
- Populate `state.symbols` list for downstream agents
- All subsequent agents shall analyze each symbol
- Support parallel execution for multiple symbols

**FR-2.4.8.4**: Stock Picker Agent shall be configurable
- Screener selection (dropdown of saved screeners)
- Top N symbols to analyze
- Refresh on each run vs use cached results
- Fallback to previous results if no symbols found

**FR-2.4.8.5**: Stock Picker Agent shall be free (no cost)
- Agent itself does not incur charges
- Downstream agents charge per symbol analyzed (see FR-2.5.10)

#### 2.4.10 Stock Screener System

**FR-2.4.10.1**: System shall provide stock screener functionality
- Create and save screening filters
- Basic filters: price range, volume, market cap, sector
- Technical filters: SMA crossovers, RSI levels, price vs moving averages
- Performance filters: day change %, volume vs average

**FR-2.4.10.2**: Screeners shall be reusable
- Save screener configurations with name and description
- Reference screeners by ID in Stock Picker Agent
- Edit and delete saved screeners
- Preview screener results before using in pipeline

**FR-2.4.10.3**: System shall support screener result import
- CSV file upload (symbol list)
- Import from Finviz URL (future)
- Import from TradingView export (future)
- Validate symbols before adding to pipeline

**FR-2.4.10.4**: Screener execution shall be efficient
- Cache screener results (configurable TTL)
- Execute on stock universe (S&P 500, Russell 2000, or all US stocks)
- Return results with sorting options (volume, price, market cap, performance)
- Limit max results (default 50)

#### 2.4.11 Custom Strategy Agent (User-Defined Strategies)

**FR-2.4.11.1**: System shall allow users to create custom strategy agents
- User describes strategy in plain English (free-form text input)
- System generates Python code from description using LLM
- Generated code shown to user for review
- User can save custom strategy agent for reuse

**FR-2.4.11.2**: System shall perform multi-layered security review
- **Layer 1 - LLM Security Review**: Use LLM to analyze generated code for security issues
  - Check for file system access, network access, OS commands
  - Check for dangerous imports (os, sys, subprocess, socket, etc.)
  - Check for code injection risks (eval, exec, compile)
  - Check for resource exhaustion patterns (infinite loops)
  - Provide risk assessment (none/low/medium/high/critical)
- **Layer 2 - Static Analysis**: Programmatic validation using AST parsing
  - Whitelist of allowed imports (none for MVP)
  - Blacklist of forbidden functions (eval, exec, open, __import__)
  - Check for syntax errors
  - Validate code structure
- **Layer 3 - Sandbox Execution**: Execute in restricted environment
  - Use RestrictedPython or similar sandboxing library
  - Limit execution time (max 5 seconds)
  - Limit memory usage (max 100MB)
  - No file system or network access
  - Only allow access to provided context (market data, indicators)

**FR-2.4.11.3**: System shall require admin approval for custom strategies (MVP)
- Custom strategy agent enters "PENDING_REVIEW" status after creation
- User cannot use agent in pipeline until approved
- Admin dashboard shows all pending custom agents
- Admin can:
  - Review strategy description
  - Review generated code
  - Review security analysis results
  - Test agent in simulation mode
  - Approve or reject with comments
- User notified of approval/rejection via email and in-app
- Approved agents enter "ACTIVE" status
- Rejected agents enter "REJECTED" status with reason

**FR-2.4.11.4**: System shall support custom agent lifecycle management
- **States**: DRAFT, PENDING_REVIEW, ACTIVE, REJECTED, ARCHIVED
- User can edit DRAFT or REJECTED agents (triggers new review)
- User can archive ACTIVE agents (soft delete)
- User can duplicate existing custom agents
- User can export/import custom agents (JSON format)
- Version history tracked for each custom agent

**FR-2.4.11.5**: Custom Strategy Agent execution shall be sandboxed
- Execute in isolated environment per execution
- Provide context object with:
  - `data`: Current OHLCV market data
  - `indicators`: Pre-calculated indicators (EMA, RSI, MACD, BB, etc.)
  - `timeframe_data`: Multi-timeframe data if requested
- Code must set `signal` variable to "BUY", "SELL", or "HOLD"
- Code can optionally set `confidence` (0-100) and `reasoning` (string)
- Execution failures logged and shown to user with plain English explanation

**FR-2.4.11.6**: System shall store generated code permanently in database
- Code generated **once** during custom agent creation
- Generated code stored in `custom_strategy_agents.generated_code` column
- Code **never regenerated** at runtime
- At runtime, code loaded from database record and executed directly
- Pipeline configuration stores only reference to custom agent (`custom_agent_id`)
- No LLM calls during pipeline execution

**FR-2.4.11.7**: System shall track code integrity via hash
- SHA256 hash of generated code stored in `code_hash` column
- Hash computed at creation time and stored with code
- Hash verified at runtime before execution to detect tampering
- If hash mismatch detected (code modified outside system), reject execution and alert admin
- Hash used for audit trail (identify which code version was executed)
- Hash used for duplicate detection (prevent users from creating identical strategies)

**FR-2.4.11.8**: System shall support custom agent modification workflow
- User cannot directly edit ACTIVE custom agents
- To modify strategy, user must:
  - **Option 1**: Duplicate existing agent → Creates new DRAFT → Edit description → Regenerate code → New review cycle
  - **Option 2**: Archive old agent → Create new agent from scratch
- Each modification creates new `custom_agent_id`
- Original approved agent remains unchanged
- Pipeline using old agent continues working
- User can update pipeline to use new agent once approved

**FR-2.4.11.9**: System shall provide testing interface for custom strategies
- "Test in Simulation" button shows what code would do on recent data
- Historical test view (last 10 executions worth of data)
- Show inputs and outputs for debugging
- Show execution time and resource usage
- Clear error messages if code fails

**FR-2.4.11.10**: System shall track custom agent usage and performance
- Number of times agent used
- Success rate (executions without errors)
- Average execution time
- Trades generated by this agent
- P&L attributed to this agent
- User can see performance metrics before using

**FR-2.4.11.11**: Custom Strategy Agent shall have premium pricing
- Higher hourly rate than standard agents (0.15-0.20/hour)
- Accounts for dual LLM calls (generation + security review)
- Accounts for additional risk and monitoring costs
- Clear cost displayed before user creates custom agent

**FR-2.4.11.12**: System shall audit all custom code executions
- Log all executions to audit table
- Include: user_id, pipeline_id, code_hash, timestamp, result, execution_time
- Store code snippet (first 500 chars) for review
- Flag anomalies (unusually long execution, errors, suspicious patterns)
- Admin dashboard for monitoring custom agent usage

**FR-2.4.11.13**: Future: System shall transition to AI-only approval (post-MVP)
- Once confidence in AI security review is high, remove manual approval
- Implement confidence threshold (e.g., 95% confidence = auto-approve)
- Medium/High risk agents still require manual review
- Low/None risk agents approved automatically
- Continuous monitoring and feedback loop to improve AI reviewer

**FR-2.4.11.14**: System shall provide agent library for sharing (future)
- Users can publish approved custom agents to community library
- Other users can clone and use published agents
- Rating and review system
- Agent marketplace (buy/sell agents) in future phase

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

**FR-2.5.6**: System shall provide pre-execution cost estimation
- Calculate estimated cost per execution before starting pipeline
- Estimate based on agent configuration and historical data
- Show cost breakdown by agent (rental cost + LLM token cost)
- Estimate daily and monthly costs based on execution mode and schedule
- Display estimated execution duration

**FR-2.5.7**: System shall compare estimates against user budget
- Calculate percentage of budget that will be used
- Show warnings if estimate exceeds 80% of budget
- Show error if estimate exceeds 100% of budget
- Allow user to adjust configuration to reduce costs

**FR-2.5.8**: System shall display cost estimates in UI
- Show estimate in pipeline builder before starting
- Display cost breakdown per agent
- Show daily and monthly cost ranges
- Provide "View Detailed Breakdown" option
- Update estimate dynamically as pipeline configuration changes

**FR-2.5.9**: System shall track estimate accuracy
- Compare estimated vs actual costs after execution
- Store accuracy metrics for improving future estimates
- Adjust estimates based on user's historical execution patterns
- Display confidence level for estimates (low, medium, high)

**FR-2.5.10**: System shall implement per-symbol pricing for multi-symbol pipelines
- Each agent charges per symbol analyzed (hourly rate × runtime × number of symbols)
- LLM token costs multiply by number of symbols
- Stock Picker Agent itself is free
- Display clear cost breakdown showing per-symbol multiplier in estimates

**FR-2.5.11**: Pipeline Manager Agent shall enforce pipeline budget limits before execution
- Check pipeline's budget allocation before starting
- Calculate estimated cost for current execution
- Block execution if estimated cost exceeds pipeline's remaining allocation
- Notify user when pipeline is blocked due to budget

**FR-2.5.12**: Pipeline Manager Agent shall stop pipeline when budget exhausted
- Monitor cumulative spend during execution via cost reports from agents
- Check pipeline budget after each agent completes
- Detect when pipeline budget cap reached mid-execution
- Stop pipeline execution immediately
- Log budget exhaustion event with details

**FR-2.5.13**: Pipeline Manager Agent shall close positions when budget exhausted
- If pipeline budget exhausted, send emergency close command to Trade Manager
- Trade Manager executes market orders to flatten all pipeline positions immediately
- Pipeline Manager logs all interventions in `manual_interventions` table
- Notify user of forced position closes with reason "pipeline_budget_exhausted"
- Only close positions belonging to this pipeline (isolated)

**FR-2.5.14**: Pipelines shall have individual budget allocations
- Each pipeline configured with daily budget limit (optional)
- Each pipeline configured with monthly budget limit (optional)
- Pipeline budget is subset/allocation from user's total budget
- Multiple pipelines can have independent allocations
- Budget allocation configured in pipeline settings

**FR-2.5.15**: System shall provide pipeline budget alerts
- Alert at 80% of pipeline budget used
- Per-pipeline budget tracking and reporting
- Email and in-app notifications for pipeline-specific budget issues
- Warning in UI if pipeline approaching budget limit

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

**FR-2.6.5**: System shall provide positions dashboard
- List all currently open positions
- Show position details: symbol, side, quantity, entry price
- Display current P&L (unrealized)
- Show stop loss and target prices
- Display which pipeline created each position
- Show position age (time held)
- Update in real-time or near real-time

**FR-2.6.6**: System shall provide manual intervention controls
- Emergency close button per position (market order)
- Emergency close all positions button
- Confirmation dialog before closing
- Manual close reasons logged for audit
- Immediately stop position monitoring after manual close

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

### 2.8 Performance Analytics & Insights

**FR-2.8.1**: System shall provide pipeline performance analytics
- Calculate key metrics: Total P&L, win rate, average win/loss, win/loss ratio
- Display advanced metrics: Sharpe ratio, max drawdown, profit factor
- Show cost analysis: Total cost, net P&L, ROI (P&L / Cost)
- Track trade statistics: Total trades, winning trades, losing trades, breakeven trades
- Calculate average hold time per position
- Identify largest win and largest loss with trade details

**FR-2.8.2**: System shall provide time-based performance breakdowns
- Analyze performance by symbol (P&L, win rate per symbol)
- Analyze performance by day of week (Monday-Friday breakdown)
- Analyze performance by time of day (market hour segments)
- Generate equity curve showing cumulative P&L over time

**FR-2.8.3**: System shall support configurable analysis periods
- Last 7 days, 30 days, 90 days, or all time
- Custom date range selection
- Performance comparison across different periods

**FR-2.8.4**: System shall enable pipeline comparison
- Side-by-side comparison of multiple pipelines
- Compare same metrics across pipelines
- Identify best/worst performing pipelines
- Support comparison within same time period

**FR-2.8.5**: System shall provide aggregate user-level analytics
- Total P&L across all user's pipelines
- Total trades executed
- Total cost incurred
- Breakdown by individual pipeline

**FR-2.8.6**: Performance dashboard shall display visual charts
- Equity curve chart (cumulative P&L over time)
- Win rate visualization
- P&L breakdown by symbol (bar chart)
- P&L breakdown by day/time (heatmap or bar chart)
- Drawdown chart

**FR-2.8.7**: System shall support performance report export
- Export performance metrics as PDF
- Export raw trade data as CSV
- Include charts and visualizations in exports

### 2.9 Testing & Dry Run Mode

**FR-2.9.1**: System shall support multiple pipeline execution modes
- **Live Mode**: Real trades executed through broker with real money
- **Paper Trading Mode**: Real broker API but paper trading account (no real money)
- **Simulation Mode**: Fully simulated trades, no broker API calls, instant execution
- **Validation Mode**: Strategy validation only, no trade execution at all

**FR-2.9.2**: Users shall be able to configure pipeline mode
- Mode selection during pipeline creation
- Ability to change mode (with confirmation for live mode)
- Mode clearly displayed in UI at all times
- Warning prompts when switching to live mode

**FR-2.9.3**: Paper Trading Mode shall integrate with broker paper accounts
- Use broker's paper trading API endpoints
- Execute trades on paper account (Alpaca Paper, etc.)
- Real market data but simulated fills
- Track paper account balance and positions
- Generate realistic trade reports with paper account data

**FR-2.9.4**: Simulation Mode shall provide instant trade simulation
- No broker API calls
- Instant trade fills at current market price
- Configurable slippage and commission simulation
- Simulated account balance tracking
- Generate trade reports identical to live mode

**FR-2.9.5**: Validation Mode shall test strategy logic without execution
- Run all agents except Trade Manager
- Validate strategy signals and risk approvals
- Generate "what would have happened" reports
- Track hypothetical performance
- No position opening or closing

**FR-2.9.6**: System shall enforce strict mode isolation
- Test mode pipelines cannot execute real trades
- Live mode requires explicit broker connection
- Clear visual indicators in UI for each mode
- Audit log for mode changes
- Confirmation dialogs for switching to live mode

**FR-2.9.7**: System shall provide test data generation
- Generate realistic market data for demos
- Pre-configured demo pipelines for new users
- Sample trade history for UI testing
- Synthetic performance data for analytics testing

**FR-2.9.8**: System shall track costs differently by mode
- Live Mode: Full cost tracking (agent fees + LLM + broker fees)
- Paper Trading Mode: Agent fees + LLM costs (no real broker fees)
- Simulation Mode: Agent fees + LLM costs only
- Validation Mode: Agent fees + LLM costs only
- Clear cost breakdown by mode in billing

**FR-2.9.9**: UI shall prominently display pipeline mode
- Large visual indicator (banner/badge) showing current mode
- Color coding: Green (Live), Blue (Paper), Yellow (Simulation), Gray (Validation)
- Mode shown in pipeline list, detail view, and execution monitoring
- Warning messages in test modes about non-real trades
- Separate performance dashboards for test vs live pipelines

**FR-2.9.10**: System shall provide mode-specific limitations
- Test mode pipelines: No real broker connection required
- Live mode pipelines: Require verified broker connection
- Test modes: Can use higher frequency triggers for faster testing
- Live mode: Enforce reasonable rate limits

**FR-2.9.11**: System shall support safe testing workflow
- New users start with simulation mode only
- Unlock paper trading after completing demo
- Unlock live mode after paper trading success + broker verification
- Option to clone live pipeline as test pipeline for modification
- Test changes before applying to live pipeline

**FR-2.9.12**: System shall generate realistic test results
- Simulation mode: Apply realistic slippage (0.1-0.5%)
- Simulation mode: Apply commission costs (broker-specific)
- Simulation mode: Simulate partial fills for large orders
- Simulation mode: Simulate order rejections (buying power, market closed)
- Paper trading mode: Use broker's realistic paper trading simulation

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

