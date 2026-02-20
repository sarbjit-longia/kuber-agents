"""
Celery Task: Stop Execution

Task to stop a running execution by marking it as cancelled.
"""
import structlog
from uuid import UUID
from datetime import datetime

from app.orchestration.celery_app import celery_app
from app.database import SessionLocal
from app.models.execution import Execution, ExecutionStatus

logger = structlog.get_logger()


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
        execution.completed_at = datetime.utcnow()
        db.commit()
        
        logger.info("execution_stopped", execution_id=execution_id)
        return {"status": "stopped"}
        
    finally:
        db.close()
