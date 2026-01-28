"""
System Metrics Collector

Collects system-level metrics for monitoring:
- Active pipelines
- Total users
- Execution statistics
- Queue sizes

These metrics are exposed via Prometheus for Grafana visualization.
"""
import structlog
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.pipeline import Pipeline
from app.models.user import User
from app.models.execution import Execution, ExecutionStatus

logger = structlog.get_logger()


class SystemMetricsCollector:
    """Collects system-level metrics from the database."""
    
    def __init__(self):
        self.metrics = {}
    
    def collect_all_metrics(self) -> dict:
        """
        Collect all system metrics.
        
        Returns:
            Dictionary of metric names to values
        """
        db = SessionLocal()
        try:
            self.metrics = {
                'active_pipelines': self._get_active_pipelines_count(db),
                'total_pipelines': self._get_total_pipelines_count(db),
                'signal_pipelines': self._get_signal_pipelines_count(db),
                'periodic_pipelines': self._get_periodic_pipelines_count(db),
                'active_users': self._get_active_users_count(db),
                'total_users': self._get_total_users_count(db),
                'executions_today': self._get_executions_today_count(db),
                'executions_running': self._get_running_executions_count(db),
                'executions_pending': self._get_pending_executions_count(db),
                'executions_total': self._get_total_executions_count(db),
                'executions_completed': self._get_completed_executions_count(db),
                'executions_failed': self._get_failed_executions_count(db),
                'success_rate_24h': self._get_success_rate_24h(db),
            }
            
            logger.debug("system_metrics_collected", metrics=self.metrics)
            return self.metrics
            
        except Exception as e:
            logger.error("error_collecting_system_metrics", error=str(e), exc_info=True)
            return {}
        finally:
            db.close()
    
    def _get_active_pipelines_count(self, db: Session) -> int:
        """Count of active pipelines."""
        result = db.execute(
            select(func.count(Pipeline.id)).where(Pipeline.is_active == True)
        )
        return result.scalar() or 0
    
    def _get_total_pipelines_count(self, db: Session) -> int:
        """Total count of all pipelines."""
        result = db.execute(select(func.count(Pipeline.id)))
        return result.scalar() or 0
    
    def _get_signal_pipelines_count(self, db: Session) -> int:
        """Count of signal-based pipelines."""
        from app.models.pipeline import TriggerMode
        result = db.execute(
            select(func.count(Pipeline.id)).where(
                and_(
                    Pipeline.is_active == True,
                    Pipeline.trigger_mode == TriggerMode.SIGNAL
                )
            )
        )
        return result.scalar() or 0
    
    def _get_periodic_pipelines_count(self, db: Session) -> int:
        """Count of periodic pipelines."""
        from app.models.pipeline import TriggerMode
        result = db.execute(
            select(func.count(Pipeline.id)).where(
                and_(
                    Pipeline.is_active == True,
                    Pipeline.trigger_mode == TriggerMode.PERIODIC
                )
            )
        )
        return result.scalar() or 0
    
    def _get_active_users_count(self, db: Session) -> int:
        """Count of users with at least one active pipeline."""
        result = db.execute(
            select(func.count(func.distinct(Pipeline.user_id))).where(
                Pipeline.is_active == True
            )
        )
        return result.scalar() or 0
    
    def _get_total_users_count(self, db: Session) -> int:
        """Total count of all users."""
        result = db.execute(select(func.count(User.id)))
        return result.scalar() or 0
    
    def _get_executions_today_count(self, db: Session) -> int:
        """Count of executions started today."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = db.execute(
            select(func.count(Execution.id)).where(
                Execution.created_at >= today_start
            )
        )
        return result.scalar() or 0
    
    def _get_running_executions_count(self, db: Session) -> int:
        """Count of currently running executions."""
        result = db.execute(
            select(func.count(Execution.id)).where(
                Execution.status == ExecutionStatus.RUNNING
            )
        )
        return result.scalar() or 0
    
    def _get_pending_executions_count(self, db: Session) -> int:
        """Count of pending executions."""
        result = db.execute(
            select(func.count(Execution.id)).where(
                Execution.status == ExecutionStatus.PENDING
            )
        )
        return result.scalar() or 0
    
    def _get_total_executions_count(self, db: Session) -> int:
        """Total count of all executions."""
        result = db.execute(select(func.count(Execution.id)))
        return result.scalar() or 0
    
    def _get_completed_executions_count(self, db: Session) -> int:
        """Count of completed executions."""
        result = db.execute(
            select(func.count(Execution.id)).where(
                Execution.status == ExecutionStatus.COMPLETED
            )
        )
        return result.scalar() or 0
    
    def _get_failed_executions_count(self, db: Session) -> int:
        """Count of failed executions."""
        result = db.execute(
            select(func.count(Execution.id)).where(
                Execution.status == ExecutionStatus.FAILED
            )
        )
        return result.scalar() or 0
    
    def _get_success_rate_24h(self, db: Session) -> float:
        """Success rate for executions in the last 24 hours."""
        yesterday = datetime.utcnow() - timedelta(hours=24)
        
        # Get total completed/failed executions in last 24h
        total_result = db.execute(
            select(func.count(Execution.id)).where(
                and_(
                    Execution.completed_at >= yesterday,
                    Execution.status.in_([ExecutionStatus.COMPLETED, ExecutionStatus.FAILED])
                )
            )
        )
        total = total_result.scalar() or 0
        
        if total == 0:
            return 0.0
        
        # Get successful executions in last 24h
        success_result = db.execute(
            select(func.count(Execution.id)).where(
                and_(
                    Execution.completed_at >= yesterday,
                    Execution.status == ExecutionStatus.COMPLETED
                )
            )
        )
        success = success_result.scalar() or 0
        
        return (success / total) * 100.0


# Global instance
system_metrics_collector = SystemMetricsCollector()

