"""
Celery Tasks: Trade Reconciliation

Safety net that catches discrepancies between DB state and broker reality.

Contains:
- reconcile_user_trades: Per-user reconciliation of broker positions vs DB state
- schedule_user_reconciliation: Master scheduler that spawns per-user tasks

Internal helpers (prefixed with _):
- _get_broker_for_execution: Resolve broker instance from pipeline config (cached)
- _check_symbol_on_broker: Safely call has_active_symbol with exception handling
- _recover_pnl_from_broker: Broker-only P&L recovery (single source of truth)
- _reconcile_closed_position: Complete reconciliation of a single closed execution
- _reschedule_orphaned_monitoring: Re-trigger broken monitoring chains
- _reconcile_comm_error_executions: Reconcile COMMUNICATION_ERROR executions
"""
import structlog
from uuid import UUID
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.orchestration.celery_app import celery_app
from app.database import SessionLocal
from app.models.execution import Execution, ExecutionStatus
from app.models.user import User
from app.models.pipeline import Pipeline
from app.services.brokers.base import BrokerService
from app.services.brokers.factory import broker_factory

from app.orchestration.tasks._helpers import (
    _extract_broker_tool,
    _send_position_closed_notification,
    load_pipeline_state,
    save_pipeline_state,
)

logger = structlog.get_logger()

# Grace period: don't reconcile executions that just entered monitoring
# — the broker API may not yet reflect the newly placed order.
GRACE_PERIOD_MINUTES = 3

# Orphan threshold: if next_check_at is this far in the past, the monitoring
# chain is considered broken and needs rescheduling.
ORPHAN_THRESHOLD_MINUTES = 2


# ---------------------------------------------------------------------------
# Broker resolution helpers
# ---------------------------------------------------------------------------

def _get_broker_for_execution(
    execution: Execution,
    db: Session,
    broker_cache: Dict[str, BrokerService],
) -> Tuple[Optional[BrokerService], Optional[str]]:
    """
    Resolve the broker instance for an execution from its pipeline config.

    Uses a cache keyed by broker_type:account_id:account_type to avoid
    creating duplicate broker connections for the same account.

    Args:
        execution: Execution ORM object
        db: Active SQLAlchemy session
        broker_cache: Mutable dict of broker_key → BrokerService

    Returns:
        (broker, broker_key) on success, (None, None) on failure
    """
    pipeline = db.query(Pipeline).filter(Pipeline.id == execution.pipeline_id).first()
    broker_tool = _extract_broker_tool(pipeline.config if pipeline else {}) if pipeline else None
    if not broker_tool:
        return None, None

    config = broker_tool.get("config", {}) or {}
    broker_key = f"{broker_tool.get('tool_type')}:{config.get('account_id')}:{config.get('account_type')}"

    if broker_key not in broker_cache:
        try:
            broker = broker_factory.from_tool_config(broker_tool)
            broker_cache[broker_key] = broker
        except Exception as e:
            logger.error(
                "reconciliation_broker_creation_failed",
                execution_id=str(execution.id),
                error=str(e),
            )
            return None, None

    return broker_cache.get(broker_key), broker_key


def _check_symbol_on_broker(
    broker: BrokerService,
    execution: Execution,
) -> Optional[bool]:
    """
    Safely check if a symbol has an active position/order on the broker.

    Returns:
        True  — symbol is active on broker
        False — symbol is NOT active on broker
        None  — API error (caller should skip this execution)
    """
    try:
        return broker.has_active_symbol(execution.symbol)
    except Exception as e:
        logger.error(
            "reconciliation_symbol_check_failed",
            execution_id=str(execution.id),
            symbol=execution.symbol,
            error=str(e),
        )
        return None


# ---------------------------------------------------------------------------
# Broker-only P&L recovery (single source of truth)
# ---------------------------------------------------------------------------

def _recover_pnl_from_broker(
    execution: Execution,
    broker: BrokerService,
    existing_trade_exec: Dict[str, Any],
) -> Tuple[str, float, float, str, str, Optional[str]]:
    """
    Recover P&L exclusively from the broker API.

    The broker is the single source of truth for trade outcomes.
    If we cannot obtain P&L from the broker (no trade_id, API failure, etc.),
    the execution is marked as NEEDS_RECONCILIATION so the user can resolve
    it manually — we never guess P&L from cached/stale data.

    Args:
        execution: Execution ORM object
        broker: Active BrokerService instance
        existing_trade_exec: trade_execution dict (from PipelineState or result)

    Returns:
        Tuple of (outcome, pnl, pnl_percent, exit_reason, close_time, trade_id)
        outcome is one of: "executed", "cancelled", "needs_reconciliation"
    """
    exec_status = (existing_trade_exec.get("status", "") or "").lower()
    close_time = datetime.utcnow().isoformat()
    trade_id = existing_trade_exec.get("trade_id") or existing_trade_exec.get("order_id")

    # If the order was never filled, it's a clean cancellation — no P&L needed.
    if exec_status not in ("filled", "partially_filled"):
        return (
            "cancelled",
            0.0,
            0.0,
            "Order was never filled — reconciled as cancelled",
            close_time,
            trade_id,
        )

    # Order was filled → we MUST get the realized P&L from the broker.
    if not trade_id:
        logger.warning(
            "reconciliation_no_trade_id",
            execution_id=str(execution.id),
            symbol=execution.symbol,
        )
        return (
            "needs_reconciliation",
            0.0,
            0.0,
            "Trade was filled but trade_id is missing — cannot fetch P&L from broker",
            close_time,
            None,
        )

    try:
        trade_details = broker.get_trade_details(str(trade_id))
    except Exception as e:
        logger.warning(
            "reconciliation_broker_api_failed",
            execution_id=str(execution.id),
            trade_id=trade_id,
            error=str(e),
        )
        return (
            "needs_reconciliation",
            0.0,
            0.0,
            f"Cannot reach broker to fetch P&L: {e}",
            close_time,
            trade_id,
        )

    if not trade_details or not trade_details.get("found"):
        logger.warning(
            "reconciliation_trade_not_found_on_broker",
            execution_id=str(execution.id),
            trade_id=trade_id,
        )
        return (
            "needs_reconciliation",
            0.0,
            0.0,
            f"Trade {trade_id} not found on broker — manual review required",
            close_time,
            trade_id,
        )

    broker_state = trade_details.get("state", "")
    broker_realized_pl = float(trade_details.get("realized_pl", 0))

    # Broker says the trade is still open — but has_active_symbol returned False.
    # This is a data inconsistency (bug in broker abstraction or race condition).
    # Flag it loudly and require user intervention.
    if broker_state == "open":
        logger.error(
            "reconciliation_bug_trade_open_but_has_active_symbol_false",
            execution_id=str(execution.id),
            trade_id=trade_id,
            symbol=execution.symbol,
        )
        return (
            "needs_reconciliation",
            0.0,
            0.0,
            f"BUG: has_active_symbol=False but broker trade {trade_id} is still open. "
            f"Manual review required.",
            close_time,
            trade_id,
        )

    # Trade is closed — use broker's realized P&L.
    if broker_state == "closed":
        entry_price = float(existing_trade_exec.get("filled_price", 0) or 0)
        units = float(trade_details.get("units", 0) or 0)
        cost_basis = entry_price * units if entry_price and units else 0
        pnl_percent = (
            (broker_realized_pl / cost_basis * 100) if cost_basis > 0 else 0.0
        )

        logger.info(
            "reconciliation_pnl_from_broker",
            execution_id=str(execution.id),
            symbol=execution.symbol,
            trade_id=trade_id,
            realized_pl=broker_realized_pl,
        )

        return (
            "executed",
            broker_realized_pl,
            pnl_percent,
            "Position closed — realized P&L from broker",
            trade_details.get("close_time") or close_time,
            trade_id,
        )

    # Unexpected broker state — mark for user review.
    logger.warning(
        "reconciliation_unexpected_broker_state",
        execution_id=str(execution.id),
        trade_id=trade_id,
        broker_state=broker_state,
    )
    return (
        "needs_reconciliation",
        0.0,
        0.0,
        f"Unexpected broker trade state: '{broker_state}' — manual review required",
        close_time,
        trade_id,
    )


# ---------------------------------------------------------------------------
# Per-execution reconciliation
# ---------------------------------------------------------------------------

def _reconcile_closed_position(
    db: Session,
    execution: Execution,
    broker: BrokerService,
) -> bool:
    """
    Reconcile a single execution whose position is no longer on the broker.

    Fetches P&L exclusively from the broker. If we cannot determine the
    actual P&L from the broker, the execution is marked as NEEDS_RECONCILIATION
    so the user can manually review — we never guess from cached data.

    Commits per-execution for isolation (one bad row doesn't poison the batch).

    Args:
        db: Active SQLAlchemy session
        execution: Execution in MONITORING or COMMUNICATION_ERROR status
        broker: Active BrokerService instance

    Returns:
        True if reconciled or marked as NEEDS_RECONCILIATION, False on commit failure
    """
    existing_result = execution.result or {}

    # Load trade_execution from PipelineState (preferred) or legacy result
    pipeline_state = load_pipeline_state(execution)
    if pipeline_state and pipeline_state.trade_execution:
        existing_trade_exec = pipeline_state.trade_execution.dict()
    else:
        existing_trade_exec = existing_result.get("trade_execution", {})

    # Broker-only P&L recovery
    outcome, pnl, pnl_percent, exit_reason, close_time, trade_id = _recover_pnl_from_broker(
        execution=execution,
        broker=broker,
        existing_trade_exec=existing_trade_exec,
    )

    # --- Determine final execution status ---
    if outcome == "needs_reconciliation":
        # Cannot determine P&L from broker — require user intervention.
        execution.status = ExecutionStatus.NEEDS_RECONCILIATION
        execution.completed_at = None  # Not truly completed
        execution.execution_phase = "needs_reconciliation"
        execution.next_check_at = None
        execution.error_message = (
            f"⚠️ Position closed but P&L could not be verified from broker. "
            f"Reason: {exit_reason}"
        )
    else:
        # Clean completion — broker confirmed the outcome (executed or cancelled).
        execution.status = ExecutionStatus.COMPLETED
        execution.completed_at = datetime.utcnow()
        execution.execution_phase = "completed"
        execution.next_check_at = None
        execution.error_message = None

    # --- Persist trade_outcome ---
    existing_result["trade_outcome"] = {
        "status": outcome,
        "pnl": pnl,
        "pnl_percent": pnl_percent,
        "exit_reason": exit_reason,
        "closed_at": close_time,
    }

    if pnl != 0:
        existing_result["final_pnl"] = pnl

    execution.result = existing_result | {
        "reconciled": True,
        "reconcile_reason": exit_reason,
    }
    flag_modified(execution, "result")

    # --- Update PipelineState if available ---
    if pipeline_state:
        pipeline_state.should_complete = True
        if pipeline_state.trade_outcome:
            pipeline_state.trade_outcome.pnl = pnl
            pipeline_state.trade_outcome.pnl_percent = pnl_percent
            pipeline_state.trade_outcome.exit_reason = exit_reason
            pipeline_state.trade_outcome.status = outcome
        save_pipeline_state(execution, pipeline_state, db=db)

    execution.version += 1

    # Per-execution commit for isolation
    try:
        db.commit()
    except Exception as commit_error:
        logger.error(
            "reconciliation_commit_failed",
            execution_id=str(execution.id),
            error=str(commit_error),
            exc_info=True,
        )
        db.rollback()
        return False

    # Send notification (best-effort, after commit)
    if outcome == "needs_reconciliation":
        _send_position_closed_notification(
            execution=execution,
            pnl=0.0,
            pnl_percent=0.0,
            exit_reason=f"⚠️ NEEDS RECONCILIATION: {exit_reason}",
        )
    else:
        _send_position_closed_notification(
            execution=execution,
            pnl=pnl,
            pnl_percent=pnl_percent,
            exit_reason=exit_reason,
        )

    logger.info(
        "execution_reconciled",
        execution_id=str(execution.id),
        symbol=execution.symbol,
        outcome=outcome,
        pnl=pnl,
        trade_id=trade_id,
    )

    return True


# ---------------------------------------------------------------------------
# Orphaned monitoring chain recovery
# ---------------------------------------------------------------------------

def _reschedule_orphaned_monitoring(
    db: Session,
    execution: Execution,
) -> bool:
    """
    Re-schedule a broken monitoring chain for an execution whose position
    is still active on the broker but whose Celery task chain has died.

    Args:
        db: Active SQLAlchemy session
        execution: Execution in MONITORING status with stale next_check_at

    Returns:
        True if rescheduled, False otherwise
    """
    # Deferred import to avoid circular dependency (monitoring → reconciliation)
    from app.orchestration.tasks.monitoring import schedule_monitoring_check

    orphan_threshold = datetime.utcnow() - timedelta(minutes=ORPHAN_THRESHOLD_MINUTES)
    is_orphaned = (
        execution.next_check_at is None
        or execution.next_check_at < orphan_threshold
    )

    if not is_orphaned:
        return False

    logger.warning(
        "monitoring_chain_broken_rescheduling",
        execution_id=str(execution.id),
        symbol=execution.symbol,
        next_check_at=str(execution.next_check_at),
    )

    # Update next_check_at so we don't re-schedule on every reconciliation cycle
    execution.next_check_at = datetime.utcnow() + timedelta(seconds=15)
    execution.version += 1

    try:
        db.commit()
    except Exception as commit_error:
        logger.error(
            "reschedule_commit_failed",
            execution_id=str(execution.id),
            error=str(commit_error),
        )
        db.rollback()
        return False

    # Re-trigger the monitoring chain
    schedule_monitoring_check.apply_async(
        args=[str(execution.id)],
        countdown=10,
    )

    return True


# ---------------------------------------------------------------------------
# COMMUNICATION_ERROR reconciliation
# ---------------------------------------------------------------------------

def _reconcile_comm_error_executions(
    db: Session,
    comm_error_executions: list,
    broker_cache: Dict[str, BrokerService],
) -> Tuple[int, int]:
    """
    Reconcile COMMUNICATION_ERROR executions.

    These are executions where the monitoring loop lost contact with the broker.
    Two sub-cases:
      1. Retries exhausted (next_check_at = None): Awaiting user intervention.
         Check if broker position is gone → auto-reconcile if so.
         If broker P&L unavailable → mark NEEDS_RECONCILIATION.
      2. Still retrying (next_check_at set): Leave for monitoring.py to handle,
         but check if the monitoring chain is broken → reschedule if so.

    Args:
        db: Active SQLAlchemy session
        comm_error_executions: List of COMMUNICATION_ERROR Execution objects
        broker_cache: Shared broker instance cache

    Returns:
        Tuple of (reconciled_count, rescheduled_count)
    """
    reconciled = 0
    rescheduled = 0

    for execution in comm_error_executions:
        if not execution.symbol:
            continue

        broker, _ = _get_broker_for_execution(execution, db, broker_cache)
        if not broker:
            continue

        has_active = _check_symbol_on_broker(broker, execution)
        if has_active is None:
            # API error — can't determine state, skip
            continue

        if not has_active:
            # Position is gone — auto-reconcile regardless of retry state
            if _reconcile_closed_position(db, execution, broker):
                reconciled += 1
        elif execution.next_check_at is not None:
            # Position still active + still retrying → check if chain is broken
            if _reschedule_orphaned_monitoring(db, execution):
                rescheduled += 1
        # else: next_check_at is None (paused) + position still active
        # → leave for user to manually handle

    return reconciled, rescheduled


# ===========================================================================
# Main Celery tasks
# ===========================================================================

@celery_app.task(
    name="app.orchestration.tasks.reconcile_user_trades",
    bind=True,
    max_retries=3,
)
def reconcile_user_trades(self, user_id: str):
    """
    Reconcile trades for a specific user.

    Checks if user's open positions on broker match MONITORING and
    COMMUNICATION_ERROR executions in database.

    For each execution:
    1. If broker says position is gone → fetch P&L from broker → COMPLETED
    2. If broker P&L unavailable (no trade_id, API error) → NEEDS_RECONCILIATION
    3. If broker says position is still open but monitoring chain is broken → reschedule
    4. If COMMUNICATION_ERROR with retries exhausted + position gone → auto-reconcile or NEEDS_RECONCILIATION

    Runs independently per user for isolation and scalability.

    Args:
        user_id: UUID of user to reconcile

    Returns:
        Dict with reconciliation results for this user
    """
    logger.info("user_reconciliation_started", user_id=user_id)

    db = SessionLocal()

    try:
        # Validate user
        user = db.query(User).filter(User.id == UUID(user_id)).first()
        if not user:
            logger.warning("user_not_found", user_id=user_id)
            return {"status": "user_not_found", "user_id": user_id}

        # Get all MONITORING executions for this user
        monitoring_executions = (
            db.query(Execution)
            .filter(
                Execution.user_id == UUID(user_id),
                Execution.status == ExecutionStatus.MONITORING,
            )
            .all()
        )

        # Get COMMUNICATION_ERROR executions (broker API issues)
        comm_error_executions = (
            db.query(Execution)
            .filter(
                Execution.user_id == UUID(user_id),
                Execution.status == ExecutionStatus.COMMUNICATION_ERROR,
            )
            .all()
        )

        # Get NEEDS_RECONCILIATION executions (P&L unknown — retry broker)
        needs_recon_executions = (
            db.query(Execution)
            .filter(
                Execution.user_id == UUID(user_id),
                Execution.status == ExecutionStatus.NEEDS_RECONCILIATION,
            )
            .all()
        )

        monitoring_symbols = {ex.symbol for ex in monitoring_executions}
        grace_cutoff = datetime.utcnow() - timedelta(minutes=GRACE_PERIOD_MINUTES)

        # Shared broker instance cache (avoids duplicate connections per account)
        broker_cache: Dict[str, BrokerService] = {}
        reconciled = 0
        rescheduled = 0

        # -----------------------------------------------------------------
        # Phase 1: Reconcile MONITORING executions
        # -----------------------------------------------------------------
        for execution in monitoring_executions:
            # Skip executions that entered monitoring very recently
            monitoring_start = execution.started_at or execution.created_at
            if monitoring_start and monitoring_start > grace_cutoff:
                logger.debug(
                    "reconciliation_skipped_grace_period",
                    execution_id=str(execution.id),
                    symbol=execution.symbol,
                    age_seconds=(datetime.utcnow() - monitoring_start).total_seconds(),
                )
                continue

            broker, _ = _get_broker_for_execution(execution, db, broker_cache)
            if not broker:
                continue

            if not execution.symbol:
                continue

            has_active = _check_symbol_on_broker(broker, execution)
            if has_active is None:
                # API error — can't determine state, skip
                continue

            if not has_active:
                # Position/order no longer exists on broker — reconcile
                if _reconcile_closed_position(db, execution, broker):
                    reconciled += 1
            else:
                # Broker still has active position — check if monitoring chain is broken
                if _reschedule_orphaned_monitoring(db, execution):
                    rescheduled += 1

        # -----------------------------------------------------------------
        # Phase 2: Reconcile COMMUNICATION_ERROR executions
        # -----------------------------------------------------------------
        comm_reconciled, comm_rescheduled = _reconcile_comm_error_executions(
            db, comm_error_executions, broker_cache,
        )
        reconciled += comm_reconciled
        rescheduled += comm_rescheduled

        # -----------------------------------------------------------------
        # Phase 3: Retry NEEDS_RECONCILIATION executions
        # These had their position closed but P&L couldn't be fetched from
        # the broker at reconciliation time. Retry the broker call — if it
        # succeeds now, promote to COMPLETED; if not, leave as-is.
        # -----------------------------------------------------------------
        recon_resolved = 0
        for execution in needs_recon_executions:
            broker, _ = _get_broker_for_execution(execution, db, broker_cache)
            if not broker:
                continue

            existing_result = execution.result or {}
            pipeline_state = load_pipeline_state(execution)
            if pipeline_state and pipeline_state.trade_execution:
                existing_trade_exec = pipeline_state.trade_execution.dict()
            else:
                existing_trade_exec = existing_result.get("trade_execution", {})

            outcome, pnl, pnl_percent, exit_reason, close_time, trade_id = (
                _recover_pnl_from_broker(
                    execution=execution,
                    broker=broker,
                    existing_trade_exec=existing_trade_exec,
                )
            )

            # Only promote to COMPLETED if broker gave us actual P&L.
            # "needs_reconciliation" again means broker still can't help — leave as-is.
            if outcome in ("executed", "cancelled"):
                execution.status = ExecutionStatus.COMPLETED
                execution.completed_at = datetime.utcnow()
                execution.execution_phase = "completed"
                execution.error_message = None

                existing_result["trade_outcome"] = {
                    "status": outcome,
                    "pnl": pnl,
                    "pnl_percent": pnl_percent,
                    "exit_reason": exit_reason,
                    "closed_at": close_time,
                }
                if pnl != 0:
                    existing_result["final_pnl"] = pnl

                execution.result = existing_result | {
                    "reconciled": True,
                    "reconcile_reason": exit_reason,
                }
                flag_modified(execution, "result")

                if pipeline_state:
                    pipeline_state.should_complete = True
                    if pipeline_state.trade_outcome:
                        pipeline_state.trade_outcome.pnl = pnl
                        pipeline_state.trade_outcome.pnl_percent = pnl_percent
                        pipeline_state.trade_outcome.exit_reason = exit_reason
                        pipeline_state.trade_outcome.status = outcome
                    save_pipeline_state(execution, pipeline_state, db=db)

                execution.version += 1
                try:
                    db.commit()
                    recon_resolved += 1
                    logger.info(
                        "needs_reconciliation_resolved",
                        execution_id=str(execution.id),
                        symbol=execution.symbol,
                        outcome=outcome,
                        pnl=pnl,
                    )
                except Exception as commit_error:
                    logger.error(
                        "needs_reconciliation_commit_failed",
                        execution_id=str(execution.id),
                        error=str(commit_error),
                    )
                    db.rollback()

        reconciled += recon_resolved

        logger.info(
            "user_reconciliation_completed",
            user_id=user_id,
            monitoring_count=len(monitoring_executions),
            monitoring_symbols=list(monitoring_symbols),
            communication_errors=len(comm_error_executions),
            needs_reconciliation=len(needs_recon_executions),
            recon_resolved=recon_resolved,
            reconciled=reconciled,
            rescheduled=rescheduled,
        )

        return {
            "status": "completed",
            "user_id": user_id,
            "monitoring_executions": len(monitoring_executions),
            "monitoring_symbols": list(monitoring_symbols),
            "communication_errors": len(comm_error_executions),
            "needs_reconciliation": len(needs_recon_executions),
            "recon_resolved": recon_resolved,
            "reconciled": reconciled,
            "rescheduled": rescheduled,
        }

    except Exception as e:
        logger.error(
            "user_reconciliation_failed",
            user_id=user_id,
            error=str(e),
            exc_info=True,
        )

        # Retry on transient failures
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60)

        return {"status": "error", "user_id": user_id, "error": str(e)}

    finally:
        db.close()


@celery_app.task(name="app.orchestration.tasks.schedule_user_reconciliation")
def schedule_user_reconciliation():
    """
    Master reconciliation scheduler.

    Spawns individual reconciliation tasks for each user with active trades.
    Runs every 1 minute via Celery Beat.

    This approach provides:
    - User isolation: One user's broker issues don't affect others
    - Scalability: Tasks distributed across workers
    - Parallel execution: All users checked simultaneously

    Returns:
        Dict with number of users scheduled
    """
    logger.info("master_reconciliation_started")

    db = SessionLocal()

    try:
        # Find users with active trades (MONITORING, COMMUNICATION_ERROR, or NEEDS_RECONCILIATION)
        users_with_active_trades = (
            db.query(User)
            .join(Execution)
            .filter(
                Execution.status.in_([
                    ExecutionStatus.MONITORING,
                    ExecutionStatus.COMMUNICATION_ERROR,
                    ExecutionStatus.NEEDS_RECONCILIATION,
                ])
            )
            .distinct()
            .all()
        )

        scheduled_count = 0

        for user in users_with_active_trades:
            reconcile_user_trades.apply_async(args=[str(user.id)])
            scheduled_count += 1

        logger.info(
            "master_reconciliation_completed",
            users_scheduled=scheduled_count,
        )

        return {
            "status": "completed",
            "users_scheduled": scheduled_count,
        }

    except Exception as e:
        logger.error("master_reconciliation_failed", error=str(e), exc_info=True)
        return {"status": "error", "error": str(e)}

    finally:
        db.close()
