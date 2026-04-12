"""Backtesting package with lazy exports to avoid heavy import-time side effects."""

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "ExecutionSimulator",
    "SlippageModel",
    "CommissionModel",
    "PerformanceAnalytics",
    "WalkForwardValidator",
]


def __getattr__(name):
    if name in {"BacktestEngine", "BacktestConfig", "BacktestResult"}:
        from .engine import BacktestEngine, BacktestConfig, BacktestResult

        return {
            "BacktestEngine": BacktestEngine,
            "BacktestConfig": BacktestConfig,
            "BacktestResult": BacktestResult,
        }[name]
    if name in {"ExecutionSimulator", "SlippageModel", "CommissionModel"}:
        from .simulation import ExecutionSimulator, SlippageModel, CommissionModel

        return {
            "ExecutionSimulator": ExecutionSimulator,
            "SlippageModel": SlippageModel,
            "CommissionModel": CommissionModel,
        }[name]
    if name == "PerformanceAnalytics":
        from .analytics import PerformanceAnalytics

        return PerformanceAnalytics
    if name == "WalkForwardValidator":
        from .walk_forward import WalkForwardValidator

        return WalkForwardValidator
    raise AttributeError(name)
