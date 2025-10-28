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

from app.database import get_db
from app.models.user import User
from app.models.execution import Execution, ExecutionStatus
from app.models.pipeline import Pipeline
from app.schemas.execution import ExecutionInDB, ExecutionCreate
from app.api.dependencies import get_current_user
from app.orchestration.tasks import execute_pipeline, stop_execution

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
    
    if not pipeline.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pipeline is not active"
        )
    
    # Create execution record
    execution = Execution(
        pipeline_id=execution_data.pipeline_id,
        user_id=current_user.id,
        status=ExecutionStatus.PENDING
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


@router.get("/{execution_id}", response_model=ExecutionInDB)
async def get_execution(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> ExecutionInDB:
    """
    Get execution details by ID.
    
    Args:
        execution_id: Execution UUID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Execution details
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
            detail="You don't have permission to view this execution"
        )
    
    return execution


@router.get("/", response_model=List[ExecutionInDB])
async def list_executions(
    pipeline_id: Optional[UUID] = Query(None, description="Filter by pipeline ID"),
    status_filter: Optional[ExecutionStatus] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Number of executions to return"),
    offset: int = Query(0, ge=0, description="Number of executions to skip"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[ExecutionInDB]:
    """
    List executions for the current user.
    
    Args:
        pipeline_id: Optional pipeline ID filter
        status_filter: Optional status filter
        limit: Maximum number of results
        offset: Number of results to skip
        current_user: Authenticated user
        db: Database session
        
    Returns:
        List of executions
    """
    query = select(Execution).where(Execution.user_id == current_user.id)
    
    if pipeline_id:
        query = query.where(Execution.pipeline_id == pipeline_id)
    
    if status_filter:
        query = query.where(Execution.status == status_filter)
    
    query = query.order_by(desc(Execution.created_at)).limit(limit).offset(offset)
    
    result = await db.execute(query)
    executions = result.scalars().all()
    
    return executions


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[dict]:
    """
    Get execution logs.
    
    Args:
        execution_id: Execution UUID
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
    
    return execution.logs or []

