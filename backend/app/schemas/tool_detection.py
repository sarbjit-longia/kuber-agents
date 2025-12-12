"""
Schemas for Tool Detection API
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ValidateInstructionsRequest(BaseModel):
    """Request to validate agent instructions and detect tools."""
    
    instructions: str = Field(
        ...,
        description="User's strategy instructions in plain text",
        min_length=10,
        max_length=10000
    )
    
    agent_type: str = Field(
        default="strategy_agent",
        description="Type of agent (strategy_agent, bias_agent, risk_manager_agent, trade_manager_agent)",
        pattern="^(strategy_agent|bias_agent|risk_manager_agent|trade_manager_agent|market_data_agent|time_trigger)$"
    )


class DetectedTool(BaseModel):
    """Information about a detected tool."""
    
    tool: str = Field(..., description="Tool name")
    params: Dict[str, Any] = Field(..., description="Tool parameters")
    reasoning: str = Field(..., description="Why this tool was selected")
    cost: float = Field(..., description="Cost per execution in USD")
    category: str = Field(..., description="Tool category (ict, indicator, price_action)")


class ValidateInstructionsResponse(BaseModel):
    """Response from instruction validation."""
    
    status: str = Field(
        ...,
        description="Status: 'success', 'partial', or 'error'",
        pattern="^(success|partial|error)$"
    )
    
    message: Optional[str] = Field(
        None,
        description="Human-readable message (for errors/warnings)"
    )
    
    tools: List[DetectedTool] = Field(
        default_factory=list,
        description="List of detected tools"
    )
    
    unsupported: List[str] = Field(
        default_factory=list,
        description="List of unsupported features mentioned in instructions"
    )
    
    total_cost: float = Field(
        ...,
        description="Total estimated cost per execution (tools only)"
    )
    
    llm_cost: Optional[float] = Field(
        None,
        description="LLM API cost for detection"
    )
    
    summary: Optional[str] = Field(
        None,
        description="Brief summary of the strategy"
    )
    
    confidence: Optional[float] = Field(
        None,
        description="Confidence score (0-1) for tool detection accuracy"
    )
    
    suggestions: Optional[str] = Field(
        None,
        description="Suggestions for unsupported features"
    )


class ToolInfo(BaseModel):
    """Information about an available tool."""
    
    name: str
    description: str
    category: str
    pricing: float
    parameters: Dict[str, Any]


class AvailableToolsResponse(BaseModel):
    """Response listing all available tools."""
    
    tools: List[ToolInfo]
    total_count: int
    categories: List[str]

