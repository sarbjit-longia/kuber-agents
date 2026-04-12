"""
Celery task entrypoint for launching a backtest runtime.
"""
from datetime import datetime
from uuid import UUID

import structlog

from app.backtesting.runtime_launcher import get_backtest_runtime_launcher
from app.database import SessionLocal
from app.models.backtest_run import BacktestRun, BacktestRunStatus
from app.orchestration.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="app.orchestration.tasks.launch_backtest_runtime", bind=True, max_retries=1)
def launch_backtest_runtime(self, backtest_run_id: str):
    db = SessionLocal()
    try:
        run = db.query(BacktestRun).filter(BacktestRun.id == UUID(backtest_run_id)).first()
        if not run:
            raise ValueError(f"Backtest run {backtest_run_id} not found")
        if run.status == BacktestRunStatus.CANCELLED:
            logger.info("launch_backtest_runtime_skipped_cancelled_run", backtest_run_id=backtest_run_id)
            return {
                "backtest_run_id": backtest_run_id,
                "launcher_mode": "skipped",
                "accepted": False,
            }

        launcher = get_backtest_runtime_launcher()
        launch_result = launcher.launch(backtest_run_id)

        run_config = dict(run.config or {})
        runtime_config = dict(run_config.get("runtime") or {})
        runtime_config.update(
            {
                "launcher_mode": launch_result.launcher_mode,
                "launch_accepted": launch_result.accepted,
                "launch_requested_at": datetime.utcnow().isoformat(),
                "launch_details": launch_result.details or {},
            }
        )
        run_config["runtime"] = runtime_config
        run.config = run_config
        db.commit()

        return {
            "backtest_run_id": backtest_run_id,
            "launcher_mode": launch_result.launcher_mode,
            "accepted": launch_result.accepted,
        }
    except Exception as exc:
        logger.exception("launch_backtest_runtime_failed", backtest_run_id=backtest_run_id)
        run = db.query(BacktestRun).filter(BacktestRun.id == UUID(backtest_run_id)).first()
        if run:
            run.status = BacktestRunStatus.FAILED
            run.failure_reason = f"Runtime launch failed: {exc}"
            run.completed_at = datetime.utcnow()
            db.commit()
        raise
    finally:
        db.close()
