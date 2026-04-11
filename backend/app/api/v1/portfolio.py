"""
Portfolio Dashboard API (TP-026) + Playbooks API (TP-027) + LLM Quality (TP-030)
+ Strategy Templates (TP-028)
"""
from typing import Annotated, Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.execution import Execution, ExecutionStatus
from app.models.user import User
from app.core.deps import get_current_active_user
from app.services.playbooks import list_playbooks, get_playbook, validate_template
from app.services.llm_monitor import compute_quality_report
from app.strategies.templates import STRATEGY_TEMPLATES, list_templates

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


# ---------------------------------------------------------------------------
# TP-026: Portfolio risk dashboard
# ---------------------------------------------------------------------------

@router.get("/risk-summary", summary="Active portfolio risk overview")
async def portfolio_risk_summary(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Returns a real-time summary of active risk across all live positions.

    Includes:
    - Total notional exposure
    - Long / short balance
    - Active symbols and strategies
    - Per-symbol P&L
    - Concentration warnings
    """
    result = await db.execute(
        select(Execution).where(
            Execution.user_id == current_user.id,
            Execution.status == ExecutionStatus.MONITORING,
        )
    )
    monitoring = result.scalars().all()

    positions = []
    total_long_exposure  = 0.0
    total_short_exposure = 0.0
    strategy_counts: Dict[str, int] = {}
    symbol_set: Dict[str, Dict[str, Any]] = {}

    for ex in monitoring:
        state = ex.pipeline_state or {}
        trade_exec = state.get("trade_execution") or {}
        strategy   = state.get("strategy") or {}
        risk       = state.get("risk_assessment") or {}

        action      = (strategy.get("action") or "").upper()
        symbol      = ex.symbol or state.get("symbol", "UNKNOWN")
        entry       = float(strategy.get("entry_price") or 0)
        qty         = float(trade_exec.get("filled_quantity") or risk.get("position_size") or 0)
        notional    = entry * qty
        strat_fam   = (strategy.get("strategy_spec") or {}).get("strategy_family", "unknown") if isinstance(strategy.get("strategy_spec"), dict) else "unknown"

        position_data = {
            "execution_id": str(ex.id),
            "symbol": symbol,
            "action": action,
            "entry_price": entry,
            "quantity": qty,
            "notional": round(notional, 2),
            "strategy_family": strat_fam,
            "stop_loss": strategy.get("stop_loss"),
            "take_profit": strategy.get("take_profit"),
        }
        positions.append(position_data)

        if action == "BUY":
            total_long_exposure += notional
        elif action == "SELL":
            total_short_exposure += notional

        strategy_counts[strat_fam] = strategy_counts.get(strat_fam, 0) + 1
        if symbol not in symbol_set:
            symbol_set[symbol] = {"count": 0, "notional": 0.0}
        symbol_set[symbol]["count"] += 1
        symbol_set[symbol]["notional"] += notional

    total_exposure = total_long_exposure + total_short_exposure
    long_pct  = total_long_exposure  / total_exposure if total_exposure > 0 else 0
    short_pct = total_short_exposure / total_exposure if total_exposure > 0 else 0

    warnings = []
    if long_pct > 0.80:
        warnings.append(f"Portfolio is {long_pct*100:.0f}% long — consider hedging or reducing exposure")
    if short_pct > 0.80:
        warnings.append(f"Portfolio is {short_pct*100:.0f}% short")

    # Symbol concentration
    for sym, data in symbol_set.items():
        if total_exposure > 0 and data["notional"] / total_exposure > 0.30:
            warnings.append(
                f"Symbol concentration: {sym} = {data['notional']/total_exposure*100:.0f}% "
                "of total exposure (>30% limit)"
            )

    return {
        "active_positions": len(positions),
        "total_exposure": round(total_exposure, 2),
        "long_exposure": round(total_long_exposure, 2),
        "short_exposure": round(total_short_exposure, 2),
        "long_pct": round(long_pct, 3),
        "short_pct": round(short_pct, 3),
        "strategy_breakdown": strategy_counts,
        "symbol_breakdown": {
            sym: {"count": d["count"], "notional": round(d["notional"], 2)}
            for sym, d in symbol_set.items()
        },
        "positions": positions,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# TP-027: Playbooks
# ---------------------------------------------------------------------------

@router.get("/playbooks", summary="List first-party strategy playbooks")
async def list_playbooks_endpoint(
    category: Optional[str] = Query(None, description="Filter by 'intraday' or 'swing'"),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
):
    """
    Returns all first-party strategy playbooks.

    Each playbook is a complete, ready-to-use pipeline template
    with pre-filled agent instructions for a specific strategy.
    Clone one to get started without building a pipeline from scratch.
    """
    pbs = list_playbooks(category=category)
    return {"playbooks": [p.to_dict() for p in pbs], "total": len(pbs)}


@router.post("/playbooks/{playbook_id}/clone", summary="Clone a playbook into a pipeline config")
async def clone_playbook(
    playbook_id: str,
    symbol: str = Query(..., description="Trading symbol e.g. AAPL"),
    mode: str = Query("paper", description="'paper' or 'live'"),
    risk_pct: Optional[float] = Query(None, description="Override default risk % (0–0.05)"),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
):
    """
    Generate a pipeline config from a playbook.

    Returns a ready-to-POST pipeline config.  The caller should then send it to
    `POST /api/v1/pipelines` to create the pipeline, then attach a broker tool.
    """
    pb = get_playbook(playbook_id)
    if not pb:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playbook '{playbook_id}' not found",
        )

    config = pb.to_pipeline_config(symbol=symbol, mode=mode, risk_pct=risk_pct)
    return {
        "playbook_id": playbook_id,
        "playbook_name": pb.name,
        "symbol": symbol,
        "mode": mode,
        "pipeline_config": config,
        "next_step": "POST /api/v1/pipelines with this config, then attach your broker tool to node-6",
    }


# ---------------------------------------------------------------------------
# TP-028: Strategy template marketplace
# ---------------------------------------------------------------------------

@router.get("/strategy-templates", summary="List deterministic strategy templates")
async def list_strategy_templates(
    category: Optional[str] = Query(None, description="'intraday' or 'swing'"),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
):
    """
    Returns all first-party deterministic strategy templates.

    Templates define machine-readable trading rules (entry trigger, stop type,
    target type, position sizing model) used by the SetupEvaluator.
    """
    templates = list_templates(category=category)
    return {"templates": templates, "total": len(templates)}


@router.post("/strategy-templates/validate", summary="Validate a strategy template")
async def validate_strategy_template(
    template: Dict[str, Any],
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
):
    """
    Validate a custom strategy template against the marketplace contract.

    Returns validation errors (empty list = valid).
    Use this before submitting a custom template to the strategy marketplace.
    """
    errors = validate_template(template)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# TP-030: LLM quality monitoring
# ---------------------------------------------------------------------------

@router.get("/llm-quality", summary="LLM decision quality metrics")
async def llm_quality_report(
    pipeline_id: Optional[UUID] = Query(None, description="Filter to a specific pipeline"),
    limit: int = Query(100, ge=10, le=500, description="Number of recent executions to analyse"),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """
    Analyse the quality and consistency of LLM-driven decisions over recent executions.

    Reports:
    - Bias distribution (BULLISH / BEARISH / NEUTRAL ratios)
    - Strategy action distribution (BUY / SELL / HOLD ratios)
    - Trade review approval rate
    - Anomaly flags (rubber-stamping, model stuck, over-cautiousness)

    Use this to detect LLM drift before it affects live trading.
    """
    report = await compute_quality_report(
        db=db,
        user_id=current_user.id,
        pipeline_id=pipeline_id,
        limit=limit,
    )
    return report.to_dict()
