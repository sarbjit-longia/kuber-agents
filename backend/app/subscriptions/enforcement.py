"""
Subscription Enforcement

Helper functions for checking and enforcing subscription limits.
"""
import structlog
from sqlalchemy.orm import Session
from typing import Tuple

from app.models.user import User, SubscriptionTier
from app.models.pipeline import Pipeline
from app.subscriptions.signal_buckets import (
    get_pipeline_limit,
    has_signal_access,
    get_available_signals
)
from app.config import settings

logger = structlog.get_logger()


def check_pipeline_limit(user: User, db: Session) -> Tuple[bool, str]:
    """
    Check if user can create another active pipeline.
    
    Args:
        user: User to check
        db: Database session
        
    Returns:
        Tuple of (can_create, message)
    """
    # Skip enforcement in dev mode
    if not settings.ENFORCE_SUBSCRIPTION_LIMITS:
        logger.debug(
            "subscription_limit_check_skipped",
            user_id=str(user.id),
            reason="enforcement_disabled"
        )
        return True, "Dev mode - limits not enforced"
    
    # Count active pipelines
    active_count = db.query(Pipeline).filter(
        Pipeline.user_id == user.id,
        Pipeline.is_active == True
    ).count()
    
    limit = get_pipeline_limit(user.subscription_tier)
    
    if active_count >= limit:
        logger.warning(
            "pipeline_limit_exceeded",
            user_id=str(user.id),
            tier=user.subscription_tier.value,
            active_count=active_count,
            limit=limit
        )
        return False, f"Pipeline limit reached ({active_count}/{limit}). Upgrade to create more pipelines."
    
    return True, f"OK ({active_count + 1}/{limit})"


def check_signal_access(user: User, signal_type: str) -> Tuple[bool, str]:
    """
    Check if user has access to a specific signal type.
    
    Args:
        user: User to check
        signal_type: Signal type to check
        
    Returns:
        Tuple of (has_access, message)
    """
    # Skip enforcement in dev mode
    if not settings.ENFORCE_SUBSCRIPTION_LIMITS:
        logger.debug(
            "signal_access_check_skipped",
            user_id=str(user.id),
            signal_type=signal_type,
            reason="enforcement_disabled"
        )
        return True, "Dev mode - access not restricted"
    
    has_access_flag = has_signal_access(user.subscription_tier, signal_type)
    
    if not has_access_flag:
        available_signals = get_available_signals(user.subscription_tier)
        logger.warning(
            "signal_access_denied",
            user_id=str(user.id),
            tier=user.subscription_tier.value,
            requested_signal=signal_type,
            available_signals=available_signals
        )
        return False, f"Signal '{signal_type}' not available in {user.subscription_tier.value} tier. Upgrade to access."
    
    return True, "Access granted"


def get_subscription_info(user: User, db: Session) -> dict:
    """
    Get comprehensive subscription information for a user.
    
    Args:
        user: User to get info for
        db: Database session
        
    Returns:
        Dict with subscription details
    """
    active_pipelines = db.query(Pipeline).filter(
        Pipeline.user_id == user.id,
        Pipeline.is_active == True
    ).count()
    
    total_pipelines = db.query(Pipeline).filter(
        Pipeline.user_id == user.id
    ).count()
    
    pipeline_limit = get_pipeline_limit(user.subscription_tier)
    available_signals = get_available_signals(user.subscription_tier)
    
    return {
        "tier": user.subscription_tier.value,
        "max_active_pipelines": pipeline_limit,
        "current_active_pipelines": active_pipelines,
        "total_pipelines": total_pipelines,
        "pipelines_remaining": max(0, pipeline_limit - active_pipelines),
        "available_signals": available_signals,
        "subscription_expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None,
        "is_limit_enforced": settings.ENFORCE_SUBSCRIPTION_LIMITS,
    }


def update_pipeline_limit(user: User) -> None:
    """
    Update user's max_active_pipelines based on their tier.
    
    Call this after changing a user's subscription tier.
    
    Args:
        user: User to update
    """
    user.max_active_pipelines = get_pipeline_limit(user.subscription_tier)
    logger.info(
        "pipeline_limit_updated",
        user_id=str(user.id),
        tier=user.subscription_tier.value,
        new_limit=user.max_active_pipelines
    )

