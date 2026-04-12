"""
Celery task package with lazy exports.
"""

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
    "liquidate_pipeline_positions",
    "check_pipeline_schedules_active_hours",
    "launch_backtest_runtime",
    "run_backtest",
]


def __getattr__(name):
    if name == "execute_pipeline":
        from app.orchestration.tasks.execute_pipeline import execute_pipeline

        return execute_pipeline
    if name == "check_scheduled_pipelines":
        from app.orchestration.tasks.check_scheduled_pipelines import check_scheduled_pipelines

        return check_scheduled_pipelines
    if name in {"reconcile_user_trades", "schedule_user_reconciliation"}:
        from app.orchestration.tasks.reconciliation import (
            reconcile_user_trades,
            schedule_user_reconciliation,
        )

        return {
            "reconcile_user_trades": reconcile_user_trades,
            "schedule_user_reconciliation": schedule_user_reconciliation,
        }[name]
    if name == "schedule_monitoring_check":
        from app.orchestration.tasks.monitoring import schedule_monitoring_check

        return schedule_monitoring_check
    if name in {
        "cleanup_old_executions",
        "cleanup_stale_running_executions",
        "reset_daily_budgets",
    }:
        from app.orchestration.tasks.maintenance import (
            cleanup_old_executions,
            cleanup_stale_running_executions,
            reset_daily_budgets,
        )

        return {
            "cleanup_old_executions": cleanup_old_executions,
            "cleanup_stale_running_executions": cleanup_stale_running_executions,
            "reset_daily_budgets": reset_daily_budgets,
        }[name]
    if name == "stop_execution":
        from app.orchestration.tasks.stop_execution import stop_execution

        return stop_execution
    if name in {"resume_approved_execution", "check_approval_timeout"}:
        from app.orchestration.tasks.approval import (
            resume_approved_execution,
            check_approval_timeout,
        )

        return {
            "resume_approved_execution": resume_approved_execution,
            "check_approval_timeout": check_approval_timeout,
        }[name]
    if name == "liquidate_pipeline_positions":
        from app.orchestration.tasks.liquidate_positions import liquidate_pipeline_positions

        return liquidate_pipeline_positions
    if name == "check_pipeline_schedules_active_hours":
        from app.orchestration.tasks.check_pipeline_schedules_active_hours import (
            check_pipeline_schedules_active_hours,
        )

        return check_pipeline_schedules_active_hours
    if name == "launch_backtest_runtime":
        from app.orchestration.tasks.launch_backtest_runtime import launch_backtest_runtime

        return launch_backtest_runtime
    if name == "run_backtest":
        from app.orchestration.tasks.run_backtest import run_backtest

        return run_backtest
    raise AttributeError(name)
