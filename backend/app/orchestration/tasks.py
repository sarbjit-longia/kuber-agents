"""
Celery Tasks for Pipeline Execution

Defines asynchronous tasks for:
- Pipeline execution
- Scheduled pipeline checks
- Background maintenance
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

logger = structlog.get_logger()


def _send_position_closed_notification(
    execution: Execution,
    pnl: float = 0.0,
    pnl_percent: float = 0.0,
    exit_reason: str = "Position closed"
):
    """
    Send Telegram notification for position closure.
    
    Args:
        execution: Execution object
        pnl: Profit/Loss in dollars
        pnl_percent: P&L percentage
        exit_reason: Reason for exit
    """
    try:
        from app.services.telegram_notifier import telegram_notifier
        from app.models.user import User as UserModel
        from app.models.pipeline import Pipeline as PipelineModel
        
        if not execution.user_id or not execution.pipeline_id:
            return
        
        db = SessionLocal()
        try:
            # Get user
            user = db.query(UserModel).filter(UserModel.id == execution.user_id).first()
            if not user or not user.telegram_enabled:
                return
            
            if not user.telegram_bot_token or not user.telegram_chat_id:
                return
            
            # Get pipeline
            pipeline = db.query(PipelineModel).filter(PipelineModel.id == execution.pipeline_id).first()
            if not pipeline or not pipeline.notification_enabled:
                return
            
            # Check if position_closed is in notification events
            notification_events = pipeline.notification_events or []
            if "position_closed" not in notification_events:
                return
            
            # Send notification
            telegram_notifier.send_position_closed(
                bot_token=user.telegram_bot_token,
                chat_id=user.telegram_chat_id,
                symbol=execution.symbol,
                pnl=pnl,
                pnl_percent=pnl_percent,
                exit_reason=exit_reason,
                pipeline_name=pipeline.name
            )
            
            logger.info(
                "telegram_notification_sent",
                user_id=str(execution.user_id),
                pipeline_id=str(execution.pipeline_id),
                event="position_closed"
            )
            
        finally:
            db.close()
            
    except Exception as e:
        # Don't fail monitoring if notification fails
        logger.error(
            "telegram_notification_failed",
            error=str(e),
            execution_id=str(execution.id) if execution else None
        )


def _extract_broker_tool(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract broker tool configuration from pipeline config.
    
    Searches for broker tool in:
    1. config.broker_tool (direct)
    2. config.nodes[].config.tools[] (nested in agent configs)
    
    Args:
        config: Pipeline configuration dict
        
    Returns:
        Broker tool config dict or None
    """
    from app.services.brokers.factory import broker_factory
    
    if not config:
        return None
    
    # Check direct broker_tool field
    broker_tool = config.get("broker_tool")
    if broker_tool:
        return broker_tool
    
    # Search in agent node configs
    nodes = config.get("nodes", []) or []
    for node in nodes:
        cfg = node.get("config") or {}
        for tool in (cfg.get("tools") or []):
            if broker_factory.is_broker_tool(tool.get("tool_type")):
                return tool
    
    return None


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

            # Preflight 1: Check DATABASE for existing MONITORING/RUNNING execution for this pipeline.
            # This prevents duplicate runs regardless of broker availability.
            from app.models.scanner import Scanner
            from app.telemetry import pipeline_executions_counter

            existing_active = db.query(Execution).filter(
                Execution.pipeline_id == pipeline.id,
                Execution.status.in_([
                    ExecutionStatus.PENDING,
                    ExecutionStatus.RUNNING,
                    ExecutionStatus.MONITORING,
                    ExecutionStatus.COMMUNICATION_ERROR,
                ])
            ).first()

            if existing_active:
                logger.info(
                    "preflight_skipped_active_execution",
                    pipeline_id=pipeline_id,
                    existing_execution_id=str(existing_active.id),
                    existing_status=existing_active.status.value,
                    symbol=existing_active.symbol,
                )
                return {
                    "status": "skipped",
                    "reason": f"Pipeline already has active execution ({existing_active.status.value})",
                    "existing_execution_id": str(existing_active.id),
                }

            # Preflight 2: Check BROKER for open order/position for this symbol.
            # This avoids paying LLM costs for strategies that would be ignored anyway.
            # Extract broker tool from pipeline config
            broker_tool = _extract_broker_tool(pipeline.config)

            # Determine symbol for preflight check
            execution_symbol = symbol
            if not execution_symbol and pipeline.scanner_id:
                scanner = db.query(Scanner).filter(Scanner.id == pipeline.scanner_id).first()
                if scanner:
                    tickers = scanner.get_tickers()
                    execution_symbol = tickers[0] if tickers else None

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
        
        # Check broker for open positions and reconcile stale monitoring executions
        broker_positions_cache: Dict[str, Any] = {}  # Cache broker instances by account
        reconciled = 0
        rescheduled = 0

        # Grace period: don't reconcile executions that just entered monitoring
        # — the broker API may not yet reflect the newly placed order.
        grace_cutoff = datetime.utcnow() - timedelta(minutes=3)

        for execution in monitoring_executions:
            # Skip executions that entered monitoring very recently
            monitoring_start = execution.started_at or execution.created_at
            if monitoring_start and monitoring_start > grace_cutoff:
                logger.debug(
                    "reconciliation_skipped_grace_period",
                    execution_id=str(execution.id),
                    symbol=execution.symbol,
                    age_seconds=(datetime.utcnow() - monitoring_start).total_seconds(),
                )
                continue

            pipeline = db.query(Pipeline).filter(Pipeline.id == execution.pipeline_id).first()
            broker_tool = _extract_broker_tool(pipeline.config if pipeline else {}) if pipeline else None
            if not broker_tool:
                continue

            config = broker_tool.get("config", {}) or {}
            broker_key = f"{broker_tool.get('tool_type')}:{config.get('account_id')}:{config.get('account_type')}"

            if broker_key not in broker_positions_cache:
                try:
                    from app.services.brokers.factory import broker_factory
                    broker = broker_factory.from_tool_config(broker_tool)
                    broker_positions_cache[broker_key] = broker
                except Exception as e:
                    logger.error("reconciliation_broker_error", user_id=user_id, error=str(e))
                    continue

            broker = broker_positions_cache.get(broker_key)
            if not broker:
                continue

            if not execution.symbol:
                continue

            # Use broker's abstracted method to check if symbol is still active
            # This handles broker-specific symbol normalization internally
            try:
                has_active = broker.has_active_symbol(execution.symbol)
            except Exception as e:
                logger.error(
                    "reconciliation_symbol_check_failed",
                    execution_id=str(execution.id),
                    symbol=execution.symbol,
                    error=str(e)
                )
                continue

            if not has_active:
                # Position/order no longer exists on broker - reconcile execution
                execution.status = ExecutionStatus.COMPLETED
                execution.completed_at = datetime.utcnow()
                execution.execution_phase = "completed"
                execution.next_check_at = None
                
                existing_result = execution.result or {}
                existing_trade_exec = existing_result.get('trade_execution', {})
                exec_status = existing_trade_exec.get('status', '').lower() if existing_trade_exec else ''
                
                # Default to cancelled (order gone from broker without P&L)
                reconcile_outcome = 'cancelled'
                reconcile_pnl = 0.0
                reconcile_pnl_percent = 0.0
                exit_reason = 'Reconciled - no open broker position/order'
                close_time = datetime.utcnow().isoformat()
                
                # ------------------------------------------------------------------
                # LAYER 1: Check trade_execution status from pipeline state
                # ------------------------------------------------------------------
                if exec_status in ('filled', 'partially_filled'):
                    reconcile_outcome = 'executed'
                
                # ------------------------------------------------------------------
                # LAYER 2: Fetch realized P&L directly from broker (most reliable)
                # If we have a trade_id, ask the broker for the final trade details
                # including the realized P&L. This handles the case where bracket
                # orders (SL/TP) closed the position between monitoring checks.
                # ------------------------------------------------------------------
                trade_id = existing_trade_exec.get('trade_id') or existing_trade_exec.get('order_id')
                if trade_id:
                    try:
                        trade_details = broker.get_trade_details(str(trade_id))
                        if trade_details.get('found'):
                            broker_state = trade_details.get('state', '')
                            broker_realized_pl = float(trade_details.get('realized_pl', 0))
                            broker_unrealized_pl = float(trade_details.get('unrealized_pl', 0))
                            
                            if broker_state == 'closed' and broker_realized_pl != 0:
                                reconcile_outcome = 'executed'
                                reconcile_pnl = broker_realized_pl
                                # Calculate percent from entry price
                                entry_price = float(existing_trade_exec.get('filled_price', 0) or 0)
                                units = float(trade_details.get('units', 0) or 0)
                                cost_basis = entry_price * units if entry_price and units else 0
                                reconcile_pnl_percent = (
                                    (broker_realized_pl / cost_basis * 100)
                                    if cost_basis > 0 else 0.0
                                )
                                exit_reason = f"Position closed by bracket order (realized P&L from broker)"
                                close_time = trade_details.get('close_time') or close_time
                                
                                logger.info(
                                    "reconciliation_pnl_from_broker",
                                    execution_id=str(execution.id),
                                    symbol=execution.symbol,
                                    trade_id=trade_id,
                                    realized_pl=broker_realized_pl,
                                )
                            elif broker_state == 'open':
                                # Trade is still open on broker but has_active_symbol
                                # returned False — this is a data inconsistency.
                                # Don't reconcile; let the next check handle it.
                                logger.warning(
                                    "reconciliation_inconsistency_trade_still_open",
                                    execution_id=str(execution.id),
                                    trade_id=trade_id,
                                )
                                continue  # Skip this execution
                    except Exception as e:
                        logger.warning(
                            "reconciliation_trade_details_failed",
                            execution_id=str(execution.id),
                            trade_id=trade_id,
                            error=str(e),
                        )
                        # Continue with fallback layers below
                
                # ------------------------------------------------------------------
                # LAYER 3: Check trade_manager_agent reports for P&L evidence
                # The monitoring report may contain unrealized_pl from a position
                # that was filled and then closed by bracket orders.
                # ------------------------------------------------------------------
                if reconcile_outcome == 'cancelled' and execution.reports:
                    for report_key, report_val in execution.reports.items():
                        if 'trade_manager' in report_key and isinstance(report_val, dict):
                            report_data = report_val.get('data', {})
                            if isinstance(report_data, str):
                                try:
                                    import json as _json
                                    report_data = _json.loads(report_data)
                                except Exception:
                                    report_data = {}
                            if isinstance(report_data, dict):
                                unrealized_pl = report_data.get('unrealized_pl', 0)
                                if unrealized_pl and float(unrealized_pl) != 0:
                                    reconcile_outcome = 'executed'
                                    reconcile_pnl = float(unrealized_pl)
                                    reconcile_pnl_percent = float(report_data.get('pnl_percent', 0))
                                    exit_reason = report_data.get('reason', 'Position closed (P&L from last monitoring report)')
                                    close_time = report_data.get('closed_at') or close_time
                                    logger.info(
                                        "reconciliation_pnl_from_reports",
                                        execution_id=str(execution.id),
                                        symbol=execution.symbol,
                                        unrealized_pl=unrealized_pl,
                                    )
                                    break
                
                # ------------------------------------------------------------------
                # LAYER 4: Check final_pnl from existing result (set during monitoring)
                # ------------------------------------------------------------------
                if reconcile_outcome == 'cancelled':
                    final_pnl_val = existing_result.get('final_pnl')
                    if final_pnl_val and float(final_pnl_val) != 0:
                        reconcile_outcome = 'executed'
                        reconcile_pnl = float(final_pnl_val)
                        exit_reason = 'Position closed (P&L from pipeline result)'
                
                # ------------------------------------------------------------------
                # LAYER 5: Check trade_outcome already set by agent
                # ------------------------------------------------------------------
                if reconcile_outcome == 'cancelled':
                    existing_outcome = existing_result.get('trade_outcome', {})
                    if existing_outcome and existing_outcome.get('status') == 'executed':
                        existing_pnl = float(existing_outcome.get('pnl', 0))
                        if existing_pnl != 0:
                            reconcile_outcome = 'executed'
                            reconcile_pnl = existing_pnl
                            reconcile_pnl_percent = float(existing_outcome.get('pnl_percent', 0))
                            exit_reason = existing_outcome.get('exit_reason', 'Position closed')
                            close_time = existing_outcome.get('closed_at') or close_time
                
                # ------------------------------------------------------------------
                # Persist trade_outcome
                # ------------------------------------------------------------------
                # Set trade_outcome if not already set, or update if existing one has 0 P&L
                existing_outcome = existing_result.get('trade_outcome', {})
                existing_outcome_pnl = float(existing_outcome.get('pnl', 0)) if existing_outcome else 0
                
                if not existing_outcome or (existing_outcome_pnl == 0 and reconcile_pnl != 0) or reconcile_outcome != 'cancelled':
                    existing_result['trade_outcome'] = {
                        'status': reconcile_outcome,
                        'pnl': reconcile_pnl,
                        'pnl_percent': reconcile_pnl_percent,
                        'exit_reason': exit_reason,
                        'closed_at': close_time,
                    }
                
                if reconcile_pnl != 0:
                    existing_result['final_pnl'] = reconcile_pnl
                
                execution.result = existing_result | {
                    "reconciled": True,
                    "reconcile_reason": exit_reason,
                }
                execution.error_message = None
                reconciled += 1
                
                logger.info(
                    "execution_reconciled",
                    execution_id=str(execution.id),
                    symbol=execution.symbol,
                    outcome=reconcile_outcome,
                    pnl=reconcile_pnl,
                    trade_id=trade_id,
                )
            else:
                # Broker still has active position/order — check if monitoring chain is broken
                # If next_check_at is in the past (or None), the Celery monitoring task chain
                # was lost (e.g., worker restart). Re-schedule it.
                orphan_threshold = datetime.utcnow() - timedelta(minutes=2)
                is_orphaned = (
                    execution.next_check_at is None
                    or execution.next_check_at < orphan_threshold
                )
                if is_orphaned:
                    logger.warning(
                        "monitoring_chain_broken_rescheduling",
                        execution_id=str(execution.id),
                        symbol=execution.symbol,
                        next_check_at=str(execution.next_check_at),
                    )
                    # Update next_check_at so we don't re-schedule on every reconciliation cycle
                    execution.next_check_at = datetime.utcnow() + timedelta(seconds=15)
                    execution.version += 1
                    db.commit()
                    # Re-trigger the monitoring chain
                    schedule_monitoring_check.apply_async(
                        args=[str(execution.id)],
                        countdown=10,  # Start in 10 seconds
                    )
                    rescheduled += 1

        if reconciled:
            db.commit()
            logger.warning(
                "monitoring_reconciled_no_position",
                user_id=user_id,
                reconciled=reconciled,
            )

        logger.info(
            "user_reconciliation_completed",
            user_id=user_id,
            monitoring_count=len(monitoring_executions),
            monitoring_symbols=list(monitoring_symbols),
            communication_errors=len(comm_error_executions),
            reconciled=reconciled,
            rescheduled=rescheduled,
        )
        
        return {
            "status": "completed",
            "user_id": user_id,
            "monitoring_executions": len(monitoring_executions),
            "monitoring_symbols": list(monitoring_symbols),
            "communication_errors": len(comm_error_executions),
            "reconciled": reconciled,
            "rescheduled": rescheduled,
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
            Execution.status.in_([ExecutionStatus.COMPLETED, ExecutionStatus.FAILED])
        ).delete()
        
        db.commit()
        
        logger.info("old_executions_cleaned", deleted=deleted)
        return {"deleted": deleted}
        
    finally:
        db.close()


@celery_app.task(name="app.orchestration.tasks.cleanup_stale_running_executions")
def cleanup_stale_running_executions(max_age_minutes: int = 20):
    """
    Fail stale RUNNING/PENDING executions so one orphaned ticker doesn't block the pipeline.

    Why this exists:
    - If a worker restarts or a task is killed mid-flight, the DB can be left with executions
      stuck in RUNNING. The trigger-dispatcher treats any RUNNING execution as a pipeline-wide lock,
      so a single orphan can stop the entire pipeline from triggering on other tickers.

    Args:
        max_age_minutes: Age threshold to consider an in-flight execution stale.
    """
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)

        stale = (
            db.query(Execution)
            .filter(
                Execution.status.in_([ExecutionStatus.RUNNING, ExecutionStatus.PENDING]),
                # Prefer started_at when present; fall back to created_at
                ((Execution.started_at.isnot(None) & (Execution.started_at < cutoff)))
                | ((Execution.started_at.is_(None)) & (Execution.created_at < cutoff))
            )
            .all()
        )

        if not stale:
            return {"stale_failed": 0}

        for ex in stale:
            ex.status = ExecutionStatus.FAILED
            ex.completed_at = datetime.utcnow()
            msg = (
                f"Stale in-flight execution auto-failed after {max_age_minutes}m "
                f"(status={ex.status}, phase={getattr(ex, 'execution_phase', None)})."
            )
            ex.error_message = msg
            ex.result = (ex.result or {}) | {"error": msg, "stale_auto_failed": True}

        db.commit()
        logger.warning("stale_executions_failed", count=len(stale), max_age_minutes=max_age_minutes)
        return {"stale_failed": len(stale)}
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
        execution.completed_at = datetime.utcnow()
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
    1. Uses a fresh DB connection each time (configurable polling: 15s default, 5m fallback)
    2. Checks if position still exists via broker API
    3. Evaluates emergency exit conditions
    4. Closes position if needed or schedules next check
    5. Uses optimistic locking to prevent concurrent update conflicts
    
    Args:
        execution_id: UUID of execution in MONITORING status
        
    Returns:
        Dict with monitoring status
    """
    logger.info("monitoring_check_started", execution_id=execution_id)
    
    # Fresh DB connection for each check
    db = SessionLocal()
    
    try:
        # Convert execution_id to UUID if it's a string (handle both string and UUID inputs)
        if isinstance(execution_id, str):
            exec_uuid = UUID(execution_id)
        else:
            exec_uuid = execution_id
        
        # Load execution with version for optimistic locking
        execution = db.query(Execution).filter(Execution.id == exec_uuid).first()
        
        if not execution:
            logger.warning("execution_not_found", execution_id=execution_id)
            return {"status": "not_found"}
        
        # ⚠️ FIX #3: Add max monitoring duration (24 hours) to prevent infinite loops
        MAX_MONITORING_HOURS = 24
        if execution.started_at:
            monitoring_duration = (datetime.utcnow() - execution.started_at).total_seconds() / 3600
            if monitoring_duration > MAX_MONITORING_HOURS:
                logger.error(
                    "monitoring_timeout_exceeded",
                    execution_id=execution_id,
                    duration_hours=monitoring_duration
                )
                execution.status = ExecutionStatus.FAILED
                execution.completed_at = datetime.utcnow()
                execution.execution_phase = "completed"
                execution.next_check_at = None
                execution.error_message = f"Monitoring timeout: exceeded {MAX_MONITORING_HOURS}h maximum duration"
                execution.version += 1
                db.commit()
                return {"status": "timeout", "duration_hours": monitoring_duration}
        
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
        
        # ⚠️ FIX #1: Use optimistic locking to prevent concurrent update conflicts
        original_version = execution.version
        
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
        
        # Increment version for optimistic locking
        execution.version += 1
        
        # Check if communication error occurred (API failure)
        if updated_state.communication_error:
            # ⚠️ FIX #3: Limit max communication error retries (60 attempts = 1 hour at 1min intervals)
            MAX_COMM_ERROR_RETRIES = 60
            error_count = updated_state.trade_execution.api_error_count if updated_state.trade_execution else 0
            
            if error_count >= MAX_COMM_ERROR_RETRIES:
                # Max retries exceeded - mark as FAILED and require manual intervention
                execution.status = ExecutionStatus.FAILED
                execution.completed_at = datetime.utcnow()
                execution.execution_phase = "completed"
                execution.next_check_at = None
                execution.error_message = f"Communication error: exceeded {MAX_COMM_ERROR_RETRIES} retry attempts. Manual intervention required."
                execution.version += 1
                
                logger.error(
                    "monitoring_max_retries_exceeded",
                    execution_id=execution_id,
                    error_count=error_count,
                    last_error=updated_state.communication_error_message
                )
                
                try:
                    db.commit()
                except Exception as commit_error:
                    logger.error("failed_to_commit_max_retries", error=str(commit_error), exc_info=True)
                    db.rollback()
                
                return {
                    "status": "failed",
                    "reason": "max_retries_exceeded",
                    "error_count": error_count
                }
            
            # Still under retry limit - mark as COMMUNICATION_ERROR and schedule retry
            execution.status = ExecutionStatus.COMMUNICATION_ERROR
            execution.next_check_at = datetime.utcnow() + timedelta(minutes=1)  # Retry in 1 minute
            
            logger.error(
                "monitoring_communication_error",
                execution_id=execution_id,
                error_count=error_count,
                last_error=updated_state.communication_error_message,
                retries_remaining=MAX_COMM_ERROR_RETRIES - error_count
            )
            
            try:
                db.commit()
            except Exception as commit_error:
                logger.error("commit_failed_on_comm_error", error=str(commit_error), exc_info=True)
                db.rollback()
                # Try recovery with new session
                db.close()
                db2 = SessionLocal()
                try:
                    ex2 = db2.query(Execution).filter(Execution.id == UUID(execution_id)).first()
                    if ex2 and ex2.version == original_version:
                        ex2.status = ExecutionStatus.COMMUNICATION_ERROR
                        ex2.next_check_at = datetime.utcnow() + timedelta(minutes=1)
                        ex2.version += 1
                        db2.commit()
                finally:
                    db2.close()
            
            # Schedule retry in 1 minute
            schedule_monitoring_check.apply_async(args=[str(execution.id)], countdown=60)
            
            return {
                "status": "communication_error",
                "error": updated_state.communication_error_message,
                "retry_in": "1 minute",
                "error_count": error_count,
                "retries_remaining": MAX_COMM_ERROR_RETRIES - error_count
            }
        
        # Check if monitoring should complete
        elif updated_state.should_complete:
            # Execution status reflects pipeline lifecycle: always COMPLETED when monitoring ends normally.
            # Trade-specific outcome (executed, accepted, cancelled, failed, etc.) is stored separately
            # in execution.result['trade_outcome'] and displayed as "Trade Outcome" on the UI.
            outcome_status = updated_state.trade_outcome.status if updated_state.trade_outcome else "executed"
            
            execution.status = ExecutionStatus.COMPLETED
            execution.execution_phase = "completed"
            
            execution.completed_at = datetime.utcnow()
            execution.next_check_at = None
            execution.version += 1
            
            # Extract P&L from trade_outcome if available
            pnl = 0.0
            pnl_percent = 0.0
            exit_reason = "Position closed"
            exit_price = None
            entry_price = None
            
            if updated_state.trade_outcome:
                pnl = updated_state.trade_outcome.pnl or 0.0
                pnl_percent = updated_state.trade_outcome.pnl_percent or 0.0
                exit_reason = updated_state.trade_outcome.exit_reason or "Position closed"
                exit_price = updated_state.trade_outcome.exit_price
                entry_price = updated_state.trade_outcome.entry_price
            
            # If there's actual P&L, the trade was filled — override 'accepted'/'pending' to 'executed'
            if pnl != 0 and outcome_status in ('accepted', 'pending'):
                outcome_status = 'executed'
            
            # Store P&L in execution result for UI display
            if not execution.result:
                execution.result = {}
            
            # Store in nested trade_outcome object (with corrected status)
            execution.result['trade_outcome'] = {
                'status': outcome_status,
                'pnl': pnl,
                'pnl_percent': pnl_percent,
                'exit_reason': exit_reason,
                'exit_price': exit_price,
                'entry_price': entry_price,
                'closed_at': datetime.utcnow().isoformat()
            }
            
            # ALSO store at top level for frontend compatibility
            execution.result['final_pnl'] = pnl
            execution.result['final_pnl_percent'] = pnl_percent
            
            logger.info(
                "monitoring_completed",
                execution_id=execution_id,
                outcome_status=outcome_status,
                execution_status=execution.status.value,
                pnl=pnl,
                pnl_percent=pnl_percent,
            )
            
            try:
                db.commit()
            except Exception as commit_error:
                logger.error("commit_failed_on_complete", error=str(commit_error), exc_info=True)
                db.rollback()
                # Try recovery with new session
                db.close()
                db2 = SessionLocal()
                try:
                    ex2 = db2.query(Execution).filter(Execution.id == UUID(execution_id)).first()
                    if ex2 and ex2.version == original_version:
                        ex2.status = ExecutionStatus.COMPLETED
                        ex2.completed_at = datetime.utcnow()
                        ex2.execution_phase = "completed"
                        ex2.next_check_at = None
                        ex2.version += 1
                        db2.commit()
                finally:
                    db2.close()
            
            # 📱 Send position closed notification
            _send_position_closed_notification(
                execution=execution,
                pnl=pnl,
                pnl_percent=pnl_percent,
                exit_reason=exit_reason
            )
            
            return {"status": "completed", "pnl": pnl, "pnl_percent": pnl_percent}
        
        else:
            # Schedule next check
            # Interval priority: execution.monitor_interval_minutes (from DB) → state.monitor_interval_minutes → 1 min fallback
            # Trade Manager sets 0.25 min (15 seconds) for active monitoring
            # Use 'is not None' checks instead of 'or' to avoid treating 0.25 as falsy
            if execution.monitor_interval_minutes is not None and execution.monitor_interval_minutes > 0:
                interval = execution.monitor_interval_minutes
            elif updated_state.monitor_interval_minutes is not None and updated_state.monitor_interval_minutes > 0:
                interval = updated_state.monitor_interval_minutes
            else:
                interval = 1  # Default fallback: 1 minute
            execution.next_check_at = datetime.utcnow() + timedelta(minutes=interval)
            execution.version += 1
            
            try:
                db.commit()
            except Exception as commit_error:
                logger.error("commit_failed_on_continue", error=str(commit_error), exc_info=True)
                db.rollback()
                # Try recovery with new session
                db.close()
                db2 = SessionLocal()
                try:
                    ex2 = db2.query(Execution).filter(Execution.id == UUID(execution_id)).first()
                    if ex2 and ex2.version == original_version:
                        ex2.next_check_at = datetime.utcnow() + timedelta(minutes=interval)
                        ex2.version += 1
                        db2.commit()
                finally:
                    db2.close()
            
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

