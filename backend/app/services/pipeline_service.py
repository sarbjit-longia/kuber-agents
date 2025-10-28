"""
Pipeline service for pipeline-related business logic.
"""
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.pipeline import Pipeline
from app.schemas.pipeline import PipelineCreate, PipelineUpdate


async def get_pipeline_by_id(
    db: AsyncSession, pipeline_id: UUID, user_id: UUID
) -> Optional[Pipeline]:
    """
    Get a pipeline by ID for a specific user.
    
    Args:
        db: Database session
        pipeline_id: Pipeline ID
        user_id: User ID (owner)
        
    Returns:
        Pipeline object or None if not found
    """
    result = await db.execute(
        select(Pipeline).where(Pipeline.id == pipeline_id, Pipeline.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_pipelines(
    db: AsyncSession, user_id: UUID, skip: int = 0, limit: int = 100
) -> List[Pipeline]:
    """
    Get all pipelines for a user.
    
    Args:
        db: Database session
        user_id: User ID
        skip: Number of records to skip
        limit: Maximum number of records to return
        
    Returns:
        List of pipeline objects
    """
    result = await db.execute(
        select(Pipeline)
        .where(Pipeline.user_id == user_id)
        .offset(skip)
        .limit(limit)
        .order_by(Pipeline.created_at.desc())
    )
    return list(result.scalars().all())


async def create_pipeline(
    db: AsyncSession, pipeline_in: PipelineCreate, user_id: UUID
) -> Pipeline:
    """
    Create a new pipeline.
    
    Args:
        db: Database session
        pipeline_in: Pipeline creation schema
        user_id: User ID (owner)
        
    Returns:
        Created pipeline object
    """
    pipeline = Pipeline(
        user_id=user_id,
        name=pipeline_in.name,
        description=pipeline_in.description,
        config=pipeline_in.config,
    )
    db.add(pipeline)
    await db.commit()
    await db.refresh(pipeline)
    return pipeline


async def update_pipeline(
    db: AsyncSession, pipeline_id: UUID, pipeline_update: PipelineUpdate, user_id: UUID
) -> Optional[Pipeline]:
    """
    Update a pipeline.
    
    Args:
        db: Database session
        pipeline_id: Pipeline ID
        pipeline_update: Pipeline update schema
        user_id: User ID (owner)
        
    Returns:
        Updated pipeline object or None if not found
    """
    pipeline = await get_pipeline_by_id(db, pipeline_id, user_id)
    if not pipeline:
        return None
    
    update_data = pipeline_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pipeline, field, value)
    
    await db.commit()
    await db.refresh(pipeline)
    return pipeline


async def delete_pipeline(db: AsyncSession, pipeline_id: UUID, user_id: UUID) -> bool:
    """
    Delete a pipeline.
    
    Args:
        db: Database session
        pipeline_id: Pipeline ID
        user_id: User ID (owner)
        
    Returns:
        True if deleted, False if not found
    """
    pipeline = await get_pipeline_by_id(db, pipeline_id, user_id)
    if not pipeline:
        return False
    
    await db.delete(pipeline)
    await db.commit()
    return True

