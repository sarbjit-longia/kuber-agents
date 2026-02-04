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
from typing import Optional, Dict, Any

from app.orchestration.celery_app import celery_app
from app.database import SessionLocal
from app.models.pipeline import Pipeline
from app.models.execution import Execution, ExecutionStatus
from app.models.cost_tracking import UserBudget
from app.orchestration.executor import PipelineExecutor
from app.agents.base import TriggerNotMetException
from app.agents.base import AgentError, InsufficientDataError, AgentProcessingError

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
            # Priority: 1. symbol override, 2. scanner tickers, 3. config symbol
            execution_symbol = symbol
            if not execution_symbol and executor.scanner_tickers:
                execution_symbol = executor.scanner_tickers[0]
                logger.info("using_scanner_ticker_in_task", 
                           execution_id=str(executor.execution_id),
                           symbol=execution_symbol, 
                           total_tickers=len(executor.scanner_tickers))
            if not execution_symbol:
                execution_symbol = pipeline.config.get("symbol")
            
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
        
        # Find active PERIODIC pipelines
        pipelines = db.query(Pipeline).filter(
            Pipeline.is_active == True,  # noqa: E712
            Pipeline.trigger_mode == TriggerMode.PERIODIC
        ).all()
        
        logger.info("periodic_pipelines_found", count=len(pipelines))
        
        for pipeline in pipelines:
            try:
                # Check if pipeline has any running executions
                running_exec = db.query(Execution).filter(
                    Execution.pipeline_id == pipeline.id,
                    Execution.status.in_([ExecutionStatus.PENDING, ExecutionStatus.RUNNING])
                ).first()
                
                if running_exec:
                    logger.debug(
                        "pipeline_already_running",
                        pipeline_id=str(pipeline.id),
                        execution_id=str(running_exec.id)
                    )
                    continue
                
                # Trigger pipeline execution
                # For MVP: Execute all active periodic pipelines every minute
                # Future: Add interval configuration (e.g., every 5min, 15min, 1h)
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


@celery_app.task(name="app.orchestration.tasks.reconcile_user_trades", bind=True, max_retries=3)
def reconcile_user_trades(self, user_id: str):
    """
    Reconcile trades for a specific user.
    
    Checks if user's open positions on broker match MONITORING executions in database.
    Runs independently per user for isolation and scalability.
    
    Args:
        user_id: UUID of user to reconcile
        
    Returns:
        Dict with reconciliation results for this user
    """
    logger.info("user_reconciliation_started", user_id=user_id)
    
    db = SessionLocal()
    
    try:
        from app.models import User, Execution, Pipeline
        from uuid import UUID
        
        # Get user
        user = db.query(User).filter(User.id == UUID(user_id)).first()
        if not user:
            logger.warning("user_not_found", user_id=user_id)
            return {"status": "user_not_found", "user_id": user_id}
        
        # Get all MONITORING executions for this user
        monitoring_executions = db.query(Execution).filter(
            Execution.user_id == UUID(user_id),
            Execution.status == ExecutionStatus.MONITORING
        ).all()
        
        monitoring_symbols = {exec.symbol for exec in monitoring_executions}
        
        # Get COMMUNICATION_ERROR executions (broker API issues)
        comm_error_executions = db.query(Execution).filter(
            Execution.user_id == UUID(user_id),
            Execution.status == ExecutionStatus.COMMUNICATION_ERROR
        ).all()
        
        logger.info(
            "user_reconciliation_completed",
            user_id=user_id,
            monitoring_count=len(monitoring_executions),
            monitoring_symbols=list(monitoring_symbols),
            communication_errors=len(comm_error_executions)
        )
        
        # TODO: Check broker for open positions (requires broker credentials architecture)
        # For now, just log monitoring state
        
        return {
            "status": "completed",
            "user_id": user_id,
            "monitoring_executions": len(monitoring_executions),
            "monitoring_symbols": list(monitoring_symbols),
            "communication_errors": len(comm_error_executions)
        }
        
    except Exception as e:
        logger.error("user_reconciliation_failed", user_id=user_id, error=str(e))
        
        # Retry on transient failures
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60)  # Retry after 1 minute
        
        return {"status": "error", "user_id": user_id, "error": str(e)}
        
    finally:
        db.close()


@celery_app.task(name="app.orchestration.tasks.schedule_user_reconciliation")
def schedule_user_reconciliation():
    """
    Master reconciliation scheduler.
    
    Spawns individual reconciliation tasks for each user with active trades.
    Runs every 1 minute via Celery Beat.
    
    This approach provides:
    - User isolation: One user's broker issues don't affect others
    - Scalability: Tasks distributed across workers
    - Parallel execution: All users checked simultaneously
    
    Returns:
        Dict with number of users scheduled
    """
    logger.info("master_reconciliation_started")
    
    db = SessionLocal()
    
    try:
        from app.models import User, Execution
        
        # Find users with active trades (MONITORING or COMMUNICATION_ERROR)
        users_with_active_trades = db.query(User).join(Execution).filter(
            Execution.status.in_([ExecutionStatus.MONITORING, ExecutionStatus.COMMUNICATION_ERROR])
        ).distinct().all()
        
        scheduled_count = 0
        
        for user in users_with_active_trades:
            # Spawn per-user reconciliation task
            reconcile_user_trades.apply_async(args=[str(user.id)])
            scheduled_count += 1
        
        logger.info(
            "master_reconciliation_completed",
            users_scheduled=scheduled_count,
            total_users=db.query(User).count()
        )
        
        return {
            "status": "completed",
            "users_scheduled": scheduled_count
        }
        
    except Exception as e:
        logger.error("master_reconciliation_failed", error=str(e))
        return {"status": "error", "error": str(e)}
        
    finally:
        db.close()


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


@celery_app.task(name="app.orchestration.tasks.schedule_monitoring_check", bind=True, max_retries=5)
def schedule_monitoring_check(self, execution_id: str):
    """
    Periodic monitoring check for open positions (Trade Manager Agent).
    
    This task:
    1. Uses a fresh DB connection each time (5-min polling)
    2. Checks if position still exists via broker API
    3. Evaluates emergency exit conditions
    4. Closes position if needed or schedules next check
    
    Args:
        execution_id: UUID of execution in MONITORING status
        
    Returns:
        Dict with monitoring status
    """
    logger.info("monitoring_check_started", execution_id=execution_id)
    
    # Fresh DB connection for each check
    db = SessionLocal()
    
    try:
        # Load execution
        execution = db.query(Execution).filter(Execution.id == UUID(execution_id)).first()
        
        if not execution:
            logger.warning("execution_not_found", execution_id=execution_id)
            return {"status": "not_found"}
        
        if execution.status != ExecutionStatus.MONITORING:
            logger.info("execution_no_longer_monitoring", execution_id=execution_id, status=execution.status.value)
            return {"status": "not_monitoring"}
        
        # Load pipeline
        pipeline = execution.pipeline
        if not pipeline:
            logger.error("pipeline_not_found", execution_id=execution_id)
            return {"status": "error", "message": "Pipeline not found"}
        
        # Deserialize current state from execution result
        state_dict = execution.result or {}
        from app.schemas.pipeline_state import PipelineState
        
        # Reconstruct state object
        state = PipelineState(
            pipeline_id=pipeline.id,
            execution_id=execution.id,
            user_id=execution.user_id,
            symbol=execution.symbol or "UNKNOWN",
            mode=execution.mode,
            execution_phase="monitoring"  # Force monitoring phase
        )
        
        # Restore state fields from result
        if "strategy" in state_dict and state_dict["strategy"]:
            from app.schemas.pipeline_state import StrategyResult
            state.strategy = StrategyResult(**state_dict["strategy"])
        
        if "risk_assessment" in state_dict and state_dict["risk_assessment"]:
            from app.schemas.pipeline_state import RiskAssessment
            state.risk_assessment = RiskAssessment(**state_dict["risk_assessment"])
        
        if "trade_execution" in state_dict and state_dict["trade_execution"]:
            from app.schemas.pipeline_state import TradeExecution
            state.trade_execution = TradeExecution(**state_dict["trade_execution"])
        
        # **CRITICAL**: Restore existing agent reports from database to preserve them
        # Otherwise, bias/strategy/risk reports will be lost when monitoring updates
        if execution.reports:
            from app.schemas.pipeline_state import AgentReport
            for agent_id, report_data in execution.reports.items():
                if isinstance(report_data, dict):
                    state.agent_reports[agent_id] = report_data
                else:
                    state.agent_reports[agent_id] = report_data
        
        # Find Trade Manager agent in pipeline
        trade_manager_node = None
        for node in pipeline.config.get("nodes", []):
            if node.get("agent_type") == "trade_manager_agent":
                trade_manager_node = node
                break
        
        if not trade_manager_node:
            logger.error("trade_manager_not_found", execution_id=execution_id)
            return {"status": "error", "message": "Trade Manager agent not found"}
        
        # Create Trade Manager agent instance
        from app.agents import get_registry
        registry = get_registry()
        
        agent = registry.create_agent(
            agent_type="trade_manager_agent",
            agent_id=trade_manager_node["id"],
            config=trade_manager_node.get("config", {})
        )
        
        # Execute monitoring logic
        updated_state = agent.process(state)
        
        # Update execution result
        def serialize_model(model):
            if model is None:
                return None
            data = model.dict()
            for key, value in data.items():
                if isinstance(value, datetime):
                    data[key] = value.isoformat()
            return data
        
        execution.result = {
            **(execution.result or {}),
            "strategy": serialize_model(updated_state.strategy),
            "risk_assessment": serialize_model(updated_state.risk_assessment),
            "trade_execution": serialize_model(updated_state.trade_execution),
            "errors": updated_state.errors,
            "warnings": updated_state.warnings,
        }
        
        # Update logs and reports
        from sqlalchemy.orm.attributes import flag_modified
        execution.logs = _serialize_logs(updated_state.execution_log)
        execution.reports = _serialize_reports(updated_state.agent_reports)
        flag_modified(execution, "logs")
        flag_modified(execution, "reports")
        flag_modified(execution, "result")
        
        # Check if communication error occurred (API failure)
        if updated_state.communication_error:
            execution.status = ExecutionStatus.COMMUNICATION_ERROR
            execution.next_check_at = datetime.utcnow() + timedelta(minutes=1)  # Retry in 1 minute
            
            logger.error(
                "monitoring_communication_error",
                execution_id=execution_id,
                error_count=updated_state.trade_execution.api_error_count if updated_state.trade_execution else 0,
                last_error=updated_state.communication_error_message
            )
            
            db.commit()
            
            # Schedule retry in 1 minute
            schedule_monitoring_check.apply_async(args=[str(execution.id)], countdown=60)
            
            return {
                "status": "communication_error",
                "error": updated_state.communication_error_message,
                "retry_in": "1 minute"
            }
        
        # Check if monitoring should complete
        elif updated_state.should_complete:
            execution.status = ExecutionStatus.COMPLETED
            execution.completed_at = datetime.utcnow()
            execution.execution_phase = "completed"
            execution.next_check_at = None
            
            logger.info("monitoring_completed", execution_id=execution_id)
            
            db.commit()
            return {"status": "completed"}
        
        else:
            # Schedule next check
            # Use interval from execution (database) instead of state for flexibility
            interval = execution.monitor_interval_minutes or updated_state.monitor_interval_minutes or 1
            execution.next_check_at = datetime.utcnow() + timedelta(minutes=interval)
            
            db.commit()
            
            # Schedule next task
            schedule_monitoring_check.apply_async(
                args=[execution_id],
                countdown=interval * 60  # Convert to seconds
            )
            
            logger.info(
                "monitoring_continuing",
                execution_id=execution_id,
                next_check_minutes=interval,
                next_check_at=execution.next_check_at.isoformat()
            )
            
            return {"status": "monitoring", "next_check_minutes": interval}
    
    except Exception as exc:
        logger.error("monitoring_check_failed", execution_id=execution_id, error=str(exc), exc_info=True)
        
        # Retry with exponential backoff (1 min, 2 min, 4 min, 8 min, 16 min)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    
    finally:
        db.close()  # Always clean up connection


def _serialize_logs(logs):
    """Helper to serialize execution logs."""
    return [
        {
            "timestamp": log.get("timestamp").isoformat() if isinstance(log.get("timestamp"), datetime) else log.get("timestamp"),
            "message": log.get("message"),
            "level": log.get("level", "info"),
            "agent_id": log.get("agent_id")
        }
        for log in logs
    ]


def _serialize_reports(reports):
    """Helper to serialize agent reports."""
    from datetime import datetime
    
    def serialize_value(value):
        """Recursively serialize values, converting datetime to ISO string."""
        if isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, dict):
            return {k: serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [serialize_value(item) for item in value]
        else:
            return value
    
    serialized = {}
    for agent_id, report in reports.items():
        if hasattr(report, 'dict'):
            report_dict = report.dict()
        else:
            report_dict = report
        
        # Recursively serialize all values in the report
        serialized[agent_id] = serialize_value(report_dict)
    
    return serialized

