"""
Backtest orchestrator for parity pipeline replay.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
import time
from typing import TYPE_CHECKING, Dict, List

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from urllib3.util.retry import Retry

from app.backtesting.analytics import PerformanceAnalytics
from app.backtesting.backtest_broker import BacktestBroker
from app.config import settings
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
            self.db.commit()
            return {"run_id": str(self.run.id), "status": self.run.status.value}

        bars_by_symbol_ts = {
            symbol: {((c.get("timestamp") or c.get("time"))): c for c in bars}
            for symbol, bars in symbol_bars.items()
        }
        total_bars = sum(len(bars) for bars in symbol_bars.values())
        checkpoint = self._load_checkpoint()
        processed = int(checkpoint.get("processed_bars", 0)) if checkpoint else 0
        if checkpoint and checkpoint.get("actual_cost") is not None:
            self.run.actual_cost = float(checkpoint["actual_cost"])
        equity_curve: List[float] = list(checkpoint.get("equity_curve") or []) if checkpoint else []
        if not equity_curve:
            equity_curve = [self.initial_capital]
        signal_types = [sub.get("signal_type") for sub in (self.pipeline.signal_subscriptions or []) if sub.get("signal_type")]

        for timeline_index, ts in enumerate(timeline):
            if checkpoint and timeline_index < int(checkpoint.get("timeline_index", 0)):
                continue
            if self._refresh_cancel_status():
                return self._finalize_cancelled(processed, total_bars, ts)

            checkpoint_at_current_ts = checkpoint if checkpoint and timeline_index == int(checkpoint.get("timeline_index", 0)) else None
            signals_already_dispatched = bool(checkpoint_at_current_ts and checkpoint_at_current_ts.get("signal_dispatch_completed"))

            if not signals_already_dispatched:
                signals = self._replay_signals_for_timestamp(ts, signal_types)
                if signals:
                    self._signal_batches += 1
                    runtime_results = self._dispatch_signals_in_runtime(signals)
                    self._pipeline_executions += len(runtime_results)
                    for item in runtime_results:
                        self.run.actual_cost += float((item.get("result") or {}).get("cost") or 0.0)
                    if self._exceeds_cost_limit():
                        return self._finalize_cost_limit_exceeded(processed, total_bars, ts)
                self._save_checkpoint(
                    timeline_index=timeline_index,
                    symbol_index=-1,
                    processed=processed,
                    total_bars=total_bars,
                    backtest_ts=ts,
                    equity_curve=equity_curve,
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
                processed += 1
                self._update_progress(symbol, processed, total_bars, ts, force=False)

                self.broker.evaluate_bar(symbol, candle)
                equity_curve.append(self.broker.get_equity())
                self._save_checkpoint(
                    timeline_index=timeline_index,
                    symbol_index=symbol_index,
                    processed=processed,
                    total_bars=total_bars,
                    backtest_ts=ts,
                    equity_curve=equity_curve,
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
        self.run.metrics = self._augment_metrics(metrics, processed, total_bars)
        _flag_modified_if_present(self.run, "metrics")
        _flag_modified_if_present(self.run, "equity_curve")
        _flag_modified_if_present(self.run, "trades")
        _flag_modified_if_present(self.run, "progress")
        self.db.commit()
        self._clear_checkpoint()
        return {"run_id": str(self.run.id), "status": self.run.status.value}

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
            return []
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
        self.run.metrics = self._augment_metrics(self.run.metrics or {}, processed, total_bars)
        _flag_modified_if_present(self.run, "progress")
        _flag_modified_if_present(self.run, "metrics")
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
        self.run.metrics = self._augment_metrics(self.run.metrics or {}, processed, total_bars)
        _flag_modified_if_present(self.run, "progress")
        _flag_modified_if_present(self.run, "metrics")
        self.db.commit()
        self._clear_checkpoint()
        return {"run_id": str(self.run.id), "status": self.run.status.value}

    def _augment_metrics(self, metrics: Dict, processed: int, total_bars: int) -> Dict:
        merged_metrics = dict(metrics or {})
        merged_metrics["runtime"] = {
            "processed_bars": processed,
            "total_bars": total_bars,
            "symbols": len(self.symbols),
            "signal_batches": self._signal_batches,
            "pipeline_executions": self._pipeline_executions,
            "progress_commits": self._progress_commits,
            "runtime_seconds": round(time.monotonic() - self._runtime_started_at, 2),
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
            "actual_cost": self.run.actual_cost,
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.broker.redis.set(self._checkpoint_key, json.dumps(checkpoint))

    def _clear_checkpoint(self) -> None:
        self.broker.redis.delete(self._checkpoint_key)

    def _exceeds_cost_limit(self) -> bool:
        return self.max_cost_usd is not None and self.run.actual_cost > self.max_cost_usd

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
