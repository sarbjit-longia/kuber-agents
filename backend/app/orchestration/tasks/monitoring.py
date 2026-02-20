"""
Celery Task: Position Monitoring Check

Periodic monitoring loop for open positions (Trade Manager Agent).
Uses optimistic locking and handles communication errors with retries.

Main entry point: schedule_monitoring_check (Celery task)
Internal helpers (prefixed with _) handle each branch of the monitoring logic.
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
from app.agents import get_registry
from app.schemas.pipeline_state import PipelineState

from app.orchestration.tasks._helpers import (
    _send_position_closed_notification,
    _send_monitoring_stalled_notification,
    _serialize_logs,
    _serialize_reports,
    load_pipeline_state,
    save_pipeline_state,
)

logger = structlog.get_logger()

# --- Constants ---
MAX_COMM_ERROR_RETRIES = 60  # Max communication error retries (~1 hour at 1min intervals)


# ──────────────────────────────────────────────────────────────────────────────
# Low-level DB helpers
# ──────────────────────────────────────────────────────────────────────────────

def _serialize_model(model) -> Optional[dict]:
    """Serialize a Pydantic model to a JSON-safe dict, converting datetimes to ISO strings."""
    if model is None:
        return None
    data = model.dict()
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


def _safe_commit(db: Session, execution_id: str, context: str) -> bool:
    """
    Attempt to commit the current DB session.

    Returns True on success, False on failure (after rollback).
    """
    try:
        db.commit()
        return True
    except Exception as commit_error:
        logger.error(
            f"commit_failed_{context}",
            execution_id=execution_id,
            error=str(commit_error),
            exc_info=True,
        )
        db.rollback()
        return False


def _recovery_commit(
    execution_id: str,
    original_version: int,
    updates: dict,
    context: str,
) -> None:
    """
    Last-resort recovery: open a brand-new DB session and apply minimal updates
    using optimistic locking (only if version hasn't changed).

    Args:
        execution_id: UUID string of the execution
        original_version: Version the execution had when we first loaded it
        updates: Dict of column-name → value to apply
        context: Label for logging
    """
    db2 = SessionLocal()
    try:
        ex2 = db2.query(Execution).filter(Execution.id == UUID(execution_id)).first()
        if ex2 and ex2.version == original_version:
            for col, val in updates.items():
                setattr(ex2, col, val)
            ex2.version += 1
            db2.commit()
            logger.info(f"recovery_commit_succeeded_{context}", execution_id=execution_id)
        else:
            logger.warning(
                f"recovery_commit_skipped_{context}",
                execution_id=execution_id,
                reason="version_mismatch" if ex2 else "not_found",
            )
    except Exception as recovery_error:
        logger.error(
            f"recovery_commit_failed_{context}",
            execution_id=execution_id,
            error=str(recovery_error),
            exc_info=True,
        )
        db2.rollback()
    finally:
        db2.close()


# ──────────────────────────────────────────────────────────────────────────────
# Step helpers — each one handles a discrete phase of the monitoring check
# ──────────────────────────────────────────────────────────────────────────────

def _load_execution(
    db: Session,
    execution_id: str,
) -> Tuple[Optional[Execution], Optional[Dict[str, Any]]]:
    """
    Load and validate the execution from DB.

    Returns:
        (execution, None) on success
        (None, error_response_dict) if execution is missing or not monitorable
    """
    try:
        exec_uuid = UUID(execution_id) if isinstance(execution_id, str) else execution_id
    except (ValueError, AttributeError) as e:
        logger.error("invalid_execution_id", execution_id=execution_id, error=str(e))
        return None, {"status": "error", "message": f"Invalid execution_id: {execution_id}"}

    execution = db.query(Execution).filter(Execution.id == exec_uuid).first()

    if not execution:
        logger.warning("execution_not_found", execution_id=execution_id)
        return None, {"status": "not_found"}

    allowed_statuses = {ExecutionStatus.MONITORING, ExecutionStatus.COMMUNICATION_ERROR}
    if execution.status not in allowed_statuses:
        logger.info(
            "execution_not_monitorable",
            execution_id=execution_id,
            status=execution.status.value,
        )
        return None, {"status": "not_monitoring", "current_status": execution.status.value}

    return execution, None


def _load_state_and_agent(
    execution: Execution,
    execution_id: str,
) -> Tuple[Optional[PipelineState], Optional[Any], Optional[Dict[str, Any]]]:
    """
    Load PipelineState and create the Trade Manager agent.

    Returns:
        (state, agent, None) on success
        (None, None, error_response_dict) on failure
    """
    # --- Pipeline ---
    pipeline = execution.pipeline
    if not pipeline:
        logger.error("pipeline_not_found", execution_id=execution_id)
        return None, None, {"status": "error", "message": "Pipeline not found"}

    # --- PipelineState ---
    state = load_pipeline_state(execution)
    if state is None:
        logger.error("pipeline_state_load_failed", execution_id=execution_id)
        return None, None, {"status": "error", "message": "Could not load pipeline state"}

    state.execution_phase = "monitoring"

    # --- Trade Manager agent ---
    trade_manager_node = None
    for node in pipeline.config.get("nodes", []):
        if node.get("agent_type") == "trade_manager_agent":
            trade_manager_node = node
            break

    if not trade_manager_node:
        logger.error("trade_manager_not_found", execution_id=execution_id)
        return None, None, {"status": "error", "message": "Trade Manager agent not found"}

    registry = get_registry()
    agent = registry.create_agent(
        agent_type="trade_manager_agent",
        agent_id=trade_manager_node["id"],
        config=trade_manager_node.get("config", {}),
    )

    return state, agent, None


def _persist_agent_output(
    db: Session,
    execution: Execution,
    updated_state: PipelineState,
) -> None:
    """
    Save the common output fields from the agent back to the execution row.

    Persists:
    - Full PipelineState snapshot (pipeline_state JSONB column)
    - Denormalized result fields (strategy, risk_assessment, trade_execution, errors, warnings)
    - Logs and reports

    Does NOT commit — the caller decides when to commit based on which branch is taken.
    """
    save_pipeline_state(execution, updated_state, db=db)

    execution.result = {
        **(execution.result or {}),
        "strategy": _serialize_model(updated_state.strategy),
        "risk_assessment": _serialize_model(updated_state.risk_assessment),
        "trade_execution": _serialize_model(updated_state.trade_execution),
        "errors": updated_state.errors,
        "warnings": updated_state.warnings,
    }

    execution.logs = _serialize_logs(updated_state.execution_log)
    execution.reports = _serialize_reports(updated_state.agent_reports)
    flag_modified(execution, "logs")
    flag_modified(execution, "reports")
    flag_modified(execution, "result")


def _handle_retries_exhausted(
    db: Session,
    execution: Execution,
    execution_id: str,
    original_version: int,
    error_count: int,
    last_error: Optional[str],
) -> Dict[str, Any]:
    """
    Handle the case where communication error retries are exhausted.

    Marks the execution as NEEDS_RECONCILIATION — the position may still be
    open on the broker but we've lost the ability to monitor it. The user
    must manually verify and reconcile.
    """
    execution.status = ExecutionStatus.NEEDS_RECONCILIATION
    execution.next_check_at = None
    execution.error_message = (
        f"⚠️ Broker communication lost after {error_count} attempts. "
        f"Position may still be open on broker. Manual reconciliation required. "
        f"Last error: {last_error or 'Unknown'}"
    )
    execution.version += 1

    logger.error(
        "monitoring_retries_exhausted_needs_reconciliation",
        execution_id=execution_id,
        error_count=error_count,
        last_error=last_error,
        symbol=execution.symbol,
    )

    if not _safe_commit(db, execution_id, "retries_exhausted"):
        _recovery_commit(
            execution_id=execution_id,
            original_version=original_version,
            updates={
                "status": ExecutionStatus.NEEDS_RECONCILIATION,
                "next_check_at": None,
                "error_message": execution.error_message,
            },
            context="retries_exhausted",
        )

    _send_monitoring_stalled_notification(
        execution=execution,
        error_count=error_count,
        last_error=last_error,
    )

    return {
        "status": "needs_reconciliation",
        "reason": "retries_exhausted",
        "error_count": error_count,
        "message": "Monitoring stopped — manual reconciliation required",
    }


def _handle_communication_error(
    db: Session,
    execution: Execution,
    execution_id: str,
    original_version: int,
    updated_state: PipelineState,
) -> Dict[str, Any]:
    """
    Handle broker communication errors.

    If retries are exhausted → pause and notify user.
    Otherwise → schedule a 1-minute retry.
    """
    error_count = (
        updated_state.trade_execution.api_error_count
        if updated_state.trade_execution
        else 0
    )
    last_error = updated_state.communication_error_message

    if error_count >= MAX_COMM_ERROR_RETRIES:
        return _handle_retries_exhausted(
            db=db,
            execution=execution,
            execution_id=execution_id,
            original_version=original_version,
            error_count=error_count,
            last_error=last_error,
        )

    # Still under retry limit — mark as COMMUNICATION_ERROR and schedule retry
    execution.status = ExecutionStatus.COMMUNICATION_ERROR
    execution.next_check_at = datetime.utcnow() + timedelta(minutes=1)
    execution.version += 1

    logger.error(
        "monitoring_communication_error",
        execution_id=execution_id,
        error_count=error_count,
        last_error=last_error,
        retries_remaining=MAX_COMM_ERROR_RETRIES - error_count,
    )

    if not _safe_commit(db, execution_id, "comm_error"):
        _recovery_commit(
            execution_id=execution_id,
            original_version=original_version,
            updates={
                "status": ExecutionStatus.COMMUNICATION_ERROR,
                "next_check_at": datetime.utcnow() + timedelta(minutes=1),
            },
            context="comm_error",
        )

    schedule_monitoring_check.apply_async(
        args=[str(execution.id)], countdown=60
    )

    return {
        "status": "communication_error",
        "error": last_error,
        "retry_in": "1 minute",
        "error_count": error_count,
        "retries_remaining": MAX_COMM_ERROR_RETRIES - error_count,
    }


def _handle_monitoring_complete(
    db: Session,
    execution: Execution,
    execution_id: str,
    original_version: int,
    updated_state: PipelineState,
) -> Dict[str, Any]:
    """
    Handle the case where the Trade Manager signals that monitoring should complete.

    Marks the execution as COMPLETED (or NEEDS_RECONCILIATION if broker P&L
    could not be fetched), stores P&L data, and sends a notification.
    """
    outcome_status = (
        updated_state.trade_outcome.status
        if updated_state.trade_outcome
        else "executed"
    )

    # Extract P&L from trade_outcome
    pnl = 0.0
    pnl_percent = 0.0
    exit_reason = "Position closed"
    exit_price = None
    entry_price = None

    if updated_state.trade_outcome:
        pnl = updated_state.trade_outcome.pnl or 0.0
        pnl_percent = updated_state.trade_outcome.pnl_percent or 0.0
        exit_reason = updated_state.trade_outcome.exit_reason or "Position closed"
        exit_price = updated_state.trade_outcome.exit_price
        entry_price = updated_state.trade_outcome.entry_price

    # If there's actual P&L, the trade was filled — override 'accepted'/'pending'
    if pnl != 0 and outcome_status in ("accepted", "pending"):
        outcome_status = "executed"

    # ---------------------------------------------------------------
    # Determine execution status based on trade outcome.
    # If the agent couldn't get P&L from the broker, mark as
    # NEEDS_RECONCILIATION so the user can resolve it manually.
    # ---------------------------------------------------------------
    if outcome_status == "needs_reconciliation":
        execution.status = ExecutionStatus.NEEDS_RECONCILIATION
        execution.execution_phase = "needs_reconciliation"
        execution.completed_at = None  # Not truly completed
        execution.next_check_at = None
        execution.error_message = (
            f"Position closed but P&L could not be verified from broker. "
            f"Reason: {exit_reason}"
        )
        execution.version += 1
    else:
        execution.status = ExecutionStatus.COMPLETED
        execution.execution_phase = "completed"
        execution.completed_at = datetime.utcnow()
        execution.next_check_at = None
        execution.version += 1

    # Store trade outcome in execution result for UI display
    if not execution.result:
        execution.result = {}

    execution.result["trade_outcome"] = {
        "status": outcome_status,
        "pnl": pnl,
        "pnl_percent": pnl_percent,
        "exit_reason": exit_reason,
        "exit_price": exit_price,
        "entry_price": entry_price,
        "closed_at": datetime.utcnow().isoformat(),
    }

    execution.result["final_pnl"] = pnl
    execution.result["final_pnl_percent"] = pnl_percent
    flag_modified(execution, "result")

    logger.info(
        "monitoring_completed",
        execution_id=execution_id,
        outcome_status=outcome_status,
        execution_status=execution.status.value,
        pnl=pnl,
        pnl_percent=pnl_percent,
    )

    if outcome_status == "needs_reconciliation":
        target_status = ExecutionStatus.NEEDS_RECONCILIATION
        target_phase = "needs_reconciliation"
    else:
        target_status = ExecutionStatus.COMPLETED
        target_phase = "completed"

    if not _safe_commit(db, execution_id, "complete"):
        _recovery_commit(
            execution_id=execution_id,
            original_version=original_version,
            updates={
                "status": target_status,
                "completed_at": datetime.utcnow() if target_status == ExecutionStatus.COMPLETED else None,
                "execution_phase": target_phase,
                "next_check_at": None,
            },
            context="complete",
        )

    if outcome_status != "needs_reconciliation":
        _send_position_closed_notification(
            execution=execution,
            pnl=pnl,
            pnl_percent=pnl_percent,
            exit_reason=exit_reason,
        )

    return {"status": target_phase, "pnl": pnl, "pnl_percent": pnl_percent}


def _handle_continue_monitoring(
    db: Session,
    execution: Execution,
    execution_id: str,
    original_version: int,
    updated_state: PipelineState,
) -> Dict[str, Any]:
    """
    Handle the normal case: position is still open, schedule the next monitoring check.

    Interval source: execution.monitor_interval_minutes (DB column, non-nullable, default 5.0).
    Set to 0.25 (15s) by Trade Manager when placing a broker order.
    """
    interval = execution.monitor_interval_minutes

    execution.next_check_at = datetime.utcnow() + timedelta(minutes=interval)
    execution.version += 1

    if not _safe_commit(db, execution_id, "continue"):
        _recovery_commit(
            execution_id=execution_id,
            original_version=original_version,
            updates={
                "next_check_at": datetime.utcnow() + timedelta(minutes=interval),
            },
            context="continue",
        )

    schedule_monitoring_check.apply_async(
        args=[str(execution.id)],
        countdown=interval * 60,
    )

    logger.info(
        "monitoring_continuing",
        execution_id=execution_id,
        next_check_minutes=interval,
        next_check_at=execution.next_check_at.isoformat()
        if execution.next_check_at
        else "unknown",
    )

    return {"status": "monitoring", "next_check_minutes": interval}


# ──────────────────────────────────────────────────────────────────────────────
# Celery task — orchestrates the helpers above
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.orchestration.tasks.schedule_monitoring_check",
    bind=True,
    max_retries=5,
)
def schedule_monitoring_check(self, execution_id: str):
    """
    Periodic monitoring check for open positions (Trade Manager Agent).

    This task:
    1. Loads the execution and validates its status
    2. Loads the PipelineState and creates the Trade Manager agent
    3. Runs the agent's monitoring logic
    4. Persists agent output (state, result, logs, reports)
    5. Branches based on agent output:
       a. Communication error → retry or pause for user intervention
       b. Should complete → mark COMPLETED, store P&L, notify
       c. Continue monitoring → schedule next check

    Args:
        execution_id: UUID string of execution in MONITORING or COMMUNICATION_ERROR status

    Returns:
        Dict with monitoring status
    """
    logger.info(
        "monitoring_check_started",
        execution_id=execution_id,
        retry_number=self.request.retries,
    )

    db = SessionLocal()

    try:
        # 1. Load and validate execution
        execution, early_return = _load_execution(db, execution_id)
        if early_return:
            return early_return

        # 2. Load PipelineState + Trade Manager agent
        state, agent, early_return = _load_state_and_agent(execution, execution_id)
        if early_return:
            return early_return

        # 3. Execute monitoring logic
        try:
            updated_state = agent.process(state)
        except Exception as agent_error:
            logger.error(
                "trade_manager_agent_process_failed",
                execution_id=execution_id,
                error=str(agent_error),
                exc_info=True,
            )
            raise

        # 4. Persist agent output (does NOT commit)
        original_version = execution.version
        _persist_agent_output(db, execution, updated_state)

        # 5. Branch based on agent output
        if updated_state.communication_error:
            return _handle_communication_error(
                db, execution, execution_id, original_version, updated_state,
            )
        elif updated_state.should_complete:
            return _handle_monitoring_complete(
                db, execution, execution_id, original_version, updated_state,
            )
        else:
            return _handle_continue_monitoring(
                db, execution, execution_id, original_version, updated_state,
            )

    except Exception as exc:
        logger.error(
            "monitoring_check_failed",
            execution_id=execution_id,
            error=str(exc),
            retry_number=self.request.retries,
            exc_info=True,
        )
        # Retry with exponential backoff (1 min, 2 min, 4 min, 8 min, 16 min)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

    finally:
        db.close()
