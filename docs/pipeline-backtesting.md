# Pipeline Backtesting — Full-Stack Design

> **Scope**: Run an existing user-built pipeline end-to-end against historical data — including signal detection, trigger dispatch, and the full agent sequence (market data → bias → strategy → risk → trade review → trade manager) — using a simulated broker instead of a live one.

---

## 1. What "Full-Stack Backtesting" Means

A standard backtest engine (see `docs/backtesting-ui-plan.md`) runs only the deterministic strategy core (`RegimeDetector + SetupEvaluator`). That is fast but ignores:

- Which signals would have fired (golden cross, MACD, RSI, etc.)
- Whether those signals would have matched the pipeline's subscription rules
- The full agent sequence and any logic those agents add on top of the strategy
- Real-world execution friction (slippage, commission) applied per agent output

**Pipeline backtesting** replays the entire live stack:

```
Historical candles (bar-by-bar)
        │
        ▼
Backtest Signal Generator   ← same algorithms as live signal-generator, on historical bars
        │ historical signals
        ▼
Backtest Trigger Dispatcher ← same matching logic as trigger-dispatcher, no Kafka
        │ matched pipeline + symbol
        ▼
PipelineExecutor (backtest mode)
  ├── MarketDataAgent    → served from historical candle window, not Data Plane HTTP
  ├── BiasAgent          → deterministic path (LLM calls bypassed)
  ├── StrategyAgent      → RegimeDetector + SetupEvaluator (deterministic ✓)
  ├── RiskManagerAgent   → validates position sizing on simulated capital
  ├── TradeReviewAgent   → deterministic path (LLM calls bypassed)
  └── TradeManagerAgent  → BacktestBroker (ExecutionSimulator) instead of real broker
        │ trades
        ▼
PerformanceAnalytics → metrics, equity curve, per-regime breakdown
```

---

## 2. Feasibility Assessment

| Component | Live Behaviour | Backtest Approach | Feasible? |
|-----------|---------------|-------------------|-----------|
| Signal Generator | Monitors live prices via Data Plane WebSocket/polling | Re-run indicator algorithms against historical candles | ✅ Yes — algorithms are stateless and deterministic |
| Trigger Dispatcher | Consumes Kafka, queries DB for active pipelines | Skip Kafka; run matching logic in-process against pre-loaded pipeline config | ✅ Yes — matching logic is pure Python |
| MarketDataAgent | HTTP GET to Data Plane (`/api/v1/data/candles`) | Serve from an in-memory `BacktestDataPlane` fed the historical window | ✅ Yes — single injection point in `executor.py` |
| BiasAgent | May call an LLM | Run in deterministic-only mode; if LLM is present, skip or return neutral bias | ✅ Yes with flag |
| StrategyAgent | `RegimeDetector + SetupEvaluator` — deterministic | Same code, no change needed | ✅ Full parity |
| RiskManagerAgent | Queries broker for account balance | Use simulated capital from `BacktestBroker` | ✅ Yes |
| TradeReviewAgent | May call LLM | Deterministic-only mode | ✅ Yes with flag |
| TradeManagerAgent | Calls Alpaca/Tradier/OANDA | Calls `BacktestBroker.execute_order()` | ✅ Yes — broker is injected |
| Position monitoring loop | Celery polling at live market prices | Evaluate exits bar-by-bar in the simulation loop | ✅ Yes |

**Bottom line**: The entire pipeline can be backtested deterministically. LLM-dependent agents (Bias, TradeReview) need a `backtest_mode` flag that switches them to a rule-based path. All other agents already run deterministic logic.

---

## 3. Architecture

### 3.1 New Components

```
backend/app/backtesting/
  engine.py            (exists) — simple strategy engine, unchanged
  analytics.py         (exists) — performance metrics, unchanged
  simulation.py        (exists) — slippage + commission models, unchanged
  walk_forward.py      (exists) — walk-forward validator, unchanged

  pipeline_runner.py   (NEW) — BacktestPipelineRunner: coordinates the full replay loop
  signal_replayer.py   (NEW) — BacktestSignalReplayer: runs indicator algorithms on historical bars
  trigger_matcher.py   (NEW) — BacktestTriggerMatcher: applies pipeline signal subscription rules
  data_plane.py        (NEW) — BacktestDataPlane: in-memory historical candle server
  broker.py            (NEW) — BacktestBroker: simulated order execution using ExecutionSimulator
```

### 3.2 BacktestSignalReplayer (`signal_replayer.py`)

Runs the same signal generator algorithms that live in `signal-generator/app/generators/` but against a rolling window of historical candles rather than live prices.

```python
class BacktestSignalReplayer:
    """
    Replays signal generation bar-by-bar over historical OHLCV data.
    Returns a list of (bar_index, signal_type, ticker, confidence, metadata).
    """
    def __init__(self, generators: List[str], symbols: List[str]):
        # generators: e.g. ["golden_cross", "macd_crossover", "rsi_oversold"]
        # If empty, run all generators registered for the pipeline's signal_subscriptions
        self.generators = generators
        self.symbols = symbols

    def replay(self, candles: Dict[str, List[Candle]]) -> List[HistoricalSignal]:
        """
        candles: {symbol: [Candle]} sorted ascending by timestamp
        Returns signals with bar_index so the runner can align them to the candle timeline.
        """
```

Each generator is called with a rolling 60-bar window (same as live). The output is a `HistoricalSignal` — identical schema to the live Kafka `Signal` dataclass but with a `bar_index` field instead of a real timestamp.

### 3.3 BacktestTriggerMatcher (`trigger_matcher.py`)

Pure Python re-implementation of the signal-matching logic from `trigger-dispatcher/app/main.py` (lines 237–345). No Kafka, no DB queries.

```python
class BacktestTriggerMatcher:
    """
    Given a pipeline config and a list of historical signals,
    returns the subset of (bar_index, symbol) pairs that would have
    triggered the pipeline.
    """
    def __init__(self, pipeline_config: dict):
        self.signal_subscriptions = pipeline_config.get("signal_subscriptions", [])
        self.scanner_tickers = pipeline_config.get("tickers", [])

    def match(self, signals: List[HistoricalSignal]) -> List[TriggerEvent]:
        """
        Applies ticker intersection, signal_type subscription, and
        confidence threshold — same rules as the live dispatcher.
        Returns list of TriggerEvent(bar_index, symbol, signal_type, confidence).
        Deduplicates: one execution per (symbol, active_trade_window) like the live dispatcher.
        """
```

### 3.4 BacktestDataPlane (`data_plane.py`)

Wraps historical candles so agents can call the same `get_candles()` / `get_quote()` interface they use in live mode. Only returns data up to `current_bar_index` — this prevents look-ahead bias.

```python
class BacktestDataPlane:
    def __init__(self, candles_by_symbol: Dict[str, Dict[str, List[Candle]]]):
        # candles_by_symbol: {symbol: {timeframe: [Candle]}}
        self.data = candles_by_symbol
        self.current_bar_index = 0          # Advances each bar in the replay loop

    async def get_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        window = self.data[symbol][timeframe]
        end = self.current_bar_index + 1
        return window[max(0, end - limit):end]   # Never leaks future bars

    async def get_quote(self, symbol: str) -> Quote:
        latest = self.data[symbol]["1m"][self.current_bar_index]
        return Quote(price=latest.close, bid=latest.close * 0.999, ask=latest.close * 1.001)
```

### 3.5 BacktestBroker (`broker.py`)

Wraps `ExecutionSimulator` (already in `simulation.py`) and maintains a virtual account.

```python
class BacktestBroker:
    def __init__(self, initial_capital: float, slippage: SlippageModel, commission: CommissionModel):
        self.capital = initial_capital
        self.positions: Dict[str, Position] = {}
        self.filled_orders: List[FilledOrder] = []
        self.simulator = ExecutionSimulator(slippage, commission)

    def execute_order(self, symbol, qty, price, action) -> FilledOrder:
        fill_price = self.simulator.apply_slippage(price, action)
        cost = self.simulator.total_cost(fill_price, qty, action)
        # Update capital and positions
        ...

    def get_position(self, symbol) -> Optional[Position]: ...
    def get_account_balance(self) -> float: ...
    def check_exit_conditions(self, symbol, current_bar: Candle) -> Optional[ExitEvent]: ...
```

### 3.6 BacktestPipelineRunner (`pipeline_runner.py`)

The main coordinator. Owns the bar-by-bar replay loop.

```python
class BacktestPipelineRunner:
    """
    Full-stack pipeline backtest runner.
    Coordinates: signal replay → trigger matching → pipeline execution → position monitoring.
    """

    def __init__(
        self,
        pipeline: Pipeline,
        config: PipelineBacktestConfig,
        candles: Dict[str, Dict[str, List[Candle]]],   # {symbol: {timeframe: [Candle]}}
    ):
        self.pipeline = pipeline
        self.config = config
        self.data_plane = BacktestDataPlane(candles)
        self.broker = BacktestBroker(
            initial_capital=config.initial_capital,
            slippage=SlippageModel(config.slippage_model, config.slippage_value),
            commission=CommissionModel(config.commission_model, config.commission_value),
        )
        self.signal_replayer = BacktestSignalReplayer(
            generators=self._get_pipeline_generators(),
            symbols=config.symbols,
        )
        self.trigger_matcher = BacktestTriggerMatcher(pipeline.config)

    async def run(self) -> PipelineBacktestResult:
        # 1. Replay all signals across the full date range
        all_signals = self.signal_replayer.replay(self._primary_candles())

        # 2. Determine which bars would have triggered the pipeline
        trigger_events = self.trigger_matcher.match(all_signals)

        # 3. Bar-by-bar loop
        n_bars = len(self._primary_candles()[config.symbols[0]])
        for bar_idx in range(n_bars):
            self.data_plane.current_bar_index = bar_idx
            current_bar = self._get_bar(bar_idx)

            # 3a. Check open position exit conditions at this bar
            await self._check_exits(bar_idx, current_bar)

            # 3b. If a trigger fired at this bar, run the pipeline agents
            bar_triggers = [t for t in trigger_events if t.bar_index == bar_idx]
            for trigger in bar_triggers:
                if self.broker.get_position(trigger.symbol):
                    continue   # Already in position — same dedup rule as live dispatcher
                await self._execute_pipeline_at_bar(trigger, bar_idx)

        # 4. Compute metrics
        return PipelineBacktestResult(
            config=self.config,
            trades=self.broker.filled_orders,
            equity_curve=self._build_equity_curve(),
            signals_fired=len(all_signals),
            triggers_matched=len(trigger_events),
            metrics=PerformanceAnalytics.compute(
                self.broker.filled_orders,
                self._build_equity_curve(),
                self.config.initial_capital,
            ),
        )

    async def _execute_pipeline_at_bar(self, trigger: TriggerEvent, bar_idx: int):
        """
        Runs the full agent sequence for one trigger event.
        Uses backtest-mode PipelineExecutor (data plane and broker injected).
        """
        executor = PipelineExecutor(
            pipeline=self.pipeline,
            user_id=self.config.user_id,
            mode="backtest",
            data_plane_override=self.data_plane,      # New injection point
            broker_override=self.broker,               # New injection point
            backtest_context=BacktestContext(
                bar_index=bar_idx,
                symbol=trigger.symbol,
                signal_type=trigger.signal_type,
            ),
        )
        await executor.execute()
```

---

## 4. Changes to Existing Code

### 4.1 `PipelineExecutor` (`backend/app/orchestration/executor.py`)

Add two optional constructor parameters:

```python
def __init__(
    self,
    ...,
    data_plane_override: Optional[BacktestDataPlane] = None,   # NEW
    broker_override: Optional[BacktestBroker] = None,           # NEW
    backtest_context: Optional[BacktestContext] = None,          # NEW
):
```

Modify `_fetch_market_data_for_pipeline()`:
- If `data_plane_override` is set, call `data_plane_override.get_candles()` instead of HTTP GET to Data Plane.
- Skip the live-hours guard (`is_market_open()` check) when in backtest mode.

Pass `broker_override` down to `TradeManagerAgent` via `PipelineState.backtest_broker`.

### 4.2 Agent Backtest Mode

Add a `BACKTEST_MODE` flag to `PipelineState`:

```python
class PipelineState(BaseModel):
    ...
    backtest_mode: bool = False
    backtest_broker: Optional[Any] = None   # BacktestBroker instance
    backtest_bar_index: Optional[int] = None
```

Agents check `state.backtest_mode`:

| Agent | Live behaviour | Backtest behaviour |
|-------|---------------|-------------------|
| `MarketDataAgent` | HTTP → Data Plane | Data served by `BacktestDataPlane` (already via executor injection) |
| `BiasAgent` | LLM call | Skip LLM; return `neutral` bias deterministically |
| `StrategyAgent` | `RegimeDetector + SetupEvaluator` | **No change** — already deterministic |
| `RiskManagerAgent` | Query broker for balance | Query `state.backtest_broker.get_account_balance()` |
| `TradeReviewAgent` | LLM call | Skip LLM; auto-approve if strategy confidence > threshold |
| `TradeManagerAgent` | Broker API | `state.backtest_broker.execute_order()` |

### 4.3 New API Endpoints (`backend/app/api/v1/pipeline_backtests.py`)

```
POST /api/v1/pipeline-backtests/run
GET  /api/v1/pipeline-backtests
GET  /api/v1/pipeline-backtests/{id}
```

**POST /run request body:**

```json
{
  "pipeline_id": "uuid",
  "symbols": ["AAPL", "MSFT"],
  "start_date": "2024-01-01",
  "end_date": "2024-06-30",
  "initial_capital": 10000.0,
  "slippage_model": "fixed",
  "slippage_value": 0.01,
  "commission_model": "per_share",
  "commission_value": 0.005,
  "signal_generators": [],      // empty = use all generators matching pipeline subscriptions
  "timeframe": "5m",
  "walk_forward": false
}
```

**POST /run response:**

```json
{
  "id": "uuid",
  "pipeline_id": "uuid",
  "pipeline_name": "My ORB Strategy",
  "symbols": ["AAPL", "MSFT"],
  "start_date": "2024-01-01",
  "end_date": "2024-06-30",
  "signals_fired": 142,
  "triggers_matched": 38,
  "executions_run": 38,
  "trades": [...],
  "equity_curve": [...],
  "metrics": {
    "total_trades": 38,
    "win_rate": 0.55,
    "total_net_pnl": 1540.20,
    "max_drawdown_pct": 0.09,
    "sharpe_ratio": 1.45,
    "sortino_ratio": 1.82,
    "calmar_ratio": 0.92,
    "profit_factor": 1.73,
    "expectancy": 40.53,
    "total_commission": 48.50,
    "total_slippage": 19.00,
    "by_regime": {...},
    "by_signal_type": {...}
  },
  "walk_forward": null,
  "created_at": "2026-04-11T12:00:00Z"
}
```

### 4.4 New Database Model (`backend/app/models/pipeline_backtest.py`)

```
id               UUID PK
user_id          UUID FK → users
pipeline_id      UUID FK → pipelines (nullable, pipeline may be deleted)
pipeline_name    VARCHAR  (snapshot at run time)
pipeline_config  JSONB    (snapshot of pipeline config at run time)
symbols          JSONB    (list of symbols)
start_date       DATE
end_date         DATE
config           JSONB    (full PipelineBacktestConfig)
signals_fired    INT
triggers_matched INT
executions_run   INT
trades           JSONB
equity_curve     JSONB
metrics          JSONB
walk_forward     BOOL
wfv_report       JSONB    (nullable)
created_at       TIMESTAMP
```

---

## 5. Historical Data Loading

The runner needs historical OHLCV candles for the selected symbols and date range before the replay loop starts. Three options (in order of preference):

### Option A — Data Plane historical endpoint (recommended for MVP)

Extend the Data Plane with:

```
GET /api/v1/data/candles/{symbol}/history?timeframe=5m&start=2024-01-01&end=2024-06-30
```

The Data Plane fetches from Tiingo (stocks) or OANDA (forex) and stores in TimescaleDB. The backend calls this before starting the runner.

### Option B — Direct TimescaleDB query

If the data is already seeded (EOD candles: 400 days), query TimescaleDB directly from the backend. Continuous aggregates provide 5m–1D candles without additional provider calls.

### Option C — On-demand provider fetch (fallback)

If TimescaleDB doesn't have the data, the Data Plane fetches from Tiingo/Finnhub/OANDA and seeds the DB as a side-effect. The backend waits for this to complete before starting the runner.

**Data availability guarantees:**

| Provider | Asset class | Max history |
|----------|-------------|-------------|
| Tiingo | US stocks | 20+ years (daily), ~2 years (intraday) |
| Finnhub | US stocks | 1 year (intraday) |
| OANDA | Forex | 5+ years (all timeframes) |

---

## 6. Signal Generators to Replay

The pipeline's `signal_subscriptions` field lists which signal types it subscribes to. The `BacktestSignalReplayer` only runs the generators corresponding to those subscriptions. This mirrors live behaviour — the pipeline only gets triggered by signals it's subscribed to.

Existing live generators (in `signal-generator/app/generators/`) that can be ported to the replayer:

| Generator | Signal type | Indicator | Look-back |
|-----------|-------------|-----------|-----------|
| `golden_cross` | `golden_cross` | SMA 50/200 crossover | 200 bars |
| `macd_crossover` | `macd_crossover` | MACD 12/26/9 | 35 bars |
| `rsi_oversold` / `rsi_overbought` | `rsi_*` | RSI 14 | 14 bars |
| `bollinger_squeeze` | `bollinger_*` | BB 20/2 | 20 bars |
| `ema_crossover` | `ema_crossover` | EMA 9/21 | 21 bars |
| `stoch_crossover` | `stoch_*` | Stochastic 14/3 | 14 bars |
| `adx_trend` | `adx_trend` | ADX 14 | 14 bars |
| ... 11 more | ... | ... | ... |

The replayer loads generator classes from the `signal-generator` package. Since `signal-generator` is a separate Docker service, the generator logic must be either:

- **Option A (recommended)**: Duplicate the pure indicator functions into `backend/app/backtesting/generators/` (these are stateless math functions — trivial to copy).
- **Option B**: Install `signal-generator` as a Python package (add a `pyproject.toml` and reference it in `backend/requirements.txt`).

Option A is simpler for MVP.

---

## 7. UI Design

### 7.1 Entry Point

Add a **"Backtest"** button to the Pipeline detail page (already exists). This navigates to `/backtesting/pipeline/:pipeline_id/new`.

```
[Pipeline Card]
  ▶ Start   ⏸ Pause   📊 Backtest   ⚙ Edit
```

### 7.2 Backtest Configuration Page

Route: `/backtesting/pipeline/:pipeline_id/new`

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Backtest: "My ORB Strategy"                                            │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  SYMBOLS                                                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  [AAPL ×]  [MSFT ×]  [+ Add symbol]                            │   │
│  │  (Pre-filled from pipeline's scanner. Editable.)                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  DATE RANGE                     TIMEFRAME                               │
│  [2024-01-01] → [2024-06-30]    [5m ▼]                                 │
│                                                                         │
│  CAPITAL          RISK PER TRADE                                        │
│  [$ 10,000]       [1.0 %]                                               │
│                                                                         │
│  ── EXECUTION COSTS (collapsible) ─────────────────────────────────    │
│  SLIPPAGE   [fixed ▼]    VALUE [$0.01]                                  │
│  COMMISSION [per_share ▼] VALUE [$0.005]                                │
│                                                                         │
│  ── OPTIONS ────────────────────────────────────────────────────────   │
│  [☐] Walk-forward validation (5 folds, 70 / 30 split)                  │
│  [☑] Simulate full signal pipeline  ← this runs signal replayer        │
│       (unchecked = use simple strategy engine only, faster)             │
│                                                                         │
│  ── SIGNAL GENERATORS ──────────────────────────────────────────────   │
│  (Shown only when "Simulate full signal pipeline" is checked)           │
│  Pipeline subscribes to: [golden_cross] [macd_crossover] [rsi_oversold] │
│  These generators will be replayed against historical data.             │
│                                                                         │
│                      [▶ Run Backtest]                                   │
│                                                                         │
│  Estimated data: AAPL 5m candles 2024-01-01→2024-06-30 ≈ 15,600 bars  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.3 Backtest Results Page

Route: `/backtesting/:id`

Uses the same sidebar + main-content layout as the execution report.

```
┌─── SIDEBAR ────────────────────────────────────────────────────────────┐
│  My ORB Strategy                                                        │
│  AAPL · MSFT                                                            │
│  Jan 1 – Jun 30, 2024  |  5m  |  Full Pipeline Mode                   │
│                                                                         │
│  Net P&L         +$1,540.20 ▲ 15.4%                                   │
│  Signals fired   142                                                    │
│  Triggers matched 38                                                    │
│  Trades executed  38                                                    │
│                                                                         │
│  ── Navigate ───────                                                    │
│  • Summary                                                              │
│  • Signal Funnel                                                        │
│  • Equity Curve                                                         │
│  • Trade List                                                           │
│  • By Regime                                                            │
│  • By Signal Type                                                       │
│  • Walk-Forward (if run)                                                │
│                                                                         │
│  [↗ Compare to simple backtest]                                         │
│  [📥 Export trades CSV]                                                 │
└────────────────────────────────────────────────────────────────────────┘

MAIN CONTENT:

┌─── SUMMARY ────────────────────────────────────────────────────────────┐
│  Metric cards (2×4 grid):                                              │
│  Trades  Win%  Profit Factor  Expectancy                               │
│  Sharpe  Sortino  Max DD  Calmar                                       │
│                                                                         │
│  Cost breakdown:                                                        │
│  Commission: $48.50   Slippage: $19.00   Total drag: $67.50            │
└────────────────────────────────────────────────────────────────────────┘

┌─── SIGNAL FUNNEL ──────────────────────────────────────────────────────┐
│  Sankey / funnel diagram showing:                                       │
│  142 signals generated                                                  │
│    → 38 matched pipeline trigger rules (26.8%)                         │
│       → 38 executions run                                              │
│          → 21 trades opened (55.3% triggered a trade)                  │
│             → 21 closed (0 open at end of period)                      │
│                                                                         │
│  Per-signal-type breakdown table:                                       │
│  Signal Type     │ Fired │ Matched │ Trades │ Win% │ Net P&L            │
│  golden_cross    │  22   │   14    │   14   │ 64%  │ +$820              │
│  macd_crossover  │  68   │   18    │   18   │ 50%  │ +$440              │
│  rsi_oversold    │  52   │    6    │    6   │ 33%  │ -$280              │
└────────────────────────────────────────────────────────────────────────┘

┌─── EQUITY CURVE ───────────────────────────────────────────────────────┐
│  Line chart: portfolio equity over time                                 │
│  Overlay: signal fire events (vertical tick marks, colour by type)     │
│  Secondary axis: daily returns bar chart                               │
│  Zoom/pan controls                                                     │
└────────────────────────────────────────────────────────────────────────┘

┌─── TRADE LIST ─────────────────────────────────────────────────────────┐
│  MatTable, paginated, sortable                                          │
│  Columns: # │ Symbol │ Signal │ Entry Time │ Action │ Entry │ Exit │    │
│           Size │ Gross P&L │ Net P&L │ R │ Regime │ Exit Reason        │
│  Green rows = winners, red = losers                                     │
│  Expandable row: shows which agent reported what at execution time      │
└────────────────────────────────────────────────────────────────────────┘

┌─── BY REGIME ──────────────────────────────────────────────────────────┐
│  Table: Regime │ Trades │ Win% │ Net P&L │ Avg R                       │
│  Horizontal bar chart per regime                                       │
└────────────────────────────────────────────────────────────────────────┘

┌─── BY SIGNAL TYPE ─────────────────────────────────────────────────────┐
│  Same structure as By Regime, grouped by signal_type                   │
└────────────────────────────────────────────────────────────────────────┘

┌─── WALK-FORWARD (conditional) ─────────────────────────────────────────┐
│  Table: Fold │ Train Period │ OOS Period │ OOS Win% │ OOS P&L │ Sharpe  │
│  Stitched OOS equity curve line chart                                  │
│  Warning if OOS Sharpe degrades > 50% vs in-sample                    │
└────────────────────────────────────────────────────────────────────────┘
```

### 7.4 History List

Route: `/backtesting` (main page, tab: History)

```
┌────────────────────────────────────────────────────────────────────────┐
│  Pipeline        │ Symbols    │ Period         │ Trades │ Win% │ P&L    │
│  My ORB Strategy │ AAPL, MSFT │ Jan–Jun 2024   │  38    │ 55%  │ +$1540 │
│  Forex Momentum  │ EUR/USD    │ Q4 2023        │  22    │ 45%  │  -$210 │
│  ...                                                                   │
│  [Load more]                                                           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Implementation Plan

### Phase 1 — Backend foundation (no UI yet)

1. Create `BacktestDataPlane`, `BacktestBroker` in `backend/app/backtesting/`
2. Add `backtest_mode`, `backtest_broker` fields to `PipelineState`
3. Add `data_plane_override`, `broker_override`, `backtest_context` params to `PipelineExecutor.__init__()`
4. Modify `PipelineExecutor._fetch_market_data_for_pipeline()` to use `data_plane_override`
5. Add backtest-mode paths to `BiasAgent`, `TradeReviewAgent`, `TradeManagerAgent`, `RiskManagerAgent`
6. Add `PipelineBacktest` DB model + Alembic migration
7. Confirm `GET /api/v1/data/candles/{symbol}/history` works on Data Plane for required date ranges

### Phase 2 — Signal replayer + trigger matcher

1. Port indicator algorithms from `signal-generator/` into `backend/app/backtesting/generators/`
2. Implement `BacktestSignalReplayer` and `BacktestTriggerMatcher`
3. Wire them into `BacktestPipelineRunner`
4. Unit tests: given a synthetic candle series, verify signals and trigger matches are correct

### Phase 3 — API endpoints + async execution

1. Create `backend/app/api/v1/pipeline_backtests.py` with POST /run, GET /, GET /{id}
2. For runs > 10 s (long date ranges), execute as a Celery task. Return `{"id": "uuid", "status": "running"}` immediately and poll via `GET /{id}` or WebSocket.
3. Add WebSocket progress events: `{type: "backtest_progress", pct: 42, signals_so_far: 60}`
4. Test via Swagger

### Phase 4 — Frontend

1. `BacktestService` (`frontend/src/app/core/services/backtest.service.ts`)
2. Backtest config component (form) — pre-fill symbols from pipeline scanner
3. Backtest result component — sidebar + sections (reuse execution report layout)
4. Signal funnel section (simple bar/table, no complex chart library needed for MVP)
5. Equity curve (Chart.js line chart)
6. Trade list (MatTable)
7. History list (MatTable)
8. Route registration + nav link
9. "Backtest" button on pipeline detail card

### Phase 5 — Walk-forward + polish

1. Wire `WalkForwardValidator` into the runner (existing code, minimal changes)
2. Walk-forward results section in UI
3. "Compare to simple backtest" side-by-side view
4. CSV export of trades
5. Re-run with tweaked config button

---

## 9. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| LLM agents produce non-deterministic output | Results unreproducible | Backtest mode bypasses LLM calls entirely; uses rule-based paths |
| Historical candles not available for requested date range | Backtest fails | Show data availability warning in UI before run; fall back to provider fetch |
| Long date ranges cause timeout | Poor UX | Celery task with WebSocket progress; hard limit 2 years |
| Look-ahead bias in data window | Inflated results | `BacktestDataPlane.get_candles()` strictly limits to `current_bar_index` |
| Signal replayer diverges from live generator | Backtest not representative | Share indicator math between replayer and live generator via common library |
| Position exit logic differs from live monitoring | Trade P&L inaccurate | `BacktestBroker.check_exit_conditions()` replicates the same stop/target/time-stop logic |
| Multiple symbols create cross-pipeline interference | Incorrect position dedup | `BacktestBroker` maintains per-symbol positions; dedup mirrors live dispatcher |

---

## 10. What Already Exists vs. What to Build

### Already exists (no changes needed)

| Component | Location | Status |
|-----------|----------|--------|
| `BacktestEngine` (simple) | `backend/app/backtesting/engine.py` | Done |
| `PerformanceAnalytics` | `backend/app/backtesting/analytics.py` | Done |
| `ExecutionSimulator` (slippage + commission) | `backend/app/backtesting/simulation.py` | Done |
| `WalkForwardValidator` | `backend/app/backtesting/walk_forward.py` | Done |
| `RegimeDetector + SetupEvaluator` | `backend/app/agents/strategy_engine/` | Done (deterministic) |
| `PipelineExecutor` | `backend/app/orchestration/executor.py` | Needs 3 new params |
| Signal matching logic | `trigger-dispatcher/app/main.py:237-345` | Needs porting to `BacktestTriggerMatcher` |

### To build

| Component | Effort |
|-----------|--------|
| `BacktestDataPlane` | Small |
| `BacktestBroker` | Small (wraps existing `ExecutionSimulator`) |
| `BacktestSignalReplayer` | Medium (port generator math) |
| `BacktestTriggerMatcher` | Small (port matching logic) |
| `BacktestPipelineRunner` | Medium |
| Agent backtest-mode flags | Small per agent (4 agents) |
| `PipelineBacktest` DB model + migration | Small |
| API endpoints | Small |
| Celery task + WebSocket progress | Medium |
| Frontend (service + 5 components) | Large |

---

## 11. File Locations Summary

```
backend/app/
  backtesting/
    engine.py              — existing, unchanged
    analytics.py           — existing, unchanged
    simulation.py          — existing, unchanged
    walk_forward.py        — existing, unchanged
    pipeline_runner.py     — NEW: BacktestPipelineRunner
    signal_replayer.py     — NEW: BacktestSignalReplayer
    trigger_matcher.py     — NEW: BacktestTriggerMatcher
    data_plane.py          — NEW: BacktestDataPlane
    broker.py              — NEW: BacktestBroker
    generators/            — NEW: ported indicator functions
      golden_cross.py
      macd.py
      rsi.py
      ...

  models/
    pipeline_backtest.py   — NEW: PipelineBacktest SQLAlchemy model

  api/v1/
    pipeline_backtests.py  — NEW: POST /run, GET /, GET /{id}

  orchestration/
    executor.py            — MODIFY: add 3 injection params

  agents/
    base.py                — MODIFY: respect backtest_mode on state
    bias_agent.py          — MODIFY: deterministic path in backtest mode
    trade_review_agent.py  — MODIFY: auto-approve in backtest mode
    trade_manager_agent.py — MODIFY: call broker_override in backtest mode
    risk_manager_agent.py  — MODIFY: query broker_override for balance

  schemas/
    pipeline_state.py      — MODIFY: add backtest_mode, backtest_broker, backtest_bar_index

frontend/src/app/
  features/backtesting/
    backtesting.component.*          — shell (Run / History tabs)
    backtest-form/
      backtest-form.component.*      — config form (pre-fills from pipeline)
    backtest-result/
      backtest-result.component.*    — full results report
    signal-funnel/
      signal-funnel.component.*      — funnel diagram + per-signal table
    trade-list/
      trade-list.component.*         — trade log MatTable
    backtest-history/
      backtest-history.component.*   — history MatTable

  core/services/
    backtest.service.ts              — API calls + WebSocket progress
```
