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
from sqlalchemy import select, desc
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
    
    execution, pipeline_name, trigger_mode, scanner_name = row
    
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
    }
    
    return execution_dict


@router.get("/", response_model=List[ExecutionSummary])
async def list_executions(
    pipeline_id: Optional[UUID] = Query(None, description="Filter by pipeline ID"),
    status_filter: Optional[ExecutionStatus] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Number of executions to return"),
    offset: int = Query(0, ge=0, description="Number of executions to skip"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[ExecutionSummary]:
    """
    List executions for the current user with summary information.
    
    Args:
        pipeline_id: Optional pipeline ID filter
        status_filter: Optional status filter
        limit: Maximum number of results
        offset: Number of results to skip
        current_user: Authenticated user
        db: Database session
        
    Returns:
        List of execution summaries
    """
    from app.models.scanner import Scanner
    
    query = select(
        Execution, 
        Pipeline.name, 
        Pipeline.trigger_mode,
        Scanner.name.label('scanner_name')
    ).join(
        Pipeline, Execution.pipeline_id == Pipeline.id
    ).outerjoin(
        Scanner, Pipeline.scanner_id == Scanner.id
    ).where(Execution.user_id == current_user.id)
    
    if pipeline_id:
        query = query.where(Execution.pipeline_id == pipeline_id)
    
    if status_filter:
        query = query.where(Execution.status == status_filter)
    
    query = query.order_by(desc(Execution.created_at)).limit(limit).offset(offset)
    
    result = await db.execute(query)
    rows = result.all()
    
    summaries = []
    for execution, pipeline_name, trigger_mode, scanner_name in rows:
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
            
            # Step 3: Fallback based on what pipeline produced
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
    
    return summaries


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
        
        # Extract trade ID from execution result (for bracket orders)
        trade_id = None
        if execution.result and 'trade_execution' in execution.result:
            trade_exec = execution.result.get('trade_execution', {})
            trade_id = trade_exec.get('order_id')
        
        # Close the position
        logger.info(
            "closing_position_from_ui",
            execution_id=str(execution_id),
            symbol=execution.symbol,
            broker=broker_name,
            mode=execution_mode,
            trade_id=trade_id
        )
        
        # Pass trade_id for proper bracket order closure
        close_result = broker.close_position(execution.symbol, trade_id=trade_id)
        
        if not close_result.get("success", False):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to close position: {close_result.get('error', 'Unknown error')}"
            )
        
        # Get final P&L from the last monitoring report
        final_pnl = None
        final_pnl_percent = None
        
        if execution.reports:
            # Find trade manager report
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
        
        # Update the result to include final P&L
        if execution.result:
            execution.result['final_pnl'] = final_pnl
            execution.result['final_pnl_percent'] = final_pnl_percent
            execution.result['closed_from_ui'] = True
            execution.result['closed_at'] = datetime.utcnow().isoformat()
        
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(execution, 'result')
        
        await db.commit()
        
        logger.info(
            "position_closed_from_ui",
            execution_id=str(execution_id),
            symbol=execution.symbol,
            close_result=close_result
        )
        
        return {
            "success": True,
            "message": f"Position for {execution.symbol} closed successfully",
            "execution_id": str(execution_id),
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
    Manually reconcile a NEEDS_RECONCILIATION execution with user-provided P&L and metadata.
    
    This endpoint allows users to manually close a trade that couldn't be automatically
    reconciled by providing P&L information and other trade metadata.
    
    Args:
        execution_id: Execution UUID
        reconciliation_data: Dict containing:
            - pnl: float (required) - Profit/Loss in dollars
            - pnl_percent: Optional[float] - Profit/Loss percentage
            - exit_reason: Optional[str] - Why the position closed
            - exit_price: Optional[float] - Exit price
            - entry_price: Optional[float] - Entry price
            - closed_at: Optional[str] - ISO datetime string when position closed
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Result of the reconciliation operation
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
            detail="You don't have permission to reconcile this execution"
        )
    
    # Verify execution is in NEEDS_RECONCILIATION status
    if execution.status != ExecutionStatus.NEEDS_RECONCILIATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reconcile execution with status: {execution.status.value}. Only NEEDS_RECONCILIATION executions can be reconciled."
        )
    
    # Validate required fields
    pnl = reconciliation_data.get("pnl")
    if pnl is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pnl is required in reconciliation_data"
        )
    
    try:
        pnl = float(pnl)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pnl must be a valid number"
        )
    
    # Extract optional fields
    pnl_percent = reconciliation_data.get("pnl_percent")
    if pnl_percent is not None:
        try:
            pnl_percent = float(pnl_percent)
        except (ValueError, TypeError):
            pnl_percent = None
    
    exit_reason = reconciliation_data.get("exit_reason", "Manually reconciled by user")
    exit_price = reconciliation_data.get("exit_price")
    entry_price = reconciliation_data.get("entry_price")
    closed_at_str = reconciliation_data.get("closed_at")
    
    # Parse closed_at if provided
    closed_at = None
    if closed_at_str:
        try:
            # Try parsing ISO format datetime string
            if isinstance(closed_at_str, str):
                closed_at = datetime.fromisoformat(closed_at_str.replace('Z', '+00:00'))
            else:
                closed_at = datetime.utcnow()
        except Exception:
            closed_at = datetime.utcnow()
    else:
        closed_at = datetime.utcnow()
    
    # Update execution status and save reconciliation data
    execution.status = ExecutionStatus.COMPLETED
    execution.completed_at = closed_at
    execution.execution_phase = "completed"
    execution.next_check_at = None
    execution.error_message = None
    
    # Update the result with reconciliation data
    if not execution.result:
        execution.result = {}
    
    execution.result['final_pnl'] = pnl
    execution.result['final_pnl_percent'] = pnl_percent
    execution.result['reconciled_manually'] = True
    execution.result['reconciled_at'] = datetime.utcnow().isoformat()
    execution.result['reconciled_by'] = str(current_user.id)
    
    # Update trade_outcome if it exists
    if 'trade_outcome' not in execution.result:
        execution.result['trade_outcome'] = {}
    
    execution.result['trade_outcome'].update({
        'status': 'executed' if pnl != 0 else 'cancelled',
        'pnl': pnl,
        'pnl_percent': pnl_percent,
        'exit_reason': exit_reason,
        'exit_price': exit_price,
        'entry_price': entry_price,
        'closed_at': closed_at.isoformat()
    })
    
    # Update pipeline state if it exists
    try:
        from app.orchestration.tasks._helpers import load_pipeline_state, save_pipeline_state
        from app.schemas.pipeline_state import TradeOutcome
        
        pipeline_state = load_pipeline_state(execution)
        if pipeline_state:
            if not pipeline_state.trade_outcome:
                from app.schemas.pipeline_state import TradeOutcome
                pipeline_state.trade_outcome = TradeOutcome(
                    status='executed' if pnl != 0 else 'cancelled',
                    pnl=pnl,
                    pnl_percent=pnl_percent,
                    exit_reason=exit_reason,
                    exit_price=exit_price,
                    entry_price=entry_price,
                    closed_at=closed_at
                )
            else:
                pipeline_state.trade_outcome.pnl = pnl
                pipeline_state.trade_outcome.pnl_percent = pnl_percent
                pipeline_state.trade_outcome.exit_reason = exit_reason
                pipeline_state.trade_outcome.exit_price = exit_price
                pipeline_state.trade_outcome.entry_price = entry_price
                pipeline_state.trade_outcome.closed_at = closed_at
                pipeline_state.trade_outcome.status = 'executed' if pnl != 0 else 'cancelled'
            
            pipeline_state.should_complete = True
            save_pipeline_state(execution, pipeline_state, db=db)
    except Exception as e:
        logger.warning(
            "failed_to_update_pipeline_state",
            execution_id=str(execution_id),
            error=str(e)
        )
    
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(execution, 'result')
    
    await db.commit()
    
    logger.info(
        "execution_reconciled_manually",
        execution_id=str(execution_id),
        symbol=execution.symbol,
        pnl=pnl,
        pnl_percent=pnl_percent
    )
    
    return {
        "success": True,
        "message": f"Execution for {execution.symbol} reconciled successfully",
        "execution_id": str(execution_id),
        "pnl": pnl,
        "pnl_percent": pnl_percent
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
    execution.error_message = None
    
    # Set next_check_at to trigger immediate monitoring check
    from datetime import timedelta
    execution.next_check_at = datetime.utcnow() + timedelta(minutes=1)
    
    # Clear any reconciliation flags in result
    if execution.result:
        execution.result.pop('reconciled_manually', None)
        execution.result.pop('reconciled_at', None)
        execution.result.pop('reconciled_by', None)
    
    from sqlalchemy.orm.attributes import flag_modified
    if execution.result:
        flag_modified(execution, 'result')
    
    await db.commit()
    
    # Schedule immediate monitoring check
    try:
        from app.orchestration.tasks.monitoring import schedule_monitoring_check
        schedule_monitoring_check.apply_async(
            args=[str(execution.id)],
            countdown=60  # 1 minute
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


