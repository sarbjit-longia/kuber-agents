"""
Tool Registry

Centralized registry for discovering and managing tools.
Similar to the Agent Registry but for tools.
"""
from typing import Dict, List, Optional, Type
import structlog

from app.tools.base import BaseTool, ToolError
from app.schemas.tool import ToolMetadata


logger = structlog.get_logger()


class ToolRegistry:
    """
    Singleton registry for managing tools.
    
    Provides methods to:
    - Register tool classes
    - Discover available tools
    - Get tool metadata
    - Create tool instances
    """
    
    _instance = None
    _registry: Dict[str, Type[BaseTool]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToolRegistry, cls).__new__(cls)
        return cls._instance
    
    def register(self, tool_class: Type[BaseTool]) -> None:
        """
        Register a tool class.
        
        Args:
            tool_class: Tool class to register (must inherit from BaseTool)
            
        Raises:
            ValueError: If tool_class is not a valid BaseTool subclass
        """
        if not issubclass(tool_class, BaseTool):
            raise ValueError(f"{tool_class.__name__} must inherit from BaseTool")
        
        metadata = tool_class.get_metadata()
        tool_type = metadata.tool_type
        
        if tool_type in self._registry:
            logger.warning(
                "tool_already_registered",
                tool_type=tool_type,
                overwriting=True
            )
        
        self._registry[tool_type] = tool_class
        logger.info("tool_registered", tool_type=tool_type, name=metadata.name)
    
    def list_tools(self, category: Optional[str] = None) -> List[ToolMetadata]:
        """
        List all registered tools.
        
        Args:
            category: Optional category filter (broker, notifier, validator, data, etc.)
            
        Returns:
            List of ToolMetadata objects
        """
        tools = []
        for tool_class in self._registry.values():
            metadata = tool_class.get_metadata()
            if category is None or metadata.category == category:
                tools.append(metadata)
        
        return sorted(tools, key=lambda x: (x.category, x.name))
    
    def get_metadata(self, tool_type: str) -> Optional[ToolMetadata]:
        """
        Get metadata for a specific tool type.
        
        Args:
            tool_type: Tool type identifier
            
        Returns:
            ToolMetadata if found, None otherwise
        """
        tool_class = self._registry.get(tool_type)
        if tool_class:
            return tool_class.get_metadata()
        return None
    
    def create_tool(self, tool_type: str, config: Optional[Dict] = None) -> BaseTool:
        """
        Create an instance of a tool.
        
        Args:
            tool_type: Tool type identifier
            config: Tool-specific configuration
            
        Returns:
            Initialized tool instance
            
        Raises:
            ToolError: If tool_type is not registered or instantiation fails
        """
        tool_class = self._registry.get(tool_type)
        
        if not tool_class:
            raise ToolError(f"Unknown tool type: {tool_type}")
        
        try:
            return tool_class(config=config)
        except Exception as e:
            logger.error(
                "tool_instantiation_failed",
                tool_type=tool_type,
                error=str(e),
                exc_info=True
            )
            raise ToolError(f"Failed to create tool {tool_type}: {e}")
    
    def get_tools_by_category(self, category: str) -> List[ToolMetadata]:
        """
        Get all tools in a specific category.
        
        Args:
            category: Tool category
            
        Returns:
            List of ToolMetadata for tools in that category
        """
        return self.list_tools(category=category)
    
    def is_registered(self, tool_type: str) -> bool:
        """
        Check if a tool type is registered.
        
        Args:
            tool_type: Tool type identifier
            
        Returns:
            True if registered, False otherwise
        """
        return tool_type in self._registry
    
    def clear(self) -> None:
        """Clear all registered tools (mainly for testing)."""
        self._registry.clear()
        logger.info("tool_registry_cleared")


# Singleton instance
_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    return _registry


def register_tool(tool_class: Type[BaseTool]) -> None:
    """
    Convenience function to register a tool.
    
    Args:
        tool_class: Tool class to register
    """
    _registry.register(tool_class)

