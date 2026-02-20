"""
Celery Tasks: Maintenance & Cleanup

Contains:
- cleanup_old_executions: Remove old execution records
- cleanup_stale_running_executions: Fail stuck RUNNING/PENDING executions
- reset_daily_budgets: Reset daily budget counters at midnight UTC
"""
import structlog
from datetime import datetime, timedelta

from app.orchestration.celery_app import celery_app
from app.database import SessionLocal
from app.models.execution import Execution, ExecutionStatus
from app.models.cost_tracking import UserBudget

logger = structlog.get_logger()


@celery_app.task(name="app.orchestration.tasks.cleanup_old_executions")
def cleanup_old_executions(days_to_keep: int = 30):
    """
    Clean up old execution records to save database space.
    
    Args:
        days_to_keep: Number of days of executions to keep
        
    Returns:
        Dict with number of executions deleted
    """
    logger.info("cleaning_up_old_executions", days_to_keep=days_to_keep)
    
    db = SessionLocal()
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # Delete old executions
        deleted = db.query(Execution).filter(
            Execution.created_at < cutoff_date,
            Execution.status.in_([ExecutionStatus.COMPLETED, ExecutionStatus.FAILED])
        ).delete()
        
        db.commit()
        
        logger.info("old_executions_cleaned", deleted=deleted)
        return {"deleted": deleted}
        
    finally:
        db.close()


@celery_app.task(name="app.orchestration.tasks.cleanup_stale_running_executions")
def cleanup_stale_running_executions(max_age_minutes: int = 20):
    """
    Fail stale in-flight executions so one orphaned ticker doesn't block the pipeline.

    Why this exists:
    - If a worker restarts or a task is killed mid-flight, the DB can be left with executions
      stuck in RUNNING/PENDING/MONITORING/COMMUNICATION_ERROR. The trigger-dispatcher treats
      any active execution as a pipeline-wide lock, so a single orphan can stop the entire
      pipeline from triggering on other tickers.

    Statuses handled:
    - RUNNING / PENDING: Standard in-flight statuses (stale after max_age_minutes)
    - MONITORING: Position monitoring loop (stale after max_monitoring_minutes)
    - COMMUNICATION_ERROR: Broker API retry loop (stale after max_monitoring_minutes)

    Args:
        max_age_minutes: Age threshold for RUNNING/PENDING executions (default: 20 min).
    """
    # MONITORING: If the Celery self-scheduling loop dies (worker crash), the execution
    # can get stuck.  We use a generous timeout because swing trades legitimately run
    # for days.  The heuristic: if next_check_at is set but far in the past, the
    # scheduler clearly died.  We only auto-fail MONITORING that has been truly orphaned.
    #
    # COMMUNICATION_ERROR with next_check_at=None: These have exhausted their retries
    # and are waiting for manual user intervention — do NOT auto-fail them.  The user
    # needs to reconcile the position on the broker side first.
    #
    # COMMUNICATION_ERROR with next_check_at set: Still auto-retrying; leave them alone.
    MAX_MONITORING_STALE_MINUTES = 60 * 25  # 25 hours

    db = SessionLocal()
    try:
        cutoff_running = datetime.utcnow() - timedelta(minutes=max_age_minutes)
        cutoff_monitoring = datetime.utcnow() - timedelta(minutes=MAX_MONITORING_STALE_MINUTES)

        # --- Stale RUNNING / PENDING ---
        stale_running = (
            db.query(Execution)
            .filter(
                Execution.status.in_([ExecutionStatus.RUNNING, ExecutionStatus.PENDING]),
                # Prefer started_at when present; fall back to created_at
                ((Execution.started_at.isnot(None)) & (Execution.started_at < cutoff_running))
                | ((Execution.started_at.is_(None)) & (Execution.created_at < cutoff_running)),
            )
            .all()
        )

        # --- Stale MONITORING ---
        # These are executions whose self-scheduling Celery loop died (worker crash).
        stale_monitoring = (
            db.query(Execution)
            .filter(
                Execution.status == ExecutionStatus.MONITORING,
                ((Execution.started_at.isnot(None)) & (Execution.started_at < cutoff_monitoring))
                | ((Execution.started_at.is_(None)) & (Execution.created_at < cutoff_monitoring)),
            )
            .all()
        )

        # --- Stale COMMUNICATION_ERROR (only those still auto-retrying) ---
        # COMMUNICATION_ERROR with next_check_at=None means retries are exhausted and
        # the execution is intentionally paused waiting for user intervention.
        # We must NOT auto-fail those — the user needs to reconcile the broker position.
        # We only clean up COMMUNICATION_ERROR that still has next_check_at set (i.e.,
        # the retry loop was supposed to continue but the worker died).
        stale_comm_error = (
            db.query(Execution)
            .filter(
                Execution.status == ExecutionStatus.COMMUNICATION_ERROR,
                Execution.next_check_at.isnot(None),  # Still supposed to be retrying
                ((Execution.started_at.isnot(None)) & (Execution.started_at < cutoff_monitoring))
                | ((Execution.started_at.is_(None)) & (Execution.created_at < cutoff_monitoring)),
            )
            .all()
        )

        stale = stale_running + stale_monitoring + stale_comm_error

        if not stale:
            return {"stale_failed": 0}

        for ex in stale:
            original_status = ex.status.value
            ex.status = ExecutionStatus.FAILED
            ex.completed_at = datetime.utcnow()
            ex.next_check_at = None  # Clear any pending monitoring schedule
            age_minutes = max_age_minutes if original_status in ("running", "pending") else MAX_MONITORING_STALE_MINUTES
            msg = (
                f"Stale execution auto-failed after {age_minutes}m "
                f"(original_status={original_status}, phase={getattr(ex, 'execution_phase', None)})."
            )
            ex.error_message = msg
            ex.result = (ex.result or {}) | {"error": msg, "stale_auto_failed": True}

        db.commit()
        logger.warning(
            "stale_executions_failed",
            count=len(stale),
            running_pending=len(stale_running),
            monitoring=len(stale_monitoring),
            comm_error_retrying=len(stale_comm_error),
            max_age_minutes=max_age_minutes,
            max_monitoring_stale_minutes=MAX_MONITORING_STALE_MINUTES,
        )
        return {
            "stale_failed": len(stale),
            "running_pending": len(stale_running),
            "monitoring_comm_error": len(stale_monitoring),
        }
    finally:
        db.close()


@celery_app.task(name="app.orchestration.tasks.reset_daily_budgets")
def reset_daily_budgets():
    """
    Reset daily budget counters at midnight UTC.
    
    Returns:
        Dict with number of budgets reset
    """
    logger.info("resetting_daily_budgets")
    
    db = SessionLocal()
    
    try:
        budgets = db.query(UserBudget).all()
        reset_count = 0
        
        for budget in budgets:
            # Check if it's been more than 24 hours
            if datetime.utcnow() - budget.daily_reset_at >= timedelta(days=1):
                budget.daily_spent = 0.0
                budget.daily_reset_at = datetime.utcnow()
                budget.alert_sent_daily = None
                reset_count += 1
        
        db.commit()
        
        logger.info("daily_budgets_reset", count=reset_count)
        return {"reset": reset_count}
        
    finally:
        db.close()
