"""
Execution API Endpoints

Provides endpoints for:
- Starting pipeline executions
- Getting execution status
- Listing executions
- Stopping running executions
- Generating executive reports
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, case, not_
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pathlib import Path
import structlog

from app.database import get_db
from app.models.user import User
from app.models.execution import Execution, ExecutionStatus
from app.models.pipeline import Pipeline
from app.schemas.execution import ExecutionInDB, ExecutionCreate, ExecutionSummary, ExecutionStats
from app.api.dependencies import get_current_user
from app.orchestration.tasks import execute_pipeline, stop_execution
from app.orchestration.validator import PipelineValidator
from app.services.executive_report_generator import executive_report_generator
from app.services.trade_analysis_generator import trade_analysis_generator
from app.services.langfuse_service import get_langfuse_client

logger = structlog.get_logger()

router = APIRouter(prefix="/executions", tags=["Executions"])


@router.post("/", response_model=ExecutionInDB, status_code=status.HTTP_202_ACCEPTED)
async def start_execution(
    execution_data: ExecutionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> ExecutionInDB:
    """
    Start a new pipeline execution.
    
    This triggers an asynchronous Celery task to execute the pipeline.
    The execution will run in the background.
    
    Args:
        execution_data: Execution configuration
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Execution record with PENDING status
    """
    # Verify pipeline exists and belongs to user
    result = await db.execute(
        select(Pipeline).where(Pipeline.id == execution_data.pipeline_id)
    )
    pipeline = result.scalar_one_or_none()
    
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found"
        )
    
    if pipeline.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to execute this pipeline"
        )
    
    # Validate pipeline configuration
    validator = PipelineValidator()
    is_valid, validation_errors = validator.validate(
        pipeline.config,
        trigger_mode=str(pipeline.trigger_mode) if pipeline.trigger_mode else "periodic",
        scanner_id=str(pipeline.scanner_id) if pipeline.scanner_id else None
    )
    
    if not is_valid:
        import structlog
        logger = structlog.get_logger()
        logger.error("Pipeline validation failed", 
                     pipeline_id=str(pipeline.id),
                     errors=validation_errors)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Pipeline validation failed",
                "errors": validation_errors
            }
        )
    
    # Note: Manual executions can run on inactive pipelines
    # Active status only matters for scheduled/automated runs
    
    # Extract symbol from pipeline config or use from execution_data
    symbol = None
    if hasattr(execution_data, 'symbol') and execution_data.symbol:
        symbol = execution_data.symbol
    elif pipeline.config and isinstance(pipeline.config, dict):
        symbol = pipeline.config.get('symbol')
    
    # Create execution record with all metadata
    execution = Execution(
        pipeline_id=execution_data.pipeline_id,
        user_id=current_user.id,
        status=ExecutionStatus.PENDING,
        mode=execution_data.mode or "paper",
        symbol=symbol,
        started_at=datetime.utcnow()  # Mark as started immediately
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    
    # Trigger async Celery task with timeout to prevent blocking UI
    try:
        execute_pipeline.apply_async(
            kwargs={
                "pipeline_id": str(execution.pipeline_id),
                "user_id": str(current_user.id),
                "mode": execution_data.mode or "paper",
                "execution_id": str(execution.id)
            },
            countdown=0,  # Execute immediately
            expires=600,  # Task expires after 10 minutes if not picked up
        )
    except Exception as e:
        import structlog
        logger = structlog.get_logger()
        logger.error("Failed to enqueue task", execution_id=str(execution.id), error=str(e))
        # Don't fail the request - execution is created, task will be retried
    
    return execution


@router.get("/stats", response_model=ExecutionStats)
async def get_execution_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> ExecutionStats:
    """
    Get execution statistics for the current user.
    
    Args:
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Execution statistics
    """
    from sqlalchemy import func
    
    # Get all executions for the user
    result = await db.execute(
        select(Execution).where(Execution.user_id == current_user.id)
    )
    executions = result.scalars().all()
    
    total_executions = len(executions)
    running_executions = len([e for e in executions if e.status == ExecutionStatus.RUNNING])
    completed_executions = len([e for e in executions if e.status == ExecutionStatus.COMPLETED])
    failed_executions = len([e for e in executions if e.status == ExecutionStatus.FAILED])
    
    total_cost = sum(e.cost for e in executions)
    
    # Calculate average duration for completed executions
    completed_with_duration = [
        e for e in executions 
        if e.status == ExecutionStatus.COMPLETED and e.started_at and e.completed_at
    ]
    
    if completed_with_duration:
        durations = [
            (e.completed_at - e.started_at).total_seconds() 
            for e in completed_with_duration
        ]
        avg_duration_seconds = sum(durations) / len(durations)
    else:
        avg_duration_seconds = 0.0
    
    # Calculate success rate
    finished_executions = completed_executions + failed_executions
    success_rate = completed_executions / finished_executions if finished_executions > 0 else 0.0
    
    return ExecutionStats(
        total_executions=total_executions,
        running_executions=running_executions,
        completed_executions=completed_executions,
        failed_executions=failed_executions,
        total_cost=total_cost,
        avg_duration_seconds=avg_duration_seconds,
        success_rate=success_rate
    )


@router.get("/{execution_id}", response_model=dict)
async def get_execution(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Get execution details by ID.
    
    Args:
        execution_id: Execution UUID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Execution details with pipeline name
    """
    from app.models.scanner import Scanner
    
    result = await db.execute(
        select(
            Execution,
            Pipeline.name,
            Pipeline.trigger_mode,
            Pipeline.config,
            Scanner.name.label('scanner_name')
        )
        .join(Pipeline, Execution.pipeline_id == Pipeline.id)
        .outerjoin(Scanner, Pipeline.scanner_id == Scanner.id)
        .where(Execution.id == execution_id)
    )
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )

    execution, pipeline_name, trigger_mode, pipeline_config, scanner_name = row
    
    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this execution"
        )
    
    # Convert execution to dict and add pipeline_name, trigger_mode, scanner_name
    execution_dict = {
        "id": str(execution.id),
        "pipeline_id": str(execution.pipeline_id),
        "pipeline_name": pipeline_name,  # Add pipeline name
        "user_id": str(execution.user_id),
        "status": execution.status.value,
        "mode": execution.mode,
        "symbol": execution.symbol,
        "trigger_mode": trigger_mode.value if trigger_mode else None,
        "scanner_name": scanner_name,
        "result": execution.result,
        "error_message": execution.error_message,
        "cost": execution.cost,
        "logs": execution.logs or [],
        "agent_states": execution.agent_states or [],
        "reports": execution.reports or {},
        "cost_breakdown": execution.cost_breakdown or {},
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        "created_at": execution.created_at.isoformat() if execution.created_at else None,
        # Add monitoring fields
        "execution_phase": execution.execution_phase,
        "next_check_at": execution.next_check_at.isoformat() + 'Z' if execution.next_check_at else None,  # Add Z for UTC
        "monitor_interval_minutes": execution.monitor_interval_minutes,
        "pipeline_config": pipeline_config,
    }

    return execution_dict


@router.get("/", response_model=dict)
async def list_executions(
    pipeline_id: Optional[UUID] = Query(None, description="Filter by pipeline ID"),
    status_filter: Optional[ExecutionStatus] = Query(None, alias="status", description="Filter by status"),
    trade_outcome: Optional[str] = Query(None, description="Filter by trade outcome (e.g. 'executed', 'skipped')"),
    limit: int = Query(50, ge=1, le=500, description="Number of executions to return"),
    offset: int = Query(0, ge=0, description="Number of executions to skip"),
    include_active: bool = Query(True, description="Always include all active executions"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    List executions for the current user with summary information.
    
    Active executions (MONITORING, RUNNING, PENDING, COMMUNICATION_ERROR,
    NEEDS_RECONCILIATION) are always returned in full — they are never
    affected by limit/offset pagination.  Historical executions are paginated
    normally.  The response includes a ``total`` count so the frontend can
    build proper pagination controls.
    
    Args:
        pipeline_id: Optional pipeline ID filter
        status_filter: Optional status filter
        limit: Maximum number of *historical* results per page
        offset: Number of historical results to skip
        include_active: When True (default) all active executions are prepended
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Dict with ``executions`` list, ``total`` count, and ``active_count``
    """
    from app.models.scanner import Scanner
    
    active_statuses = [
        ExecutionStatus.MONITORING,
        ExecutionStatus.RUNNING,
        ExecutionStatus.PENDING,
        ExecutionStatus.COMMUNICATION_ERROR,
        ExecutionStatus.NEEDS_RECONCILIATION,
        ExecutionStatus.AWAITING_APPROVAL,
    ]
    
    base_filters = [Execution.user_id == current_user.id]
    if pipeline_id:
        base_filters.append(Execution.pipeline_id == pipeline_id)
    
    base_join = (
        select(
            Execution,
            Pipeline.name,
            Pipeline.trigger_mode,
            Scanner.name.label('scanner_name'),
        )
        .join(Pipeline, Execution.pipeline_id == Pipeline.id)
        .outerjoin(Scanner, Pipeline.scanner_id == Scanner.id)
        .where(*base_filters)
    )
    
    # ── 1. Always fetch ALL active executions ──────────────────────────
    active_rows = []
    active_ids: set = set()
    if include_active and not status_filter:
        active_query = (
            base_join
            .where(Execution.status.in_(active_statuses))
            .order_by(desc(Execution.created_at))
        )
        active_result = await db.execute(active_query)
        active_rows = active_result.all()
        active_ids = {row[0].id for row in active_rows}
    
    # ── 2. Fetch paginated historical executions ──────────────────────
    hist_query = base_join
    if status_filter:
        hist_query = hist_query.where(Execution.status == status_filter)
    elif include_active:
        # Exclude active ones (already fetched above)
        hist_query = hist_query.where(not_(Execution.status.in_(active_statuses)))

    # Filter by trade_outcome (JSONB: result->'trade_outcome'->>'status')
    if trade_outcome:
        hist_query = hist_query.where(
            Execution.result['trade_outcome']['status'].as_string() == trade_outcome
        )

    # Get total count for pagination
    count_query = (
        select(func.count())
        .select_from(Execution)
        .where(*base_filters)
    )
    if status_filter:
        count_query = count_query.where(Execution.status == status_filter)
    elif include_active:
        count_query = count_query.where(not_(Execution.status.in_(active_statuses)))
    if trade_outcome:
        count_query = count_query.where(
            Execution.result['trade_outcome']['status'].as_string() == trade_outcome
        )
    
    total_result = await db.execute(count_query)
    total_historical = total_result.scalar() or 0
    
    hist_query = hist_query.order_by(desc(Execution.created_at)).limit(limit).offset(offset)
    hist_result = await db.execute(hist_query)
    hist_rows = hist_result.all()
    
    # ── 3. Merge: active first, then historical ───────────────────────
    all_rows = list(active_rows) + [r for r in hist_rows if r[0].id not in active_ids]
    
    summaries = []
    for execution, pipeline_name, trigger_mode, scanner_name in all_rows:
        duration_seconds = None
        if execution.started_at and execution.completed_at:
            duration_seconds = (execution.completed_at - execution.started_at).total_seconds()
        
        agent_states = execution.agent_states or []
        agent_count = len(agent_states)
        agents_completed = len([a for a in agent_states if a.get('status') == 'completed'])
        
        # Extract strategy result for quick view
        strategy_action = None
        strategy_confidence = None
        trade_outcome = None
        
        if execution.result and isinstance(execution.result, dict):
            strategy = execution.result.get('strategy')
            if strategy:
                strategy_action = strategy.get('action')
                strategy_confidence = strategy.get('confidence')
            
            # Determine trade outcome
            trade_execution = execution.result.get('trade_execution')
            risk_assessment = execution.result.get('risk_assessment')
            trade_outcome_obj = execution.result.get('trade_outcome')  # From monitoring completion
            
            # Step 1: Check if monitoring completed (has final trade_outcome from agent)
            if trade_outcome_obj and isinstance(trade_outcome_obj, dict):
                raw_status = trade_outcome_obj.get('status', 'unknown')
                # Normalize: merge 'accepted' into 'pending' (both = order at broker, not filled)
                trade_outcome = 'pending' if raw_status == 'accepted' else raw_status
            
            # Step 2: Check trade_execution status from broker
            if not trade_outcome and trade_execution:
                exec_status = trade_execution.get('status', '').lower()
                if exec_status in ['filled', 'partially_filled']:
                    trade_outcome = 'executed'
                elif exec_status in ['accepted', 'pending']:
                    trade_outcome = 'pending'  # Order at broker, waiting to fill
                elif exec_status == 'rejected':
                    trade_outcome = 'rejected'
                elif exec_status == 'cancelled':
                    trade_outcome = 'cancelled'
                else:
                    trade_outcome = exec_status or 'unknown'
            
            # Step 3: Check for preflight-skipped executions
            if not trade_outcome and execution.result.get('skipped'):
                trade_outcome = 'skipped'

            # Step 4: Fallback based on what pipeline produced
            if not trade_outcome:
                if risk_assessment:
                    approval = risk_assessment.get('approved', None)
                    if approval is False:
                        trade_outcome = 'rejected'
                    elif strategy_action and strategy_action != 'HOLD':
                        trade_outcome = 'no_trade'
                    else:
                        trade_outcome = 'no_action'
                elif strategy_action:
                    if strategy_action == 'HOLD':
                        trade_outcome = 'no_action'
                    else:
                        trade_outcome = 'no_trade'
            
            # FINAL OVERRIDE 1: For actively monitored executions, if reports show
            # unrealized P&L from trade_manager_agent, the trade IS executed —
            # override whatever earlier logic determined (e.g. 'no_trade', 'accepted')
            if execution.status in (
                ExecutionStatus.MONITORING, ExecutionStatus.RUNNING,
                ExecutionStatus.COMMUNICATION_ERROR
            ):
                if execution.reports and isinstance(execution.reports, dict):
                    for agent_id, report in execution.reports.items():
                        if isinstance(report, dict) and report.get('agent_type') == 'trade_manager_agent':
                            data = report.get('data', {})
                            if data.get('unrealized_pl') is not None or data.get('position_size'):
                                trade_outcome = 'executed'
                                break
            
            # FINAL OVERRIDE 2: For completed executions with real P&L, the trade
            # was actually filled — override 'pending'/'accepted' to 'executed'.
            # This handles limit orders that were filled and closed but whose
            # trade_execution.status was never updated from 'accepted'.
            if execution.status == ExecutionStatus.COMPLETED and trade_outcome in ('pending', 'accepted'):
                has_real_pnl = False
                result = execution.result or {}
                
                # Check final_pnl (top-level)
                final_pnl = result.get('final_pnl')
                if final_pnl is not None and final_pnl != 0:
                    has_real_pnl = True
                
                # Check trade_outcome.pnl
                if not has_real_pnl and trade_outcome_obj and isinstance(trade_outcome_obj, dict):
                    try:
                        pnl_val = float(trade_outcome_obj.get('pnl', 0))
                        if pnl_val != 0:
                            has_real_pnl = True
                    except (TypeError, ValueError):
                        pass
                
                # Check reports for unrealized_pl (reconciled trades captured P&L here)
                if not has_real_pnl and execution.reports and isinstance(execution.reports, dict):
                    for agent_id, report in execution.reports.items():
                        if isinstance(report, dict) and report.get('agent_type') == 'trade_manager_agent':
                            data = report.get('data', {})
                            upl = data.get('unrealized_pl')
                            if upl is not None and upl != 0:
                                has_real_pnl = True
                                break
                
                if has_real_pnl:
                    trade_outcome = 'executed'
        
        summaries.append(ExecutionSummary(
            id=execution.id,
            pipeline_id=execution.pipeline_id,
            pipeline_name=pipeline_name,
            status=execution.status,
            mode=execution.mode,
            symbol=execution.symbol,
            trigger_mode=trigger_mode.value if trigger_mode else None,
            scanner_name=scanner_name,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            duration_seconds=duration_seconds,
            total_cost=execution.cost,
            agent_count=agent_count,
            agents_completed=agents_completed,
            error_message=execution.error_message,
            strategy_action=strategy_action,
            strategy_confidence=strategy_confidence,
            trade_outcome=trade_outcome,
            result=execution.result,  # Include full result for P&L
            reports=execution.reports  # Include reports for monitoring P&L
        ))
    
    return {
        "executions": summaries,
        "total": total_historical + len(active_rows),
        "active_count": len(active_rows),
        "historical_total": total_historical,
        "limit": limit,
        "offset": offset,
    }


@router.post("/{execution_id}/stop", response_model=dict)
async def stop_execution_endpoint(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Stop a running execution.
    
    Args:
        execution_id: Execution UUID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Status message
    """
    result = await db.execute(
        select(Execution).where(Execution.id == execution_id)
    )
    execution = result.scalar_one_or_none()
    
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to stop this execution"
        )
    
    if execution.status != ExecutionStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot stop execution with status: {execution.status.value}"
        )
    
    # Trigger stop task
    stop_execution.delay(
        execution_id=str(execution_id),
        user_id=str(current_user.id)
    )
    
    return {"message": "Stop request sent", "execution_id": str(execution_id)}


@router.post("/{execution_id}/close-position", response_model=dict)
async def close_position_endpoint(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Close an open position for a monitoring execution.
    
    This endpoint allows manual closure of positions from the UI.
    It verifies the execution is in MONITORING status, closes the position
    via the broker, and marks the execution as COMPLETED.
    
    Args:
        execution_id: Execution UUID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Result of the close operation
    """
    # Load execution
    result = await db.execute(
        select(Execution, Pipeline)
        .join(Pipeline, Execution.pipeline_id == Pipeline.id)
        .where(Execution.id == execution_id)
    )
    row = result.first()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    execution, pipeline = row
    
    # Verify ownership
    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to close this position"
        )
    
    # Verify execution is in monitoring status
    if execution.status != ExecutionStatus.MONITORING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot close position for execution with status: {execution.status.value}. Only MONITORING executions can be closed."
        )
    
    # Get broker configuration from the pipeline config
    # The tools are stored in the pipeline nodes, not in agent_states
    pipeline_config = pipeline.config or {}
    nodes = pipeline_config.get("nodes", [])
    
    # Find trade manager node
    trade_manager_node = None
    for node in nodes:
        if node.get("agent_type") == "trade_manager_agent":
            trade_manager_node = node
            break
    
    if not trade_manager_node:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No trade manager agent found in pipeline configuration"
        )
    
    logger.info(
        "found_trade_manager_node",
        execution_id=str(execution_id),
        node_id=trade_manager_node.get("id"),
        has_config=bool(trade_manager_node.get("config"))
    )
    
    # Get broker from trade manager node config
    node_config = trade_manager_node.get("config", {})
    broker_name = node_config.get("broker", "alpaca")
    execution_mode = node_config.get("execution_mode", "paper")
    
    # Get tools from the trade manager node - this is where user's broker credentials are stored
    tools = node_config.get("tools", [])
    
    logger.info(
        "extracted_trade_manager_config",
        execution_id=str(execution_id),
        broker=broker_name,
        mode=execution_mode,
        tools_count=len(tools)
    )
    
    # Find the broker tool with credentials
    broker_tool_config = None
    for tool in tools:
        tool_type = tool.get("tool_type", "")
        if "broker" in tool_type.lower():  # oanda_broker, alpaca_broker, etc.
            broker_tool_config = tool
            logger.info(
                "found_broker_tool",
                execution_id=str(execution_id),
                tool_type=tool_type,
                has_config=bool(tool.get("config"))
            )
            break
    
    if not broker_tool_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No broker tool found in trade manager configuration. Available tools: {[t.get('tool_type') for t in tools]}"
        )
    
    try:
        from app.services.brokers.factory import broker_factory
        
        # Use the broker tool config which contains the user's credentials
        broker = broker_factory.from_tool_config(broker_tool_config)
        
        # Extract trade details from execution result
        trade_id = None
        order_id = None
        broker_response = {}
        if execution.result and 'trade_execution' in execution.result:
            trade_exec = execution.result.get('trade_execution', {})
            trade_id = trade_exec.get('trade_id')   # position-level ID
            order_id = trade_exec.get('order_id')   # order-level ID
            broker_response = trade_exec.get('broker_response', {})
        
        # Close the position
        logger.info(
            "closing_position_from_ui",
            execution_id=str(execution_id),
            symbol=execution.symbol,
            broker=broker_name,
            mode=execution_mode,
            trade_id=trade_id,
            order_id=order_id,
        )
        
        close_result = broker.close_position(execution.symbol, trade_id=trade_id)
        
        if not close_result.get("success", False):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to close position: {close_result.get('error', 'Unknown error')}"
            )
        
        # Fetch final P&L from broker (single source of truth)
        final_pnl = None
        final_pnl_percent = None

        # First try to get realized P&L from broker
        # Wait briefly for the closing order to settle before querying
        if trade_id or order_id:
            import time
            time.sleep(2)  # Give broker time to fill the closing market order
            try:
                trade_details = broker.get_trade_details(
                    trade_id=str(trade_id) if trade_id else None,
                    order_id=str(order_id) if order_id else None,
                )
                if trade_details and trade_details.get("found"):
                    broker_realized_pl = float(trade_details.get("realized_pl", 0))
                    entry_price = trade_details.get("open_price")
                    exit_price = trade_details.get("close_price")
                    if broker_realized_pl != 0 or exit_price:
                        # Broker has valid P&L data
                        final_pnl = broker_realized_pl
                        if entry_price and float(entry_price) > 0 and exit_price:
                            final_pnl_percent = ((float(exit_price) - float(entry_price)) / float(entry_price)) * 100
                    else:
                        # Broker returned 0 P&L with no exit price — closing order
                        # may not have settled yet. Leave final_pnl as None so
                        # we fall through to the monitoring report fallback.
                        logger.warning(
                            "broker_pnl_not_available_yet",
                            execution_id=str(execution_id),
                            realized_pl=broker_realized_pl,
                            exit_price=exit_price,
                        )
            except Exception as e:
                logger.warning(f"Could not fetch trade details for P&L: {e}")

        # Fallback: use unrealized P&L from last monitoring report
        if final_pnl is None and execution.reports:
            trade_manager_report = None
            for agent_id, report in execution.reports.items():
                if report.get('agent_type') == 'trade_manager_agent':
                    trade_manager_report = report
                    break
            if trade_manager_report and 'data' in trade_manager_report:
                final_pnl = trade_manager_report['data'].get('unrealized_pl')
                final_pnl_percent = trade_manager_report['data'].get('pnl_percent')
        
        # Update execution status and save final P&L
        execution.status = ExecutionStatus.COMPLETED
        execution.completed_at = datetime.utcnow()
        execution.execution_phase = "completed"
        execution.next_check_at = None
        
        # Update the result to include final P&L and trade_outcome
        if execution.result:
            execution.result['final_pnl'] = final_pnl
            execution.result['final_pnl_percent'] = final_pnl_percent
            execution.result['closed_from_ui'] = True
            execution.result['closed_at'] = datetime.utcnow().isoformat()
            # Ensure trade_outcome is set so dashboard P&L counts this execution
            execution.result['trade_outcome'] = {
                "status": "executed",
                "pnl": final_pnl or 0.0,
                "pnl_percent": final_pnl_percent or 0.0,
                "exit_reason": "Position closed manually from UI",
                "exit_price": None,
                "entry_price": (execution.result.get('trade_execution', {}) or {}).get('filled_price'),
                "closed_at": datetime.utcnow().isoformat(),
            }
        
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(execution, 'result')
        
        await db.commit()
        
        logger.info(
            "position_closed_from_ui",
            execution_id=str(execution_id),
            symbol=execution.symbol,
            final_pnl=final_pnl,
            close_result=close_result
        )
        
        return {
            "success": True,
            "message": f"Position for {execution.symbol} closed successfully",
            "execution_id": str(execution_id),
            "final_pnl": final_pnl,
            "final_pnl_percent": final_pnl_percent,
            "close_result": close_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "close_position_failed",
            execution_id=str(execution_id),
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close position: {str(e)}"
        )


@router.post("/{execution_id}/reconcile", response_model=dict)
async def reconcile_execution_endpoint(
    execution_id: UUID,
    reconciliation_data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Reconcile a NEEDS_RECONCILIATION execution.

    Resolution strategy (tried in order):
    1. **Auto-reconcile from broker** – if the execution has a ``trade_id``,
       call ``broker.get_trade_details()`` to obtain the realized P&L, exit
       price, and close time directly from the broker (single source of truth).
    2. **Calculate P&L from prices** – if the user provides ``entry_price``
       and ``exit_price`` (and quantity is known from the execution), compute
       the P&L.  The user does NOT need to provide ``pnl`` manually.
    3. **User-supplied P&L** – if neither of the above is possible the user
       may provide ``pnl`` directly.

    Args:
        execution_id: Execution UUID
        reconciliation_data: Dict containing (all optional, see strategy above):
            - pnl: float - Explicit P&L in dollars
            - pnl_percent: float - Profit/Loss percentage
            - exit_reason: str - Why the position closed
            - exit_price: float - Exit price
            - entry_price: float - Entry price (overrides stored value)
            - closed_at: str - ISO datetime when position closed
            - auto_reconcile: bool - If True, force auto-reconcile from broker
        current_user: Authenticated user
        db: Database session

    Returns:
        Result of the reconciliation operation
    """
    # Load execution with its pipeline
    result = await db.execute(
        select(Execution, Pipeline)
        .join(Pipeline, Execution.pipeline_id == Pipeline.id)
        .where(Execution.id == execution_id)
    )
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )

    execution, pipeline = row

    # Verify ownership
    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to reconcile this execution",
        )

    # Verify execution is in NEEDS_RECONCILIATION status
    if execution.status != ExecutionStatus.NEEDS_RECONCILIATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot reconcile execution with status: {execution.status.value}. "
                "Only NEEDS_RECONCILIATION executions can be reconciled."
            ),
        )

    # ── Extract trade metadata from execution result ────────────────
    existing_result = execution.result or {}
    trade_exec = existing_result.get("trade_execution", {})
    trade_id = trade_exec.get("trade_id")       # position-level ID (Oanda trade, Tradier position)
    order_id = trade_exec.get("order_id")       # order-level ID (Tradier/Alpaca order)
    broker_response = trade_exec.get("broker_response", {})
    stored_entry_price = trade_exec.get("filled_price") or trade_exec.get("price")
    stored_qty = (
        trade_exec.get("filled_quantity")
        or trade_exec.get("units")
        or trade_exec.get("quantity")
        or 1
    )
    # Side may be stored at top level or in broker_response.action
    stored_side = (
        trade_exec.get("side")
        or (broker_response.get("action") or "").lower()
        or "buy"
    ).lower()

    # User-supplied overrides
    user_pnl = reconciliation_data.get("pnl")
    user_pnl_percent = reconciliation_data.get("pnl_percent")
    user_exit_price = reconciliation_data.get("exit_price")
    user_entry_price = reconciliation_data.get("entry_price")
    user_exit_reason = reconciliation_data.get("exit_reason")
    closed_at_str = reconciliation_data.get("closed_at")
    force_auto = reconciliation_data.get("auto_reconcile", False)

    # Parse closed_at — always store as naive UTC (DB column is TIMESTAMP WITHOUT TIME ZONE)
    closed_at = None
    if closed_at_str:
        try:
            if isinstance(closed_at_str, str):
                dt = datetime.fromisoformat(closed_at_str.replace("Z", "+00:00"))
                # Strip tzinfo so it's naive UTC (DB column is TIMESTAMP WITHOUT TIME ZONE)
                closed_at = dt.replace(tzinfo=None) if dt.tzinfo else dt
            else:
                closed_at = datetime.utcnow()
        except Exception:
            closed_at = datetime.utcnow()
    else:
        closed_at = datetime.utcnow()

    # ── Strategy 1: Auto-reconcile from broker ──────────────────────
    pnl = None
    pnl_percent = None
    exit_price = user_exit_price
    entry_price = user_entry_price or stored_entry_price
    exit_reason = user_exit_reason or "Manually reconciled by user"
    reconcile_method = "manual"

    auto_reconcile_error = None  # Track broker error for user feedback

    has_any_id = trade_id or order_id
    if has_any_id and (force_auto or user_pnl is None):
        try:
            from app.services.brokers.factory import broker_factory
            from app.orchestration.tasks._helpers import _extract_broker_tool

            broker_tool = _extract_broker_tool(pipeline.config or {})
            if broker_tool:
                broker = broker_factory.from_tool_config(broker_tool)
                # Pass both IDs — each broker decides which one to use
                trade_details = broker.get_trade_details(
                    trade_id=str(trade_id) if trade_id else None,
                    order_id=str(order_id) if order_id else None,
                )

                if trade_details and trade_details.get("found"):
                    broker_pnl = float(trade_details.get("realized_pl", 0))
                    broker_close_price = trade_details.get("close_price")
                    broker_open_price = trade_details.get("open_price")
                    broker_close_time = trade_details.get("close_time")
                    broker_state = trade_details.get("state", "")

                    # Only use broker data if position is actually closed AND
                    # we have meaningful closing data (P&L or close_price).
                    # SAFEGUARD: For OTOCO bracket orders, broker_state="closed"
                    # means the ORDER completed (all legs resolved). But if
                    # realized_pl is still 0 and no close_price was found, it
                    # means we couldn't identify the closing leg — we should NOT
                    # accept pnl=0 as a valid reconciliation.
                    order_class = trade_details.get("order_class", "")
                    has_closing_data = broker_pnl != 0 or broker_close_price is not None

                    if has_closing_data and (broker_state == "closed" or broker_pnl != 0 or broker_close_price):
                        pnl = broker_pnl
                        exit_price = float(broker_close_price) if broker_close_price else exit_price
                        entry_price = float(broker_open_price) if broker_open_price else entry_price

                        # Build exit reason from leg details if available
                        broker_legs = trade_details.get("legs", [])
                        exit_via = None
                        for bl in broker_legs:
                            bl_status = (bl.get("status", "") or "").lower()
                            bl_side = (bl.get("side", "") or "").lower()
                            if bl_status == "filled" and bl_side != stored_side:
                                bl_type = (bl.get("type", "") or "").lower()
                                if bl_type == "limit":
                                    exit_via = "take-profit"
                                elif bl_type == "stop":
                                    exit_via = "stop-loss"
                                else:
                                    exit_via = bl_type
                                break

                        if exit_via:
                            exit_reason = f"Auto-reconciled from broker ({exit_via} filled)"
                        else:
                            exit_reason = "Auto-reconciled from broker data"
                        reconcile_method = "auto_broker"

                        if entry_price and float(entry_price) > 0:
                            pnl_percent = (pnl / (float(entry_price) * abs(float(stored_qty)))) * 100

                        if broker_close_time:
                            try:
                                dt = datetime.fromisoformat(
                                    str(broker_close_time).replace("Z", "+00:00")
                                )
                                closed_at = dt.replace(tzinfo=None) if dt.tzinfo else dt
                            except Exception:
                                pass

                        logger.info(
                            "auto_reconciled_from_broker",
                            execution_id=str(execution_id),
                            trade_id=trade_id,
                            order_id=order_id,
                            pnl=pnl,
                            exit_price=exit_price,
                            exit_via=exit_via,
                        )
                    elif broker_state == "closed" and not has_closing_data:
                        # OTOCO/bracket order shows "closed" but no exit price or P&L
                        # was extracted — the closing leg data may not be available yet.
                        id_label = order_id or trade_id
                        auto_reconcile_error = (
                            f"Trade {id_label} order is 'closed' on broker but no "
                            f"exit price or P&L was found. The broker may not have "
                            f"processed the closing leg yet. Please try again in a "
                            f"few minutes, or provide exit_price and entry_price manually."
                        )
                        logger.warning(
                            "broker_closed_but_no_closing_data",
                            execution_id=str(execution_id),
                            trade_id=trade_id,
                            order_id=order_id,
                            broker_state=broker_state,
                            order_class=order_class,
                        )
                    else:
                        id_label = order_id or trade_id
                        auto_reconcile_error = (
                            f"Trade {id_label} is still open on the broker "
                            f"(state: {broker_state}). Close the position on the "
                            f"broker first, then try auto-reconcile again."
                        )
                        logger.info(
                            "broker_trade_still_open_or_no_pnl",
                            execution_id=str(execution_id),
                            trade_id=trade_id,
                            order_id=order_id,
                            broker_state=broker_state,
                        )
                else:
                    broker_error_msg = trade_details.get("error", "Unknown error") if trade_details else "No response"
                    id_label = order_id or trade_id
                    auto_reconcile_error = (
                        f"Broker API error for trade {id_label}: {broker_error_msg}"
                    )
                    logger.warning(
                        "broker_trade_not_found_during_reconcile",
                        execution_id=str(execution_id),
                        trade_id=trade_id,
                        order_id=order_id,
                        details=trade_details,
                    )
            else:
                auto_reconcile_error = (
                    "No broker tool found in pipeline configuration. "
                    "Cannot auto-reconcile without broker connection."
                )
        except Exception as e:
            auto_reconcile_error = f"Auto-reconcile failed: {str(e)}"
            logger.warning(
                "auto_reconcile_from_broker_failed",
                execution_id=str(execution_id),
                trade_id=trade_id,
                order_id=order_id,
                error=str(e),
            )

    # If user explicitly requested auto_reconcile and it failed, return
    # the specific error immediately instead of silently falling through
    if force_auto and reconcile_method != "auto_broker" and auto_reconcile_error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=auto_reconcile_error,
        )

    # ── Strategy 2: Calculate P&L from entry/exit prices ────────────
    if pnl is None and user_pnl is None:
        effective_entry = float(entry_price) if entry_price else None
        effective_exit = float(exit_price) if exit_price else None

        if effective_entry and effective_exit and effective_entry > 0:
            qty = abs(float(stored_qty))
            if stored_side in ("buy", "long"):
                pnl = (effective_exit - effective_entry) * qty
            else:
                pnl = (effective_entry - effective_exit) * qty

            pnl_percent = ((effective_exit - effective_entry) / effective_entry) * 100
            if stored_side in ("sell", "short"):
                pnl_percent = -pnl_percent

            reconcile_method = "calculated_from_prices"
            exit_reason = user_exit_reason or "Manually reconciled (P&L calculated from prices)"

            logger.info(
                "pnl_calculated_from_prices",
                execution_id=str(execution_id),
                entry=effective_entry,
                exit=effective_exit,
                qty=qty,
                side=stored_side,
                pnl=pnl,
            )

    # ── Strategy 3: Use user-supplied P&L directly ──────────────────
    if pnl is None and user_pnl is not None:
        try:
            pnl = float(user_pnl)
            reconcile_method = "user_supplied"
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="pnl must be a valid number",
            )

    if user_pnl_percent is not None and pnl_percent is None:
        try:
            pnl_percent = float(user_pnl_percent)
        except (ValueError, TypeError):
            pass

    # ── Validation: we must have P&L by now ─────────────────────────
    if pnl is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Could not determine P&L. Please provide either: "
                "(1) entry_price and exit_price so P&L can be calculated, or "
                "(2) pnl directly. "
                "If a trade_id exists, the system will also try to auto-fetch from the broker."
            ),
        )

    # ── Persist reconciliation ──────────────────────────────────────
    execution.status = ExecutionStatus.COMPLETED
    execution.completed_at = closed_at
    execution.execution_phase = "completed"
    execution.next_check_at = None
    execution.error_message = None

    if not execution.result:
        execution.result = {}

    execution.result["final_pnl"] = pnl
    execution.result["final_pnl_percent"] = pnl_percent
    execution.result["reconciled_manually"] = reconcile_method != "auto_broker"
    execution.result["reconcile_method"] = reconcile_method
    execution.result["reconciled_at"] = datetime.utcnow().isoformat()
    execution.result["reconciled_by"] = str(current_user.id)

    if "trade_outcome" not in execution.result:
        execution.result["trade_outcome"] = {}

    execution.result["trade_outcome"].update(
        {
            "status": "executed" if pnl != 0 else "cancelled",
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "exit_reason": exit_reason,
            "exit_price": exit_price,
            "entry_price": entry_price,
            "closed_at": closed_at.isoformat(),
        }
    )

    # Update pipeline state if it exists
    try:
        from app.orchestration.tasks._helpers import load_pipeline_state, save_pipeline_state
        from app.schemas.pipeline_state import TradeOutcome

        pipeline_state = load_pipeline_state(execution)
        if pipeline_state:
            outcome_data = dict(
                status="executed" if pnl != 0 else "cancelled",
                pnl=pnl,
                pnl_percent=pnl_percent,
                exit_reason=exit_reason,
                exit_price=exit_price,
                entry_price=entry_price,
                closed_at=closed_at,
            )
            if not pipeline_state.trade_outcome:
                pipeline_state.trade_outcome = TradeOutcome(**outcome_data)
            else:
                for k, v in outcome_data.items():
                    setattr(pipeline_state.trade_outcome, k, v)

            pipeline_state.should_complete = True
            save_pipeline_state(execution, pipeline_state)
    except Exception as e:
        logger.warning(
            "failed_to_update_pipeline_state",
            execution_id=str(execution_id),
            error=str(e),
        )

    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(execution, "result")

    await db.commit()

    logger.info(
        "execution_reconciled",
        execution_id=str(execution_id),
        symbol=execution.symbol,
        pnl=pnl,
        pnl_percent=pnl_percent,
        method=reconcile_method,
    )

    return {
        "success": True,
        "message": f"Execution for {execution.symbol} reconciled successfully",
        "execution_id": str(execution_id),
        "pnl": pnl,
        "pnl_percent": pnl_percent,
        "reconcile_method": reconcile_method,
    }


@router.post("/{execution_id}/resume-monitoring", response_model=dict)
async def resume_monitoring_endpoint(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Resume monitoring for a NEEDS_RECONCILIATION execution.
    
    This endpoint pushes a NEEDS_RECONCILIATION execution back into MONITORING status,
    allowing the system to resume automatic monitoring and P&L tracking.
    
    Args:
        execution_id: Execution UUID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Result of the resume operation
    """
    # Load execution
    result = await db.execute(
        select(Execution).where(Execution.id == execution_id)
    )
    execution = result.scalar_one_or_none()
    
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    # Verify ownership
    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to resume monitoring for this execution"
        )
    
    # Verify execution is in NEEDS_RECONCILIATION status
    if execution.status != ExecutionStatus.NEEDS_RECONCILIATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot resume monitoring for execution with status: {execution.status.value}. Only NEEDS_RECONCILIATION executions can resume monitoring."
        )
    
    # Update execution status back to MONITORING
    execution.status = ExecutionStatus.MONITORING
    execution.execution_phase = "monitoring"
    execution.error_message = None
    
    # Set next_check_at to trigger monitoring check in 15 seconds
    from datetime import timedelta
    execution.next_check_at = datetime.utcnow() + timedelta(seconds=15)
    
    # Clear any reconciliation flags in result
    if execution.result:
        execution.result.pop('reconciled_manually', None)
        execution.result.pop('reconciled_at', None)
        execution.result.pop('reconciled_by', None)
        # Clear stale trade_outcome from the NEEDS_RECONCILIATION phase
        execution.result.pop('trade_outcome', None)
        execution.result.pop('final_pnl', None)
        execution.result.pop('final_pnl_percent', None)
    
    from sqlalchemy.orm.attributes import flag_modified
    if execution.result:
        flag_modified(execution, 'result')
    
    # ── CRITICAL: Reset stale flags in pipeline_state ──────────────────
    # When the execution was NEEDS_RECONCILIATION, the pipeline_state had
    # should_complete=True and trade_outcome with status="needs_reconciliation".
    # If we don't clear these, the next monitoring check will immediately
    # re-mark the execution as NEEDS_RECONCILIATION because the agent's
    # FOUND path doesn't touch should_complete.
    from app.orchestration.tasks._helpers import load_pipeline_state, save_pipeline_state
    try:
        pipeline_state = load_pipeline_state(execution)
        if pipeline_state:
            pipeline_state.should_complete = False
            pipeline_state.trade_outcome = None
            pipeline_state.communication_error = False
            save_pipeline_state(execution, pipeline_state)
            flag_modified(execution, 'pipeline_state')
    except Exception as e:
        logger.warning(
            "failed_to_reset_pipeline_state_on_resume",
            execution_id=str(execution_id),
            error=str(e)
        )
    
    await db.commit()
    
    # Schedule immediate monitoring check
    try:
        from app.orchestration.tasks.monitoring import schedule_monitoring_check
        schedule_monitoring_check.apply_async(
            args=[str(execution.id)],
            countdown=15  # 15 seconds
        )
    except Exception as e:
        logger.error(
            "failed_to_schedule_monitoring",
            execution_id=str(execution_id),
            error=str(e)
        )
        # Don't fail the request - status is updated, monitoring will be picked up by reconciliation task
    
    logger.info(
        "monitoring_resumed",
        execution_id=str(execution_id),
        symbol=execution.symbol
    )
    
    return {
        "success": True,
        "message": f"Monitoring resumed for {execution.symbol}",
        "execution_id": str(execution_id),
        "status": "MONITORING",
        "next_check_at": execution.next_check_at.isoformat() if execution.next_check_at else None
    }


@router.get("/{execution_id}/logs", response_model=List[dict])
async def get_execution_logs(
    execution_id: UUID,
    limit: int = Query(100, ge=1, le=1000, description="Max number of logs"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[dict]:
    """
    Get execution logs.
    
    Args:
        execution_id: Execution UUID
        limit: Maximum number of logs to return
        current_user: Authenticated user
        db: Database session
        
    Returns:
        List of log entries
    """
    result = await db.execute(
        select(Execution).where(Execution.id == execution_id)
    )
    execution = result.scalar_one_or_none()
    
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view these logs"
        )
    
    logs = execution.logs or []
    return logs[-limit:] if len(logs) > limit else logs


@router.post("/{execution_id}/pause", response_model=ExecutionInDB)
async def pause_execution(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> ExecutionInDB:
    """
    Pause a running execution.
    
    Args:
        execution_id: Execution UUID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Updated execution
    """
    result = await db.execute(
        select(Execution).where(Execution.id == execution_id)
    )
    execution = result.scalar_one_or_none()
    
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to pause this execution"
        )
    
    if execution.status != ExecutionStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot pause execution with status: {execution.status.value}"
        )
    
    execution.status = ExecutionStatus.PAUSED
    await db.commit()
    await db.refresh(execution)
    
    return execution


@router.post("/{execution_id}/resume", response_model=ExecutionInDB)
async def resume_execution(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> ExecutionInDB:
    """
    Resume a paused execution.
    
    Args:
        execution_id: Execution UUID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Updated execution
    """
    result = await db.execute(
        select(Execution).where(Execution.id == execution_id)
    )
    execution = result.scalar_one_or_none()
    
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to resume this execution"
        )
    
    if execution.status != ExecutionStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot resume execution with status: {execution.status.value}"
        )
    
    execution.status = ExecutionStatus.RUNNING
    await db.commit()
    await db.refresh(execution)
    
    return execution


@router.post("/{execution_id}/cancel", response_model=ExecutionInDB)
async def cancel_execution(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> ExecutionInDB:
    """
    Cancel an execution.
    
    Args:
        execution_id: Execution UUID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Updated execution
    """
    result = await db.execute(
        select(Execution).where(Execution.id == execution_id)
    )
    execution = result.scalar_one_or_none()
    
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to cancel this execution"
        )
    
    if execution.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel execution with status: {execution.status.value}"
        )
    
    execution.status = ExecutionStatus.CANCELLED
    execution.completed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(execution)
    
    return execution


@router.get("/{execution_id}/executive-report", response_model=dict)
async def generate_executive_report(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Generate an AI-powered executive summary report for an execution.
    
    This endpoint uses LLM to synthesize all agent reports, strategy decisions,
    and execution results into a comprehensive, actionable summary.
    
    Args:
        execution_id: Execution UUID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Executive report with summary, insights, and recommendations
    """
    # Get execution with full data
    result = await db.execute(
        select(
            Execution, 
            Pipeline.name,
            Pipeline.trigger_mode
        )
        .join(Pipeline, Execution.pipeline_id == Pipeline.id)
        .where(Execution.id == execution_id)
    )
    row = result.first()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    execution, pipeline_name, trigger_mode = row
    
    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this execution"
        )
    
    if execution.status != ExecutionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot generate report for execution with status: {execution.status.value}"
        )
    
    # Return saved executive report if available
    if execution.executive_report:
        return execution.executive_report
    
    # Otherwise, generate report on-demand (for backward compatibility with old executions)
    # Build execution data for report generator
    execution_data = {
        "id": str(execution.id),
        "pipeline_name": pipeline_name,
        "symbol": execution.symbol,
        "mode": execution.mode,
        "status": execution.status.value,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        "duration_seconds": (execution.completed_at - execution.started_at).total_seconds() if execution.started_at and execution.completed_at else None,
        "cost": execution.cost,
        "reports": execution.reports or {},
        "result": execution.result or {},
        "agent_states": execution.agent_states or [],
    }
    
    # Create Langfuse trace (completely optional - won't affect report generation)
    langfuse_client = get_langfuse_client()
    trace = None
    if langfuse_client:
        try:
            trace = langfuse_client.trace(
                name="executive_report_generation",
                user_id=str(current_user.id),
                session_id=str(execution_id),
                metadata={
                    "execution_id": str(execution_id),
                    "pipeline_name": pipeline_name,
                }
            )
        except Exception:
            # Silently ignore Langfuse errors (quota exhaustion, rate limiting, etc.)
            # Report generation works regardless of Langfuse availability
            pass
    
    # Generate report
    report = await executive_report_generator.generate_executive_summary(
        execution_data,
        langfuse_trace=trace
    )
    
    # Add execution context to report
    report["execution_context"] = {
        "id": str(execution.id),
        "pipeline_name": pipeline_name,
        "symbol": execution.symbol,
        "mode": execution.mode,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        "duration_seconds": execution_data["duration_seconds"],
        "total_cost": execution.cost,
    }
    
    # Include all agent reports
    report["agent_reports"] = execution.reports or {}
    
    # Include execution artifacts (charts, etc.)
    if execution.result and isinstance(execution.result, dict):
        report["execution_artifacts"] = execution.result.get("execution_artifacts", {})
        report["strategy"] = execution.result.get("strategy")
        report["bias"] = execution.result.get("biases")
        report["risk_assessment"] = execution.result.get("risk_assessment")
        report["trade_execution"] = execution.result.get("trade_execution")
    
    return report


@router.get("/{execution_id}/trade-analysis", response_model=dict)
async def get_trade_analysis(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get AI-powered post-trade analysis for a completed execution.

    Analyzes trade quality, provides a grade, and offers lessons learned.
    Results are cached in the execution's trade_analysis column.

    Args:
        execution_id: Execution UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Trade analysis with grade, lessons, and recommendations
    """
    result = await db.execute(
        select(Execution).where(Execution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )

    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this execution",
        )

    if execution.status != ExecutionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot generate trade analysis for execution with status: {execution.status.value}",
        )

    # Return cached analysis if available
    if execution.trade_analysis:
        return execution.trade_analysis

    # Build execution data for the generator
    execution_data = {
        "id": str(execution.id),
        "symbol": execution.symbol,
        "mode": execution.mode,
        "result": execution.result or {},
    }

    # Create Langfuse trace (optional)
    langfuse_client = get_langfuse_client()
    trace = None
    if langfuse_client:
        try:
            trace = langfuse_client.trace(
                name="trade_analysis_generation",
                user_id=str(current_user.id),
                session_id=str(execution_id),
                metadata={
                    "execution_id": str(execution_id),
                },
            )
        except Exception:
            pass

    analysis = await trade_analysis_generator.generate_trade_analysis(
        execution_data, langfuse_trace=trace
    )

    # Cache the result
    execution.trade_analysis = analysis
    await db.commit()

    return analysis


@router.get("/{execution_id}/report.pdf")
async def download_execution_report_pdf(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Download the generated PDF report for an execution.
    
    Returns the pre-generated PDF file if available, or 404 if not yet generated.
    
    Args:
        execution_id: Execution UUID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        PDF file as download
    """
    # Get execution
    result = await db.execute(
        select(Execution).where(Execution.id == execution_id)
    )
    execution = result.scalar_one_or_none()
    
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    if execution.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this execution"
        )
    
    if not execution.report_pdf_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF report not yet generated for this execution"
        )
    
    # Construct full path to PDF file
    from app.config import settings
    pdf_dir = Path(settings.PDF_STORAGE_PATH if hasattr(settings, 'PDF_STORAGE_PATH') else '/app/data/reports')
    pdf_filename = Path(execution.report_pdf_path).name
    pdf_filepath = pdf_dir / pdf_filename
    
    if not pdf_filepath.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF file not found on server"
        )
    
    # Return file as download
    return FileResponse(
        path=str(pdf_filepath),
        media_type="application/pdf",
        filename=pdf_filename,
        headers={
            "Content-Disposition": f"attachment; filename={pdf_filename}"
        }
    )


