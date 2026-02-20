"""
Celery Task: Check Scheduled Pipelines

Periodic task that checks for pipelines due for execution based on their schedule.
Runs every minute via Celery Beat.
"""
import structlog
from datetime import datetime, timedelta

from app.orchestration.celery_app import celery_app
from app.database import SessionLocal
from app.models.pipeline import Pipeline
from app.models.execution import Execution, ExecutionStatus

logger = structlog.get_logger()


@celery_app.task(name="app.orchestration.tasks.check_scheduled_pipelines")
def check_scheduled_pipelines():
    """
    Check for pipelines that should be executed based on their schedule.
    
    This task runs every minute (configured in beat_schedule) and:
    1. Finds active periodic pipelines
    2. Checks if they should run based on their schedule
    3. Triggers execution tasks for pipelines that should run
    
    Returns:
        Dict with number of pipelines scheduled
    """
    logger.info("checking_scheduled_pipelines")
    
    db = SessionLocal()
    scheduled_count = 0
    triggered_count = 0
    
    try:
        from app.models.pipeline import TriggerMode
        from app.orchestration.tasks.execute_pipeline import execute_pipeline
        
        # Find active PERIODIC pipelines
        pipelines = db.query(Pipeline).filter(
            Pipeline.is_active == True,  # noqa: E712
            Pipeline.trigger_mode == TriggerMode.PERIODIC
        ).all()
        
        logger.info("periodic_pipelines_found", count=len(pipelines))
        
        for pipeline in pipelines:
            try:
                # Check if pipeline has any running or actively monitoring executions.
                # Include MONITORING so we don't launch a new execution while a limit
                # order is still pending on the broker from a previous run.
                running_exec = db.query(Execution).filter(
                    Execution.pipeline_id == pipeline.id,
                    Execution.status.in_([
                        ExecutionStatus.PENDING,
                        ExecutionStatus.RUNNING,
                        ExecutionStatus.MONITORING,
                    ])
                ).first()
                
                if running_exec:
                    logger.debug(
                        "pipeline_already_running",
                        pipeline_id=str(pipeline.id),
                        execution_id=str(running_exec.id)
                    )
                    continue
                
                # ✅ Rate limiting: Check when last execution completed
                # Default interval: 5 minutes (configurable per pipeline in future)
                last_completed = db.query(Execution).filter(
                    Execution.pipeline_id == pipeline.id,
                    Execution.status.in_([ExecutionStatus.COMPLETED, ExecutionStatus.FAILED])
                ).order_by(Execution.completed_at.desc()).first()
                
                if last_completed and last_completed.completed_at:
                    # Get interval from pipeline config, default to 5 minutes
                    interval_minutes = pipeline.config.get("interval_minutes", 5) if pipeline.config else 5
                    time_since_last = datetime.utcnow() - last_completed.completed_at
                    
                    if time_since_last < timedelta(minutes=interval_minutes):
                        logger.debug(
                            "periodic_pipeline_skipped_rate_limit",
                            pipeline_id=str(pipeline.id),
                            interval_minutes=interval_minutes,
                            time_since_last_seconds=time_since_last.total_seconds()
                        )
                        continue
                
                # Trigger pipeline execution
                logger.info(
                    "triggering_periodic_pipeline",
                    pipeline_id=str(pipeline.id),
                    name=pipeline.name
                )
                
                execute_pipeline.delay(
                    pipeline_id=str(pipeline.id),
                    user_id=str(pipeline.user_id),
                    mode="paper"  # Default to paper for periodic executions
                )
                
                triggered_count += 1
                scheduled_count += 1
                    
            except Exception as e:
                logger.error(
                    "error_checking_pipeline",
                    pipeline_id=str(pipeline.id),
                    error=str(e),
                    exc_info=True
                )
                continue
        
        logger.info(
            "scheduled_pipelines_checked",
            total_found=len(pipelines),
            triggered=triggered_count
        )
        return {"scheduled": scheduled_count, "triggered": triggered_count}
        
    finally:
        db.close()
