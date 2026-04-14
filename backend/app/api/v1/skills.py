"""
Skill catalog API endpoints.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.skill import SkillDetail, SkillSummary
from app.services.skill_registry import skill_registry


router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=List[SkillSummary])
async def list_skills(agent_type: Optional[str] = Query(default=None)) -> List[SkillSummary]:
    return skill_registry.list_skills(agent_type=agent_type)


@router.get("/{skill_id}", response_model=SkillDetail)
async def get_skill(skill_id: str) -> SkillDetail:
    skill = skill_registry.get_skill(skill_id)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_id}' not found",
        )
    return skill
