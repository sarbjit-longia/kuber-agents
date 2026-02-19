"""
Dashboard API Endpoint

Provides aggregated data for the main dashboard view including:
- Pipeline overview
- Execution statistics
- Broker accounts with P&L
- Active positions
- Recent activity
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, and_
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import structlog

from app.database import get_db
from app.models.user import User
from app.models.pipeline import Pipeline, TriggerMode
from app.models.execution import Execution, ExecutionStatus
from app.api.dependencies import get_current_user

logger = structlog.get_logger()
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _extract_broker_info(pipeline: Pipeline) -> Optional[Dict[str, Any]]:
    """
    Extract broker configuration from a pipeline's config.
    
    Looks for broker_tool at pipeline level first, then in node configs.
    
    Args:
        pipeline: Pipeline model instance
        
    Returns:
        Dict with broker info or None
    """
    config = pipeline.config or {}
    
    # Check pipeline-level broker_tool first (guided builder)
    broker_tool = config.get("broker_tool")
    if broker_tool:
        tool_type = broker_tool.get("tool_type", "")
        broker_config = broker_tool.get("config", {})
        return {
            "tool_type": tool_type,
            "broker_name": _broker_display_name(tool_type),
            "account_id": broker_config.get("account_id", ""),
            "account_type": broker_config.get("account_type", "paper"),
        }
    
    # Check node configs for broker tools
    nodes = config.get("nodes", []) or []
    for node in nodes:
        node_config = node.get("config") or {}
        tools = node_config.get("tools") or []
        for tool in tools:
            tool_type = tool.get("tool_type", "")
            if "broker" in tool_type.lower():
                broker_config = tool.get("config", {})
                return {
                    "tool_type": tool_type,
                    "broker_name": _broker_display_name(tool_type),
                    "account_id": broker_config.get("account_id", ""),
                    "account_type": broker_config.get("account_type", "paper"),
                }
    
    return None


def _broker_display_name(tool_type: str) -> str:
    """Map tool_type to a human-readable broker name."""
    names = {
        "alpaca_broker": "Alpaca",
        "oanda_broker": "Oanda",
        "tradier_broker": "Tradier",
    }
    return names.get(tool_type, tool_type.replace("_", " ").title())


def _extract_pnl(execution: Execution) -> Optional[Dict[str, Any]]:
    """
    Extract P&L from an execution.
    
    Checks final_pnl (completed) and reports (monitoring) in that order.
    
    Args:
        execution: Execution model instance
        
    Returns:
        Dict with value, percent, and type or None
    """
    result = execution.result or {}
    
    # Check final P&L (completed trades)
    if result.get("final_pnl") is not None:
        return {
            "value": result["final_pnl"],
            "percent": result.get("final_pnl_percent"),
            "type": "realized",
        }
    
    # Check monitoring reports (live trades)
    reports = execution.reports or {}
    for agent_id, report in reports.items():
        if isinstance(report, dict) and report.get("agent_type") == "trade_manager_agent":
            data = report.get("data", {})
            if data and data.get("unrealized_pl") is not None:
                return {
                    "value": data["unrealized_pl"],
                    "percent": data.get("pnl_percent"),
                    "type": "unrealized",
                }
    
    return None


def _extract_trade_info(execution: Execution) -> Optional[Dict[str, Any]]:
    """
    Extract trade information from execution reports for active positions.
    
    Args:
        execution: Execution model instance
        
    Returns:
        Dict with trade details or None
    """
    reports = execution.reports or {}
    for agent_id, report in reports.items():
        if isinstance(report, dict) and report.get("agent_type") == "trade_manager_agent":
            data = report.get("data", {})
            if data:
                return {
                    "order_status": data.get("order_status"),
                    "order_type": data.get("order_type"),
                    "side": data.get("side"),
                    "entry_price": data.get("entry_price"),
                    "current_price": data.get("current_price"),
                    "quantity": data.get("quantity") or data.get("units"),
                    "unrealized_pl": data.get("unrealized_pl"),
                    "pnl_percent": data.get("pnl_percent"),
                    "take_profit": data.get("take_profit"),
                    "stop_loss": data.get("stop_loss"),
                }
    return None


@router.get("/")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get aggregated dashboard data for the current user.
    
    Returns pipeline overview, execution stats, broker accounts with P&L,
    active positions, and recent activity.
    
    Args:
        current_user: Authenticated user
        db: Async database session
        
    Returns:
        Dashboard data dictionary
    """
    # ── 1. Load all pipelines ──────────────────────────────────
    pipeline_result = await db.execute(
        select(Pipeline).where(Pipeline.user_id == current_user.id)
    )
    pipelines = list(pipeline_result.scalars().all())
    
    total_pipelines = len(pipelines)
    active_pipelines = len([p for p in pipelines if p.is_active])
    signal_pipelines = len([p for p in pipelines if p.trigger_mode == TriggerMode.SIGNAL])
    periodic_pipelines = len([p for p in pipelines if p.trigger_mode == TriggerMode.PERIODIC])
    
    # ── 2. Load all executions ─────────────────────────────────
    exec_result = await db.execute(
        select(Execution, Pipeline.name.label("pipeline_name"))
        .join(Pipeline, Execution.pipeline_id == Pipeline.id)
        .where(Execution.user_id == current_user.id)
        .order_by(Execution.created_at.desc())
    )
    rows = exec_result.all()
    
    executions_with_names = [(row[0], row[1]) for row in rows]
    all_executions = [row[0] for row in rows]
    
    total_executions = len(all_executions)
    running_count = len([e for e in all_executions if e.status == ExecutionStatus.RUNNING])
    monitoring_count = len([e for e in all_executions if e.status == ExecutionStatus.MONITORING])
    completed_count = len([e for e in all_executions if e.status == ExecutionStatus.COMPLETED])
    failed_count = len([e for e in all_executions if e.status == ExecutionStatus.FAILED])
    
    total_cost = sum(e.cost or 0 for e in all_executions)
    
    finished = completed_count + failed_count
    success_rate = completed_count / finished if finished > 0 else 0.0
    
    # ── 3. P&L aggregation ─────────────────────────────────────
    total_realized_pnl = 0.0
    total_unrealized_pnl = 0.0
    
    # Map pipeline → broker info for later grouping
    pipeline_broker_map: Dict[str, Dict[str, Any]] = {}
    for p in pipelines:
        broker = _extract_broker_info(p)
        if broker:
            pipeline_broker_map[str(p.id)] = broker
    
    # Aggregate P&L per broker account
    # key = (broker_name, account_id, account_type)
    broker_pnl: Dict[tuple, Dict[str, Any]] = {}
    
    for execution in all_executions:
        pnl = _extract_pnl(execution)
        if pnl is None:
            continue
        
        pnl_value = pnl["value"] or 0
        
        if pnl["type"] == "realized":
            total_realized_pnl += pnl_value
        else:
            total_unrealized_pnl += pnl_value
        
        # Group by broker
        broker = pipeline_broker_map.get(str(execution.pipeline_id))
        if broker:
            key = (broker["broker_name"], broker["account_id"], broker["account_type"])
            if key not in broker_pnl:
                broker_pnl[key] = {
                    "broker_name": broker["broker_name"],
                    "account_id": broker["account_id"],
                    "account_type": broker["account_type"],
                    "realized_pnl": 0.0,
                    "unrealized_pnl": 0.0,
                    "total_trades": 0,
                    "active_positions": 0,
                    "pipeline_count": 0,
                    "pipeline_ids": set(),
                }
            
            entry = broker_pnl[key]
            entry["total_trades"] += 1
            entry["pipeline_ids"].add(str(execution.pipeline_id))
            
            if pnl["type"] == "realized":
                entry["realized_pnl"] += pnl_value
            else:
                entry["unrealized_pnl"] += pnl_value
                entry["active_positions"] += 1
    
    # Finalize broker accounts list
    broker_accounts = []
    for key, entry in broker_pnl.items():
        entry["pipeline_count"] = len(entry["pipeline_ids"])
        entry["total_pnl"] = entry["realized_pnl"] + entry["unrealized_pnl"]
        del entry["pipeline_ids"]  # Not serializable (set)
        broker_accounts.append(entry)
    
    # Also add broker accounts that have no executions yet
    seen_keys = set(broker_pnl.keys())
    for p in pipelines:
        broker = pipeline_broker_map.get(str(p.id))
        if broker:
            key = (broker["broker_name"], broker["account_id"], broker["account_type"])
            if key not in seen_keys:
                seen_keys.add(key)
                broker_accounts.append({
                    "broker_name": broker["broker_name"],
                    "account_id": broker["account_id"],
                    "account_type": broker["account_type"],
                    "realized_pnl": 0.0,
                    "unrealized_pnl": 0.0,
                    "total_pnl": 0.0,
                    "total_trades": 0,
                    "active_positions": 0,
                    "pipeline_count": 1,
                })
    
    # ── 4. Active positions ────────────────────────────────────
    active_positions = []
    for execution, pipeline_name in executions_with_names:
        if execution.status not in (ExecutionStatus.MONITORING, ExecutionStatus.RUNNING):
            continue
        
        trade_info = _extract_trade_info(execution)
        pnl = _extract_pnl(execution)
        
        active_positions.append({
            "execution_id": str(execution.id),
            "pipeline_id": str(execution.pipeline_id),
            "pipeline_name": pipeline_name,
            "symbol": execution.symbol,
            "mode": execution.mode,
            "status": execution.status.value,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "trade_info": trade_info,
            "pnl": pnl,
            "broker": pipeline_broker_map.get(str(execution.pipeline_id)),
        })
    
    # ── 5. Recent completed executions (only with valid P&L) ─────────────────────────
    recent_executions = []
    for execution, pipeline_name in executions_with_names[:50]:  # Check more to find 10 with P&L
        if execution.status not in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED):
            continue
        if len(recent_executions) >= 10:
            break
        
        pnl = _extract_pnl(execution)
        
        # Only include executions with valid P&L (not None, not 0, or explicitly 0 from a closed trade)
        # This filters out executions that never resulted in a trade (rejected, skipped, etc.)
        if pnl is None:
            continue
        
        # Allow 0 P&L only if it's from a completed trade (has trade_outcome)
        pnl_value = pnl.get("value")
        if pnl_value is None:
            continue
        
        # Check if this is a real trade attempt (has trade_outcome with a relevant status)
        result = execution.result or {}
        trade_outcome = result.get("trade_outcome")
        if trade_outcome and isinstance(trade_outcome, dict):
            outcome_status = trade_outcome.get("status")
            # Include:
            # - "executed" = trade was filled, position opened and closed (has real P&L)
            # - "cancelled" = limit order was cancelled before fill (shows trade was attempted)
            # Skip:
            # - "accepted" = limit order never filled (no real P&L)
            # - "rejected", "failed", "no_action", "pending" = no real trade
            if outcome_status in ("executed", "cancelled"):
                pass  # Include it
            else:
                continue  # Skip non-trade outcomes
        elif pnl_value == 0:
            # No trade_outcome but P&L is 0 - likely not a real trade, skip
            continue
        
        # Extract strategy action
        strategy_action = None
        if execution.result and isinstance(execution.result, dict):
            strategy = execution.result.get("strategy")
            if strategy:
                strategy_action = strategy.get("action")
        
        duration_seconds = None
        if execution.started_at and execution.completed_at:
            duration_seconds = (execution.completed_at - execution.started_at).total_seconds()
        
        recent_executions.append({
            "execution_id": str(execution.id),
            "pipeline_name": pipeline_name,
            "symbol": execution.symbol,
            "mode": execution.mode,
            "status": execution.status.value,
            "strategy_action": strategy_action,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "duration_seconds": duration_seconds,
            "cost": execution.cost or 0,
            "pnl": pnl,
        })
    
    # ── 6. Pipeline list with status ───────────────────────────
    pipeline_list = []
    for p in pipelines:
        # Count executions per pipeline
        p_execs = [e for e in all_executions if str(e.pipeline_id) == str(p.id)]
        p_active = len([e for e in p_execs if e.status in (ExecutionStatus.MONITORING, ExecutionStatus.RUNNING)])
        p_completed = len([e for e in p_execs if e.status == ExecutionStatus.COMPLETED])
        p_failed = len([e for e in p_execs if e.status == ExecutionStatus.FAILED])
        
        # P&L for this pipeline
        pipeline_pnl = 0.0
        for e in p_execs:
            pnl = _extract_pnl(e)
            if pnl:
                pipeline_pnl += pnl["value"] or 0
        
        broker = pipeline_broker_map.get(str(p.id))
        
        pipeline_list.append({
            "id": str(p.id),
            "name": p.name,
            "is_active": p.is_active,
            "trigger_mode": p.trigger_mode.value if p.trigger_mode else "periodic",
            "broker": broker,
            "total_executions": len(p_execs),
            "active_executions": p_active,
            "completed_executions": p_completed,
            "failed_executions": p_failed,
            "total_pnl": pipeline_pnl,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    
    # ── 7. Today's stats ───────────────────────────────────────
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_execs = [e for e in all_executions if e.created_at and e.created_at >= today_start]
    today_count = len(today_execs)
    today_cost = sum(e.cost or 0 for e in today_execs)
    today_pnl = 0.0
    for e in today_execs:
        pnl = _extract_pnl(e)
        if pnl:
            today_pnl += pnl["value"] or 0
    
    # ── 8. Cost & P&L history (last 30 days) ──────────────────
    history_days = 30
    history_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=history_days - 1)
    
    # Initialize daily buckets
    cost_history: Dict[str, float] = {}
    pnl_history: Dict[str, float] = {}
    for i in range(history_days):
        day = (history_start + timedelta(days=i)).strftime("%Y-%m-%d")
        cost_history[day] = 0.0
        pnl_history[day] = 0.0
    
    for e in all_executions:
        if not e.created_at or e.created_at < history_start:
            continue
        day_key = e.created_at.strftime("%Y-%m-%d")
        if day_key in cost_history:
            cost_history[day_key] += e.cost or 0
        
        pnl = _extract_pnl(e)
        if pnl and day_key in pnl_history:
            pnl_history[day_key] += pnl["value"] or 0
    
    cost_history_list = [
        {"date": d, "cost": round(v, 4)} for d, v in sorted(cost_history.items())
    ]
    pnl_history_list = [
        {"date": d, "pnl": round(v, 2)} for d, v in sorted(pnl_history.items())
    ]
    
    # ── 9. Trade stats (win/loss analysis) ────────────────────
    winning_trades: List[float] = []
    losing_trades: List[float] = []
    
    for e in all_executions:
        if e.status != ExecutionStatus.COMPLETED:
            continue
        pnl = _extract_pnl(e)
        if pnl is None:
            continue
        pnl_val = pnl["value"]
        if pnl_val is None:
            continue
        # Only count real trades (same filter as recent executions)
        result_data = e.result or {}
        trade_outcome = result_data.get("trade_outcome")
        if trade_outcome and isinstance(trade_outcome, dict):
            if trade_outcome.get("status") not in ("executed", "cancelled"):
                continue
        elif pnl_val == 0:
            continue
        
        if pnl_val > 0:
            winning_trades.append(pnl_val)
        elif pnl_val < 0:
            losing_trades.append(pnl_val)
    
    total_trades_counted = len(winning_trades) + len(losing_trades)
    trade_stats = {
        "total_trades": total_trades_counted,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": round(len(winning_trades) / total_trades_counted, 4) if total_trades_counted > 0 else 0.0,
        "avg_win": round(sum(winning_trades) / len(winning_trades), 2) if winning_trades else 0.0,
        "avg_loss": round(sum(losing_trades) / len(losing_trades), 2) if losing_trades else 0.0,
        "best_trade": round(max(winning_trades), 2) if winning_trades else 0.0,
        "worst_trade": round(min(losing_trades), 2) if losing_trades else 0.0,
        "profit_factor": round(
            abs(sum(winning_trades) / sum(losing_trades)), 2
        ) if losing_trades and sum(losing_trades) != 0 else 0.0,
    }
    
    return {
        "pipelines": {
            "total": total_pipelines,
            "active": active_pipelines,
            "inactive": total_pipelines - active_pipelines,
            "signal_based": signal_pipelines,
            "periodic": periodic_pipelines,
        },
        "executions": {
            "total": total_executions,
            "running": running_count,
            "monitoring": monitoring_count,
            "completed": completed_count,
            "failed": failed_count,
            "total_cost": round(total_cost, 4),
            "success_rate": round(success_rate, 4),
        },
        "pnl": {
            "total_realized": round(total_realized_pnl, 2),
            "total_unrealized": round(total_unrealized_pnl, 2),
            "total": round(total_realized_pnl + total_unrealized_pnl, 2),
        },
        "today": {
            "executions": today_count,
            "cost": round(today_cost, 4),
            "pnl": round(today_pnl, 2),
        },
        "broker_accounts": broker_accounts,
        "active_positions": active_positions,
        "recent_executions": recent_executions,
        "pipeline_list": pipeline_list,
        "cost_history": cost_history_list,
        "pnl_history": pnl_history_list,
        "trade_stats": trade_stats,
    }
