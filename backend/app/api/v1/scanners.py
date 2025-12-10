"""
Scanner API Endpoints

CRUD operations for managing scanners (ticker lists).
"""
from typing import List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_

from app.database import get_db
from app.core.deps import get_current_active_user
from app.models.user import User
from app.models.scanner import Scanner
from app.models.pipeline import Pipeline
from app.schemas.scanner import (
    ScannerCreate,
    ScannerUpdate,
    ScannerResponse,
    ScannerTickersResponse
)

router = APIRouter()


@router.get("/scanners", response_model=List[ScannerResponse])
async def list_scanners(
    skip: int = 0,
    limit: int = 100,
    is_active: bool = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> List[ScannerResponse]:
    """
    List all scanners for the current user.
    
    Args:
        skip: Number of records to skip (pagination)
        limit: Maximum number of records to return
        is_active: Filter by active status (optional)
        db: Database session
        current_user: Current authenticated user
        
    Returns:
        List of scanner responses with computed fields
    """
    # Build query
    query = select(Scanner).where(Scanner.user_id == current_user.id)
    
    if is_active is not None:
        query = query.where(Scanner.is_active == is_active)
    
    query = query.order_by(Scanner.created_at.desc()).offset(skip).limit(limit)
    
    # Execute query
    result = await db.execute(query)
    scanners = result.scalars().all()
    
    # Get pipeline counts for each scanner
    scanner_responses = []
    for scanner in scanners:
        # Count pipelines using this scanner
        pipeline_count_query = select(func.count(Pipeline.id)).where(
            and_(
                Pipeline.scanner_id == scanner.id,
                Pipeline.user_id == current_user.id
            )
        )
        pipeline_count_result = await db.execute(pipeline_count_query)
        pipeline_count = pipeline_count_result.scalar() or 0
        
        scanner_responses.append(
            ScannerResponse.from_db_model(scanner, pipeline_count=pipeline_count)
        )
    
    return scanner_responses


@router.post("/scanners", response_model=ScannerResponse, status_code=status.HTTP_201_CREATED)
async def create_scanner(
    scanner_data: ScannerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> ScannerResponse:
    """
    Create a new scanner.
    
    Args:
        scanner_data: Scanner creation data
        db: Database session
        current_user: Current authenticated user
        
    Returns:
        Created scanner
        
    Raises:
        HTTPException: If scanner with same name already exists
    """
    # Check for duplicate name (per user)
    result = await db.execute(
        select(Scanner).where(
            and_(
                Scanner.user_id == current_user.id,
                Scanner.name == scanner_data.name
            )
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Scanner with name '{scanner_data.name}' already exists"
        )
    
    # Create scanner
    scanner = Scanner(
        user_id=current_user.id,
        name=scanner_data.name,
        description=scanner_data.description,
        scanner_type=scanner_data.scanner_type,
        config=scanner_data.config,
        is_active=scanner_data.is_active,
        refresh_interval=scanner_data.refresh_interval
    )
    
    db.add(scanner)
    await db.commit()
    await db.refresh(scanner)
    
    return ScannerResponse.from_db_model(scanner, pipeline_count=0)


@router.get("/scanners/{scanner_id}", response_model=ScannerResponse)
async def get_scanner(
    scanner_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> ScannerResponse:
    """
    Get a scanner by ID.
    
    Args:
        scanner_id: Scanner UUID
        db: Database session
        current_user: Current authenticated user
        
    Returns:
        Scanner details
        
    Raises:
        HTTPException: If scanner not found or not owned by user
    """
    result = await db.execute(
        select(Scanner).where(
            and_(
                Scanner.id == scanner_id,
                Scanner.user_id == current_user.id
            )
        )
    )
    scanner = result.scalar_one_or_none()
    
    if not scanner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scanner {scanner_id} not found"
        )
    
    # Get pipeline count
    pipeline_count_result = await db.execute(
        select(func.count(Pipeline.id)).where(Pipeline.scanner_id == scanner_id)
    )
    pipeline_count = pipeline_count_result.scalar() or 0
    
    return ScannerResponse.from_db_model(scanner, pipeline_count=pipeline_count)


@router.patch("/scanners/{scanner_id}", response_model=ScannerResponse)
async def update_scanner(
    scanner_id: UUID,
    scanner_update: ScannerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> ScannerResponse:
    """
    Update a scanner.
    
    Args:
        scanner_id: Scanner UUID
        scanner_update: Fields to update
        db: Database session
        current_user: Current authenticated user
        
    Returns:
        Updated scanner
        
    Raises:
        HTTPException: If scanner not found or not owned by user
    """
    result = await db.execute(
        select(Scanner).where(
            and_(
                Scanner.id == scanner_id,
                Scanner.user_id == current_user.id
            )
        )
    )
    scanner = result.scalar_one_or_none()
    
    if not scanner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scanner {scanner_id} not found"
        )
    
    # Check for duplicate name if changing name
    if scanner_update.name and scanner_update.name != scanner.name:
        existing_result = await db.execute(
            select(Scanner).where(
                and_(
                    Scanner.user_id == current_user.id,
                    Scanner.name == scanner_update.name,
                    Scanner.id != scanner_id
                )
            )
        )
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scanner with name '{scanner_update.name}' already exists"
            )
    
    # Update fields
    update_data = scanner_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(scanner, field, value)
    
    await db.commit()
    await db.refresh(scanner)
    
    # Get pipeline count
    pipeline_count_result = await db.execute(
        select(func.count(Pipeline.id)).where(Pipeline.scanner_id == scanner_id)
    )
    pipeline_count = pipeline_count_result.scalar() or 0
    
    return ScannerResponse.from_db_model(scanner, pipeline_count=pipeline_count)


@router.delete("/scanners/{scanner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scanner(
    scanner_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Delete a scanner.
    
    Args:
        scanner_id: Scanner UUID
        db: Database session
        current_user: Current authenticated user
        
    Raises:
        HTTPException: If scanner not found, not owned, or in use by pipelines
    """
    result = await db.execute(
        select(Scanner).where(
            and_(
                Scanner.id == scanner_id,
                Scanner.user_id == current_user.id
            )
        )
    )
    scanner = result.scalar_one_or_none()
    
    if not scanner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scanner {scanner_id} not found"
        )
    
    # Check if scanner is in use
    pipeline_count_result = await db.execute(
        select(func.count(Pipeline.id)).where(Pipeline.scanner_id == scanner_id)
    )
    pipeline_count = pipeline_count_result.scalar() or 0
    
    if pipeline_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete scanner: used by {pipeline_count} pipeline(s). "
                   "Remove scanner from pipelines first."
        )
    
    # Delete scanner
    await db.delete(scanner)
    await db.commit()


@router.get("/scanners/{scanner_id}/tickers", response_model=ScannerTickersResponse)
async def get_scanner_tickers(
    scanner_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> ScannerTickersResponse:
    """
    Get the ticker list from a scanner.
    
    Args:
        scanner_id: Scanner UUID
        db: Database session
        current_user: Current authenticated user
        
    Returns:
        Scanner ticker list
        
    Raises:
        HTTPException: If scanner not found or not owned by user
    """
    result = await db.execute(
        select(Scanner).where(
            and_(
                Scanner.id == scanner_id,
                Scanner.user_id == current_user.id
            )
        )
    )
    scanner = result.scalar_one_or_none()
    
    if not scanner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scanner {scanner_id} not found"
        )
    
    tickers = scanner.get_tickers()
    
    return ScannerTickersResponse(
        scanner_id=scanner.id,
        scanner_name=scanner.name,
        tickers=tickers,
        ticker_count=len(tickers),
        last_refreshed_at=scanner.last_refreshed_at
    )


@router.get("/scanners/{scanner_id}/usage")
async def get_scanner_usage(
    scanner_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Get pipelines using this scanner.
    
    Args:
        scanner_id: Scanner UUID
        db: Database session
        current_user: Current authenticated user
        
    Returns:
        Scanner usage information
        
    Raises:
        HTTPException: If scanner not found or not owned by user
    """
    result = await db.execute(
        select(Scanner).where(
            and_(
                Scanner.id == scanner_id,
                Scanner.user_id == current_user.id
            )
        )
    )
    scanner = result.scalar_one_or_none()
    
    if not scanner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scanner {scanner_id} not found"
        )
    
    # Get pipelines using this scanner
    pipelines_result = await db.execute(
        select(Pipeline).where(
            and_(
                Pipeline.scanner_id == scanner_id,
                Pipeline.user_id == current_user.id
            )
        )
    )
    pipelines = pipelines_result.scalars().all()
    
    return {
        "scanner_id": str(scanner_id),
        "scanner_name": scanner.name,
        "pipeline_count": len(pipelines),
        "pipelines": [
            {
                "id": str(p.id),
                "name": p.name,
                "is_active": p.is_active,
                "trigger_mode": p.trigger_mode.value
            }
            for p in pipelines
        ]
    }

