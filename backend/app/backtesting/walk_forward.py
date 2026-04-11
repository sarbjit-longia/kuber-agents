"""
Walk-Forward Validation (TP-016)

Splits a candle dataset into non-overlapping in-sample / out-of-sample windows
and runs BacktestEngine on each, then aggregates the results.

This prevents overfitting: strategy parameters that look good in-sample must
also hold up in the held-out out-of-sample window.

Usage::
    validator = WalkForwardValidator(
        config=base_config,
        n_splits=5,
        train_pct=0.70,
    )
    report = validator.run(candles)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.backtesting.engine import BacktestConfig, BacktestResult, Trade
from app.schemas.pipeline_state import TimeframeData


@dataclass
class WalkForwardWindow:
    """One in-sample + out-of-sample split."""
    split_index: int
    train_start: int           # candle index
    train_end:   int
    test_start:  int
    test_end:    int
    train_result: Optional["BacktestResult"] = None
    test_result:  Optional["BacktestResult"] = None


@dataclass
class WalkForwardReport:
    """Aggregate summary across all WFV windows."""
    config: "BacktestConfig"
    windows: List[WalkForwardWindow] = field(default_factory=list)
    aggregate_metrics: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        m = self.aggregate_metrics
        return (
            f"WFV {self.config.symbol} {self.config.strategy_family} "
            f"| {len(self.windows)} windows "
            f"| OOS Win% {m.get('oos_win_rate', 0)*100:.1f}% "
            f"| OOS PF {m.get('oos_profit_factor', 0):.2f} "
            f"| OOS Net P&L ${m.get('oos_total_net_pnl', 0):,.2f}"
        )


class WalkForwardValidator:
    """
    Runs walk-forward validation over a candle dataset.

    For each split:
      - train window:  in-sample optimisation (BacktestEngine as-is)
      - test window:   out-of-sample validation (same unmodified engine)

    No parameter optimisation is performed here — the evaluators are
    deterministic so there is nothing to optimise. WFV is used purely to
    measure whether the strategy regime-conditions generalise out-of-sample.
    """

    def __init__(
        self,
        config: "BacktestConfig",
        n_splits: int = 5,
        train_pct: float = 0.70,
        min_bars: int = 100,
    ):
        """
        Args:
            config:    BacktestConfig to use for all splits.
            n_splits:  Number of walk-forward windows.
            train_pct: Fraction of each window used for training (0 < pct < 1).
            min_bars:  Minimum bars in the test window; splits below this are skipped.
        """
        self.config    = config
        self.n_splits  = n_splits
        self.train_pct = train_pct
        self.min_bars  = min_bars

    def run(self, candles: List[TimeframeData]) -> WalkForwardReport:
        """
        Run walk-forward validation on candle data.

        Args:
            candles: Full candle dataset in chronological order.

        Returns:
            WalkForwardReport with per-window and aggregate metrics.
        """
        from app.backtesting.engine import BacktestEngine
        from app.backtesting.analytics import PerformanceAnalytics

        report = WalkForwardReport(config=self.config)
        windows = self._build_windows(candles)

        for win in windows:
            train_candles = candles[win.train_start : win.train_end]
            test_candles  = candles[win.test_start  : win.test_end]

            if len(test_candles) < self.min_bars:
                continue

            engine = BacktestEngine(self.config)

            if len(train_candles) > engine.WARMUP_BARS:
                win.train_result = engine.run(train_candles)

            engine2 = BacktestEngine(self.config)
            win.test_result = engine2.run(test_candles)

            report.windows.append(win)

        report.aggregate_metrics = self._aggregate(report.windows)
        return report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_windows(self, candles: List[TimeframeData]) -> List[WalkForwardWindow]:
        n = len(candles)
        window_size = math.ceil(n / self.n_splits)
        windows = []

        for i in range(self.n_splits):
            win_start = i * window_size
            win_end   = min(win_start + window_size, n)
            if win_end <= win_start:
                break

            split = win_start + int((win_end - win_start) * self.train_pct)
            windows.append(WalkForwardWindow(
                split_index=i,
                train_start=win_start,
                train_end=split,
                test_start=split,
                test_end=win_end,
            ))

        return windows

    def _aggregate(self, windows: List[WalkForwardWindow]) -> Dict[str, Any]:
        """Aggregate out-of-sample metrics across all completed windows."""
        oos_trades: List["Trade"] = []
        oos_equity_curves: List[List[float]] = []

        for w in windows:
            if w.test_result:
                oos_trades.extend(w.test_result.trades)
                oos_equity_curves.append(w.test_result.equity_curve)

        if not oos_trades:
            return {"oos_total_trades": 0}

        from app.backtesting.analytics import PerformanceAnalytics

        # Build a stitched equity curve (normalise each window to start at 1)
        oos_equity_flat: List[float] = []
        base = self.config.initial_capital
        for curve in oos_equity_curves:
            if not curve:
                continue
            # Re-base each window off the prior ending equity
            scale = base / curve[0] if curve[0] != 0 else 1.0
            for v in curve:
                oos_equity_flat.append(v * scale)
            base = oos_equity_flat[-1]

        metrics = PerformanceAnalytics.compute(
            trades=oos_trades,
            equity_curve=oos_equity_flat,
            initial_capital=self.config.initial_capital,
        )

        # Re-key to make it clear these are out-of-sample figures
        return {f"oos_{k}": v for k, v in metrics.items()}
