"""
API Dependencies

Common dependencies used across API endpoints.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.config import settings
from app.models.user import User

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from JWT token.
    
    Args:
        credentials: HTTP Bearer token
        db: Database session
        
    Returns:
        Current user
        
    Raises:
        HTTPException: If authentication fails
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user


async def get_current_user_ws(token: str) -> User:
    """
    Get the current authenticated user from JWT token (for WebSocket).
    
    This is a separate function because WebSocket connections can't use Depends().
    
    Args:
        token: JWT token string
        
    Returns:
        Current user
        
    Raises:
        Exception: If authentication fails
    """
    from app.database import SessionLocal
    
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise Exception("Invalid token")
    except JWTError as e:
        raise Exception(f"Token validation failed: {str(e)}")
    
    # Create sync session for WebSocket
    db = SessionLocal()
    try:
        result = db.query(User).filter(User.id == user_id).first()
        
        if result is None:
            raise Exception("User not found")
        
        if not result.is_active:
            raise Exception("Inactive user")
        
        return result
    finally:
        db.close()

