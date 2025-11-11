"""
Pipeline API endpoints.
"""
from typing import Annotated, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.pipeline import Pipeline, PipelineCreate, PipelineUpdate, PipelineList
from app.models.user import User
from app.services.pipeline_service import (
    get_pipeline_by_id,
    get_user_pipelines,
    create_pipeline,
    update_pipeline,
    delete_pipeline,
)
from app.core.deps import get_current_active_user
from app.orchestration.validator import PipelineValidator


router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("", response_model=PipelineList)
async def list_pipelines(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """
    Get all pipelines for the current user.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        
    Returns:
        List of user's pipelines
    """
    pipelines = await get_user_pipelines(db, current_user.id, skip=skip, limit=limit)
    return {"pipelines": pipelines, "total": len(pipelines)}


@router.post("", response_model=Pipeline, status_code=status.HTTP_201_CREATED)
async def create_new_pipeline(
    pipeline_in: PipelineCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new pipeline.
    
    Args:
        pipeline_in: Pipeline creation data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Created pipeline object
    """
    pipeline = await create_pipeline(db, pipeline_in, current_user.id)
    return pipeline


@router.get("/{pipeline_id}", response_model=Pipeline)
async def get_pipeline(
    pipeline_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get a specific pipeline.
    
    Args:
        pipeline_id: Pipeline ID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Pipeline object
        
    Raises:
        HTTPException: If pipeline not found
    """
    pipeline = await get_pipeline_by_id(db, pipeline_id, current_user.id)
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found",
        )
    return pipeline


@router.patch("/{pipeline_id}", response_model=Pipeline)
async def update_existing_pipeline(
    pipeline_id: UUID,
    pipeline_update: PipelineUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update a pipeline.
    
    Args:
        pipeline_id: Pipeline ID
        pipeline_update: Pipeline update data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Updated pipeline object
        
    Raises:
        HTTPException: If pipeline not found or validation fails when activating
    """
    # If activating the pipeline, validate it first
    if hasattr(pipeline_update, 'is_active') and pipeline_update.is_active:
        # Get existing pipeline to validate its config
        existing_pipeline = await get_pipeline_by_id(db, pipeline_id, current_user.id)
        if not existing_pipeline:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pipeline not found",
            )
        
        # Use updated config if provided, otherwise use existing
        config_to_validate = pipeline_update.config if hasattr(pipeline_update, 'config') and pipeline_update.config else existing_pipeline.config
        
        # Validate pipeline configuration
        validator = PipelineValidator()
        is_valid, validation_errors = validator.validate(config_to_validate)
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Cannot activate pipeline: validation failed",
                    "errors": validation_errors
                }
            )
    
    pipeline = await update_pipeline(db, pipeline_id, pipeline_update, current_user.id)
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found",
        )
    return pipeline


@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_pipeline(
    pipeline_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete a pipeline.
    
    Args:
        pipeline_id: Pipeline ID
        current_user: Current authenticated user
        db: Database session
        
    Raises:
        HTTPException: If pipeline not found
    """
    success = await delete_pipeline(db, pipeline_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found",
        )

