"""
Performance Analytics (TP-015)

Computes standard trading performance metrics from a completed backtest.
All metrics are deterministic given the same trade list and equity curve.
"""
from __future__ import annotations

import math
import statistics
from typing import List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.backtesting.engine import Trade


class PerformanceAnalytics:
    """Static methods to compute backtest performance metrics."""

    @staticmethod
    def compute(
        trades: List["Trade"],
        equity_curve: List[float],
        initial_capital: float,
    ) -> Dict[str, Any]:
        """
        Compute the full performance metric suite.

        Args:
            trades:          Closed trades from BacktestEngine.run()
            equity_curve:    Equity snapshots (one per bar + final close)
            initial_capital: Starting account balance

        Returns:
            Dict with all metrics (safe to JSON-serialise — all values are
            Python scalars or None).
        """
        if not trades:
            return PerformanceAnalytics._empty_metrics(initial_capital)

        winners = [t for t in trades if t.net_pnl > 0]
        losers  = [t for t in trades if t.net_pnl <= 0]

        total_net_pnl = sum(t.net_pnl for t in trades)
        gross_profit  = sum(t.net_pnl for t in winners)
        gross_loss    = abs(sum(t.net_pnl for t in losers))

        win_rate = len(winners) / len(trades)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        avg_win  = (gross_profit / len(winners))  if winners else 0.0
        avg_loss = (gross_loss   / len(losers))   if losers  else 0.0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

        r_multiples = [t.r_multiple for t in trades if t.r_multiple != 0]
        avg_r = statistics.mean(r_multiples) if r_multiples else 0.0

        # Drawdown from equity curve
        max_dd_pct, max_dd_abs = PerformanceAnalytics._max_drawdown(equity_curve)

        # Sharpe / Sortino computed on bar-level returns, annualised with periods=252.
        # For 5m data this understates the ratio by sqrt(78); use for relative comparison only.
        daily_returns = PerformanceAnalytics._daily_returns(equity_curve)
        sharpe = PerformanceAnalytics._sharpe(daily_returns)
        sortino = PerformanceAnalytics._sortino(daily_returns)

        # Calmar ratio = CAGR / |max_drawdown_pct|
        final_equity = equity_curve[-1] if equity_curve else initial_capital
        total_return_pct = (final_equity - initial_capital) / initial_capital
        calmar = (total_return_pct / max_dd_pct) if max_dd_pct > 0 else 0.0

        durations = [t.duration_bars for t in trades if t.duration_bars > 0]
        avg_duration_bars = statistics.mean(durations) if durations else 0.0

        commissions_total = sum(t.commission for t in trades)
        slippage_total    = sum(t.slippage   for t in trades)

        # Per-regime breakdown
        regime_stats = PerformanceAnalytics._by_key(trades, "regime")
        family_stats = PerformanceAnalytics._by_key(trades, "strategy_family")

        return {
            # Summary
            "total_trades":        len(trades),
            "winning_trades":      len(winners),
            "losing_trades":       len(losers),
            "win_rate":            round(win_rate, 4),
            # P&L
            "total_net_pnl":       round(total_net_pnl, 2),
            "gross_profit":        round(gross_profit, 2),
            "gross_loss":          round(gross_loss, 2),
            "profit_factor":       round(profit_factor, 4) if math.isfinite(profit_factor) else None,
            # Per-trade
            "avg_win":             round(avg_win, 2),
            "avg_loss":            round(avg_loss, 2),
            "expectancy":          round(expectancy, 2),
            "avg_r_multiple":      round(avg_r, 3),
            # Risk / Drawdown
            "max_drawdown_pct":    round(max_dd_pct, 4),
            "max_drawdown_abs":    round(max_dd_abs, 2),
            # Risk-adjusted returns
            "sharpe_ratio":        round(sharpe,  3) if math.isfinite(sharpe)  else None,
            "sortino_ratio":       round(sortino, 3) if math.isfinite(sortino) else None,
            "calmar_ratio":        round(calmar,  3),
            "total_return_pct":    round(total_return_pct, 4),
            # Costs
            "total_commission":    round(commissions_total, 2),
            "total_slippage":      round(slippage_total, 2),
            # Duration
            "avg_duration_bars":   round(avg_duration_bars, 1),
            # Breakdown
            "by_regime":           regime_stats,
            "by_strategy_family":  family_stats,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_metrics(initial_capital: float) -> Dict[str, Any]:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_net_pnl": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "profit_factor": None,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "expectancy": 0.0,
            "avg_r_multiple": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_abs": 0.0,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "calmar_ratio": 0.0,
            "total_return_pct": 0.0,
            "total_commission": 0.0,
            "total_slippage": 0.0,
            "avg_duration_bars": 0.0,
            "by_regime": {},
            "by_strategy_family": {},
        }

    @staticmethod
    def _max_drawdown(equity_curve: List[float]):
        """Return (max_drawdown_pct, max_drawdown_abs) from an equity curve."""
        if len(equity_curve) < 2:
            return 0.0, 0.0
        peak = equity_curve[0]
        max_dd_pct = 0.0
        max_dd_abs = 0.0
        for v in equity_curve[1:]:
            if v > peak:
                peak = v
            if peak > 0:
                dd_pct = (peak - v) / peak
                dd_abs = peak - v
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct
                    max_dd_abs = dd_abs
        return max_dd_pct, max_dd_abs

    @staticmethod
    def _daily_returns(equity_curve: List[float]) -> List[float]:
        """Convert equity curve to period-over-period returns."""
        if len(equity_curve) < 2:
            return []
        returns = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]
            if prev > 0:
                returns.append((equity_curve[i] - prev) / prev)
        return returns

    @staticmethod
    def _sharpe(returns: List[float], risk_free: float = 0.0, periods: int = 252) -> float:
        """Annualised Sharpe ratio."""
        if len(returns) < 2:
            return 0.0
        excess = [r - risk_free / periods for r in returns]
        mean_e = statistics.mean(excess)
        std_e  = statistics.stdev(excess)
        if std_e == 0:
            return 0.0
        return (mean_e / std_e) * math.sqrt(periods)

    @staticmethod
    def _sortino(returns: List[float], risk_free: float = 0.0, periods: int = 252) -> float:
        """Annualised Sortino ratio (downside deviation only)."""
        if len(returns) < 2:
            return 0.0
        excess = [r - risk_free / periods for r in returns]
        mean_e = statistics.mean(excess)
        downside = [r for r in excess if r < 0]
        if not downside:
            return float("inf")
        downside_std = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
        if downside_std == 0:
            return 0.0
        return (mean_e / downside_std) * math.sqrt(periods)

    @staticmethod
    def _by_key(trades: List["Trade"], key: str) -> Dict[str, Dict[str, Any]]:
        """Compute win/loss/pnl breakdown grouped by a trade attribute."""
        groups: Dict[str, list] = {}
        for t in trades:
            k = str(getattr(t, key, "unknown") or "unknown")
            groups.setdefault(k, []).append(t)

        result = {}
        for k, group in groups.items():
            wins = [t for t in group if t.net_pnl > 0]
            result[k] = {
                "trades":    len(group),
                "win_rate":  round(len(wins) / len(group), 4),
                "net_pnl":   round(sum(t.net_pnl for t in group), 2),
            }
        return result
