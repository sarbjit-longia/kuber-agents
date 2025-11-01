"""
Pydantic schemas for tool metadata and configuration.
"""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class ToolConfigSchema(BaseModel):
    """JSON Schema definition for tool configuration."""
    type: str = "object"
    title: str
    description: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    required: List[str] = Field(default_factory=list)


class ToolMetadata(BaseModel):
    """Metadata describing a tool's capabilities and configuration."""
    tool_type: str = Field(..., description="Unique identifier for the tool type")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Detailed description of what the tool does")
    category: str = Field(..., description="Tool category: broker, notifier, validator, data, etc.")
    version: str = Field(default="1.0.0", description="Tool version")
    icon: Optional[str] = Field(default="extension", description="Material icon name")
    requires_credentials: bool = Field(default=False, description="Whether tool requires API credentials")
    config_schema: ToolConfigSchema = Field(..., description="JSON schema for tool configuration")
    
    class Config:
        json_schema_extra = {
            "example": {
                "tool_type": "alpaca_broker",
                "name": "Alpaca Broker",
                "description": "Execute trades via Alpaca API",
                "category": "broker",
                "version": "1.0.0",
                "icon": "account_balance",
                "requires_credentials": True,
                "config_schema": {
                    "type": "object",
                    "title": "Alpaca Broker Configuration",
                    "properties": {
                        "account_type": {
                            "type": "string",
                            "title": "Account Type",
                            "enum": ["live", "paper"],
                            "default": "paper"
                        }
                    },
                    "required": ["account_type"]
                }
            }
        }


class ToolInstance(BaseModel):
    """Represents a configured instance of a tool attached to an agent."""
    tool_type: str = Field(..., description="Type of tool")
    enabled: bool = Field(default=True, description="Whether the tool is enabled")
    config: Dict[str, Any] = Field(default_factory=dict, description="Tool-specific configuration")
    
    class Config:
        json_schema_extra = {
            "example": {
                "tool_type": "alpaca_broker",
                "enabled": True,
                "config": {
                    "account_type": "paper"
                }
            }
        }

