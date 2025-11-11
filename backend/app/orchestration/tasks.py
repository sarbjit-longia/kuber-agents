"""
Celery Tasks for Pipeline Execution

Defines asynchronous tasks for:
- Pipeline execution
- Scheduled pipeline checks
- Background maintenance
"""
import structlog
from uuid import UUID
from datetime import datetime, timedelta
from typing import Optional

from app.orchestration.celery_app import celery_app
from app.database import SessionLocal
from app.models.pipeline import Pipeline
from app.models.execution import Execution, ExecutionStatus
from app.models.cost_tracking import UserBudget
from app.orchestration.executor import PipelineExecutor
from app.agents.base import TriggerNotMetException

logger = structlog.get_logger()


@celery_app.task(name="app.orchestration.tasks.execute_pipeline", bind=True, max_retries=3)
def execute_pipeline(
    self,
    pipeline_id: str,
    user_id: str,
    mode: str = "paper",
    execution_id: Optional[str] = None
):
    """
    Execute a trading pipeline asynchronously.
    
    This is the main Celery task for running pipelines in the background.
    
    Args:
        pipeline_id: UUID of pipeline to execute
        user_id: UUID of user
        mode: Execution mode ("live", "paper", "simulation", "validation")
        execution_id: Optional pre-created execution ID
        
    Returns:
        Dict with execution results
    """
    logger.info(
        "celery_task_started",
        task_id=self.request.id,
        pipeline_id=pipeline_id,
        user_id=user_id,
        mode=mode
    )
    
    try:
        # Create database session
        db = SessionLocal()
        
        try:
            # Load pipeline
            pipeline = db.query(Pipeline).filter(Pipeline.id == UUID(pipeline_id)).first()
            if not pipeline:
                raise ValueError(f"Pipeline {pipeline_id} not found")
            
            if str(pipeline.user_id) != user_id:
                raise PermissionError("Pipeline does not belong to user")
            
            # Note: Manual executions don't require pipeline to be active
            # Active status only matters for scheduled runs
            # The check is done by check_scheduled_pipelines task
            
            # Check user budget
            budget = db.query(UserBudget).filter(UserBudget.user_id == UUID(user_id)).first()
            if budget:
                exceeded, reason = budget.check_budget_exceeded()
                if exceeded:
                    logger.warning("budget_exceeded", user_id=user_id, reason=reason)
                    return {"status": "skipped", "reason": reason}
            
            # Create executor
            executor = PipelineExecutor(
                pipeline=pipeline,
                user_id=UUID(user_id),
                mode=mode,
                execution_id=UUID(execution_id) if execution_id else None
            )
            
            # Execute pipeline synchronously for Celery
            # Get or create execution record
            execution = db.query(Execution).filter(Execution.id == executor.execution_id).first()
            
            if not execution:
                # Create new execution record
                execution = Execution(
                    id=executor.execution_id,
                    pipeline_id=pipeline.id,
                    user_id=UUID(user_id),
                    status=ExecutionStatus.RUNNING,
                    mode=mode,
                    symbol=pipeline.config.get("symbol"),
                    started_at=datetime.utcnow()
                )
                db.add(execution)
                db.commit()
            else:
                # Update existing execution
                execution.status = ExecutionStatus.RUNNING
                if not execution.started_at:
                    execution.started_at = datetime.utcnow()
                db.commit()
            
            try:
                # Execute pipeline (runs async internally)
                import asyncio
                
                # Create a new event loop for this task
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    state = loop.run_until_complete(executor.execute())
                finally:
                    loop.close()
                
                # Update execution with results
                execution.status = ExecutionStatus.COMPLETED if not state.errors else ExecutionStatus.FAILED
                execution.completed_at = datetime.utcnow()
                execution.result = {
                    "trigger_met": state.trigger_met,
                    "trigger_reason": state.trigger_reason,
                    "strategy": state.strategy.dict() if state.strategy else None,
                    "risk_assessment": state.risk_assessment.dict() if state.risk_assessment else None,
                    "trade_execution": state.trade_execution.dict() if state.trade_execution else None,
                    "errors": state.errors,
                    "warnings": state.warnings
                }
                execution.cost = state.total_cost
                execution.logs = state.execution_log
                db.commit()
                
            except TriggerNotMetException as e:
                execution.status = ExecutionStatus.SKIPPED
                execution.completed_at = datetime.utcnow()
                execution.result = {"trigger_met": False, "reason": str(e)}
                db.commit()
                
            except Exception as e:
                execution.status = ExecutionStatus.FAILED
                execution.completed_at = datetime.utcnow()
                execution.result = {"error": str(e)}
                execution.error_message = str(e)
                db.commit()
                raise
            
            logger.info(
                "celery_task_completed",
                task_id=self.request.id,
                execution_id=str(execution.id),
                status=execution.status.value,
                cost=execution.cost
            )
            
            return {
                "status": "completed",
                "execution_id": str(execution.id),
                "cost": execution.cost,
                "errors": execution.result.get("errors", []) if execution.result else []
            }
            
        finally:
            db.close()
            
    except Exception as exc:
        logger.exception("celery_task_failed", task_id=self.request.id)
        
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 60)


@celery_app.task(name="app.orchestration.tasks.check_scheduled_pipelines")
def check_scheduled_pipelines():
    """
    Check for pipelines that should be executed based on their schedule.
    
    This task runs every minute (configured in beat_schedule) and:
    1. Finds active pipelines with schedules
    2. Checks if they should run based on their schedule
    3. Triggers execution tasks for pipelines that should run
    
    Returns:
        Dict with number of pipelines scheduled
    """
    logger.info("checking_scheduled_pipelines")
    
    db = SessionLocal()
    scheduled_count = 0
    
    try:
        # Find active pipelines
        # Note: For MVP, we use Celery Beat for scheduling via time triggers
        # Future: Add database-level schedule field for more complex scheduling
        pipelines = db.query(Pipeline).filter(
            Pipeline.is_active == True  # noqa: E712
        ).all()
        
        for pipeline in pipelines:
            try:
                # For now, just log active pipelines
                # The actual scheduling is handled by TimeTriggerAgent in each pipeline
                logger.debug(
                    "active_pipeline_found",
                    pipeline_id=str(pipeline.id),
                    name=pipeline.name
                )
                scheduled_count += 1
                    
            except Exception as e:
                logger.error(
                    "error_checking_pipeline",
                    pipeline_id=str(pipeline.id),
                    error=str(e)
                )
                continue
        
        logger.info("scheduled_pipelines_checked", count=scheduled_count)
        return {"scheduled": scheduled_count}
        
    finally:
        db.close()


# TODO: Remove this function - we use Celery Beat and TimeTriggerAgent for scheduling
# def _should_run_pipeline(pipeline: Pipeline) -> bool:
#     """
#     Determine if a pipeline should run based on its schedule.
#     
#     Args:
#         pipeline: Pipeline to check
#         
#     Returns:
#         True if should run, False otherwise
#     """
#     if not pipeline.schedule:
#         return False
#     
#     # Get last execution
#     db = SessionLocal()
#     try:
#         last_execution = db.query(Execution).filter(
#             Execution.pipeline_id == pipeline.id
#         ).order_by(Execution.created_at.desc()).first()
#         
#         # Parse schedule (simple cron-like format)
#         interval = pipeline.schedule.get("interval", "1h")
#         
#         # Convert interval to timedelta
#         interval_map = {
#             "1m": timedelta(minutes=1),
#             "5m": timedelta(minutes=5),
#             "15m": timedelta(minutes=15),
#             "30m": timedelta(minutes=30),
#             "1h": timedelta(hours=1),
#             "4h": timedelta(hours=4),
#             "1d": timedelta(days=1),
#         }
#         
#         interval_delta = interval_map.get(interval, timedelta(hours=1))
#         
#         # Check if enough time has passed
#         if last_execution:
#             time_since_last = datetime.utcnow() - last_execution.created_at
#             return time_since_last >= interval_delta
#         else:
#             # No previous execution, run now
#             return True
#             
#     finally:
#         db.close()


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
            Execution.status.in_([ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.SKIPPED])
        ).delete()
        
        db.commit()
        
        logger.info("old_executions_cleaned", deleted=deleted)
        return {"deleted": deleted}
        
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


@celery_app.task(name="app.orchestration.tasks.stop_execution")
def stop_execution(execution_id: str, user_id: str):
    """
    Stop a running execution.
    
    Args:
        execution_id: UUID of execution to stop
        user_id: UUID of user (for permission check)
        
    Returns:
        Dict with stop status
    """
    logger.info("stopping_execution", execution_id=execution_id)
    
    db = SessionLocal()
    
    try:
        execution = db.query(Execution).filter(Execution.id == UUID(execution_id)).first()
        
        if not execution:
            return {"status": "error", "message": "Execution not found"}
        
        if str(execution.user_id) != user_id:
            return {"status": "error", "message": "Permission denied"}
        
        if execution.status != ExecutionStatus.RUNNING:
            return {"status": "error", "message": "Execution not running"}
        
        # Mark as cancelled
        execution.status = ExecutionStatus.CANCELLED
        execution.end_time = datetime.utcnow()
        db.commit()
        
        logger.info("execution_stopped", execution_id=execution_id)
        return {"status": "stopped"}
        
    finally:
        db.close()

