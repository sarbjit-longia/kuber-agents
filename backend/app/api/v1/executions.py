"""
Execution API Endpoints

Provides endpoints for:
- Starting pipeline executions
- Getting execution status
- Listing executions
- Stopping running executions
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.execution import Execution, ExecutionStatus
from app.models.pipeline import Pipeline
from app.schemas.execution import ExecutionInDB, ExecutionCreate, ExecutionSummary, ExecutionStats
from app.api.dependencies import get_current_user
from app.orchestration.tasks import execute_pipeline, stop_execution
from app.orchestration.validator import PipelineValidator

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
    
    # Trigger async Celery task
    execute_pipeline.delay(
        pipeline_id=str(execution.pipeline_id),
        user_id=str(current_user.id),
        mode=execution_data.mode or "paper",
        execution_id=str(execution.id)
    )
    
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
            error_message=execution.error_message
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

