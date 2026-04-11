# Backtesting UI Implementation Plan

## What Is Already Built (Backend)

The backtesting engine is fully implemented in `backend/app/backtesting/`. Nothing needs to be built there — only wired up via a REST API and then consumed by the frontend.

### Engine capabilities

| Component | File | What it does |
|-----------|------|--------------|
| `BacktestEngine` | `engine.py` | Runs a full event-driven backtest over OHLCV candles using the same `RegimeDetector` + `SetupEvaluator` as live trading |
| `PerformanceAnalytics` | `analytics.py` | Computes 20+ metrics: win rate, profit factor, Sharpe, Sortino, Calmar, max drawdown, R-multiples, per-regime and per-strategy breakdowns |
| `WalkForwardValidator` | `walk_forward.py` | Splits data into N folds (default 5, 70% train), runs engine per fold, stitches out-of-sample equity curve to prevent overfitting |
| `ExecutionSimulator` | `simulation.py` | Applies slippage (fixed / pct / spread) and commission (per_share / flat / pct) to fills |

### BacktestConfig fields

```
symbol           string    Ticker (e.g. "AAPL")
strategy_family  string    orb | vwap_pullback | first_pullback | ema_trend |
                           rsi_mean_reversion | volatility_breakout | overnight_gap
start_date       date      Backtest window start
end_date         date      Backtest window end
initial_capital  float     Starting capital (default 10 000)
risk_pct         float     Risk per trade as fraction (default 0.01 = 1%)
timeframe        string    Candle timeframe (default "5m")
slippage_model   string    fixed | pct | spread
slippage_value   float     Dollar or fraction amount
commission_model string    per_share | flat | pct
commission_value float     Commission rate
allow_short      bool      Allow short positions (default true)
```

### Metrics returned

**Summary:** `total_trades`, `winning_trades`, `losing_trades`, `win_rate`

**P&L:** `total_net_pnl`, `gross_profit`, `gross_loss`, `profit_factor`

**Per-trade:** `avg_win`, `avg_loss`, `expectancy`, `avg_r_multiple`

**Risk:** `max_drawdown_pct`, `max_drawdown_abs`, `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`, `total_return_pct`

**Costs:** `total_commission`, `total_slippage`

**Breakdowns:** `by_regime` and `by_strategy_family` → `{trades, win_rate, net_pnl}` per bucket

**Walk-forward only:** Per-fold in-sample and out-of-sample metrics, stitched OOS equity curve

### Trade fields (per completed trade)

`entry_time`, `exit_time`, `entry_price`, `exit_price`, `action` (BUY/SELL), `stop_loss`, `take_profit`, `position_size`, `gross_pnl`, `net_pnl`, `commission`, `slippage`, `exit_reason` (target / stop / time_stop / eod), `regime`, `session`, `duration_bars`, `r_multiple`

---

## What Needs to Be Built

### Phase A — Backend REST API (prerequisite for UI)

Two new endpoints are needed. Both belong in a new file `backend/app/api/v1/backtests.py`, registered in `backend/app/api/v1/__init__.py`.

#### `POST /api/v1/backtests/run`

Accepts `BacktestConfig` JSON. Internally:
1. Fetches OHLCV candles from the data plane service (`http://data-plane:8005/api/v1/bars/{symbol}`)
2. Calls `BacktestEngine(config).run(candles)`
3. Optionally runs `WalkForwardValidator` if `walk_forward: true` in the request
4. Stores result in a new `Backtest` database table
5. Returns the full result immediately (synchronous for now; make async with Celery later if runtimes exceed 10 s)

**Request body:**
```json
{
  "symbol": "AAPL",
  "strategy_family": "orb",
  "start_date": "2024-01-01",
  "end_date": "2024-06-30",
  "initial_capital": 10000,
  "risk_pct": 0.01,
  "timeframe": "5m",
  "slippage_model": "fixed",
  "slippage_value": 0.01,
  "commission_model": "per_share",
  "commission_value": 0.005,
  "allow_short": true,
  "walk_forward": false
}
```

**Response:** full metrics + trades list + equity curve (see schema below)

#### `GET /api/v1/backtests`

Returns paginated list of past backtests for the current user. Used to populate the history table on the UI.

**Response:**
```json
{
  "backtests": [
    {
      "id": "uuid",
      "symbol": "AAPL",
      "strategy_family": "orb",
      "start_date": "2024-01-01",
      "end_date": "2024-06-30",
      "total_trades": 48,
      "win_rate": 0.54,
      "total_net_pnl": 1230.50,
      "max_drawdown_pct": 0.08,
      "sharpe_ratio": 1.32,
      "created_at": "2026-04-11T12:00:00Z"
    }
  ],
  "total": 12
}
```

#### `GET /api/v1/backtests/{id}`

Returns the full result for a single past backtest (metrics + trades + equity curve). Used when the user clicks into a history row.

#### Database model

Add a `Backtest` SQLAlchemy model with these columns:

```
id             UUID PK
user_id        UUID FK → users
symbol         VARCHAR
strategy_family VARCHAR
start_date     DATE
end_date       DATE
config         JSONB   (full BacktestConfig)
metrics        JSONB   (computed metrics dict)
trades         JSONB   (list of trade dicts)
equity_curve   JSONB   (list of floats)
walk_forward   BOOL
wfv_report     JSONB   (walk-forward results, nullable)
created_at     TIMESTAMP
```

Create an Alembic migration after adding the model.

---

### Phase B — Frontend

#### File structure to create

```
frontend/src/app/features/backtesting/
  backtesting.component.ts        — Parent shell (tabs: Run / History)
  backtesting.component.html
  backtesting.component.scss

  backtest-form/
    backtest-form.component.ts    — Config form
    backtest-form.component.html
    backtest-form.component.scss

  backtest-result/
    backtest-result.component.ts  — Full result report (sidebar + sections)
    backtest-result.component.html
    backtest-result.component.scss

  backtest-history/
    backtest-history.component.ts — Table of past runs
    backtest-history.component.html
    backtest-history.component.scss

frontend/src/app/core/services/
  backtest.service.ts             — API calls + BehaviorSubject state
```

#### Routing

Add to `frontend/src/app/app.routes.ts`:

```typescript
{
  path: 'backtesting',
  loadComponent: () => import('./features/backtesting/backtesting.component')
    .then(m => m.BacktestingComponent),
  canActivate: [authGuard],
},
{
  path: 'backtesting/:id',
  loadComponent: () => import('./features/backtesting/backtest-result/backtest-result.component')
    .then(m => m.BacktestResultComponent),
  canActivate: [authGuard],
},
```

#### BacktestService

```typescript
// frontend/src/app/core/services/backtest.service.ts

export interface BacktestRequest { ... }   // matches BacktestConfig fields
export interface BacktestSummary { ... }   // list row fields
export interface BacktestResult  { ... }   // full result with trades + equity curve

@Injectable({ providedIn: 'root' })
export class BacktestService {
  private resultSubject = new BehaviorSubject<BacktestResult | null>(null);
  result$ = this.resultSubject.asObservable();

  runBacktest(req: BacktestRequest): Observable<BacktestResult>
  listBacktests(limit = 20, offset = 0): Observable<{ backtests: BacktestSummary[]; total: number }>
  getBacktest(id: string): Observable<BacktestResult>
}
```

---

## UI Layout Design

### Page 1 — `/backtesting` (Run + History tabs)

```
┌─────────────────────────────────────────────────────────┐
│  Backtesting                                            │
│  ──────────────────────────────────────────────────     │
│  [Run New Backtest]  [History]   ← tab bar              │
│                                                         │
│  ┌──── RUN TAB ─────────────────────────────────────┐   │
│  │                                                   │   │
│  │  SYMBOL         [AAPL              ]              │   │
│  │  STRATEGY       [ORB ▼             ]              │   │
│  │  DATE RANGE     [2024-01-01] → [2024-06-30]       │   │
│  │  CAPITAL        [10000             ]              │   │
│  │  RISK %         [1.0               ]              │   │
│  │  TIMEFRAME      [5m ▼              ]              │   │
│  │                                                   │   │
│  │  ── COSTS (collapsible) ──────────────────────    │   │
│  │  SLIPPAGE MODEL [fixed ▼]  VALUE [0.01]           │   │
│  │  COMMISSION     [per_share▼] VALUE [0.005]        │   │
│  │                                                   │   │
│  │  ── OPTIONS ──────────────────────────────────    │   │
│  │  [☐] Allow short    [☐] Walk-forward validation   │   │
│  │       (5 folds, 70/30 split)                      │   │
│  │                                                   │   │
│  │           [▶ Run Backtest]                        │   │
│  │                                                   │   │
│  │  ── RESULT (appears after run) ───────────────    │   │
│  │  [inline BacktestResultComponent]                 │   │
│  │                                                   │   │
│  └───────────────────────────────────────────────────┘   │
│                                                         │
│  ┌──── HISTORY TAB ──────────────────────────────────┐   │
│  │  Symbol │ Strategy │ Period     │ Trades │ Win% │ P&L │
│  │  AAPL   │ ORB      │ Jan–Jun 24 │ 48     │ 54%  │ +$1230 │
│  │  ...                                              │   │
│  │  [Load more]                                      │   │
│  └───────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Page 2 — `/backtesting/:id` (Full Result Report)

Follows the same layout as the execution report: **sticky left sidebar** + **scrollable main content**.

```
┌─── SIDEBAR ───────────────────────────────────────────────────────────────────┐
│  AAPL · ORB                                                                   │
│  Jan 1 – Jun 30, 2024                                                         │
│                                                                               │
│  Net P&L                                                                      │
│  +$1,230.50 ▲ 12.3%                                                           │
│                                                                               │
│  ── Navigate ──────                                                           │
│  • Summary                                                                    │
│  • Equity Curve                                                               │
│  • Trade List                                                                 │
│  • By Regime                                                                  │
│  • By Strategy                                                                │
│  • Walk-Forward (if run)                                                      │
└───────────────────────────────────────────────────────────────────────────────┘

MAIN CONTENT SECTIONS:

┌─── SUMMARY ─────────────────────────────────────────────────────────────────┐
│  8-12 metric cards in a responsive grid:                                    │
│  Trades  Win%  Profit Factor  Expectancy  Sharpe  Sortino  Max DD  Calmar   │
│  Gross P  Net P  Commission  Slippage  Avg Duration                         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─── EQUITY CURVE ────────────────────────────────────────────────────────────┐
│  Line chart: equity_curve over time                                         │
│  Secondary: daily_returns bar chart                                         │
│  Use TradingChartComponent (existing shared component) or lightweight       │
│  Chart.js line chart if candlestick is not needed                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─── TRADE LIST ──────────────────────────────────────────────────────────────┐
│  MatTable with pagination + sorting                                         │
│  Columns: #  Entry Time  Symbol  Action  Entry  Exit  Size  P&L  R  Regime  │
│  Color rows: green = winner, red = loser                                    │
│  Exit reason chip: target | stop | time_stop | eod                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─── BY REGIME ───────────────────────────────────────────────────────────────┐
│  Table: Regime | Trades | Win% | Net P&L | Avg R                            │
│  + horizontal bar chart per regime showing win rate                         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─── BY STRATEGY ─────────────────────────────────────────────────────────────┐
│  Same layout as By Regime                                                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─── WALK-FORWARD (conditional) ──────────────────────────────────────────────┐
│  Table: Fold | Train Period | OOS Period | OOS Win% | OOS P&L | OOS Sharpe  │
│  Line chart: stitched OOS equity curve                                      │
│  Warning banner if OOS Sharpe degrades >50% vs in-sample                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Order

### Step 1 — Database model + migration

1. Add `backend/app/models/backtest.py` with the `Backtest` SQLAlchemy model
2. Add to `backend/app/models/__init__.py`
3. Run `docker exec -it clovercharts-backend alembic revision --autogenerate -m "add_backtest_table"` and `alembic upgrade head`

### Step 2 — API endpoints

1. Create `backend/app/api/v1/backtests.py` with `POST /run`, `GET /`, `GET /{id}`
2. Add `from app.api.v1.backtests import router as backtests_router` in `__init__.py`
3. The endpoint fetches candles from `http://data-plane:8005/api/v1/bars/{symbol}?timeframe=...&start=...&end=...` and passes them to `BacktestEngine.run()`
4. Test via Swagger at `http://localhost:8000/docs`

### Step 3 — BacktestService

Create `frontend/src/app/core/services/backtest.service.ts` with typed interfaces and RxJS methods.

### Step 4 — Backtest form component

Build `backtest-form.component` using Angular Material form fields:
- `MatSelectModule` for strategy family, slippage model, commission model, timeframe
- `MatDatepickerModule` for date range
- `MatInputModule` for numeric fields
- `MatCheckboxModule` for allow_short and walk_forward flags
- Emit `BacktestRequest` on submit

### Step 5 — Backtest result component

Build `backtest-result.component` using the execution-report layout pattern (already exists in the codebase):
- Summary metric cards (copy the `agent-data-grid` pattern from execution report)
- Equity curve: use `Chart.js` (already a dependency via `ng2-charts` or add it) for a simple line chart
- Trade table: `MatTable` with `MatSort` and `MatPaginator`
- Regime/strategy breakdown tables
- Walk-forward section (conditional on `result.walk_forward === true`)

### Step 6 — History component

Build `backtest-history.component` as a simple `MatTable` with sortable columns and a "View" button per row that navigates to `/backtesting/:id`.

### Step 7 — Parent shell + routing

Build the `BacktestingComponent` shell with `MatTabGroup` (Run / History tabs). Register routes in `app.routes.ts`. Add a "Backtesting" link to the navigation bar.

---

## Dependency Notes

- **Chart.js / ng2-charts**: If not already installed, add `ng2-charts` and `chart.js` for the equity curve. Check `frontend/package.json` first — if `ngx-echarts` or similar is already present, use that instead.
- **Data plane candles**: The endpoint `GET /api/v1/bars/{symbol}` must be reachable from the backend container at `http://data-plane:8005`. Confirm the data plane has sufficient history for the requested date range; the response will be empty for dates before the ingestion start.
- **Long-running backtests**: For date ranges > 1 year on 5m candles (~18 000 bars), the engine may take 5–15 seconds. For now, run synchronously and show a spinner. If this becomes a bottleneck, move to a Celery task and poll for status with WebSocket updates (same pattern as pipeline execution).

---

## What Already Exists and Can Be Reused

| Existing asset | Reuse for |
|----------------|-----------|
| `execution-report` sidebar+main layout | `BacktestResultComponent` layout |
| `agent-data-grid` CSS class | Summary metric cards |
| `TradingChartComponent` | Equity curve (if adapted to line data) |
| `MatTable` pattern in monitoring list | Trade list and history table |
| `JsonSchemaFormComponent` | Could auto-generate form from BacktestConfig schema |
| `LocalDatePipe` | Format entry/exit timestamps in trade table |
| `ConfirmDialogComponent` | Re-run confirmation |
| `AuthGuard` / `ApiService` | Protect route and make HTTP calls |
