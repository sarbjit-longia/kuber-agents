"""
Strategy marketplace service layer.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import Pipeline as PipelineModel
from app.models.strategy import Strategy, StrategyVote
from app.schemas.pipeline import PipelineCreate
from app.schemas.strategy import StrategyCreate, StrategyReviewRequest, StrategyUpdate
from app.services.pipeline_service import create_pipeline, get_pipeline_by_id
from app.services.strategy_documents import (
    build_strategy_scaffold,
    compose_markdown,
    filter_frontmatter,
    merge_strategy_metadata,
    normalize_pipeline_spec,
    parse_frontmatter,
    remove_pipeline_brokers,
    remove_pipeline_secrets,
    slugify,
)


_FRONTMATTER_KEYS = (
    "title",
    "summary",
    "visibility",
    "category",
    "style",
    "difficulty",
    "markets",
    "timeframes",
    "tags",
    "risk_notes",
    "pipeline_snapshot_version",
)


def _pipeline_snapshot_from_model(pipeline: PipelineModel, *, scrub_secrets: bool = False) -> Dict[str, Any]:
    config = deepcopy(pipeline.config or {})
    if scrub_secrets:
        config = remove_pipeline_secrets(config)
    snapshot = {
        "name": pipeline.name,
        "description": pipeline.description,
        "config": config,
        "trigger_mode": pipeline.trigger_mode.value if hasattr(pipeline.trigger_mode, "value") else str(pipeline.trigger_mode),
        "scanner_id": str(pipeline.scanner_id) if pipeline.scanner_id else None,
        "signal_subscriptions": deepcopy(pipeline.signal_subscriptions or []),
        "notification_enabled": pipeline.notification_enabled,
        "notification_events": deepcopy(pipeline.notification_events or []),
        "require_approval": pipeline.require_approval,
        "approval_modes": deepcopy(pipeline.approval_modes or []),
        "approval_timeout_minutes": pipeline.approval_timeout_minutes,
        "approval_channels": deepcopy(pipeline.approval_channels or []),
        "schedule_enabled": pipeline.schedule_enabled,
        "schedule_start_time": pipeline.schedule_start_time,
        "schedule_end_time": pipeline.schedule_end_time,
        "schedule_days": deepcopy(pipeline.schedule_days or []),
        "liquidate_on_deactivation": pipeline.liquidate_on_deactivation,
    }
    return remove_pipeline_brokers(snapshot)


def _strategy_spec_from_pipeline(pipeline: PipelineModel) -> Dict[str, Any]:
    snapshot = _pipeline_snapshot_from_model(pipeline, scrub_secrets=True)
    return normalize_pipeline_spec(
        {
            "pipeline": snapshot,
            "source": {
                "pipeline_id": str(pipeline.id),
                "exported_at": datetime.utcnow().isoformat(),
            },
        }
    )


def _build_strategy_metadata(payload: StrategyCreate | StrategyUpdate, pipeline_spec: Dict[str, Any]) -> Dict[str, Any]:
    input_data = payload.model_dump(exclude_unset=True)
    markdown = input_data.get("markdown_content")
    body_markdown = input_data.get("body_markdown")

    parsed_frontmatter, parsed_body = parse_frontmatter(markdown or "")
    defaults = {
        "title": input_data.get("title") or parsed_frontmatter.get("title") or "Untitled Strategy",
        "summary": input_data.get("summary") or parsed_frontmatter.get("summary"),
        "visibility": input_data.get("visibility") or parsed_frontmatter.get("visibility") or "private",
        "category": input_data.get("category") or parsed_frontmatter.get("category"),
        "style": input_data.get("style") or parsed_frontmatter.get("style"),
        "difficulty": input_data.get("difficulty") or parsed_frontmatter.get("difficulty"),
        "tags": input_data.get("tags") or parsed_frontmatter.get("tags") or [],
        "markets": input_data.get("markets") or parsed_frontmatter.get("markets") or [],
        "timeframes": input_data.get("timeframes") or parsed_frontmatter.get("timeframes") or [],
        "risk_notes": input_data.get("risk_notes") or parsed_frontmatter.get("risk_notes"),
        "pipeline_snapshot_version": 1,
    }
    metadata = merge_strategy_metadata(input_data, parsed_frontmatter, defaults=defaults)
    final_body = body_markdown if body_markdown is not None else parsed_body
    if not final_body.strip():
        final_body = "" if pipeline_spec.get("pipeline") else build_strategy_scaffold(
            metadata["title"], metadata.get("summary")
        )
    metadata["body_markdown"] = final_body
    metadata["markdown_content"] = compose_markdown(filter_frontmatter(metadata, _FRONTMATTER_KEYS), final_body)
    metadata["frontmatter"] = filter_frontmatter(metadata, _FRONTMATTER_KEYS)
    metadata["normalized_spec"] = pipeline_spec
    return metadata


async def get_strategy_by_id(db: AsyncSession, strategy_id: UUID) -> Optional[Strategy]:
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    return result.scalar_one_or_none()


async def get_strategy_for_user(db: AsyncSession, strategy_id: UUID, user_id: UUID) -> Optional[Strategy]:
    strategy = await get_strategy_by_id(db, strategy_id)
    if not strategy:
        return None
    if strategy.user_id != user_id and strategy.publication_status != "published":
        return None
    return strategy


async def list_marketplace_strategies(
    db: AsyncSession,
    *,
    q: Optional[str] = None,
    sort: str = "most_voted",
    limit: int = 24,
) -> list[Strategy]:
    stmt = select(Strategy).where(Strategy.visibility == "public", Strategy.publication_status == "published")
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where((Strategy.title.ilike(like)) | (Strategy.summary.ilike(like)))
    if sort == "most_used":
        stmt = stmt.order_by(Strategy.use_count.desc(), Strategy.updated_at.desc())
    elif sort == "newest":
        stmt = stmt.order_by(Strategy.published_at.desc().nullslast(), Strategy.created_at.desc())
    else:
        stmt = stmt.order_by(Strategy.vote_count.desc(), Strategy.updated_at.desc())
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_user_strategies(db: AsyncSession, user_id: UUID) -> list[Strategy]:
    result = await db.execute(
        select(Strategy).where(Strategy.user_id == user_id).order_by(Strategy.updated_at.desc())
    )
    return list(result.scalars().all())


async def list_pending_review_strategies(db: AsyncSession) -> list[Strategy]:
    result = await db.execute(
        select(Strategy)
        .where(Strategy.publication_status == "pending_review")
        .order_by(Strategy.submitted_at.desc().nullslast(), Strategy.updated_at.desc())
    )
    return list(result.scalars().all())


async def delete_strategy_for_user(
    db: AsyncSession,
    *,
    strategy: Strategy,
    user_id: UUID,
) -> None:
    if strategy.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    await db.delete(strategy)
    await db.commit()


async def create_strategy_from_payload(
    db: AsyncSession,
    *,
    user_id: UUID,
    payload: StrategyCreate,
) -> Strategy:
    source_pipeline = None
    pipeline_spec = normalize_pipeline_spec(payload.normalized_spec)
    if payload.source_pipeline_id:
        source_pipeline = await get_pipeline_by_id(db, payload.source_pipeline_id, user_id)
        if not source_pipeline:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source pipeline not found")
        pipeline_spec = _strategy_spec_from_pipeline(source_pipeline)

    metadata = _build_strategy_metadata(payload, pipeline_spec)
    strategy = Strategy(
        user_id=user_id,
        source_pipeline_id=source_pipeline.id if source_pipeline else payload.source_pipeline_id,
        title=metadata["title"],
        slug=slugify(metadata["title"]),
        summary=metadata.get("summary"),
        visibility=metadata.get("visibility", "private"),
        category=metadata.get("category"),
        style=metadata.get("style"),
        difficulty=metadata.get("difficulty"),
        tags=metadata.get("tags", []),
        markets=metadata.get("markets", []),
        timeframes=metadata.get("timeframes", []),
        risk_notes=metadata.get("risk_notes"),
        markdown_content=metadata["markdown_content"],
        body_markdown=metadata["body_markdown"],
        frontmatter=metadata["frontmatter"],
        normalized_spec=metadata["normalized_spec"],
    )
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)
    return strategy


async def update_strategy_from_payload(
    db: AsyncSession,
    *,
    strategy: Strategy,
    user_id: UUID,
    payload: StrategyUpdate,
) -> Strategy:
    if strategy.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    pipeline_spec = normalize_pipeline_spec(payload.normalized_spec or strategy.normalized_spec)
    source_pipeline_id = payload.source_pipeline_id if payload.source_pipeline_id is not None else strategy.source_pipeline_id
    if source_pipeline_id:
        source_pipeline = await get_pipeline_by_id(db, source_pipeline_id, user_id)
        if source_pipeline:
            pipeline_spec = _strategy_spec_from_pipeline(source_pipeline)
            strategy.source_pipeline_id = source_pipeline.id

    metadata = _build_strategy_metadata(payload, pipeline_spec)
    for field in ("title", "summary", "visibility", "category", "style", "difficulty", "risk_notes"):
        value = metadata.get(field)
        if value is not None:
            setattr(strategy, field, value)
    strategy.slug = slugify(metadata["title"])
    strategy.tags = metadata.get("tags", strategy.tags)
    strategy.markets = metadata.get("markets", strategy.markets)
    strategy.timeframes = metadata.get("timeframes", strategy.timeframes)
    strategy.markdown_content = metadata["markdown_content"]
    strategy.body_markdown = metadata["body_markdown"]
    strategy.frontmatter = metadata["frontmatter"]
    strategy.normalized_spec = metadata["normalized_spec"]
    strategy.current_version += 1

    if strategy.publication_status == "published":
        strategy.publication_status = "draft"

    await db.commit()
    await db.refresh(strategy)
    return strategy


async def submit_strategy_for_review(db: AsyncSession, *, strategy: Strategy, user_id: UUID) -> Strategy:
    if strategy.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    if not strategy.normalized_spec.get("is_runnable"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strategy needs a pipeline snapshot before it can be submitted",
        )
    strategy.publication_status = "pending_review"
    strategy.submitted_at = datetime.utcnow()
    await db.commit()
    await db.refresh(strategy)
    return strategy


async def review_strategy_submission(
    db: AsyncSession,
    *,
    strategy: Strategy,
    review: StrategyReviewRequest,
) -> Strategy:
    strategy.review_notes = review.review_notes
    if review.approved:
        strategy.publication_status = "published"
        strategy.visibility = "public"
        strategy.published_version = strategy.current_version
        strategy.published_markdown_content = strategy.markdown_content
        strategy.published_frontmatter = strategy.frontmatter
        strategy.published_normalized_spec = strategy.normalized_spec
        strategy.published_at = datetime.utcnow()
    else:
        strategy.publication_status = "rejected"
    await db.commit()
    await db.refresh(strategy)
    return strategy


async def toggle_strategy_vote(db: AsyncSession, *, strategy: Strategy, user_id: UUID) -> bool:
    existing = await db.execute(
        select(StrategyVote).where(StrategyVote.strategy_id == strategy.id, StrategyVote.user_id == user_id)
    )
    vote = existing.scalar_one_or_none()
    if vote:
        await db.execute(delete(StrategyVote).where(StrategyVote.id == vote.id))
        strategy.vote_count = max(0, strategy.vote_count - 1)
        has_voted = False
    else:
        db.add(StrategyVote(strategy_id=strategy.id, user_id=user_id))
        strategy.vote_count += 1
        has_voted = True
    await db.commit()
    return has_voted


async def user_has_voted(db: AsyncSession, *, strategy_id: UUID, user_id: UUID) -> bool:
    result = await db.execute(
        select(func.count()).select_from(StrategyVote).where(
            StrategyVote.strategy_id == strategy_id, StrategyVote.user_id == user_id
        )
    )
    return bool(result.scalar() or 0)


async def create_pipeline_from_strategy(
    db: AsyncSession,
    *,
    strategy: Strategy,
    user_id: UUID,
) -> PipelineModel:
    pipeline_spec = (
        strategy.normalized_spec.get("private_pipeline")
        if strategy.user_id == user_id and strategy.normalized_spec.get("private_pipeline")
        else strategy.normalized_spec.get("pipeline")
    ) or {}
    if not pipeline_spec.get("config"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Strategy is not runnable yet")

    pipeline_spec = remove_pipeline_brokers(remove_pipeline_secrets(deepcopy(pipeline_spec)))

    pipeline_create = PipelineCreate(
        name=pipeline_spec.get("name") or strategy.title,
        description=pipeline_spec.get("description") if pipeline_spec.get("description") is not None else strategy.summary,
        config=deepcopy(pipeline_spec["config"]),
        trigger_mode=pipeline_spec.get("trigger_mode", "periodic"),
        scanner_id=pipeline_spec.get("scanner_id"),
        signal_subscriptions=deepcopy(pipeline_spec.get("signal_subscriptions") or []),
        notification_enabled=pipeline_spec.get("notification_enabled", False),
        notification_events=deepcopy(pipeline_spec.get("notification_events") or []),
        require_approval=pipeline_spec.get("require_approval", False),
        approval_modes=deepcopy(pipeline_spec.get("approval_modes") or []),
        approval_timeout_minutes=pipeline_spec.get("approval_timeout_minutes", 15),
        approval_channels=deepcopy(pipeline_spec.get("approval_channels") or []),
        schedule_enabled=pipeline_spec.get("schedule_enabled", False),
        schedule_start_time=pipeline_spec.get("schedule_start_time"),
        schedule_end_time=pipeline_spec.get("schedule_end_time"),
        schedule_days=deepcopy(pipeline_spec.get("schedule_days") or []),
        liquidate_on_deactivation=pipeline_spec.get("liquidate_on_deactivation", False),
    )
    pipeline = await create_pipeline(db, pipeline_create, user_id)
    strategy.use_count += 1
    await db.commit()
    await db.refresh(strategy)
    return pipeline


async def export_pipeline_as_strategy(
    db: AsyncSession,
    *,
    pipeline: PipelineModel,
    user_id: UUID,
) -> Strategy:
    public_snapshot = _pipeline_snapshot_from_model(pipeline, scrub_secrets=True)
    payload = StrategyCreate(
        title=pipeline.name,
        summary=pipeline.description or "Exported from a configured trading pipeline.",
        visibility="private",
        category="pipeline-export",
        tags=["exported"],
        body_markdown="",
        normalized_spec=_strategy_spec_from_pipeline(pipeline),
        source_pipeline_id=pipeline.id,
    )
    return await create_strategy_from_payload(db, user_id=user_id, payload=payload)
