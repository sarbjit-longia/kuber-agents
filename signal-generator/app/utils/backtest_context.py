"""
Context helpers for historical/backtest signal replay.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional


_backtest_ts: ContextVar[Optional[str]] = ContextVar("signal_generator_backtest_ts", default=None)


def get_backtest_ts() -> Optional[str]:
    return _backtest_ts.get()


@contextmanager
def use_backtest_ts(timestamp: Optional[str]):
    token = _backtest_ts.set(timestamp)
    try:
        yield
    finally:
        _backtest_ts.reset(token)
