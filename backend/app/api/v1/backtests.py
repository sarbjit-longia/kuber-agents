"""
Backtesting API endpoints.
"""
import os
from typing import Annotated, Any
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from openai import BadRequestError
import json

from app.config import settings
from app.backtesting.backtest_broker import BacktestBroker
from app.backtesting.snapshot import build_backtest_runtime_snapshot
from app.core.deps import get_current_active_user
from app.database import get_db
from app.models.backtest_run import BacktestRun, BacktestRunStatus
from app.models.backtest_event import BacktestEvent
from app.models.execution import Execution
from app.models.pipeline import Pipeline
from app.models.user import User
from app.backtesting.runtime_launcher import get_backtest_runtime_launcher
from app.schemas.backtest import (
    BacktestCreate,
    BacktestExecutionList,
    BacktestRunList,
    BacktestReportResponse,
    BacktestRunResult,
    BacktestRunSummary,
    BacktestStartResponse,
    BacktestTimelineEvent,
    BacktestTimelineResponse,
)
from app.orchestration.tasks.launch_backtest_runtime import launch_backtest_runtime
from app.services.llm_provider import create_openai_client, get_llm_api_key, resolve_chat_model

router = APIRouter(prefix="/backtests", tags=["backtests"])

ACTIVE_BACKTEST_STATUSES = (
    BacktestRunStatus.PENDING,
    BacktestRunStatus.RUNNING,
)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _estimate_cost_usd(symbol_count: int, start_date, end_date) -> float:
    days = max((end_date - start_date).days, 1)
    # Heuristic from proposal doc: ~100 executions / symbol / month at mid-case cost.
    est_executions = symbol_count * max(1, round(days / 30 * 100))
    return round(est_executions * 0.075, 2)


def _snapshot_pipeline(pipeline: Pipeline, *, user_timezone: str | None = None) -> dict:
    return {
        "id": str(pipeline.id),
        "user_id": str(pipeline.user_id),
        "name": pipeline.name,
        "description": pipeline.description,
        "config": pipeline.config or {},
        "trigger_mode": pipeline.trigger_mode.value if pipeline.trigger_mode else None,
        "scanner_id": str(pipeline.scanner_id) if pipeline.scanner_id else None,
        "signal_subscriptions": pipeline.signal_subscriptions or [],
        "scanner_tickers": pipeline.scanner_tickers or [],
        "require_approval": pipeline.require_approval,
        "approval_modes": pipeline.approval_modes or [],
        "schedule_enabled": pipeline.schedule_enabled,
        "schedule_start_time": pipeline.schedule_start_time,
        "schedule_end_time": pipeline.schedule_end_time,
        "schedule_days": pipeline.schedule_days or [],
        "liquidate_on_deactivation": pipeline.liquidate_on_deactivation,
        "user_timezone": user_timezone or "America/New_York",
        "snapshot_created_at": datetime.utcnow().isoformat(),
    }


def _execution_belongs_to_backtest(run_id: UUID):
    return Execution.result["backtest_run_id"].as_string() == str(run_id)


async def _get_backtest_or_404(run_id: UUID, current_user: User, db: AsyncSession) -> BacktestRun:
    result = await db.execute(
        select(BacktestRun).where(BacktestRun.id == run_id, BacktestRun.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest run not found")
    return run


def _safe_number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _load_backtest_runtime_state(run: BacktestRun) -> dict[str, Any]:
    config = run.config or {}
    initial_capital = _safe_number(config.get("initial_capital") or 10_000.0)
    try:
        broker = BacktestBroker(
            run_id=str(run.id),
            initial_capital=initial_capital,
            slippage_model=config.get("slippage_model", "fixed"),
            slippage_value=_safe_number(config.get("slippage_value") or 0.01),
            commission_model=config.get("commission_model", "per_share"),
            commission_value=_safe_number(config.get("commission_value") or 0.005),
        )
        account = broker.get_account() or {}
        positions_map = broker.get_positions() or {}
        positions = list(positions_map.values())
        cash = _safe_number(account.get("cash"))
        equity = _safe_number(account.get("equity"))
        if equity <= 0:
            equity = initial_capital
        if cash <= 0 and not positions:
            cash = initial_capital
        return {
            "account_equity": equity,
            "cash_balance": cash,
            "unrealized_pnl": round(equity - cash, 2),
            "open_positions": positions,
            "open_positions_count": len(positions),
        }
    except Exception:
        return {
            "account_equity": None,
            "cash_balance": None,
            "unrealized_pnl": None,
            "open_positions": [],
            "open_positions_count": 0,
        }


def _load_backtest_runtime_trades(run: BacktestRun) -> list[dict[str, Any]]:
    config = run.config or {}
    initial_capital = _safe_number(config.get("initial_capital") or 10_000.0)
    try:
        broker = BacktestBroker(
            run_id=str(run.id),
            initial_capital=initial_capital,
            slippage_model=config.get("slippage_model", "fixed"),
            slippage_value=_safe_number(config.get("slippage_value") or 0.01),
            commission_model=config.get("commission_model", "per_share"),
            commission_value=_safe_number(config.get("commission_value") or 0.005),
        )
        return list(broker.get_closed_trades() or [])
    except Exception:
        return []


def _attach_trade_execution_links(
    trades: list[dict[str, Any]],
    executions: list[Execution],
) -> list[dict[str, Any]]:
    if not trades:
        return []

    normalized: list[dict[str, Any]] = []
    valid_execution_ids = {str(execution.id) for execution in executions}
    for trade in trades:
        trade_record = dict(trade)
        execution_id = trade_record.get("execution_id")
        if execution_id:
            trade_record["execution_id"] = str(execution_id)
            if trade_record["execution_id"] not in valid_execution_ids:
                trade_record.pop("execution_id", None)

        normalized.append(trade_record)

    return normalized


def _load_backtest_checkpoint(run: BacktestRun) -> dict[str, Any]:
    try:
        broker = BacktestBroker(run_id=str(run.id), initial_capital=_safe_number((run.config or {}).get("initial_capital") or 10_000.0))
        raw = broker.redis.get(f"backtest:{run.id}:checkpoint")
        return raw and __import__("json").loads(raw) or {}
    except Exception:
        return {}


def _filled_orders_count(executions: list[Execution]) -> int:
    count = 0
    for execution in executions:
        trade_execution = (execution.result or {}).get("trade_execution") or {}
        if trade_execution.get("status") == "filled":
            count += 1
    return count


def _build_run_payload(run: BacktestRun, executions: list[Execution] | None = None) -> dict[str, Any]:
    runtime_state = _load_backtest_runtime_state(run)
    checkpoint = _load_backtest_checkpoint(run)
    executions = executions or []
    runtime_trades = _load_backtest_runtime_trades(run)
    trades = _attach_trade_execution_links(runtime_trades or list(run.trades or []), executions)
    filled_orders_count = _filled_orders_count(executions)
    equity_curve = list(run.equity_curve or checkpoint.get("equity_curve") or [])
    equity_series = list(((run.metrics or {}).get("runtime") or {}).get("equity_points") or checkpoint.get("equity_points") or [])
    account_equity = runtime_state.get("account_equity")
    daily_pnl = _build_daily_pnl(equity_series, _safe_number((run.config or {}).get("initial_capital") or 10_000.0))

    return {
        "id": run.id,
        "pipeline_id": run.pipeline_id,
        "pipeline_name": run.pipeline_name,
        "status": run.status,
        "config": run.config or {},
        "progress": run.progress or {},
        "metrics": run.metrics or {},
        "trades_count": len(trades),
        "filled_orders_count": filled_orders_count,
        "open_positions_count": runtime_state["open_positions_count"],
        "account_equity": runtime_state["account_equity"],
        "cash_balance": runtime_state["cash_balance"],
        "unrealized_pnl": runtime_state["unrealized_pnl"],
        "estimated_cost": run.estimated_cost,
        "actual_cost": run.actual_cost,
        "failure_reason": run.failure_reason,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "equity_curve": equity_curve,
        "equity_series": equity_series,
        "daily_pnl": daily_pnl,
        "trades": trades,
        "open_positions": runtime_state["open_positions"],
    }


def _build_daily_pnl(equity_series: list[dict[str, Any]], initial_capital: float) -> list[dict[str, Any]]:
    if not equity_series:
        return []

    daily_last: dict[str, float] = {}
    for point in equity_series:
        ts = str(point.get("ts") or "")
        date_key = ts[:10]
        if not date_key:
            continue
        daily_last[date_key] = _safe_number(point.get("equity"))

    if not daily_last:
        return []

    rows: list[dict[str, Any]] = []
    previous_equity = initial_capital
    for day in sorted(daily_last.keys()):
        equity = daily_last[day]
        pnl = equity - previous_equity
        rows.append({"date": day, "pnl": round(pnl, 2), "equity": round(equity, 2)})
        previous_equity = equity
    return rows


async def _load_backtest_executions(db: AsyncSession, current_user: User, run_id: UUID) -> list[Execution]:
    result = await db.execute(
        select(Execution)
        .where(
            Execution.user_id == current_user.id,
            Execution.mode == "backtest",
            _execution_belongs_to_backtest(run_id),
        )
        .order_by(desc(Execution.created_at))
    )
    return result.scalars().all()


def _build_report_summary(
    run: BacktestRun,
    executions: list[Execution],
    events: list[BacktestEvent],
) -> dict[str, Any]:
    trades = _load_backtest_runtime_trades(run) or list(run.trades or [])
    net_pnl = sum(_safe_number(trade.get("net_pnl")) for trade in trades)
    gross_pnl = sum(_safe_number(trade.get("gross_pnl")) for trade in trades)
    winning_trades = [trade for trade in trades if _safe_number(trade.get("net_pnl")) > 0]
    losing_trades = [trade for trade in trades if _safe_number(trade.get("net_pnl")) < 0]
    rejected = [
        ex for ex in executions
        if (ex.reports or {}).get("node-trade_review_agent", {}).get("data", {}).get("decision") == "REJECTED"
    ]
    holds = [
        ex for ex in executions
        if ((ex.result or {}).get("strategy") or {}).get("action") == "HOLD"
    ]
    event_counts: dict[str, int] = {}
    for event in events:
        event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
    return {
        "pipeline_name": run.pipeline_name,
        "symbols": (run.config or {}).get("symbols", []),
        "timeframe": (run.config or {}).get("timeframe"),
        "date_range": {
            "start": (run.config or {}).get("start_date"),
            "end": (run.config or {}).get("end_date"),
        },
        "status": run.status.value,
        "net_pnl": round(net_pnl, 2),
        "gross_pnl": round(gross_pnl, 2),
        "return_pct": round((net_pnl / _safe_number((run.config or {}).get("initial_capital") or 1)) * 100, 2),
        "trade_count": len(trades),
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": round((len(winning_trades) / len(trades) * 100), 2) if trades else 0.0,
        "execution_count": len(executions),
        "review_rejections": len(rejected),
        "strategy_holds": len(holds),
        "actual_cost": round(_safe_number(run.actual_cost), 2),
        "max_drawdown": (run.metrics or {}).get("max_drawdown"),
        "signal_batches": event_counts.get("signals_replayed", 0),
        "matched_signal_batches": event_counts.get("signals_matched", 0),
        "runtime_seconds": ((run.metrics or {}).get("runtime") or {}).get("runtime_seconds"),
    }


def _build_report_sections(
    run: BacktestRun,
    executions: list[Execution],
    events: list[BacktestEvent],
) -> list[dict[str, Any]]:
    metrics = run.metrics or {}
    trades = _load_backtest_runtime_trades(run) or list(run.trades or [])
    config = run.config or {}
    pipeline_snapshot = config.get("pipeline_snapshot") or {}
    runtime_snapshot = config.get("runtime_snapshot") or {}
    rejection_reasons: dict[str, int] = {}
    per_symbol: dict[str, dict[str, Any]] = {}
    event_counts: dict[str, int] = {}

    for event in events:
        event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1

    for execution in executions:
        symbol = execution.symbol or "Unknown"
        per_symbol.setdefault(
            symbol,
            {"executions": 0, "cost": 0.0, "completed": 0, "failed": 0, "trades": 0, "net_pnl": 0.0},
        )
        per_symbol[symbol]["executions"] += 1
        per_symbol[symbol]["cost"] += _safe_number(execution.cost)
        if execution.status.value == "COMPLETED":
            per_symbol[symbol]["completed"] += 1
        if execution.status.value == "FAILED":
            per_symbol[symbol]["failed"] += 1

        report = (execution.reports or {}).get("node-trade_review_agent", {})
        decision = (report.get("data") or {}).get("decision")
        if decision:
            rejection_reasons[decision] = rejection_reasons.get(decision, 0) + 1

    for trade in trades:
        symbol = trade.get("symbol") or trade.get("ticker") or "Unknown"
        per_symbol.setdefault(
            symbol,
            {"executions": 0, "cost": 0.0, "completed": 0, "failed": 0, "trades": 0, "net_pnl": 0.0},
        )
        per_symbol[symbol]["trades"] += 1
        per_symbol[symbol]["net_pnl"] += _safe_number(trade.get("net_pnl"))

    best_trade = max(trades, key=lambda trade: _safe_number(trade.get("net_pnl")), default=None)
    worst_trade = min(trades, key=lambda trade: _safe_number(trade.get("net_pnl")), default=None)
    runtime_metrics = metrics.get("runtime") or {}
    top_symbols = sorted(
        per_symbol.items(),
        key=lambda item: (item[1]["net_pnl"], item[1]["completed"]),
        reverse=True,
    )
    schedule_enabled = bool(pipeline_snapshot.get("schedule_enabled"))
    schedule_days = pipeline_snapshot.get("schedule_days") or []
    backtest_settings = [
        f"Initial capital: {_safe_number(config.get('initial_capital')):.2f}",
        f"Symbols: {', '.join(config.get('symbols') or []) or 'N/A'}",
        f"Date range: {(config.get('start_date') or 'N/A')} to {(config.get('end_date') or 'N/A')}",
        f"Timeframe: {config.get('timeframe') or 'N/A'}",
        f"Slippage: {(config.get('slippage_model') or 'fixed')} / {_safe_number(config.get('slippage_value')):.4f}",
        f"Commission: {(config.get('commission_model') or 'per_share')} / {_safe_number(config.get('commission_value')):.4f}",
        f"Max LLM cost cap: {config.get('max_cost_usd') if config.get('max_cost_usd') is not None else 'Not set'}",
    ]
    pipeline_config_items = [
        f"Pipeline name: {pipeline_snapshot.get('name') or run.pipeline_name or 'N/A'}",
        f"Trigger mode: {pipeline_snapshot.get('trigger_mode') or 'N/A'}",
        f"Require approval: {pipeline_snapshot.get('require_approval', False)}",
        f"Approval modes: {', '.join(pipeline_snapshot.get('approval_modes') or []) or 'None'}",
        f"Signal subscriptions: {', '.join((sub.get('signal_type') for sub in (pipeline_snapshot.get('signal_subscriptions') or []) if sub.get('signal_type'))) or 'All matched signals'}",
        f"Scanner tickers: {', '.join(pipeline_snapshot.get('scanner_tickers') or []) or 'None'}",
        f"Schedule enabled: {schedule_enabled}",
        f"Schedule window: {pipeline_snapshot.get('schedule_start_time') or 'N/A'} to {pipeline_snapshot.get('schedule_end_time') or 'N/A'}",
        f"Schedule days: {', '.join(str(day) for day in schedule_days) or 'Default weekdays'}",
        f"Liquidate on deactivation: {pipeline_snapshot.get('liquidate_on_deactivation', False)}",
        f"User timezone snapshot: {pipeline_snapshot.get('user_timezone') or 'America/New_York'}",
    ]

    agent_sections: list[dict[str, Any]] = []
    agent_configs = runtime_snapshot.get("agent_configs") or {}
    for agent_name, agent_config in agent_configs.items():
        agent_sections.append(
            {
                "title": f"{agent_name.replace('_', ' ').title()} Snapshot",
                "items": [
                    f"Model: {agent_config.get('model') or 'N/A'}",
                    f"Instructions: {agent_config.get('instructions') or 'None'}",
                ],
            }
        )

    return [
        {
            "title": "Backtest Configuration",
            "items": backtest_settings,
        },
        {
            "title": "Pipeline Configuration",
            "items": pipeline_config_items,
        },
        {
            "title": "Performance Overview",
            "items": [
                f"Net P&L: {_safe_number(sum(_safe_number(trade.get('net_pnl')) for trade in trades)):.2f}",
                f"Trades closed: {len(trades)}",
                f"Win rate: {metrics.get('win_rate', 0)}%",
                f"Max drawdown: {metrics.get('max_drawdown', 'N/A')}",
                f"Profit factor: {metrics.get('profit_factor', 'N/A')}",
                f"Average winner: {metrics.get('avg_winner', 'N/A')}",
                f"Average loser: {metrics.get('avg_loser', 'N/A')}",
            ],
        },
        {
            "title": "Execution Flow",
            "items": [
                f"Pipeline executions: {len(executions)}",
                f"Backtest cost consumed: ${run.actual_cost:.2f}",
                f"Completed executions: {sum(1 for ex in executions if ex.status.value == 'COMPLETED')}",
                f"Failed executions: {sum(1 for ex in executions if ex.status.value == 'FAILED')}",
                f"Signal batches replayed: {event_counts.get('signals_replayed', 0)}",
                f"Signal batches matched: {event_counts.get('signals_matched', 0)}",
                f"Runtime seconds: {runtime_metrics.get('runtime_seconds', 'N/A')}",
            ],
        },
        {
            "title": "Rejections and Holds",
            "items": [
                *(f"{reason}: {count}" for reason, count in sorted(rejection_reasons.items())),
                f"Strategy HOLD decisions: {sum(1 for ex in executions if ((ex.result or {}).get('strategy') or {}).get('action') == 'HOLD')}",
                f"Unmatched signal batches: {event_counts.get('signals_unmatched', 0)}",
            ] or ["No review decisions or holds recorded."],
        },
        {
            "title": "Symbol Breakdown",
            "items": [
                (
                    f"{symbol}: {data['executions']} executions, {data['trades']} trades, "
                    f"${data['cost']:.2f} cost, ${data['net_pnl']:.2f} net P&L, "
                    f"{data['completed']} completed, {data['failed']} failed"
                )
                for symbol, data in top_symbols[:10]
            ] or ["No symbol activity recorded."],
        },
        {
            "title": "Best and Worst Trades",
            "items": [
                f"Best trade: {best_trade.get('id')} / {best_trade.get('net_pnl')}" if best_trade else "Best trade: N/A",
                f"Worst trade: {worst_trade.get('id')} / {worst_trade.get('net_pnl')}" if worst_trade else "Worst trade: N/A",
                f"Total commissions: {sum(_safe_number(trade.get('commission')) for trade in trades):.2f}",
                f"Total slippage: {sum(_safe_number(trade.get('slippage')) for trade in trades):.2f}",
            ],
        },
        {
            "title": "Runtime Visibility",
            "items": [
                f"Bars processed: {runtime_metrics.get('processed_bars', run.progress.get('current_bar', 0))}",
                f"Total bars planned: {runtime_metrics.get('total_bars', run.progress.get('total_bars', 0))}",
                f"Progress commits: {runtime_metrics.get('progress_commits', 'N/A')}",
                f"Current failure reason: {run.failure_reason or 'None'}",
            ],
        },
        *agent_sections,
    ]


async def _generate_optional_llm_analysis(summary: dict[str, Any], sections: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not get_llm_api_key():
        return None

    client = create_openai_client(async_client=True)
    prompt = (
        "You are reviewing a completed trading backtest. Produce concise JSON with keys "
        "`executive_summary`, `strengths`, `weaknesses`, and `recommendations`. "
        "Ground everything only in the provided facts.\n\n"
        f"SUMMARY:\n{summary}\n\nSECTIONS:\n{sections}"
    )
    messages = [
        {"role": "system", "content": "You are a trading performance analyst. Return valid JSON only."},
        {"role": "user", "content": prompt},
    ]
    try:
        response = await client.chat.completions.create(
            model=resolve_chat_model(settings.OPENAI_MODEL),
            temperature=0.2,
            max_tokens=700,
            response_format={"type": "json_object"},
            messages=messages,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
    except BadRequestError as exc:
        if "response_format" not in str(exc):
            return None
        try:
            fallback_response = await client.chat.completions.create(
                model=resolve_chat_model(settings.OPENAI_MODEL),
                temperature=0.2,
                max_tokens=700,
                messages=messages,
            )
            content = fallback_response.choices[0].message.content or "{}"
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                content = content[start:end + 1]
            return json.loads(content)
        except Exception:
            return None
    except Exception:
        return None


def _load_cached_report(run: BacktestRun) -> dict[str, Any] | None:
    config = run.config or {}
    cached = config.get("report_cache")
    return cached if isinstance(cached, dict) else None


def _store_cached_report(run: BacktestRun, report_payload: dict[str, Any]) -> None:
    config = dict(run.config or {})
    config["report_cache"] = report_payload
    run.config = config


def _timeline_sort_key(event: BacktestTimelineEvent) -> tuple[str, str]:
    return (event.ts, event.id)


@router.post("", response_model=BacktestStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_backtest(
    payload: BacktestCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Pipeline).where(Pipeline.id == payload.pipeline_id)
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
    if pipeline.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pipeline does not belong to user")

    per_user_limit = max(1, _env_int("BACKTEST_MAX_ACTIVE_RUNS_PER_USER", 2))
    per_pipeline_limit = max(1, _env_int("BACKTEST_MAX_ACTIVE_RUNS_PER_PIPELINE", 1))
    global_limit = max(1, _env_int("BACKTEST_MAX_ACTIVE_RUNS_GLOBAL", 100))

    active_for_user = await db.scalar(
        select(func.count())
        .select_from(BacktestRun)
        .where(
            BacktestRun.user_id == current_user.id,
            BacktestRun.status.in_(ACTIVE_BACKTEST_STATUSES),
        )
    )
    if (active_for_user or 0) >= per_user_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"User backtest concurrency limit reached ({per_user_limit} active runs)",
        )

    active_for_pipeline = await db.scalar(
        select(func.count())
        .select_from(BacktestRun)
        .where(
            BacktestRun.pipeline_id == pipeline.id,
            BacktestRun.status.in_(ACTIVE_BACKTEST_STATUSES),
        )
    )
    if (active_for_pipeline or 0) >= per_pipeline_limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This pipeline already has an active backtest run",
        )

    global_active = await db.scalar(
        select(func.count())
        .select_from(BacktestRun)
        .where(BacktestRun.status.in_(ACTIVE_BACKTEST_STATUSES))
    )
    if (global_active or 0) >= global_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Backtest capacity is currently full, try again shortly",
        )

    estimated_cost = _estimate_cost_usd(len(payload.symbols), payload.start_date, payload.end_date)
    if payload.max_cost_usd is not None and estimated_cost > payload.max_cost_usd:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estimated run cost ${estimated_cost:.2f} exceeds max_cost_usd ${payload.max_cost_usd:.2f}",
        )

    run_config = payload.model_dump(mode="json")
    run_config["pipeline_snapshot"] = _snapshot_pipeline(
        pipeline,
        user_timezone=getattr(current_user, "timezone", None) or "America/New_York",
    )
    run_config["runtime_snapshot"] = build_backtest_runtime_snapshot(pipeline)
    run_config["runtime"] = {
        "mode": "ephemeral_sandbox",
        "launcher_mode": settings.BACKTEST_RUNTIME_MODE,
        "namespace": settings.BACKTEST_RUNTIME_NAMESPACE,
        "image": settings.BACKTEST_RUNTIME_IMAGE,
    }

    run = BacktestRun(
        user_id=current_user.id,
        pipeline_id=pipeline.id,
        pipeline_name=pipeline.name,
        status=BacktestRunStatus.PENDING,
        config=run_config,
        progress={"current_bar": 0, "total_bars": 0, "percent_complete": 0.0},
        estimated_cost=estimated_cost,
        created_at=datetime.utcnow(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    launch_backtest_runtime.apply_async(
        kwargs={"backtest_run_id": str(run.id)},
        expires=60 * 60 * 6,
    )

    return BacktestStartResponse(run_id=run.id, status=run.status)


@router.get("", response_model=BacktestRunList)
async def list_backtests(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Annotated[BacktestRunStatus | None, Query(alias="status")] = None,
):
    base_query = select(BacktestRun).where(BacktestRun.user_id == current_user.id)
    count_query = select(func.count()).select_from(BacktestRun).where(BacktestRun.user_id == current_user.id)
    if status_filter is not None:
        base_query = base_query.where(BacktestRun.status == status_filter)
        count_query = count_query.where(BacktestRun.status == status_filter)

    total = await db.scalar(count_query)
    result = await db.execute(
        base_query
        .order_by(BacktestRun.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    runs = result.scalars().all()
    backtests: list[BacktestRunSummary] = []
    for run in runs:
        executions = await _load_backtest_executions(db, current_user, run.id)
        backtests.append(BacktestRunSummary.model_validate(_build_run_payload(run, executions)))
    return BacktestRunList(backtests=backtests, total=total or 0)


@router.get("/{run_id}", response_model=BacktestRunSummary)
async def get_backtest(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(BacktestRun).where(BacktestRun.id == run_id, BacktestRun.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest run not found")
    executions = await _load_backtest_executions(db, current_user, run.id)
    return BacktestRunSummary.model_validate(_build_run_payload(run, executions))


@router.get("/{run_id}/results", response_model=BacktestRunResult)
async def get_backtest_results(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    run = await _get_backtest_or_404(run_id, current_user, db)
    executions = await _load_backtest_executions(db, current_user, run.id)
    return BacktestRunResult.model_validate(_build_run_payload(run, executions))


@router.get("/{run_id}/executions", response_model=BacktestExecutionList)
async def list_backtest_executions(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_backtest_or_404(run_id, current_user, db)
    executions = await _load_backtest_executions(db, current_user, run_id)
    return BacktestExecutionList(executions=executions, total=len(executions))


@router.get("/{run_id}/timeline", response_model=BacktestTimelineResponse)
async def get_backtest_timeline(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    run = await _get_backtest_or_404(run_id, current_user, db)
    event_result = await db.execute(
        select(BacktestEvent)
        .where(BacktestEvent.run_id == run.id, BacktestEvent.user_id == current_user.id)
        .order_by(desc(BacktestEvent.created_at))
    )
    stored_events = event_result.scalars().all()

    events: list[BacktestTimelineEvent] = [
        BacktestTimelineEvent(
            id=str(event.id),
            ts=event.created_at.isoformat(),
            type=event.event_type,
            title=event.title,
            message=event.message,
            symbol=event.symbol,
            execution_id=str(event.execution_id) if event.execution_id else None,
            level=event.level,
            data=event.data or {},
        )
        for event in stored_events
    ]

    if not events:
        events.append(
            BacktestTimelineEvent(
                id=f"{run.id}-created",
                ts=run.created_at.isoformat(),
                type="run_created",
                title="Backtest queued",
                message=f"{run.pipeline_name or 'Pipeline'} queued for replay",
                data={"status": run.status.value},
            )
        )
        if run.started_at:
            events.append(
                BacktestTimelineEvent(
                    id=f"{run.id}-started",
                    ts=run.started_at.isoformat(),
                    type="run_started",
                    title="Backtest started",
                    message="Replay runtime started processing historical data",
                    data={"progress": run.progress or {}},
                )
            )
        if run.completed_at:
            events.append(
                BacktestTimelineEvent(
                    id=f"{run.id}-completed",
                    ts=run.completed_at.isoformat(),
                    type="run_completed",
                    title=f"Backtest {run.status.value.lower()}",
                    message=run.failure_reason or "Replay completed",
                    level="error" if run.status == BacktestRunStatus.FAILED else "info",
                    data={"metrics": run.metrics or {}, "trades_count": run.trades_count},
                )
            )

    events.sort(key=_timeline_sort_key, reverse=True)
    return BacktestTimelineResponse(events=events[:500])


@router.get("/{run_id}/report", response_model=BacktestReportResponse)
async def get_backtest_report(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    run = await _get_backtest_or_404(run_id, current_user, db)
    if run.status == BacktestRunStatus.COMPLETED:
        cached_report = _load_cached_report(run)
        if cached_report:
            return BacktestReportResponse.model_validate(cached_report)

    event_result = await db.execute(
        select(BacktestEvent)
        .where(BacktestEvent.run_id == run.id, BacktestEvent.user_id == current_user.id)
        .order_by(BacktestEvent.created_at.asc())
    )
    events = event_result.scalars().all()
    execution_result = await db.execute(
        select(Execution)
        .where(
            Execution.user_id == current_user.id,
            Execution.mode == "backtest",
            _execution_belongs_to_backtest(run_id),
        )
        .order_by(desc(Execution.created_at))
    )
    executions = execution_result.scalars().all()

    summary = _build_report_summary(run, executions, events)
    sections = _build_report_sections(run, executions, events)
    llm_analysis = None
    if run.status == BacktestRunStatus.COMPLETED:
        llm_analysis = await _generate_optional_llm_analysis(summary, sections)

    report_payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": summary,
        "sections": sections,
        "llm_analysis": llm_analysis,
    }

    if run.status == BacktestRunStatus.COMPLETED:
        _store_cached_report(run, report_payload)
        await db.commit()

    return BacktestReportResponse(
        generated_at=report_payload["generated_at"],
        summary=report_payload["summary"],
        sections=report_payload["sections"],
        llm_analysis=report_payload["llm_analysis"],
    )


@router.post("/{run_id}/cancel", response_model=BacktestRunSummary)
async def cancel_backtest(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(BacktestRun).where(BacktestRun.id == run_id, BacktestRun.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest run not found")

    if run.status in (BacktestRunStatus.COMPLETED, BacktestRunStatus.FAILED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Backtest run is already {run.status.value.lower()}",
        )

    if run.status != BacktestRunStatus.CANCELLED:
        previous_status = run.status
        run.status = BacktestRunStatus.CANCELLED
        run.failure_reason = "Cancelled by user"
        run_config = dict(run.config or {})
        runtime_config = dict(run_config.get("runtime") or {})
        runtime_config["cancel_requested_at"] = datetime.utcnow().isoformat()
        run_config["runtime"] = runtime_config
        run.config = run_config
        run.completed_at = datetime.utcnow()
        if previous_status == BacktestRunStatus.RUNNING:
            try:
                launcher = get_backtest_runtime_launcher()
                launcher.stop(runtime_config.get("launch_details"))
            except Exception:
                pass
        await db.commit()
        await db.refresh(run)

    executions = await _load_backtest_executions(db, current_user, run.id)
    return BacktestRunSummary.model_validate(_build_run_payload(run, executions))
