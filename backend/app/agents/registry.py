"""
Agent Registry

Central registry for all available agents.
Agents must be registered here to be discovered and used in pipelines.
"""
from typing import Dict, Type, List
import logging

from app.agents.base import BaseAgent
from app.schemas.pipeline_state import AgentMetadata


logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Registry for managing available agents.
    
    Usage:
        # Register an agent
        registry.register(MyAgent)
        
        # Get agent metadata
        metadata = registry.get_metadata("my_agent")
        
        # Create agent instance
        agent = registry.create_agent("my_agent", "agent-123", {"config": "value"})
    """
    
    def __init__(self):
        self._agents: Dict[str, Type[BaseAgent]] = {}
    
    def register(self, agent_class: Type[BaseAgent]):
        """
        Register an agent class.
        
        Args:
            agent_class: Agent class to register
        """
        metadata = agent_class.get_metadata()
        agent_type = metadata.agent_type
        
        if agent_type in self._agents:
            logger.warning(f"Agent {agent_type} already registered, overwriting")
        
        self._agents[agent_type] = agent_class
        logger.info(f"Registered agent: {agent_type} ({metadata.name})")
    
    def get_agent_class(self, agent_type: str) -> Type[BaseAgent]:
        """
        Get agent class by type.
        
        Args:
            agent_type: Type of agent
            
        Returns:
            Agent class
            
        Raises:
            KeyError: If agent type not found
        """
        if agent_type not in self._agents:
            raise KeyError(f"Agent type not found: {agent_type}")
        
        return self._agents[agent_type]
    
    def create_agent(self, agent_type: str, agent_id: str, config: dict) -> BaseAgent:
        """
        Create an agent instance.
        
        Args:
            agent_type: Type of agent to create
            agent_id: Unique ID for this agent instance
            config: Agent configuration
            
        Returns:
            Agent instance
        """
        agent_class = self.get_agent_class(agent_type)
        return agent_class(agent_id, config)
    
    def get_metadata(self, agent_type: str) -> AgentMetadata:
        """
        Get metadata for an agent type.
        
        Args:
            agent_type: Type of agent
            
        Returns:
            Agent metadata
        """
        agent_class = self.get_agent_class(agent_type)
        return agent_class.get_metadata()
    
    def list_all_metadata(self) -> List[AgentMetadata]:
        """
        Get metadata for all registered agents.
        
        Returns:
            List of agent metadata
        """
        return [agent_class.get_metadata() for agent_class in self._agents.values()]
    
    def list_agents_by_category(self, category: str) -> List[AgentMetadata]:
        """
        Get all agents in a category.
        
        Args:
            category: Category name (trigger, data, analysis, risk, execution, reporting)
            
        Returns:
            List of agent metadata in that category
        """
        return [
            metadata for metadata in self.list_all_metadata()
            if metadata.category == category
        ]
    
    def is_registered(self, agent_type: str) -> bool:
        """
        Check if an agent type is registered.
        
        Args:
            agent_type: Type of agent
            
        Returns:
            True if registered, False otherwise
        """
        return agent_type in self._agents


# Global registry instance
registry = AgentRegistry()


def get_registry() -> AgentRegistry:
    """Get the global agent registry."""
    return registry

