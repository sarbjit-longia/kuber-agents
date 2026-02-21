"""
Celery Tasks for Pipeline Execution

Split into individual modules for maintainability:
- execute_pipeline: Main pipeline execution task
- check_scheduled_pipelines: Periodic pipeline scheduler
- reconciliation: Trade reconciliation (per-user + master scheduler)
- monitoring: Position monitoring check loop
- maintenance: Cleanup and budget reset tasks
- stop_execution: Stop a running execution

All tasks are re-exported here so existing imports continue to work:
    from app.orchestration.tasks import execute_pipeline
"""

from app.orchestration.tasks.execute_pipeline import execute_pipeline
from app.orchestration.tasks.check_scheduled_pipelines import check_scheduled_pipelines
from app.orchestration.tasks.reconciliation import (
    reconcile_user_trades,
    schedule_user_reconciliation,
)
from app.orchestration.tasks.monitoring import schedule_monitoring_check
from app.orchestration.tasks.maintenance import (
    cleanup_old_executions,
    cleanup_stale_running_executions,
    reset_daily_budgets,
)
from app.orchestration.tasks.stop_execution import stop_execution
from app.orchestration.tasks.approval import (
    resume_approved_execution,
    check_approval_timeout,
)

__all__ = [
    "execute_pipeline",
    "check_scheduled_pipelines",
    "reconcile_user_trades",
    "schedule_user_reconciliation",
    "schedule_monitoring_check",
    "cleanup_old_executions",
    "cleanup_stale_running_executions",
    "reset_daily_budgets",
    "stop_execution",
    "resume_approved_execution",
    "check_approval_timeout",
]
