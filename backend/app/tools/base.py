"""
Base Tool Interface

All tools must inherit from BaseTool and implement the required methods.
Tools are utilities that agents can use to interact with external services.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import logging


logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Base exception for tool errors."""
    pass


class BaseTool(ABC):
    """
    Base class for all tools.
    
    Tools are utilities that agents use to:
    - Fetch market data
    - Execute trades
    - Send notifications
    - Access databases
    - Call external APIs
    
    Example:
        class MyTool(BaseTool):
            def execute(self, **kwargs) -> Any:
                # Tool logic here
                return result
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the tool.
        
        Args:
            config: Tool-specific configuration
        """
        self.config = config or {}
        self._validate_config()
    
    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """
        Execute the tool operation.
        
        Args:
            **kwargs: Tool-specific parameters
            
        Returns:
            Tool-specific result
            
        Raises:
            ToolError: If tool execution fails
        """
        pass
    
    def _validate_config(self):
        """
        Validate tool configuration.
        
        Override this method to add custom validation.
        
        Raises:
            ValueError: If configuration is invalid
        """
        pass
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"

