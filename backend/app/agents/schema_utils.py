"""
Agent Schema Utilities - Helper functions for agent configuration schemas
"""
from typing import Dict, Any


def add_standard_fields(properties: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add standard fields (instructions, strategy_document) to agent config schema properties.
    
    These fields are added to ALL agents to support LLM-powered instruction-based execution.
    
    Args:
        properties: Existing agent-specific configuration properties
        
    Returns:
        Updated properties dict with standard fields added
    """
    
    standard_fields = {
        "instructions": {
            "type": "string",
            "title": "Agent Instructions",
            "description": "Describe what this agent should do in plain English. The agent will use attached tools and LLM reasoning to execute your instructions.",
            "format": "textarea",
            "default": ""
        },
        "strategy_document_url": {
            "type": "string",
            "title": "Strategy Document (Optional)",
            "description": "URL to uploaded strategy document (PDF). Upload via /api/v1/files/upload",
            "format": "hidden",  # Hidden field, set by frontend after upload
            "default": ""
        }
    }
    
    # Add standard fields at the beginning
    return {**standard_fields, **properties}


def get_base_config_schema() -> Dict[str, Any]:
    """
    Get base configuration schema structure with standard fields.
    
    Returns:
        Base schema dict
    """
    return {
        "type": "object",
        "properties": add_standard_fields({}),
        "required": []
    }

