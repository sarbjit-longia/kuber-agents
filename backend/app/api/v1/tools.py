"""
Tools API Endpoints

Endpoints for discovering and managing tools.
"""
from fastapi import APIRouter, HTTPException, status
from typing import List, Optional

from app.tools import get_registry
from app.schemas.tool import ToolMetadata
import structlog


logger = structlog.get_logger()
router = APIRouter(prefix="/tools", tags=["Tools"])


@router.get("/", response_model=List[ToolMetadata])
async def list_tools(category: Optional[str] = None):
    """
    List all available tools.
    
    Args:
        category: Optional category filter (broker, notifier, validator, data, etc.)
        
    Returns:
        List of tool metadata objects
    """
    registry = get_registry()
    tools = registry.list_tools(category=category)
    
    logger.info("tools_list_requested", category=category, count=len(tools))
    
    return tools


@router.get("/category/{category}", response_model=List[ToolMetadata])
async def get_tools_by_category(category: str):
    """
    Get all tools in a specific category.
    
    Args:
        category: Tool category (broker, notifier, validator, data, etc.)
        
    Returns:
        List of tool metadata for tools in that category
    """
    registry = get_registry()
    tools = registry.get_tools_by_category(category)
    
    logger.info("tools_by_category_requested", category=category, count=len(tools))
    
    return tools


@router.get("/{tool_type}", response_model=ToolMetadata)
async def get_tool_metadata(tool_type: str):
    """
    Get metadata for a specific tool.
    
    Args:
        tool_type: Tool type identifier
        
    Returns:
        Tool metadata
        
    Raises:
        HTTPException: If tool not found
    """
    registry = get_registry()
    metadata = registry.get_metadata(tool_type)
    
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool type '{tool_type}' not found"
        )
    
    logger.info("tool_metadata_requested", tool_type=tool_type)
    
    return metadata

