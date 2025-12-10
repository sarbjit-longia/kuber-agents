"""
User API endpoints.

Handles user profile and subscription information.
"""
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserSubscriptionInfo
from app.core.deps import get_current_active_user
from app.subscriptions.enforcement import get_subscription_info


router = APIRouter(prefix="/users", tags=["users"])


def get_sync_db():
    """Get synchronous database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/me/subscription", response_model=UserSubscriptionInfo)
def get_my_subscription(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_sync_db)]
):
    """
    Get current user's subscription information.
    
    Returns detailed subscription info including tier, limits, and usage.
    
    Args:
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Subscription information
    """
    return get_subscription_info(current_user, db)
