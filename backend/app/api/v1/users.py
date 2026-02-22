"""
User API endpoints.

Handles user profile and subscription information.
"""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User as UserModel
from app.models.pipeline import Pipeline
from app.schemas.user import (
    UserSubscriptionInfo,
    User as UserSchema,
    UserUpdate,
    TelegramConfigUpdate,
    TelegramConfigResponse,
    TelegramTestRequest
)
from app.core.deps import get_current_active_user
from app.core.security import hash_password
from app.subscriptions.signal_buckets import get_pipeline_limit, get_available_signals
from app.config import settings
from app.services.telegram_notifier import telegram_notifier
import structlog

logger = structlog.get_logger()


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


@router.put("/me", response_model=UserSchema)
async def update_current_user_profile(
    update_data: UserUpdate,
    current_user: Annotated[UserModel, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Update current user's profile (name and/or password)."""
    if update_data.full_name is not None:
        current_user.full_name = update_data.full_name
    if update_data.password is not None:
        current_user.hashed_password = hash_password(update_data.password)

    await db.commit()
    await db.refresh(current_user)

    logger.info("user_profile_updated", user_id=str(current_user.id))
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


@router.get("/me/telegram", response_model=TelegramConfigResponse)
async def get_telegram_config(
    current_user: Annotated[UserModel, Depends(get_current_active_user)]
):
    """
    Get current user's Telegram configuration.
    
    Returns whether Telegram is configured and enabled.
    Does NOT return the bot token for security.
    
    Args:
        current_user: Authenticated user
        
    Returns:
        Telegram configuration status
    """
    is_configured = bool(current_user.telegram_bot_token and current_user.telegram_chat_id)
    
    return TelegramConfigResponse(
        enabled=current_user.telegram_enabled,
        chat_id=current_user.telegram_chat_id if is_configured else None,
        is_configured=is_configured
    )


@router.put("/me/telegram", response_model=TelegramConfigResponse)
async def update_telegram_config(
    config: TelegramConfigUpdate,
    current_user: Annotated[UserModel, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Update user's Telegram configuration.
    
    Validates the bot token and chat ID by sending a test message.
    
    Args:
        config: Telegram configuration (bot token, chat ID)
        current_user: Authenticated user
        db: Async database session
        
    Returns:
        Updated Telegram configuration
        
    Raises:
        HTTPException: If bot token or chat ID is invalid
    """
    # Test the connection first
    test_result = telegram_notifier.send_test_message(
        bot_token=config.bot_token,
        chat_id=config.chat_id
    )
    
    if test_result["status"] != "sent":
        logger.warning(
            "telegram_config_test_failed",
            user_id=str(current_user.id),
            error=test_result.get("message")
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Telegram configuration test failed: {test_result.get('message', 'Unknown error')}"
        )
    
    # Update user's Telegram config
    current_user.telegram_bot_token = config.bot_token
    current_user.telegram_chat_id = config.chat_id
    current_user.telegram_enabled = config.enabled
    
    await db.commit()
    await db.refresh(current_user)
    
    logger.info(
        "telegram_config_updated",
        user_id=str(current_user.id),
        enabled=config.enabled
    )
    
    return TelegramConfigResponse(
        enabled=current_user.telegram_enabled,
        chat_id=current_user.telegram_chat_id,
        is_configured=True
    )


@router.post("/me/telegram/test")
async def test_telegram_connection(
    test_request: TelegramTestRequest,
    current_user: Annotated[UserModel, Depends(get_current_active_user)]
):
    """
    Test Telegram connection without saving credentials.
    
    Useful for users to verify their bot token and chat ID before saving.
    
    Args:
        test_request: Bot token and chat ID to test
        current_user: Authenticated user
        
    Returns:
        Test result with status
        
    Raises:
        HTTPException: If test fails
    """
    result = telegram_notifier.send_test_message(
        bot_token=test_request.bot_token,
        chat_id=test_request.chat_id
    )
    
    if result["status"] != "sent":
        logger.warning(
            "telegram_test_failed",
            user_id=str(current_user.id),
            error=result.get("message")
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Telegram test failed: {result.get('message', 'Unknown error')}"
        )
    
    logger.info("telegram_test_success", user_id=str(current_user.id))
    
    return {
        "status": "success",
        "message": "Test message sent successfully! Check your Telegram.",
        "message_id": result.get("message_id")
    }


@router.delete("/me/telegram")
async def delete_telegram_config(
    current_user: Annotated[UserModel, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Delete user's Telegram configuration.
    
    Removes bot token and chat ID from the database.
    
    Args:
        current_user: Authenticated user
        db: Async database session
        
    Returns:
        Success message
    """
    current_user.telegram_bot_token = None
    current_user.telegram_chat_id = None
    current_user.telegram_enabled = False
    
    await db.commit()
    
    logger.info("telegram_config_deleted", user_id=str(current_user.id))
    
    return {
        "status": "success",
        "message": "Telegram configuration deleted successfully"
    }

