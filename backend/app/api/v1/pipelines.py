"""
Pipeline API endpoints.
"""
from typing import Annotated, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.pipeline import (
    Pipeline,
    PipelineCloneRequest,
    PipelineCreate,
    PipelineList,
    PipelineUpdate,
)
from app.models.user import User
from app.services.pipeline_service import (
    clone_pipeline,
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


@router.post("/{pipeline_id}/clone", response_model=Pipeline, status_code=status.HTTP_201_CREATED)
async def clone_existing_pipeline(
    pipeline_id: UUID,
    clone_request: PipelineCloneRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Clone a pipeline for the current user."""
    pipeline = await clone_pipeline(
        db,
        pipeline_id=pipeline_id,
        user_id=current_user.id,
        name=clone_request.name,
    )
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found",
        )
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
    liquidate_positions: bool = Query(False, description="Close all open positions when deactivating"),
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
        
        # Get trigger mode and scanner_id (updated values or existing)
        trigger_mode = pipeline_update.trigger_mode if hasattr(pipeline_update, 'trigger_mode') and pipeline_update.trigger_mode else existing_pipeline.trigger_mode
        scanner_id = pipeline_update.scanner_id if hasattr(pipeline_update, 'scanner_id') and pipeline_update.scanner_id is not None else existing_pipeline.scanner_id
        
        # Validate pipeline configuration
        validator = PipelineValidator()
        is_valid, validation_errors = validator.validate(
            config_to_validate,
            trigger_mode=str(trigger_mode) if trigger_mode else "periodic",
            scanner_id=str(scanner_id) if scanner_id else None
        )
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Cannot activate pipeline: validation failed",
                    "errors": validation_errors
                }
            )

        # ── Deployment guardrails for live mode (TP-025) ──────────────
        # Determine the effective mode: updated value or existing config default.
        effective_mode = (
            (config_to_validate.get("mode") if isinstance(config_to_validate, dict) else None)
            or existing_pipeline.config.get("mode", "paper")
        )
        if effective_mode == "live":
            from app.services.deployment_guardrails import check_live_deployment
            guardrail = await check_live_deployment(
                db=db,
                pipeline_id=pipeline_id,
                pipeline_config=config_to_validate if isinstance(config_to_validate, dict) else {},
            )
            if not guardrail.passed:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "message": "Cannot activate pipeline in live mode: deployment guardrails not met",
                        "failures": guardrail.failures,
                        "warnings": guardrail.warnings,
                        "metrics": guardrail.metrics,
                    }
                )
    
    pipeline = await update_pipeline(db, pipeline_id, pipeline_update, current_user.id)
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found",
        )

    # If deactivating with liquidation requested, enqueue position closure
    if pipeline_update.is_active is False and liquidate_positions:
        from app.orchestration.tasks.liquidate_positions import liquidate_pipeline_positions
        liquidate_pipeline_positions.delay(
            pipeline_id=str(pipeline_id),
            user_id=str(current_user.id),
            reason="manual_deactivation",
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
