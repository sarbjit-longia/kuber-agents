"""
LLM Model Registry - Database models for LLM providers and pricing

Stores information about available LLM models, their pricing, and capabilities.
"""
from sqlalchemy import Column, String, Float, Boolean, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import uuid


class LLMModel(Base):
    """
    LLM Model registry table.
    
    Stores information about available LLM models for agents to use,
    including pricing information for cost tracking.
    """
    __tablename__ = "llm_models"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Model identification
    model_id = Column(String, unique=True, nullable=False, index=True)  # e.g., "gpt-4", "gpt-3.5-turbo"
    provider = Column(String, nullable=False)  # e.g., "openai", "anthropic", "local"
    display_name = Column(String, nullable=False)  # e.g., "GPT-4"
    description = Column(String)
    
    # Capabilities
    max_tokens = Column(Integer, nullable=False)  # Maximum context window
    supports_functions = Column(Boolean, default=True)  # Supports function calling
    supports_vision = Column(Boolean, default=False)  # Supports image inputs
    
    # Pricing (in USD)
    cost_per_1k_input_tokens = Column(Float, nullable=False)  # Input token cost
    cost_per_1k_output_tokens = Column(Float, nullable=False)  # Output token cost
    
    # Typical execution costs (pre-calculated estimates)
    typical_agent_cost = Column(Float, nullable=False)  # Typical cost per agent execution
    
    # Availability
    is_active = Column(Boolean, default=True)  # Is this model available?
    is_default = Column(Boolean, default=False)  # Is this the default model?
    environment = Column(String, default="all")  # "development", "production", or "all"
    
    # Additional model metadata
    model_metadata = Column(JSON, default={})  # Any additional info (e.g., requires_local_setup, quality)
    
    def __repr__(self):
        return f"<LLMModel {self.model_id} (${self.typical_agent_cost:.3f}/exec)>"
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost for a specific token usage.
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            
        Returns:
            Total cost in USD
        """
        input_cost = (input_tokens / 1000) * self.cost_per_1k_input_tokens
        output_cost = (output_tokens / 1000) * self.cost_per_1k_output_tokens
        return input_cost + output_cost

