"""
Backtest runtime-local signal matching and execution helpers.

This mirrors the relevant trigger-dispatcher matching behavior for the single
pipeline owned by an ephemeral backtest runtime.
"""
from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5
from typing import Any, Dict, List, Set

from app.orchestration.tasks.execute_pipeline import execute_pipeline_inline


def _signal_ticker_symbols(signal: Dict[str, Any]) -> Set[str]:
    return {
        ticker.get("ticker")
        for ticker in (signal.get("tickers") or [])
        if ticker.get("ticker")
    }


def _build_signal_context(signal: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    ticker_match = next(
        (item for item in (signal.get("tickers") or []) if item.get("ticker") == ticker),
        {},
    )
    return {
        "signal_id": str(signal.get("signal_id")),
        "signal_type": signal.get("signal_type"),
        "source": signal.get("source"),
        "timestamp": signal.get("timestamp"),
        "tickers": [ticker],
        "confidence": ticker_match.get("confidence", 50.0),
        "metadata": signal.get("metadata") or {},
    }


def _build_backtest_execution_id(
    *,
    pipeline_id: str,
    ticker: str,
    signal_context: Dict[str, Any],
) -> str | None:
    metadata = signal_context.get("metadata") or {}
    backtest_run_id = metadata.get("backtest_run_id")
    backtest_ts = metadata.get("backtest_ts") or signal_context.get("timestamp")
    if not backtest_run_id or not backtest_ts:
        return None
    return str(uuid5(NAMESPACE_URL, f"{backtest_run_id}:{pipeline_id}:{ticker}:{backtest_ts}"))


def _signal_matches_subscription(
    signal: Dict[str, Any],
    matched_tickers: Set[str],
    signal_subscriptions: List[Dict[str, Any]],
) -> bool:
    if not signal_subscriptions:
        return True

    signal_type = signal.get("signal_type")
    signal_timeframe = (signal.get("metadata") or {}).get("timeframe")

    for subscription in signal_subscriptions:
        if subscription.get("signal_type") != signal_type:
            continue

        subscription_timeframe = subscription.get("timeframe")
        if subscription_timeframe and signal_timeframe and subscription_timeframe != signal_timeframe:
            continue

        min_confidence = subscription.get("min_confidence")
        if min_confidence is not None:
            max_confidence = 0.0
            for ticker_signal in signal.get("tickers") or []:
                ticker_symbol = ticker_signal.get("ticker")
                if ticker_symbol and ticker_symbol in matched_tickers:
                    max_confidence = max(max_confidence, float(ticker_signal.get("confidence", 0.0)))
            if max_confidence < float(min_confidence):
                continue

        return True

    return False


def match_signals_to_single_pipeline(
    signals: List[Dict[str, Any]],
    pipeline,
    allowed_tickers: List[str],
) -> Dict[str, Dict[str, Any]]:
    """
    Return ticker -> signal_context for matches against a single pipeline.
    """
    matched_by_ticker: Dict[str, Dict[str, Any]] = {}
    pipeline_id = str(pipeline.id)
    pipeline_tickers = set(allowed_tickers)
    signal_subscriptions = pipeline.signal_subscriptions or []

    for signal in signals:
        signal_metadata = signal.get("metadata") or {}
        ticker_pipelines = signal_metadata.get("ticker_pipelines") or {}
        matched_tickers = _signal_ticker_symbols(signal) & pipeline_tickers
        if not matched_tickers:
            continue

        if ticker_pipelines:
            routed_tickers = set()
            for ticker in matched_tickers:
                pipelines_for_ticker = ticker_pipelines.get(ticker) or []
                if any(item.get("pipeline_id") == pipeline_id for item in pipelines_for_ticker):
                    routed_tickers.add(ticker)
            matched_tickers = routed_tickers
            if not matched_tickers:
                continue

        if not _signal_matches_subscription(signal, matched_tickers, signal_subscriptions):
            continue

        for ticker in matched_tickers:
            matched_by_ticker.setdefault(ticker, _build_signal_context(signal, ticker))

    return matched_by_ticker


def execute_runtime_matches(
    pipeline,
    user_id: str,
    matched_by_ticker: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    pipeline_snapshot = {
        "id": str(pipeline.id),
        "user_id": str(pipeline.user_id),
        "name": getattr(pipeline, "name", None),
        "description": getattr(pipeline, "description", None),
        "config": pipeline.config or {},
        "trigger_mode": getattr(pipeline, "trigger_mode", None),
        "scanner_id": str(getattr(pipeline, "scanner_id", None)) if getattr(pipeline, "scanner_id", None) else None,
        "signal_subscriptions": pipeline.signal_subscriptions or [],
        "scanner_tickers": getattr(pipeline, "scanner_tickers", []) or [],
        "require_approval": getattr(pipeline, "require_approval", False),
        "approval_modes": getattr(pipeline, "approval_modes", []) or [],
        "schedule_enabled": getattr(pipeline, "schedule_enabled", False),
        "schedule_start_time": getattr(pipeline, "schedule_start_time", None),
        "schedule_end_time": getattr(pipeline, "schedule_end_time", None),
        "schedule_days": getattr(pipeline, "schedule_days", []) or [],
        "liquidate_on_deactivation": getattr(pipeline, "liquidate_on_deactivation", False),
        "user_timezone": getattr(pipeline, "user_timezone", "America/New_York"),
    }
    runtime_snapshot = getattr(pipeline, "runtime_snapshot", None) or {}
    for ticker, signal_context in matched_by_ticker.items():
        result = execute_pipeline_inline(
            pipeline_id=str(pipeline.id),
            user_id=user_id,
            mode="backtest",
            execution_id=_build_backtest_execution_id(
                pipeline_id=str(pipeline.id),
                ticker=ticker,
                signal_context=signal_context,
            ),
            signal_context=signal_context,
            symbol=ticker,
            pipeline_snapshot=pipeline_snapshot,
            runtime_snapshot=runtime_snapshot,
        )
        results.append(
            {
                "ticker": ticker,
                "signal_context": signal_context,
                "result": result,
            }
        )
    return results
