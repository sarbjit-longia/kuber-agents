"""
Agent API Endpoints

Endpoints for discovering and managing agents.
"""
from typing import List
from fastapi import APIRouter, HTTPException, status, Depends
import structlog
import os
from sqlalchemy.orm import Session

from app.agents import get_registry
from app.schemas.pipeline_state import AgentMetadata
from app.schemas.tool_detection import (
    ValidateInstructionsRequest,
    ValidateInstructionsResponse,
    AvailableToolsResponse,
    ToolInfo
)
from app.services.tool_detection_service import ToolDetectionService
from app.tools.strategy_tools_registry import STRATEGY_TOOL_REGISTRY
from app.api.dependencies import get_current_user
from app.models.user import User
from app.services.model_registry import model_registry
from app.database import SessionLocal

logger = structlog.get_logger()

router = APIRouter(prefix="/agents", tags=["agents"])


def _inject_model_choices(metadata: AgentMetadata, db: Session) -> AgentMetadata:
    """
    Dynamically inject available model choices into agent config schema.
    
    Args:
        metadata: Agent metadata with potentially hardcoded model enum
        db: Database session
        
    Returns:
        Updated metadata with dynamic model choices from registry
    """
    # Check if this agent has a "model" field in config
    if metadata.config_schema and metadata.config_schema.properties:
        if "model" in metadata.config_schema.properties:
            # Get available models from registry
            model_choices = model_registry.get_model_choices_for_schema(db)
            
            # Update the enum with live data from database
            metadata.config_schema.properties["model"]["enum"] = model_choices
            
            logger.debug(
                "injected_model_choices",
                agent_type=metadata.agent_type,
                model_count=len(model_choices),
                models=model_choices
            )
    
    return metadata


@router.get("", response_model=List[AgentMetadata])
async def list_agents():
    """
    Get list of all available agents with their metadata.
    
    This endpoint is used by the frontend to discover available agents
    and generate configuration forms dynamically. Model choices are
    dynamically populated from the model registry database.
    
    Returns:
        List of agent metadata with live model choices
    """
    registry = get_registry()
    agents = registry.list_all_metadata()
    
    # Inject dynamic model choices
    db = SessionLocal()
    try:
        agents = [_inject_model_choices(agent, db) for agent in agents]
    finally:
        db.close()
    
    return agents


@router.get("/category/{category}", response_model=List[AgentMetadata])
async def list_agents_by_category(category: str):
    """
    Get all agents in a specific category.
    
    Model choices are dynamically populated from the model registry database.
    
    Args:
        category: Category name (trigger, data, analysis, risk, execution, reporting)
        
    Returns:
        List of agent metadata in that category with live model choices
    """
    registry = get_registry()
    agents = registry.list_agents_by_category(category)
    
    if not agents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No agents found in category: {category}"
        )
    
    # Inject dynamic model choices
    db = SessionLocal()
    try:
        agents = [_inject_model_choices(agent, db) for agent in agents]
    finally:
        db.close()
    
    return agents


@router.get("/{agent_type}", response_model=AgentMetadata)
async def get_agent_metadata(agent_type: str):
    """
    Get metadata for a specific agent type.
    
    Model choices are dynamically populated from the model registry database.
    
    Args:
        agent_type: Type of agent
        
    Returns:
        Agent metadata with live model choices
        
    Raises:
        HTTPException: If agent type not found
    """
    registry = get_registry()
    
    try:
        metadata = registry.get_metadata(agent_type)
        
        # Inject dynamic model choices
        db = SessionLocal()
        try:
            metadata = _inject_model_choices(metadata, db)
        finally:
            db.close()
        
        return metadata
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent type not found: {agent_type}"
        )


@router.post("/validate-instructions", response_model=ValidateInstructionsResponse)
async def validate_instructions(
    request: ValidateInstructionsRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Validate agent instructions and auto-detect required tools.
    
    This endpoint analyzes user-provided strategy instructions and uses
    LLM function calling to automatically determine which tools are needed.
    
    Args:
        request: Instructions and agent type
        current_user: Authenticated user
        
    Returns:
        Detected tools, cost estimate, and unsupported features
        
    Example:
        POST /api/v1/agents/validate-instructions
        {
            "instructions": "Buy when bullish FVG forms in discount zone",
            "agent_type": "strategy"
        }
        
        Response:
        {
            "status": "success",
            "tools": [
                {
                    "tool": "fvg_detector",
                    "params": {"timeframe": "1h"},
                    "cost": 0.01
                },
                {
                    "tool": "premium_discount",
                    "params": {"range_period": "daily"},
                    "cost": 0.01
                }
            ],
            "total_cost": 0.02,
            "summary": "ICT-based buy setup"
        }
    """
    
    try:
        # Get OpenAI API key from environment
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI API key not configured"
            )
        
        # Initialize detection service
        detection_service = ToolDetectionService(
            openai_api_key=openai_api_key,
            model="gpt-4"
        )
        
        # Detect tools
        result = await detection_service.detect_tools(
            instructions=request.instructions,
            agent_type=request.agent_type
        )
        
        logger.info(
            "instructions_validated",
            user_id=current_user.id,
            agent_type=request.agent_type,
            status=result["status"],
            num_tools=len(result.get("tools", [])),
            total_cost=result.get("total_cost", 0.0)
        )
        
        return ValidateInstructionsResponse(**result)
        
    except Exception as e:
        logger.error("instruction_validation_failed", error=str(e), user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation failed: {str(e)}"
        )


@router.get("/tools/available", response_model=AvailableToolsResponse)
async def get_available_tools(current_user: User = Depends(get_current_user)):
    """
    Get list of all available strategy tools.
    
    Returns information about all tools that can be auto-detected
    from user instructions.
    
    Returns:
        List of available tools with descriptions and pricing
    """
    
    tools = []
    categories = set()
    
    for tool_name, tool_def in STRATEGY_TOOL_REGISTRY.items():
        function = tool_def.get("function", {})
        category = tool_def.get("category", "unknown")
        categories.add(category)
        
        tools.append(ToolInfo(
            name=tool_name,
            description=function.get("description", ""),
            category=category,
            pricing=tool_def.get("pricing", 0.0),
            parameters=function.get("parameters", {})
        ))
    
    return AvailableToolsResponse(
        tools=tools,
        total_count=len(tools),
        categories=sorted(list(categories))
    )

