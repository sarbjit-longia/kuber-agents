"""
Strategy marketplace API endpoints.
"""
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.schemas.strategy import (
    StrategyCreate,
    StrategyListResponse,
    StrategyPipelineCreateResponse,
    StrategyRead,
    StrategyReviewRequest,
    StrategyUpdate,
    StrategyVoteResponse,
)
from app.services.strategy_service import (
    create_pipeline_from_strategy,
    create_strategy_from_payload,
    delete_strategy_for_user,
    get_strategy_by_id,
    get_strategy_for_user,
    list_marketplace_strategies,
    list_pending_review_strategies,
    list_user_strategies,
    review_strategy_submission,
    submit_strategy_for_review,
    toggle_strategy_vote,
    update_strategy_from_payload,
    user_has_voted,
)
from app.services.strategy_documents import remove_pipeline_brokers


router = APIRouter(prefix="/strategies", tags=["strategies"])


def _serialize_strategy(strategy, *, has_voted: bool = False) -> StrategyRead:
    sanitized_spec = dict(strategy.normalized_spec or {})
    sanitized_spec.pop("private_pipeline", None)
    if isinstance(sanitized_spec.get("pipeline"), dict):
        sanitized_spec["pipeline"] = remove_pipeline_brokers(sanitized_spec["pipeline"])
    serialized = {
        **strategy.__dict__,
        "normalized_spec": sanitized_spec,
    }
    data = StrategyRead.model_validate(serialized)
    data.has_voted = has_voted
    data.is_runnable = bool(sanitized_spec.get("is_runnable"))
    return data


@router.get("/marketplace", response_model=StrategyListResponse)
async def get_marketplace_strategies(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Optional[str] = Query(None),
    sort: str = Query("most_voted"),
    limit: int = Query(24, ge=1, le=100),
):
    strategies = await list_marketplace_strategies(db, q=q, sort=sort, limit=limit)
    serialized = []
    for strategy in strategies:
        serialized.append(_serialize_strategy(strategy, has_voted=await user_has_voted(db, strategy_id=strategy.id, user_id=current_user.id)))
    return {"strategies": serialized, "total": len(serialized)}


@router.get("/my", response_model=StrategyListResponse)
async def get_my_strategies(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strategies = await list_user_strategies(db, current_user.id)
    return {"strategies": [_serialize_strategy(strategy) for strategy in strategies], "total": len(strategies)}


@router.get("/admin/pending", response_model=StrategyListResponse)
async def get_admin_pending_strategies(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    strategies = await list_pending_review_strategies(db)
    return {"strategies": [_serialize_strategy(strategy) for strategy in strategies], "total": len(strategies)}


@router.post("", response_model=StrategyRead, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    payload: StrategyCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strategy = await create_strategy_from_payload(db, user_id=current_user.id, payload=payload)
    return _serialize_strategy(strategy)


@router.get("/{strategy_id}", response_model=StrategyRead)
async def get_strategy(
    strategy_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strategy = await get_strategy_for_user(db, strategy_id, current_user.id)
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return _serialize_strategy(strategy, has_voted=await user_has_voted(db, strategy_id=strategy.id, user_id=current_user.id))


@router.patch("/{strategy_id}", response_model=StrategyRead)
async def update_strategy(
    strategy_id: UUID,
    payload: StrategyUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strategy = await get_strategy_by_id(db, strategy_id)
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    updated = await update_strategy_from_payload(db, strategy=strategy, user_id=current_user.id, payload=payload)
    return _serialize_strategy(updated)


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strategy = await get_strategy_by_id(db, strategy_id)
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    await delete_strategy_for_user(db, strategy=strategy, user_id=current_user.id)
    return None


@router.post("/{strategy_id}/submit", response_model=StrategyRead)
async def submit_strategy(
    strategy_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strategy = await get_strategy_by_id(db, strategy_id)
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    updated = await submit_strategy_for_review(db, strategy=strategy, user_id=current_user.id)
    return _serialize_strategy(updated)


@router.post("/{strategy_id}/publish-review", response_model=StrategyRead)
async def review_strategy(
    strategy_id: UUID,
    review: StrategyReviewRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    strategy = await get_strategy_by_id(db, strategy_id)
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    updated = await review_strategy_submission(db, strategy=strategy, review=review)
    return _serialize_strategy(updated)


@router.post("/{strategy_id}/vote", response_model=StrategyVoteResponse)
async def vote_for_strategy(
    strategy_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strategy = await get_strategy_by_id(db, strategy_id)
    if not strategy or strategy.publication_status != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    has_voted = await toggle_strategy_vote(db, strategy=strategy, user_id=current_user.id)
    await db.refresh(strategy)
    return {"vote_count": strategy.vote_count, "has_voted": has_voted}


@router.post("/{strategy_id}/create-pipeline", response_model=StrategyPipelineCreateResponse)
async def use_strategy(
    strategy_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strategy = await get_strategy_for_user(db, strategy_id, current_user.id)
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    pipeline = await create_pipeline_from_strategy(db, strategy=strategy, user_id=current_user.id)
    return {"pipeline_id": pipeline.id}
