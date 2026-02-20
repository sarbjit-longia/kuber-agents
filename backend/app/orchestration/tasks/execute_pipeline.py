"""
Celery Task: Execute Pipeline

Main task for running a trading pipeline asynchronously.
Handles preflight checks, broker validation, and pipeline execution.
"""
import structlog
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from app.orchestration.celery_app import celery_app
from app.database import SessionLocal
from app.models.pipeline import Pipeline
from app.models.execution import Execution, ExecutionStatus
from app.models.cost_tracking import UserBudget
from app.orchestration.executor import PipelineExecutor
from app.agents.base import TriggerNotMetException
from app.agents.base import AgentError, InsufficientDataError, AgentProcessingError
from billiard.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded

from app.orchestration.tasks._helpers import _extract_broker_tool

logger = structlog.get_logger()


@celery_app.task(name="app.orchestration.tasks.execute_pipeline", bind=True, max_retries=3)
def execute_pipeline(
    self,
    pipeline_id: str,
    user_id: str,
    mode: str = "paper",
    execution_id: Optional[str] = None,
    signal_context: Optional[Dict[str, Any]] = None,
    symbol: Optional[str] = None
):
    """
    Execute a trading pipeline asynchronously.
    
    This is the main Celery task for running pipelines in the background.
    
    Args:
        pipeline_id: UUID of pipeline to execute
        user_id: UUID of user
        mode: Execution mode ("live", "paper", "simulation", "validation")
        execution_id: Optional pre-created execution ID
        signal_context: Optional signal data that triggered this execution
        symbol: Optional symbol override (for scanner-based pipelines)
        
    Returns:
        Dict with execution results
    """
    logger.info(
        "celery_task_started",
        task_id=self.request.id,
        pipeline_id=pipeline_id,
        user_id=user_id,
        mode=mode,
        symbol=symbol,
        has_signal_context=bool(signal_context)
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

            # Preflight 1: Check DATABASE for existing active execution for the SAME SYMBOL
            # in this pipeline.  We intentionally do NOT block the entire pipeline when a
            # different ticker is already running — only duplicate (pipeline + ticker)
            # pairs are prevented.
            from app.models.scanner import Scanner
            from app.telemetry import pipeline_executions_counter

            # Determine the symbol we're about to execute so we can scope the check.
            execution_symbol_for_preflight = symbol
            if not execution_symbol_for_preflight and pipeline.scanner_id:
                scanner = db.query(Scanner).filter(Scanner.id == pipeline.scanner_id).first()
                if scanner:
                    tickers = scanner.get_tickers()
                    execution_symbol_for_preflight = tickers[0] if tickers else None

            preflight_query = db.query(Execution).filter(
                Execution.pipeline_id == pipeline.id,
                Execution.status.in_([
                    ExecutionStatus.PENDING,
                    ExecutionStatus.RUNNING,
                    ExecutionStatus.MONITORING,
                    ExecutionStatus.COMMUNICATION_ERROR,
                ])
            )
            # When we know the symbol, only block if the SAME symbol is active.
            # If the symbol is unknown (manual run without symbol), fall back to
            # pipeline-level guard to be safe.
            if execution_symbol_for_preflight:
                preflight_query = preflight_query.filter(
                    Execution.symbol == execution_symbol_for_preflight
                )

            existing_active = preflight_query.first()

            if existing_active:
                logger.info(
                    "preflight_skipped_active_execution",
                    pipeline_id=pipeline_id,
                    existing_execution_id=str(existing_active.id),
                    existing_status=existing_active.status.value,
                    existing_symbol=existing_active.symbol,
                    requested_symbol=execution_symbol_for_preflight,
                )
                return {
                    "status": "skipped",
                    "reason": f"Pipeline already has active execution for {existing_active.symbol} ({existing_active.status.value})",
                    "existing_execution_id": str(existing_active.id),
                }

            # Preflight 2: Check BROKER for open order/position for this symbol.
            # This avoids paying LLM costs for strategies that would be ignored anyway.
            # Extract broker tool from pipeline config
            broker_tool = _extract_broker_tool(pipeline.config)

            # Reuse symbol resolved in Preflight 1 (avoids duplicate scanner query)
            execution_symbol = execution_symbol_for_preflight

            # Preflight 2a: Cross-pipeline symbol guard — prevent duplicate MONITORING
            # for the same user+symbol across ALL pipelines (not just this one).
            if execution_symbol:
                existing_symbol_monitoring = db.query(Execution).filter(
                    Execution.user_id == UUID(user_id),
                    Execution.symbol == execution_symbol,
                    Execution.status.in_([
                        ExecutionStatus.MONITORING,
                        ExecutionStatus.COMMUNICATION_ERROR,
                    ])
                ).first()

                if existing_symbol_monitoring:
                    logger.info(
                        "preflight_skipped_symbol_already_monitored",
                        pipeline_id=pipeline_id,
                        symbol=execution_symbol,
                        existing_execution_id=str(existing_symbol_monitoring.id),
                        existing_pipeline_id=str(existing_symbol_monitoring.pipeline_id),
                    )
                    return {
                        "status": "skipped",
                        "reason": f"Symbol {execution_symbol} already being monitored (execution {existing_symbol_monitoring.id})",
                        "existing_execution_id": str(existing_symbol_monitoring.id),
                    }

            if broker_tool and execution_symbol:
                try:
                    from app.services.brokers.factory import broker_factory
                    broker = broker_factory.from_tool_config(broker_tool)
                    # Use broker's abstracted method to check for active symbols
                    # This handles broker-specific symbol normalization internally
                    has_active = broker.has_active_symbol(execution_symbol)

                    if has_active:
                        # Create or update execution record as COMPLETED (skipped).
                        execution = db.query(Execution).filter(
                            Execution.id == UUID(execution_id)
                        ).first() if execution_id else None

                        now = datetime.utcnow()
                        if not execution:
                            execution = Execution(
                                id=UUID(execution_id) if execution_id else uuid4(),
                                pipeline_id=pipeline.id,
                                user_id=UUID(user_id),
                                status=ExecutionStatus.COMPLETED,
                                mode=mode,
                                symbol=execution_symbol,
                                started_at=now,
                                completed_at=now,
                                execution_phase="completed",
                                result={
                                    "skipped": True,
                                    "reason": "Duplicate open order/position exists on broker",
                                    "symbol": execution_symbol,
                                },
                                logs=[{
                                    "timestamp": now.isoformat(),
                                    "agent_id": "preflight",
                                    "level": "info",
                                    "message": f"Preflight skip: existing broker order/position for {execution_symbol}",
                                }],
                                agent_states=[],
                            )
                            db.add(execution)
                        else:
                            execution.status = ExecutionStatus.COMPLETED
                            execution.completed_at = now
                            execution.execution_phase = "completed"
                            execution.result = {
                                "skipped": True,
                                "reason": "Duplicate open order/position exists on broker",
                                "symbol": execution_symbol,
                            }
                            execution.logs = [{
                                "timestamp": now.isoformat(),
                                "agent_id": "preflight",
                                "level": "info",
                                "message": f"Preflight skip: existing broker order/position for {execution_symbol}",
                            }]
                            execution.agent_states = []

                        db.commit()
                        pipeline_executions_counter.labels(
                            status="skipped",
                            pipeline_id=str(pipeline.id)
                        ).inc()
                        logger.info(
                            "preflight_skipped_existing_broker_order_or_position",
                            pipeline_id=pipeline_id,
                            symbol=execution_symbol,
                        )
                        return {
                            "status": "skipped",
                            "execution_id": str(execution.id),
                            "reason": "Duplicate open order/position exists on broker",
                        }
                except Exception as e:
                    # If broker check fails, continue with normal execution (do not block pipeline).
                    logger.error(
                        "preflight_broker_check_failed",
                        pipeline_id=pipeline_id,
                        symbol=execution_symbol,
                        error=str(e),
                    )
            
            # Create executor with signal context and database session
            executor = PipelineExecutor(
                pipeline=pipeline,
                user_id=UUID(user_id),
                mode=mode,
                execution_id=UUID(execution_id) if execution_id else None,
                signal_context=signal_context,
                symbol_override=symbol,  # Pass symbol override for scanner-based pipelines
                db_session=db  # Pass database session to load scanner
            )
            
            # Execute pipeline synchronously for Celery
            # Get or create execution record
            execution = db.query(Execution).filter(Execution.id == executor.execution_id).first()
            
            # Determine symbol for execution record
            # Symbol should always come from symbol parameter (passed by trigger-dispatcher)
            execution_symbol = symbol
            if not execution_symbol and executor.scanner_tickers:
                # Fallback for manual testing
                execution_symbol = executor.scanner_tickers[0]
                logger.warning("using_scanner_ticker_fallback_in_task", 
                           execution_id=str(executor.execution_id),
                           symbol=execution_symbol)
            
            if not execution:
                # Create new execution record
                execution = Execution(
                    id=executor.execution_id,
                    pipeline_id=pipeline.id,
                    user_id=UUID(user_id),
                    status=ExecutionStatus.RUNNING,
                    mode=mode,
                    symbol=execution_symbol,
                    started_at=datetime.utcnow()
                )
                db.add(execution)
                db.commit()
            else:
                # Update existing execution
                execution.status = ExecutionStatus.RUNNING
                execution.symbol = execution_symbol  # Update symbol if provided
                # Clear prior completion/error fields if this execution is being re-used
                execution.completed_at = None
                execution.error_message = None
                execution.result = None
                if not execution.started_at:
                    execution.started_at = datetime.utcnow()
                db.commit()
            
            try:
                # Execute pipeline with real-time DB updates using sync session
                execution = executor.execute_with_sync_db_tracking(db, execution)
                
            except TriggerNotMetException as e:
                # Ensure session is usable after any flush/commit errors inside executor tracking
                try:
                    db.rollback()
                except Exception:  # pragma: no cover
                    pass
                # Re-load execution in a fresh transaction
                execution = db.query(Execution).filter(Execution.id == executor.execution_id).first() or execution
                # Trigger not met - mark as COMPLETED (successfully determined not to execute)
                execution.status = ExecutionStatus.COMPLETED
                execution.completed_at = datetime.utcnow()
                execution.result = {"trigger_met": False, "reason": str(e)}
                try:
                    db.commit()
                except Exception:
                    # Last resort: update status using a new session so we never leave RUNNING stuck
                    db.close()
                    db2 = SessionLocal()
                    try:
                        ex2 = db2.query(Execution).filter(Execution.id == executor.execution_id).first()
                        if ex2:
                            ex2.status = ExecutionStatus.COMPLETED
                            ex2.completed_at = datetime.utcnow()
                            ex2.result = {"trigger_met": False, "reason": str(e)}
                            db2.commit()
                    finally:
                        db2.close()
                
            except (SoftTimeLimitExceeded, TimeLimitExceeded) as e:
                # Celery time limit exceeded. Persist FAILED to avoid leaving executions stuck in RUNNING.
                try:
                    db.rollback()
                except Exception:  # pragma: no cover
                    pass
                execution = db.query(Execution).filter(Execution.id == executor.execution_id).first() or execution
                execution.status = ExecutionStatus.FAILED
                execution.completed_at = datetime.utcnow()
                execution.error_message = f"Celery time limit exceeded: {str(e)}"
                execution.result = {"error": execution.error_message}
                try:
                    db.commit()
                except Exception:
                    # Last resort: update status using a new session so we never leave RUNNING stuck
                    db.close()
                    db2 = SessionLocal()
                    try:
                        ex2 = db2.query(Execution).filter(Execution.id == executor.execution_id).first()
                        if ex2:
                            ex2.status = ExecutionStatus.FAILED
                            ex2.completed_at = datetime.utcnow()
                            ex2.error_message = f"Celery time limit exceeded: {str(e)}"
                            ex2.result = {"error": ex2.error_message}
                            db2.commit()
                    finally:
                        db2.close()
                return {"status": "failed", "execution_id": str(execution.id), "error": execution.error_message}

            except Exception as e:
                # Critical: if executor DB tracking hit a flush error, this Session may be in
                # "pending rollback" state; rollback before attempting to persist FAILED.
                try:
                    db.rollback()
                except Exception:  # pragma: no cover
                    pass
                # Re-load execution in a fresh transaction
                execution = db.query(Execution).filter(Execution.id == executor.execution_id).first() or execution

                execution.status = ExecutionStatus.FAILED
                execution.completed_at = datetime.utcnow()
                execution.result = {"error": str(e)}
                execution.error_message = str(e)
                try:
                    db.commit()
                except Exception:
                    # Last resort: update status using a new session so we never leave RUNNING stuck
                    db.close()
                    db2 = SessionLocal()
                    try:
                        ex2 = db2.query(Execution).filter(Execution.id == executor.execution_id).first()
                        if ex2:
                            ex2.status = ExecutionStatus.FAILED
                            ex2.completed_at = datetime.utcnow()
                            ex2.result = {"error": str(e)}
                            ex2.error_message = str(e)
                            db2.commit()
                    finally:
                        db2.close()
                # Do NOT retry deterministic agent failures; they should surface to the UI as-is.
                # Retrying here has been causing "stuck RUNNING" executions and confusing states.
                if isinstance(e, (InsufficientDataError, AgentProcessingError, AgentError, ValueError, PermissionError)):
                    return {"status": "failed", "execution_id": str(execution.id), "error": str(e)}
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
        # Important: we intentionally do NOT auto-retry here. With `acks_late=True` tasks will
        # be re-queued if the worker dies; for logical errors we want a single failure and a clear
        # error surfaced in the execution record.
        logger.exception("celery_task_failed", task_id=self.request.id)
        raise
