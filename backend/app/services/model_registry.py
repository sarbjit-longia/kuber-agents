"""
Model Registry Service - Manages LLM models and pricing

Provides a centralized service for looking up model information and calculating costs.
"""
import structlog
import os
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.models.llm_model import LLMModel

logger = structlog.get_logger()


class ModelRegistry:
    """
    Service for managing LLM model registry and pricing.
    
    This service provides model information and cost calculations
    without hardcoding values in agent code.
    """
    
    # In-memory cache for model data (refreshed periodically)
    _model_cache: Dict[str, LLMModel] = {}
    _default_model_id: Optional[str] = None
    
    @classmethod
    def get_model(cls, model_id: str, db: Session) -> Optional[LLMModel]:
        """
        Get model information by model ID.
        
        Args:
            model_id: Model identifier (e.g., "gpt-4")
            db: Database session
            
        Returns:
            LLMModel object or None if not found
        """
        # Check cache first
        if model_id in cls._model_cache:
            return cls._model_cache[model_id]
        
        # Query database
        model = db.query(LLMModel).filter(
            LLMModel.model_id == model_id,
            LLMModel.is_active == True
        ).first()
        
        if model:
            cls._model_cache[model_id] = model
        else:
            logger.warning("model_not_found", model_id=model_id)
        
        return model
    
    @classmethod
    def get_default_model(cls, db: Session) -> Optional[LLMModel]:
        """
        Get the default model.
        
        Args:
            db: Database session
            
        Returns:
            Default LLMModel object
        """
        model = db.query(LLMModel).filter(
            LLMModel.is_default == True,
            LLMModel.is_active == True
        ).first()
        
        if not model:
            # Fallback: get any active model
            model = db.query(LLMModel).filter(
                LLMModel.is_active == True
            ).first()
        
        return model
    
    @classmethod
    def list_available_models(cls, db: Session) -> List[LLMModel]:
        """
        List all available models for the current environment.
        
        Filters models based on the ENVIRONMENT variable:
        - development: Shows all models including local ones
        - production: Shows only production-ready models (no local/dev models)
        
        Args:
            db: Database session
            
        Returns:
            List of active LLMModel objects appropriate for current environment
        """
        # Get current environment (default to production for safety)
        current_env = os.getenv("ENVIRONMENT", "production").lower()
        
        query = db.query(LLMModel).filter(LLMModel.is_active == True)
        
        # Filter by environment
        if current_env == "development":
            # In development, show all models (environment = 'all' OR 'development')
            query = query.filter(
                (LLMModel.environment == "all") | (LLMModel.environment == "development")
            )
        else:
            # In production, only show production-ready models (environment = 'all' OR 'production')
            query = query.filter(
                (LLMModel.environment == "all") | (LLMModel.environment == "production")
            )
        
        models = query.order_by(LLMModel.display_name).all()
        
        logger.debug(
            "models_listed",
            environment=current_env,
            model_count=len(models),
            model_ids=[m.model_id for m in models]
        )
        
        return models
    
    @classmethod
    def calculate_agent_cost(
        cls,
        model_id: str,
        db: Session,
        base_cost: float = 0.0,
        estimated_input_tokens: int = 0,
        estimated_output_tokens: int = 0
    ) -> float:
        """
        Calculate total cost for an agent execution.
        
        Args:
            model_id: Model identifier
            db: Database session
            base_cost: Base cost of agent (non-LLM costs like tool usage)
            estimated_input_tokens: Estimated input tokens (optional)
            estimated_output_tokens: Estimated output tokens (optional)
            
        Returns:
            Total cost in USD
        """
        model = cls.get_model(model_id, db)
        
        if not model:
            logger.error("model_not_found_for_cost_calc", model_id=model_id)
            # Fallback to a reasonable estimate
            return base_cost + 0.10
        
        # If token estimates provided, calculate precise cost
        if estimated_input_tokens > 0 or estimated_output_tokens > 0:
            llm_cost = model.calculate_cost(estimated_input_tokens, estimated_output_tokens)
        else:
            # Use typical agent cost
            llm_cost = model.typical_agent_cost
        
        total_cost = base_cost + llm_cost
        
        logger.info(
            "agent_cost_calculated",
            model_id=model_id,
            base_cost=base_cost,
            llm_cost=llm_cost,
            total_cost=total_cost
        )
        
        return total_cost
    
    @classmethod
    def get_model_choices_for_schema(cls, db: Session) -> List[str]:
        """
        Get list of model IDs for use in agent config schemas.
        
        Args:
            db: Database session
            
        Returns:
            List of model IDs (e.g., ["gpt-3.5-turbo", "gpt-4"])
        """
        models = cls.list_available_models(db)
        return [m.model_id for m in models]
    
    @classmethod
    def clear_cache(cls):
        """Clear the in-memory model cache."""
        cls._model_cache = {}
        cls._default_model_id = None
        logger.info("model_cache_cleared")


# Singleton instance
model_registry = ModelRegistry()

