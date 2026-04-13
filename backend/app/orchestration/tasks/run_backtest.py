"""
Celery task entrypoint for parity backtests.
"""
import asyncio
from datetime import datetime
from uuid import UUID

import structlog

from app.api.v1.backtests import (
    _build_report_sections,
    _build_report_summary,
    _execution_belongs_to_backtest,
    _generate_optional_llm_analysis,
    _load_cached_report,
    _store_cached_report,
)
from app.backtesting.snapshot import hydrate_pipeline_from_snapshot
from app.backtesting.events import create_backtest_event
from app.database import SessionLocal
from app.models.backtest_run import BacktestRun, BacktestRunStatus
from app.models.backtest_event import BacktestEvent
from app.models.execution import Execution
from app.models.pipeline import Pipeline
from app.orchestration.celery_app import celery_app
from app.backtesting.orchestrator import BacktestOrchestrator

logger = structlog.get_logger()


def _hydrate_pipeline_snapshot(run: BacktestRun):
    snapshot = (run.config or {}).get("pipeline_snapshot") or {}
    if not snapshot:
        return None

    snapshot["runtime_snapshot"] = (run.config or {}).get("runtime_snapshot") or {}
    pipeline = hydrate_pipeline_from_snapshot(
        snapshot,
        fallback_pipeline_id=run.pipeline_id,
        fallback_user_id=run.user_id,
    )
    pipeline.id = UUID(str(pipeline.id)) if pipeline.id else run.pipeline_id
    pipeline.user_id = UUID(str(pipeline.user_id)) if pipeline.user_id else run.user_id
    pipeline.scanner_id = UUID(str(pipeline.scanner_id)) if pipeline.scanner_id else None
    pipeline.name = pipeline.name or run.pipeline_name
    return pipeline


def execute_backtest_run(backtest_run_id: str):
    db = SessionLocal()
    try:
        run = db.query(BacktestRun).filter(BacktestRun.id == UUID(backtest_run_id)).first()
        if not run:
            raise ValueError(f"Backtest run {backtest_run_id} not found")
        pipeline = _hydrate_pipeline_snapshot(run)
        if not pipeline:
            pipeline = db.query(Pipeline).filter(Pipeline.id == run.pipeline_id).first()
            if not pipeline:
                raise ValueError(f"Pipeline {run.pipeline_id} not found")

        orchestrator = BacktestOrchestrator(run, pipeline, db)
        result = orchestrator.run_backtest()

        db.refresh(run)
        if run.status == BacktestRunStatus.COMPLETED and not _load_cached_report(run):
            executions = (
                db.query(Execution)
                .filter(
                    Execution.user_id == run.user_id,
                    Execution.mode == "backtest",
                    _execution_belongs_to_backtest(run.id),
                )
                .order_by(Execution.created_at.desc())
                .all()
            )
            events = (
                db.query(BacktestEvent)
                .filter(BacktestEvent.run_id == run.id, BacktestEvent.user_id == run.user_id)
                .order_by(BacktestEvent.created_at.asc())
                .all()
            )
            summary = _build_report_summary(run, executions, events)
            sections = _build_report_sections(run, executions, events)
            llm_analysis = asyncio.run(_generate_optional_llm_analysis(summary, sections))
            _store_cached_report(
                run,
                {
                    "generated_at": datetime.utcnow().isoformat(),
                    "summary": summary,
                    "sections": sections,
                    "llm_analysis": llm_analysis,
                },
            )
            db.commit()

        return result
    except Exception as exc:
        logger.exception("run_backtest_failed", backtest_run_id=backtest_run_id)
        run = db.query(BacktestRun).filter(BacktestRun.id == UUID(backtest_run_id)).first()
        if run and run.status != BacktestRunStatus.CANCELLED:
            run.status = BacktestRunStatus.FAILED
            run.failure_reason = str(exc)
            run.completed_at = datetime.utcnow()
            db.add(
                create_backtest_event(
                    run=run,
                    event_type="run_failed",
                    title="Backtest failed",
                    message=str(exc),
                    level="error",
                )
            )
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task(name="app.orchestration.tasks.run_backtest", bind=True, time_limit=60 * 60 * 6)
def run_backtest(self, backtest_run_id: str):
    return execute_backtest_run(backtest_run_id)
