"""
Event-Driven Backtest Engine (TP-014)

Replays historical candles through the same deterministic strategy engine
used in live trading. Uses identical RegimeDetector + SetupEvaluator so that
backtest results match live behaviour.

Usage::
    config = BacktestConfig(
        symbol="AAPL",
        strategy_family="orb",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 6, 30),
        initial_capital=10000.0,
        risk_pct=0.01,
    )
    engine = BacktestEngine(config)
    result = engine.run(candles)
"""
from __future__ import annotations

import uuid
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Dict, Any

from app.agents.strategy_engine import RegimeDetector, SetupEvaluator
from app.schemas.pipeline_state import TimeframeData, StrategySpec
from app.backtesting.simulation import ExecutionSimulator, SlippageModel, CommissionModel


@dataclass
class BacktestConfig:
    symbol: str
    strategy_family: str           # One of the evaluator families
    start_date: date
    end_date: date
    initial_capital: float = 10_000.0
    risk_pct: float = 0.01         # 1% per trade default
    timeframe: str = "5m"
    slippage_model: str = "fixed"  # "fixed" | "pct" | "spread"
    slippage_value: float = 0.01   # $0.01 per share fixed, or 0.001 = 0.1%
    commission_model: str = "per_share"
    commission_value: float = 0.005  # $0.005/share (Interactive Brokers-like)
    max_concurrent: int = 1
    allow_short: bool = True
    session_filter: Optional[str] = None  # Only trade certain sessions


@dataclass
class Trade:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    strategy_family: str = ""
    action: str = ""              # BUY | SELL
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    entry_price: float = 0.0
    exit_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    position_size: float = 0.0
    gross_pnl: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    net_pnl: float = 0.0
    exit_reason: str = ""         # "target" | "stop" | "time_stop" | "eod"
    regime: str = ""
    session: str = ""
    duration_bars: int = 0
    r_multiple: float = 0.0       # net_pnl / initial_risk


@dataclass
class BacktestResult:
    config: BacktestConfig
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        m = self.metrics
        return (
            f"Backtest: {self.config.symbol} {self.config.strategy_family} "
            f"| {len(self.trades)} trades "
            f"| Win% {m.get('win_rate', 0)*100:.1f}% "
            f"| PF {m.get('profit_factor', 0):.2f} "
            f"| Max DD {m.get('max_drawdown_pct', 0)*100:.1f}% "
            f"| Net P&L ${m.get('total_net_pnl', 0):,.2f}"
        )


class BacktestEngine:
    """
    Replay candles through deterministic evaluators and simulate execution.

    The engine works in three stages per bar:
      1. Build a rolling candle window and run RegimeDetector + SetupEvaluator
      2. If a setup fires and no position is open, open a simulated trade
      3. For open positions, check stop/target/time-stop against the current bar
    """

    # Minimum bars needed before evaluators can fire
    WARMUP_BARS = 30

    def __init__(self, config: BacktestConfig):
        self.config  = config
        self.detector = RegimeDetector()
        self.evaluator = SetupEvaluator()
        self.simulator = ExecutionSimulator(
            slippage=SlippageModel(config.slippage_model, config.slippage_value),
            commission=CommissionModel(config.commission_model, config.commission_value),
        )

    def run(self, candles: List[TimeframeData]) -> BacktestResult:
        """
        Run the full backtest over a list of candles.

        Args:
            candles: List of TimeframeData in chronological order.

        Returns:
            BacktestResult with trades, equity curve, and performance metrics.
        """
        result   = BacktestResult(config=self.config)
        capital  = self.config.initial_capital
        position: Optional[Trade] = None

        result.equity_curve.append(capital)

        for i in range(self.WARMUP_BARS, len(candles)):
            window = candles[max(0, i - 60): i + 1]  # up to 60-bar window
            current = candles[i]

            # ── 1. Manage open position ────────────────────────────────────
            if position is not None:
                position, capital, closed = self._manage_position(
                    position, current, capital
                )
                if closed:
                    result.trades.append(closed)
                    position = None

            # ── 2. Look for new entry (only if flat) ───────────────────────
            if position is None:
                spec = self._evaluate(window, float(current.close))
                if spec and spec.action != "HOLD":
                    entry_price = self.simulator.apply_slippage(
                        float(spec.entry_price or current.close),
                        spec.action,
                    )
                    size = self._position_size(
                        capital,
                        entry_price,
                        float(spec.stop_loss or entry_price * 0.98),
                    )
                    if size > 0:
                        commission = self.simulator.commission.calculate(entry_price, size)
                        position = Trade(
                            strategy_family=spec.strategy_family,
                            action=spec.action,
                            entry_time=current.timestamp,
                            entry_price=entry_price,
                            stop_loss=float(spec.stop_loss or 0),
                            take_profit=float(spec.take_profit or 0),
                            position_size=size,
                            commission=commission,
                            regime=self._regime_label(window, current),
                        )
                        capital -= commission  # Debit entry commission

            result.equity_curve.append(capital + self._open_pnl(position, current))

        # Close any open position at end of data
        if position is not None:
            last = candles[-1]
            closed = self._force_close(position, last, "eod")
            capital += closed.net_pnl
            result.trades.append(closed)

        result.equity_curve.append(capital)

        # Compute metrics
        from app.backtesting.analytics import PerformanceAnalytics
        result.metrics = PerformanceAnalytics.compute(
            trades=result.trades,
            equity_curve=result.equity_curve,
            initial_capital=self.config.initial_capital,
        )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _evaluate(
        self, window: List[TimeframeData], price: float
    ) -> Optional[StrategySpec]:
        """Run regime + setup evaluation on the current window."""
        try:
            regime = self.detector.detect(
                candles_5m=window,
                current_price=price,
            )
            spec = self.evaluator.evaluate(
                regime=regime,
                candles_5m=window,
                current_price=price,
                execution_timeframe=self.config.timeframe,
            )
            if spec and spec.strategy_family != self.config.strategy_family:
                return None  # Only trade the configured family
            return spec
        except Exception:
            return None

    def _regime_label(self, window: List[TimeframeData], current: TimeframeData) -> str:
        try:
            r = self.detector.detect(candles_5m=window, current_price=float(current.close))
            return r.trend
        except Exception:
            return "unknown"

    def _position_size(self, capital: float, entry: float, stop: float) -> float:
        risk_pct  = self.config.risk_pct
        risk_dist = abs(entry - stop)
        if risk_dist <= 0 or entry <= 0:
            return 0.0
        size = (capital * risk_pct) / risk_dist
        max_affordable = capital / entry
        return max(0.0, min(size, max_affordable))

    def _manage_position(
        self,
        position: Trade,
        bar: TimeframeData,
        capital: float,
    ):
        """Check stop/target on current bar. Returns (position, capital, closed_trade)."""
        action  = position.action
        stop    = position.stop_loss
        target  = position.take_profit
        size    = position.position_size
        high    = float(bar.high)
        low     = float(bar.low)
        closed  = None

        if action == "BUY":
            # Check stop first (conservative)
            if stop > 0 and low <= stop:
                exit_price = self.simulator.apply_slippage(stop, "SELL")
                closed = self._close_trade(position, bar, exit_price, "stop")
                capital += closed.net_pnl
            elif target > 0 and high >= target:
                exit_price = self.simulator.apply_slippage(target, "SELL")
                closed = self._close_trade(position, bar, exit_price, "target")
                capital += closed.net_pnl

        elif action == "SELL":
            if stop > 0 and high >= stop:
                exit_price = self.simulator.apply_slippage(stop, "BUY")
                closed = self._close_trade(position, bar, exit_price, "stop")
                capital += closed.net_pnl
            elif target > 0 and low <= target:
                exit_price = self.simulator.apply_slippage(target, "BUY")
                closed = self._close_trade(position, bar, exit_price, "target")
                capital += closed.net_pnl

        if closed:
            return None, capital, closed
        return position, capital, None

    def _close_trade(
        self,
        trade: Trade,
        bar: TimeframeData,
        exit_price: float,
        reason: str,
    ) -> Trade:
        exit_commission = self.simulator.commission.calculate(exit_price, trade.position_size)
        # Slippage = difference between the reference level and the actual fill price.
        # Only meaningful for stop/target exits; eod/time-stop exits have no slippage reference.
        if reason == "stop":
            ref_price = trade.stop_loss
        elif reason == "target":
            ref_price = trade.take_profit
        else:
            ref_price = exit_price  # eod / time_stop — no slippage beyond what's in exit_price
        slippage_cost = abs(exit_price - ref_price)

        if trade.action == "BUY":
            gross_pnl = (exit_price - trade.entry_price) * trade.position_size
        else:
            gross_pnl = (trade.entry_price - exit_price) * trade.position_size

        net_pnl = gross_pnl - trade.commission - exit_commission

        initial_risk = abs(trade.entry_price - trade.stop_loss) * trade.position_size
        r_multiple   = net_pnl / initial_risk if initial_risk > 0 else 0.0

        trade.exit_time     = bar.timestamp
        trade.exit_price    = exit_price
        trade.gross_pnl     = gross_pnl
        trade.commission   += exit_commission
        trade.slippage      = slippage_cost
        trade.net_pnl       = net_pnl
        trade.exit_reason   = reason
        trade.r_multiple    = r_multiple
        return trade

    def _force_close(self, trade: Trade, bar: TimeframeData, reason: str) -> Trade:
        return self._close_trade(trade, bar, float(bar.close), reason)

    def _open_pnl(self, position: Optional[Trade], bar: TimeframeData) -> float:
        if position is None:
            return 0.0
        price = float(bar.close)
        if position.action == "BUY":
            return (price - position.entry_price) * position.position_size
        return (position.entry_price - price) * position.position_size
