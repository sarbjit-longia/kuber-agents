"""
User API endpoints.

Handles user profile and subscription information.
"""
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User as UserModel
from app.models.pipeline import Pipeline
from app.schemas.user import UserSubscriptionInfo, User as UserSchema
from app.core.deps import get_current_active_user
from app.subscriptions.signal_buckets import get_pipeline_limit, get_available_signals
from app.config import settings


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserSchema)
async def get_current_user_profile(
    current_user: Annotated[UserModel, Depends(get_current_active_user)]
):
    """
    Get current user profile.
    
    Returns the authenticated user's profile information including
    subscription tier, email, and account details.
    
    Args:
        current_user: Authenticated user
        
    Returns:
        User profile information
    """
    return current_user


@router.get("/me/subscription", response_model=UserSubscriptionInfo)
async def get_my_subscription(
    current_user: Annotated[UserModel, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Get current user's subscription information.
    
    Returns detailed subscription info including tier, limits, and usage.
    
    Args:
        current_user: Authenticated user
        db: Async database session
        
    Returns:
        Subscription information
    """
    # Count active pipelines
    active_query = select(func.count(Pipeline.id)).where(
        Pipeline.user_id == current_user.id,
        Pipeline.is_active == True
    )
    active_result = await db.execute(active_query)
    active_pipelines = active_result.scalar() or 0
    
    # Count total pipelines
    total_query = select(func.count(Pipeline.id)).where(
        Pipeline.user_id == current_user.id
    )
    total_result = await db.execute(total_query)
    total_pipelines = total_result.scalar() or 0
    
    # Get subscription limits and available signals
    pipeline_limit = get_pipeline_limit(current_user.subscription_tier)
    available_signals = get_available_signals(current_user.subscription_tier)
    
    return UserSubscriptionInfo(
        tier=current_user.subscription_tier.value,
        max_active_pipelines=pipeline_limit,
        current_active_pipelines=active_pipelines,
        total_pipelines=total_pipelines,
        pipelines_remaining=max(0, pipeline_limit - active_pipelines),
        available_signals=available_signals,
        subscription_expires_at=current_user.subscription_expires_at.isoformat() if current_user.subscription_expires_at else None,
        is_limit_enforced=settings.ENFORCE_SUBSCRIPTION_LIMITS,
    )
