"""
Backtest orchestrator for parity pipeline replay.
"""
from __future__ import annotations

from datetime import datetime, time as dt_time
import json
import os
import time
from typing import TYPE_CHECKING, Dict, List
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from urllib3.util.retry import Retry

from app.backtesting.analytics import PerformanceAnalytics
from app.backtesting.backtest_broker import BacktestBroker
from app.backtesting.events import create_backtest_event
from app.config import settings
from app.models.backtest_event import BacktestEvent
from app.models.execution import Execution
from app.models.backtest_run import BacktestRun, BacktestRunStatus

if TYPE_CHECKING:
    from app.backtesting.engine import Trade


def _flag_modified_if_present(instance, key: str) -> None:
    if hasattr(instance, "_sa_instance_state"):
        flag_modified(instance, key)


class BacktestOrchestrator:
    def __init__(self, run: BacktestRun, pipeline, db_session):
        self.run = run
        self.pipeline = pipeline
        self.db = db_session
        self.config = run.config or {}
        self.symbols: List[str] = self.config.get("symbols", [])
        self.timeframe = self.config.get("timeframe", "5m")
        self.data_plane_url = getattr(settings, "DATA_PLANE_URL", "http://data-plane:8000")
        self.signal_generator_url = getattr(settings, "SIGNAL_GENERATOR_URL", "http://signal-generator:8000")
        self.initial_capital = float(self.config.get("initial_capital", 10_000.0))
        self.max_cost_usd = (
            float(self.config["max_cost_usd"])
            if self.config.get("max_cost_usd") is not None
            else None
        )
        self.broker = BacktestBroker(
            run_id=str(run.id),
            initial_capital=self.initial_capital,
            slippage_model=self.config.get("slippage_model", "fixed"),
            slippage_value=float(self.config.get("slippage_value", 0.01)),
            commission_model=self.config.get("commission_model", "per_share"),
            commission_value=float(self.config.get("commission_value", 0.005)),
        )
        self._progress_every_bars = max(1, int(os.getenv("BACKTEST_PROGRESS_FLUSH_BARS", "25")))
        self._progress_every_seconds = max(1, int(os.getenv("BACKTEST_PROGRESS_FLUSH_SECONDS", "2")))
        self._last_progress_commit_at = 0.0
        self._runtime_started_at = time.monotonic()
        self._signal_batches = 0
        self._pipeline_executions = 0
        self._progress_commits = 0
        self._checkpoint_key = f"backtest:{self.run.id}:checkpoint"
        self.http = self._build_http_session()
        self._last_seen_candles: Dict[str, Dict] = {}

    def _persist_closed_trade_outcome(self, trade_record: Dict) -> None:
        execution_id = trade_record.get("execution_id")
        if not execution_id:
            return

        execution = self.db.execute(
            select(Execution).where(Execution.id == execution_id)
        ).scalar_one_or_none()
        if not execution:
            return

        result = dict(execution.result or {})
        entry_price = float(trade_record.get("entry_price") or 0.0) or None
        exit_price = float(trade_record.get("exit_price") or 0.0) or None
        net_pnl = float(trade_record.get("net_pnl") or 0.0)
        pnl_percent = None
        if entry_price and exit_price:
            direction = str(trade_record.get("action") or "").upper()
            pnl_percent = (
                ((entry_price - exit_price) / entry_price) * 100
                if direction == "SELL"
                else ((exit_price - entry_price) / entry_price) * 100
            )

        result["final_pnl"] = net_pnl
        result["final_pnl_percent"] = pnl_percent
        result["trade_outcome"] = {
            "status": "executed",
            "pnl": net_pnl,
            "pnl_percent": pnl_percent,
            "exit_reason": trade_record.get("exit_reason"),
            "exit_price": exit_price,
            "entry_price": entry_price,
            "closed_at": trade_record.get("exit_time"),
        }
        execution.result = result
        _flag_modified_if_present(execution, "result")
        self.db.commit()

    def _sync_new_closed_trades(self, seen_trade_count: int) -> int:
        closed_trades = list(self.broker.get_closed_trades() or [])
        if len(closed_trades) <= seen_trade_count:
            return len(closed_trades)

        for trade_record in closed_trades[seen_trade_count:]:
            self._persist_closed_trade_outcome(trade_record)

        return len(closed_trades)

    @staticmethod
    def _build_http_session() -> requests.Session:
        retry_count = max(0, int(os.getenv("BACKTEST_HTTP_RETRY_TOTAL", "3")))
        backoff_factor = float(os.getenv("BACKTEST_HTTP_RETRY_BACKOFF_SECONDS", "0.5"))

        session = requests.Session()
        retry = Retry(
            total=retry_count,
            connect=retry_count,
            read=retry_count,
            status=retry_count,
            backoff_factor=backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _fetch_symbol_bars(self, symbol: str) -> List[Dict]:
        start_date = self.config["start_date"]
        end_date = self.config["end_date"]
        response = self.http.get(
            f"{self.data_plane_url}/api/v1/data/candles/{symbol}",
            params={
                "timeframe": self.timeframe,
                "limit": 5000,
                "start": f"{start_date}T00:00:00",
                "end": f"{end_date}T23:59:59",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("candles", [])

    def run_backtest(self) -> Dict:
        self.run.status = BacktestRunStatus.RUNNING
        self.run.started_at = datetime.utcnow()
        self._record_event(
            event_type="run_started",
            title="Backtest started",
            message="Replay runtime started processing historical data.",
            data={"symbols": self.symbols, "timeframe": self.timeframe},
        )
        _flag_modified_if_present(self.run, "progress")
        self.db.commit()

        symbol_bars = {symbol: self._fetch_symbol_bars(symbol) for symbol in self.symbols}
        timeline = sorted(
            {
                candle.get("timestamp") or candle.get("time")
                for bars in symbol_bars.values()
                for candle in bars
                if candle.get("timestamp") or candle.get("time")
            }
        )
        if not timeline:
            self.run.status = BacktestRunStatus.FAILED
            self.run.failure_reason = "No historical candles found for requested range"
            self.run.completed_at = datetime.utcnow()
            self._record_event(
                event_type="run_failed",
                title="No historical data",
                message=self.run.failure_reason,
                level="error",
            )
            self.db.commit()
            return {"run_id": str(self.run.id), "status": self.run.status.value}

        bars_by_symbol_ts = {
            symbol: {((c.get("timestamp") or c.get("time"))): c for c in bars}
            for symbol, bars in symbol_bars.items()
        }
        total_bars = sum(len(bars) for bars in symbol_bars.values())
        checkpoint = self._load_checkpoint()
        processed = int(checkpoint.get("processed_bars", 0)) if checkpoint else 0
        closed_trade_count = len(self.broker.get_closed_trades() or [])
        if checkpoint and checkpoint.get("actual_cost") is not None:
            self.run.actual_cost = float(checkpoint["actual_cost"])
        equity_curve: List[float] = list(checkpoint.get("equity_curve") or []) if checkpoint else []
        equity_points: List[Dict] = list(checkpoint.get("equity_points") or []) if checkpoint else []
        if not equity_curve and equity_points:
            equity_curve = [float(point.get("equity", self.initial_capital)) for point in equity_points]
        signal_types = [sub.get("signal_type") for sub in (self.pipeline.signal_subscriptions or []) if sub.get("signal_type")]

        previous_inside_window = None
        for timeline_index, ts in enumerate(timeline):
            if checkpoint and timeline_index < int(checkpoint.get("timeline_index", 0)):
                continue
            if self._refresh_cancel_status():
                return self._finalize_cancelled(processed, total_bars, ts)

            inside_window = self._is_inside_active_window(ts)
            if previous_inside_window is None:
                previous_inside_window = inside_window

            if previous_inside_window and not inside_window:
                self._record_event(
                    event_type="schedule_deactivated",
                    title="Schedule window closed",
                    message=f"Replay moved outside the active schedule window at {ts}.",
                    data={"backtest_ts": ts},
                )
                if getattr(self.pipeline, "liquidate_on_deactivation", False):
                    liquidated = self._liquidate_open_positions(
                        backtest_ts=ts,
                        reason="schedule",
                    )
                    closed_trade_count = self._sync_new_closed_trades(closed_trade_count)
                    if liquidated:
                        self._record_event(
                            event_type="schedule_liquidated",
                            title="Positions liquidated on deactivation",
                            message=f"Closed {liquidated} open position(s) as the schedule window ended.",
                            data={"backtest_ts": ts, "positions_closed": liquidated},
                        )
            previous_inside_window = inside_window

            checkpoint_at_current_ts = checkpoint if checkpoint and timeline_index == int(checkpoint.get("timeline_index", 0)) else None
            signals_already_dispatched = bool(checkpoint_at_current_ts and checkpoint_at_current_ts.get("signal_dispatch_completed"))

            if inside_window and not signals_already_dispatched:
                signals = self._replay_signals_for_timestamp(ts, signal_types)
                if signals:
                    self._signal_batches += 1
                    self._record_event(
                        event_type="signals_replayed",
                        title="Signals replayed",
                        message=f"Replayed {len(signals)} signal batch item(s) at {ts}.",
                        data={"backtest_ts": ts, "signals": len(signals)},
                    )
                    runtime_results = self._dispatch_signals_in_runtime(signals)
                    self._pipeline_executions += len(runtime_results)
                    for item in runtime_results:
                        self.run.actual_cost += float((item.get("result") or {}).get("cost") or 0.0)
                        self._record_execution_event(item, ts)
                    if self._exceeds_cost_limit():
                        return self._finalize_cost_limit_exceeded(processed, total_bars, ts)
                self._save_checkpoint(
                    timeline_index=timeline_index,
                    symbol_index=-1,
                    processed=processed,
                    total_bars=total_bars,
                    backtest_ts=ts,
                    equity_curve=equity_curve,
                    equity_points=equity_points,
                    signal_dispatch_completed=True,
                )
            elif not inside_window and not signals_already_dispatched:
                self._record_event(
                    event_type="schedule_skipped",
                    title="Outside active schedule",
                    message="Skipped signal replay because the pipeline was outside its configured active window.",
                    data={"backtest_ts": ts},
                )
                self._save_checkpoint(
                    timeline_index=timeline_index,
                    symbol_index=-1,
                    processed=processed,
                    total_bars=total_bars,
                    backtest_ts=ts,
                    equity_curve=equity_curve,
                    equity_points=equity_points,
                    signal_dispatch_completed=True,
                )

            start_symbol_index = 0
            if checkpoint_at_current_ts:
                start_symbol_index = int(checkpoint_at_current_ts.get("current_symbol_index", -1)) + 1
                if start_symbol_index >= len(self.symbols):
                    checkpoint = None
                    continue

            for symbol_index, symbol in enumerate(self.symbols):
                if symbol_index < start_symbol_index:
                    continue
                candle = bars_by_symbol_ts.get(symbol, {}).get(ts)
                if not candle:
                    continue
                self._last_seen_candles[symbol] = candle
                processed += 1
                self._update_progress(symbol, processed, total_bars, ts, force=False)

                self.broker.evaluate_bar(symbol, candle)
                closed_trade_count = self._sync_new_closed_trades(closed_trade_count)
                current_equity = self.broker.get_equity()
                equity_curve.append(current_equity)
                if equity_points and equity_points[-1].get("ts") == ts:
                    equity_points[-1]["equity"] = current_equity
                else:
                    equity_points.append({"ts": ts, "equity": current_equity})
                self._save_checkpoint(
                    timeline_index=timeline_index,
                    symbol_index=symbol_index,
                    processed=processed,
                    total_bars=total_bars,
                    backtest_ts=ts,
                    equity_curve=equity_curve,
                    equity_points=equity_points,
                    signal_dispatch_completed=True,
                )

            checkpoint = None

        trades = [self._trade_from_dict(t) for t in self.broker.get_closed_trades()]
        metrics = PerformanceAnalytics.compute(trades, equity_curve, self.initial_capital)
        self.run.status = BacktestRunStatus.COMPLETED
        self.run.completed_at = datetime.utcnow()
        self.run.metrics = metrics
        self.run.equity_curve = equity_curve
        self.run.trades = self.broker.get_closed_trades()
        self.run.trades_count = len(self.run.trades)
        self.run.progress = {
            "current_symbol": self.symbols[-1] if self.symbols else None,
            "current_bar": processed,
            "total_bars": total_bars,
            "percent_complete": 100.0,
            "current_ts": timeline[-1],
        }
        self.run.metrics = self._augment_metrics(metrics, processed, total_bars, equity_points)
        self._record_event(
            event_type="run_completed",
            title="Backtest completed",
            message=f"Replay completed with {len(self.run.trades)} closed trade(s).",
            data={
                "processed_bars": processed,
                "total_bars": total_bars,
                "trades_count": self.run.trades_count,
                "actual_cost": self.run.actual_cost,
            },
        )
        _flag_modified_if_present(self.run, "metrics")
        _flag_modified_if_present(self.run, "equity_curve")
        _flag_modified_if_present(self.run, "trades")
        _flag_modified_if_present(self.run, "progress")
        self.db.commit()
        self._clear_checkpoint()
        return {"run_id": str(self.run.id), "status": self.run.status.value}

    def _is_inside_active_window(self, backtest_ts: str) -> bool:
        if not getattr(self.pipeline, "schedule_enabled", False):
            return True

        start_time = getattr(self.pipeline, "schedule_start_time", None)
        end_time = getattr(self.pipeline, "schedule_end_time", None)
        if not start_time or not end_time:
            return True

        tz_name = getattr(self.pipeline, "user_timezone", None) or "America/New_York"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("America/New_York")

        ts = datetime.fromisoformat(backtest_ts.replace("Z", "+00:00")).astimezone(tz)
        schedule_days = getattr(self.pipeline, "schedule_days", None) or [1, 2, 3, 4, 5]
        if ts.isoweekday() not in schedule_days:
            return False

        current_time = ts.time().replace(second=0, microsecond=0)
        start = dt_time.fromisoformat(start_time)
        end = dt_time.fromisoformat(end_time)
        return start <= current_time < end

    def _liquidate_open_positions(self, *, backtest_ts: str, reason: str) -> int:
        positions = self.broker.get_positions()
        if not positions:
            return 0

        closed_count = 0
        closed_at = datetime.fromisoformat(backtest_ts.replace("Z", "+00:00"))
        for symbol in list(positions.keys()):
            last_candle = self._last_seen_candles.get(symbol)
            exit_price = None
            if last_candle:
                try:
                    exit_price = float(last_candle.get("close"))
                except (TypeError, ValueError):
                    exit_price = None
            if exit_price is None:
                position = positions.get(symbol) or {}
                exit_price = float(position.get("mark_price") or position.get("entry_price") or 0.0)
            trade = self.broker.close_position(symbol, exit_price, reason, closed_at=closed_at)
            if trade:
                closed_count += 1
        return closed_count

    def _replay_signals_for_timestamp(self, backtest_ts: str, signal_types: List[str]) -> List[Dict]:
        response = self.http.post(
            f"{self.signal_generator_url}/backtest/replay",
            json={
                "symbols": self.symbols,
                "backtest_ts": backtest_ts,
                "signal_types": signal_types,
                "backtest_run_id": str(self.run.id),
                "pipeline_id": str(self.pipeline.id),
                "user_id": str(self.run.user_id),
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

    def _dispatch_signals_in_runtime(self, signals: List[Dict]) -> List[Dict]:
        from app.backtesting.runtime_dispatcher import (
            execute_runtime_matches,
            match_signals_to_single_pipeline,
        )

        matched_by_ticker = match_signals_to_single_pipeline(
            signals=signals,
            pipeline=self.pipeline,
            allowed_tickers=self.symbols,
        )
        if not matched_by_ticker:
            self._record_event(
                event_type="signals_unmatched",
                title="No pipeline matches",
                message="Replayed signals did not match the selected pipeline subscriptions or symbol set.",
                data={"signals": len(signals)},
            )
            return []
        self._record_event(
            event_type="signals_matched",
            title="Signals matched",
            message=f"Matched {len(matched_by_ticker)} ticker(s) into pipeline execution.",
            data={"matched_tickers": sorted(matched_by_ticker.keys())},
        )
        return execute_runtime_matches(
            pipeline=self.pipeline,
            user_id=str(self.run.user_id),
            matched_by_ticker=matched_by_ticker,
        )

    def _update_progress(
        self,
        symbol: str,
        current_bar: int,
        total_bars: int,
        backtest_ts: str,
        *,
        force: bool,
    ) -> None:
        pct = round((current_bar / total_bars) * 100, 2) if total_bars else 0.0
        self.run.progress = {
            "current_symbol": symbol,
            "current_bar": current_bar,
            "total_bars": total_bars,
            "percent_complete": pct,
            "current_ts": backtest_ts,
        }
        _flag_modified_if_present(self.run, "progress")
        if force or self._should_flush_progress(current_bar, total_bars):
            self.db.commit()
            self._last_progress_commit_at = time.monotonic()
            self._progress_commits += 1

    def _should_flush_progress(self, current_bar: int, total_bars: int) -> bool:
        if current_bar == 1 or current_bar >= total_bars:
            return True
        if current_bar % self._progress_every_bars == 0:
            return True
        return (time.monotonic() - self._last_progress_commit_at) >= self._progress_every_seconds

    def _refresh_cancel_status(self) -> bool:
        current_status = self.db.execute(
            select(BacktestRun.status).where(BacktestRun.id == self.run.id)
        ).scalar_one_or_none()
        return current_status == BacktestRunStatus.CANCELLED

    def _finalize_cancelled(self, processed: int, total_bars: int, current_ts: str) -> Dict:
        self.run.completed_at = self.run.completed_at or datetime.utcnow()
        self.run.progress = {
            "current_symbol": self.run.progress.get("current_symbol"),
            "current_bar": processed,
            "total_bars": total_bars,
            "percent_complete": round((processed / total_bars) * 100, 2) if total_bars else 0.0,
            "current_ts": current_ts,
            "cancelled": True,
        }
        checkpoint = self._load_checkpoint() or {}
        equity_curve = list(checkpoint.get("equity_curve") or self.run.equity_curve or [])
        equity_points = list(checkpoint.get("equity_points") or ((self.run.metrics or {}).get("runtime") or {}).get("equity_points") or [])
        self.run.equity_curve = equity_curve
        self.run.metrics = self._augment_metrics(self.run.metrics or {}, processed, total_bars, equity_points)
        self._record_event(
            event_type="run_cancelled",
            title="Backtest cancelled",
            message="Replay stopped before completion.",
            level="warning",
            data={"processed_bars": processed, "total_bars": total_bars, "backtest_ts": current_ts},
        )
        _flag_modified_if_present(self.run, "progress")
        _flag_modified_if_present(self.run, "metrics")
        _flag_modified_if_present(self.run, "equity_curve")
        self.db.commit()
        self._clear_checkpoint()
        return {"run_id": str(self.run.id), "status": self.run.status.value}

    def _finalize_cost_limit_exceeded(self, processed: int, total_bars: int, current_ts: str) -> Dict:
        self.run.status = BacktestRunStatus.FAILED
        self.run.failure_reason = (
            f"Backtest exceeded max_cost_usd budget (${self.max_cost_usd:.2f}); "
            f"actual_cost=${self.run.actual_cost:.2f}"
        )
        self.run.completed_at = datetime.utcnow()
        self.run.progress = {
            "current_symbol": self.run.progress.get("current_symbol"),
            "current_bar": processed,
            "total_bars": total_bars,
            "percent_complete": round((processed / total_bars) * 100, 2) if total_bars else 0.0,
            "current_ts": current_ts,
            "stopped_for_cost_limit": True,
        }
        checkpoint = self._load_checkpoint() or {}
        equity_curve = list(checkpoint.get("equity_curve") or self.run.equity_curve or [])
        equity_points = list(checkpoint.get("equity_points") or ((self.run.metrics or {}).get("runtime") or {}).get("equity_points") or [])
        self.run.equity_curve = equity_curve
        self.run.metrics = self._augment_metrics(self.run.metrics or {}, processed, total_bars, equity_points)
        self._record_event(
            event_type="cost_limit_exceeded",
            title="Backtest stopped by cost cap",
            message=self.run.failure_reason,
            level="error",
            data={"processed_bars": processed, "total_bars": total_bars, "backtest_ts": current_ts},
        )
        _flag_modified_if_present(self.run, "progress")
        _flag_modified_if_present(self.run, "metrics")
        _flag_modified_if_present(self.run, "equity_curve")
        self.db.commit()
        self._clear_checkpoint()
        return {"run_id": str(self.run.id), "status": self.run.status.value}

    def _augment_metrics(self, metrics: Dict, processed: int, total_bars: int, equity_points: List[Dict] | None = None) -> Dict:
        merged_metrics = dict(metrics or {})
        merged_metrics["runtime"] = {
            "processed_bars": processed,
            "total_bars": total_bars,
            "symbols": len(self.symbols),
            "signal_batches": self._signal_batches,
            "pipeline_executions": self._pipeline_executions,
            "progress_commits": self._progress_commits,
            "runtime_seconds": round(time.monotonic() - self._runtime_started_at, 2),
            "equity_points": list(equity_points or []),
        }
        return merged_metrics

    def _load_checkpoint(self) -> Dict | None:
        raw = self.broker.redis.get(self._checkpoint_key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _save_checkpoint(
        self,
        *,
        timeline_index: int,
        symbol_index: int,
        processed: int,
        total_bars: int,
        backtest_ts: str,
        equity_curve: List[float],
        equity_points: List[Dict],
        signal_dispatch_completed: bool,
    ) -> None:
        checkpoint = {
            "timeline_index": timeline_index,
            "current_symbol_index": symbol_index,
            "processed_bars": processed,
            "total_bars": total_bars,
            "current_ts": backtest_ts,
            "signal_dispatch_completed": signal_dispatch_completed,
            "equity_curve": equity_curve,
            "equity_points": equity_points,
            "actual_cost": self.run.actual_cost,
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.broker.redis.set(self._checkpoint_key, json.dumps(checkpoint))

    def _clear_checkpoint(self) -> None:
        self.broker.redis.delete(self._checkpoint_key)

    def _exceeds_cost_limit(self) -> bool:
        return self.max_cost_usd is not None and self.run.actual_cost > self.max_cost_usd

    def _record_event(
        self,
        *,
        event_type: str,
        title: str,
        message: str,
        level: str = "info",
        symbol: str | None = None,
        execution_id: str | None = None,
        data: Dict | None = None,
    ) -> None:
        event = create_backtest_event(
            run=self.run,
            event_type=event_type,
            title=title,
            message=message,
            level=level,
            symbol=symbol,
            execution_id=execution_id,
            data=data,
        )
        self.db.add(event)

    def _record_execution_event(self, item: Dict, backtest_ts: str) -> None:
        result = item.get("result") or {}
        execution_id = result.get("execution_id")
        status = str(result.get("status") or "UNKNOWN")
        ticker = item.get("ticker")
        signal_context = item.get("signal_context") or {}
        event_type = "execution_completed" if status == "COMPLETED" else "execution_result"
        level = "error" if status in {"FAILED", "CANCELLED"} else "info"
        self._record_event(
            event_type=event_type,
            title=f"Execution {status.lower()}",
            message=str(result.get("error_message") or result.get("trigger_reason") or "Pipeline execution finished."),
            level=level,
            symbol=ticker,
            execution_id=execution_id,
            data={
                "backtest_ts": backtest_ts,
                "signal_type": signal_context.get("signal_type"),
                "timestamp": signal_context.get("timestamp"),
                "cost": result.get("cost"),
                "status": status,
            },
        )

    @staticmethod
    def _trade_from_dict(data: Dict) -> Trade:
        from app.backtesting.engine import Trade

        return Trade(
            id=data.get("id", ""),
            strategy_family=data.get("strategy_family", ""),
            action=data.get("action", ""),
            entry_time=datetime.fromisoformat(data["entry_time"]) if data.get("entry_time") else None,
            exit_time=datetime.fromisoformat(data["exit_time"]) if data.get("exit_time") else None,
            entry_price=float(data.get("entry_price", 0.0)),
            exit_price=float(data.get("exit_price", 0.0)),
            stop_loss=float(data.get("stop_loss", 0.0)),
            take_profit=float(data.get("take_profit", 0.0)),
            position_size=float(data.get("position_size", 0.0)),
            gross_pnl=float(data.get("gross_pnl", 0.0)),
            commission=float(data.get("commission", 0.0)),
            slippage=float(data.get("slippage", 0.0)),
            net_pnl=float(data.get("net_pnl", 0.0)),
            exit_reason=data.get("exit_reason", ""),
            regime=data.get("regime", ""),
            session=data.get("session", ""),
            duration_bars=int(data.get("duration_bars", 0)),
            r_multiple=float(data.get("r_multiple", 0.0)),
        )
