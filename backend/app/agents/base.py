"""
Base Agent Class

All agents must inherit from BaseAgent and implement the required methods.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging
from datetime import datetime

from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentReportMetric


logger = logging.getLogger(__name__)


class AgentError(Exception):
    """Base exception for agent errors."""
    pass


class InsufficientDataError(AgentError):
    """Raised when agent doesn't have sufficient data to process."""
    pass


class TriggerNotMetException(AgentError):
    """
    Raised when a trigger agent determines the trigger condition is not met.
    
    This is not an error condition - it's normal operation.
    The pipeline execution should pause and check again later.
    """
    pass


class BudgetExceededException(AgentError):
    """Raised when user's budget limit is exceeded."""
    pass


class AgentProcessingError(AgentError):
    """Generic agent processing error."""
    pass


class BaseAgent(ABC):
    """
    Base class for all agents.
    
    All agents must:
    1. Inherit from this class
    2. Implement get_metadata() classmethod
    3. Implement process() method
    4. Define their config_schema in metadata
    
    Example:
        class MyAgent(BaseAgent):
            @classmethod
            def get_metadata(cls) -> AgentMetadata:
                return AgentMetadata(
                    agent_type="my_agent",
                    name="My Agent",
                    description="Does something cool",
                    category="analysis",
                    version="1.0.0",
                    icon="analytics",
                    config_schema=AgentConfigSchema(...)
                )
            
            def process(self, state: PipelineState) -> PipelineState:
                # Your agent logic here
                return state
    """
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        """
        Initialize the agent.
        
        Args:
            agent_id: Unique identifier for this agent instance
            config: Agent-specific configuration
        """
        self.agent_id = agent_id
        self.config = config
        self.metadata = self.get_metadata()
        self.logger = logger  # Instance logger for convenience
        
        # Validate configuration
        self._validate_config()
        
        logger.info(f"Initialized agent: {self.agent_id} ({self.metadata.name})")
    
    @classmethod
    @abstractmethod
    def get_metadata(cls) -> AgentMetadata:
        """
        Return metadata describing this agent.
        
        This is a classmethod so metadata can be retrieved without instantiating the agent.
        
        Returns:
            AgentMetadata object with agent information
        """
        pass
    
    @abstractmethod
    def process(self, state: PipelineState) -> PipelineState:
        """
        Process the pipeline state and return updated state.
        
        This is the main method that agents implement to perform their logic.
        Agents should:
        1. Validate they have the data they need
        2. Perform their analysis/action
        3. Update the state with their results
        4. Add logs and track costs
        5. Return the updated state
        
        Args:
            state: Current pipeline state
            
        Returns:
            Updated pipeline state
            
        Raises:
            InsufficientDataError: If required data is missing
            TriggerNotMetException: If trigger condition not met (trigger agents only)
            BudgetExceededException: If budget limit exceeded
            AgentProcessingError: If processing fails
        """
        pass
    
    def _validate_config(self):
        """
        Validate agent configuration against schema and apply defaults.
        
        Raises:
            ValueError: If configuration is invalid
        """
        schema = self.metadata.config_schema
        required_fields = schema.required
        
        # Apply defaults for missing fields
        for field_name, field_schema in schema.properties.items():
            if field_name not in self.config and "default" in field_schema:
                self.config[field_name] = field_schema["default"]
        
        # Validate required fields
        for field in required_fields:
            if field not in self.config:
                raise ValueError(
                    f"Missing required configuration field: {field} for agent {self.agent_id}"
                )
    
    def validate_input(self, state: PipelineState) -> bool:
        """
        Validate that the state has required inputs for this agent.
        
        Args:
            state: Pipeline state to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Check if required timeframes are present
        if self.metadata.requires_timeframes:
            if not state.market_data:
                return False
            
            for timeframe in self.metadata.requires_timeframes:
                if timeframe not in state.market_data.timeframes:
                    return False
        
        # Check if market data is required
        if self.metadata.requires_market_data and not state.market_data:
            return False
        
        # Check if position is required
        if self.metadata.requires_position and not state.current_position:
            return False
        
        return True
    
    def log(self, state: PipelineState, message: str, level: str = "info"):
        """
        Add a log entry to the state.
        
        Args:
            state: Pipeline state
            message: Log message
            level: Log level (info, warning, error)
        """
        state.add_log(self.agent_id, message, level)
        
        # Also log to Python logger
        log_method = getattr(logger, level, logger.info)
        log_method(f"[{self.agent_id}] {message}")
    
    def track_cost(self, state: PipelineState, cost: float):
        """
        Track cost for this agent execution.
        
        Args:
            state: Pipeline state
            cost: Cost incurred
        """
        state.add_cost(self.agent_id, cost)
        self.log(state, f"Cost tracked: ${cost:.4f}")
    
    def add_error(self, state: PipelineState, error: str):
        """
        Add an error to the state.
        
        Args:
            state: Pipeline state
            error: Error message
        """
        state.errors.append(f"{self.agent_id}: {error}")
        self.log(state, f"Error: {error}", level="error")
    
    def add_warning(self, state: PipelineState, warning: str):
        """
        Add a warning to the state.
        
        Args:
            state: Pipeline state
            warning: Warning message
        """
        state.warnings.append(f"{self.agent_id}: {warning}")
        self.log(state, f"Warning: {warning}", level="warning")
    
    def record_report(
        self,
        state: PipelineState,
        title: str,
        summary: str,
        *,
        details: Optional[str] = None,
        status: str = "completed",
        metrics: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        """
        Record a structured report entry for this agent.
        """
        metric_entries = []
        if metrics:
            for name, value in metrics.items():
                if isinstance(value, AgentReportMetric):
                    metric_entries.append(value)
                else:
                    metric_entries.append(AgentReportMetric(name=name, value=value))
        
        state.add_report(
            agent_id=self.agent_id,
            agent_type=self.metadata.agent_type,
            title=title,
            summary=summary,
            details=details,
            status=status,
            metrics=metric_entries,
            data=data,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize agent to dictionary.
        
        Returns:
            Dictionary representation of the agent
        """
        return {
            "agent_id": self.agent_id,
            "agent_type": self.metadata.agent_type,
            "config": self.config,
            "metadata": self.metadata.model_dump()
        }
    
    def _load_tools(self) -> Dict[str, Any]:
        """
        Load and instantiate tools from agent configuration.
        
        Returns:
            Dict mapping tool_type to instantiated tool objects
            
        Example:
            tools = self._load_tools()
            broker = tools.get("alpaca_broker")
            if broker:
                result = broker.execute(action="buy", symbol="AAPL", quantity=100)
        """
        from app.tools import get_registry
        
        tools = {}
        tool_configs = self.config.get("tools", [])
        
        if not tool_configs:
            return tools
        
        registry = get_registry()
        
        for tool_config in tool_configs:
            tool_type = tool_config.get("tool_type")
            enabled = tool_config.get("enabled", True)
            config = tool_config.get("config", {})
            
            if not enabled:
                continue
            
            try:
                tool_instance = registry.create_tool(tool_type, config)
                tools[tool_type] = tool_instance
                self.logger.info(
                    f"Tool loaded: {tool_type} for agent {self.agent_id}"
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to load tool {tool_type} for agent {self.agent_id}: {str(e)}",
                    exc_info=True
                )
                # Continue loading other tools even if one fails
        
        return tools
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseAgent':
        """
        Deserialize agent from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            Agent instance
        """
        return cls(
            agent_id=data["agent_id"],
            config=data["config"]
        )
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.agent_id})>"

