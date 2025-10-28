"""
Agent API Endpoints

Endpoints for discovering and managing agents.
"""
from typing import List
from fastapi import APIRouter, HTTPException, status

from app.agents import get_registry
from app.schemas.pipeline_state import AgentMetadata


router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=List[AgentMetadata])
async def list_agents():
    """
    Get list of all available agents with their metadata.
    
    This endpoint is used by the frontend to discover available agents
    and generate configuration forms dynamically.
    
    Returns:
        List of agent metadata
    """
    registry = get_registry()
    return registry.list_all_metadata()


@router.get("/category/{category}", response_model=List[AgentMetadata])
async def list_agents_by_category(category: str):
    """
    Get all agents in a specific category.
    
    Args:
        category: Category name (trigger, data, analysis, risk, execution, reporting)
        
    Returns:
        List of agent metadata in that category
    """
    registry = get_registry()
    agents = registry.list_agents_by_category(category)
    
    if not agents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No agents found in category: {category}"
        )
    
    return agents


@router.get("/{agent_type}", response_model=AgentMetadata)
async def get_agent_metadata(agent_type: str):
    """
    Get metadata for a specific agent type.
    
    Args:
        agent_type: Type of agent
        
    Returns:
        Agent metadata
        
    Raises:
        HTTPException: If agent type not found
    """
    registry = get_registry()
    
    try:
        return registry.get_metadata(agent_type)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent type not found: {agent_type}"
        )

