"""
LLM Models Seed Data

This script seeds the database with available LLM models and their pricing.
Run this after database migrations to populate the llm_models table.

Usage:
    python -m app.seeds.llm_models
"""
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.llm_model import LLMModel
import logging

logger = logging.getLogger(__name__)


# Default LLM models with current pricing (as of Jan 2026)
DEFAULT_LLM_MODELS = [
    {
        "model_id": "gpt-3.5-turbo",
        "provider": "openai",
        "display_name": "GPT-3.5 Turbo",
        "description": "Fast and cost-effective model for most tasks",
        "max_tokens": 16385,
        "supports_functions": True,
        "supports_vision": False,
        "cost_per_1k_input_tokens": 0.0005,  # $0.50 per 1M tokens
        "cost_per_1k_output_tokens": 0.0015,  # $1.50 per 1M tokens
        "typical_agent_cost": 0.01,  # ~$0.01 per agent execution
        "is_active": True,
        "is_default": False,
        "environment": "all",
        "model_metadata": {
            "quality": "good",
            "speed": "fast",
            "recommended_for": ["risk_management", "simple_analysis", "reporting"]
        }
    },
    {
        "model_id": "gpt-4",
        "provider": "openai",
        "display_name": "GPT-4",
        "description": "Most capable model for complex reasoning",
        "max_tokens": 8192,
        "supports_functions": True,
        "supports_vision": False,
        "cost_per_1k_input_tokens": 0.03,  # $30 per 1M tokens
        "cost_per_1k_output_tokens": 0.06,  # $60 per 1M tokens
        "typical_agent_cost": 0.15,  # ~$0.15 per agent execution
        "is_active": True,
        "is_default": False,
        "environment": "all",
        "model_metadata": {
            "quality": "excellent",
            "speed": "medium",
            "recommended_for": ["strategy", "complex_analysis"]
        }
    },
    {
        "model_id": "gpt-4-turbo",
        "provider": "openai",
        "display_name": "GPT-4 Turbo",
        "description": "Faster and more cost-effective GPT-4",
        "max_tokens": 128000,
        "supports_functions": True,
        "supports_vision": True,
        "cost_per_1k_input_tokens": 0.01,  # $10 per 1M tokens
        "cost_per_1k_output_tokens": 0.03,  # $30 per 1M tokens
        "typical_agent_cost": 0.08,  # ~$0.08 per agent execution
        "is_active": True,
        "is_default": True,  # Default model
        "environment": "all",
        "model_metadata": {
            "quality": "excellent",
            "speed": "fast",
            "recommended_for": ["bias_analysis", "strategy", "all_purpose"]
        }
    },
    {
        "model_id": "gpt-4o",
        "provider": "openai",
        "display_name": "GPT-4o",
        "description": "Omni model with vision and audio capabilities",
        "max_tokens": 128000,
        "supports_functions": True,
        "supports_vision": True,
        "cost_per_1k_input_tokens": 0.005,  # $5 per 1M tokens
        "cost_per_1k_output_tokens": 0.015,  # $15 per 1M tokens
        "typical_agent_cost": 0.05,  # ~$0.05 per agent execution
        "is_active": True,
        "is_default": False,
        "environment": "all",
        "model_metadata": {
            "quality": "excellent",
            "speed": "very_fast",
            "recommended_for": ["chart_analysis", "multimodal", "fast_execution"]
        }
    },
    {
        "model_id": "gpt-4o-mini",
        "provider": "openai",
        "display_name": "GPT-4o Mini",
        "description": "Smaller, faster, and more affordable version of GPT-4o",
        "max_tokens": 128000,
        "supports_functions": True,
        "supports_vision": True,
        "cost_per_1k_input_tokens": 0.00015,  # $0.15 per 1M tokens
        "cost_per_1k_output_tokens": 0.0006,  # $0.60 per 1M tokens
        "typical_agent_cost": 0.005,  # ~$0.005 per agent execution
        "is_active": True,
        "is_default": False,
        "environment": "all",
        "model_metadata": {
            "quality": "very_good",
            "speed": "very_fast",
            "recommended_for": ["high_volume", "cost_sensitive", "quick_analysis"]
        }
    },
    {
        "model_id": "o1-preview",
        "provider": "openai",
        "display_name": "O1 Preview",
        "description": "Advanced reasoning model for complex problem-solving",
        "max_tokens": 128000,
        "supports_functions": False,
        "supports_vision": False,
        "cost_per_1k_input_tokens": 0.015,  # $15 per 1M tokens
        "cost_per_1k_output_tokens": 0.06,  # $60 per 1M tokens
        "typical_agent_cost": 0.20,  # ~$0.20 per agent execution
        "is_active": True,
        "is_default": False,
        "environment": "all",
        "model_metadata": {
            "quality": "exceptional",
            "speed": "slow",
            "recommended_for": ["complex_reasoning", "advanced_strategy"],
            "note": "Best for deep analytical tasks, slower than GPT-4"
        }
    },
    {
        "model_id": "o1-mini",
        "provider": "openai",
        "display_name": "O1 Mini",
        "description": "Smaller reasoning model for faster execution",
        "max_tokens": 128000,
        "supports_functions": False,
        "supports_vision": False,
        "cost_per_1k_input_tokens": 0.003,  # $3 per 1M tokens
        "cost_per_1k_output_tokens": 0.012,  # $12 per 1M tokens
        "typical_agent_cost": 0.04,  # ~$0.04 per agent execution
        "is_active": True,
        "is_default": False,
        "environment": "all",
        "model_metadata": {
            "quality": "excellent",
            "speed": "medium",
            "recommended_for": ["reasoning_tasks", "balanced_performance"]
        }
    },
    {
        "model_id": "lmstudio-local",
        "provider": "local",
        "display_name": "LM Studio (Local)",
        "description": "Local LLM running through LM Studio (free, but slower)",
        "max_tokens": 8192,
        "supports_functions": False,
        "supports_vision": False,
        "cost_per_1k_input_tokens": 0.0,  # Free
        "cost_per_1k_output_tokens": 0.0,  # Free
        "typical_agent_cost": 0.0,  # Free
        "is_active": True,
        "is_default": False,
        "environment": "development",
        "model_metadata": {
            "quality": "variable",
            "speed": "slow",
            "recommended_for": ["development", "testing"],
            "requires_local_setup": True,
            "note": "Requires LM Studio running locally"
        }
    }
]


def seed_llm_models(db: Session = None):
    """
    Seed the database with default LLM models.
    
    Args:
        db: Database session (if None, creates a new one)
    """
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    
    try:
        logger.info("Starting LLM models seeding...")
        
        for model_data in DEFAULT_LLM_MODELS:
            # Check if model already exists
            existing_model = db.query(LLMModel).filter(
                LLMModel.model_id == model_data["model_id"]
            ).first()
            
            if existing_model:
                # Update existing model with latest data
                for key, value in model_data.items():
                    setattr(existing_model, key, value)
                logger.info(f"✅ Updated model: {model_data['model_id']} ({model_data['display_name']})")
            else:
                # Create new model
                new_model = LLMModel(**model_data)
                db.add(new_model)
                logger.info(f"✅ Created model: {model_data['model_id']} ({model_data['display_name']})")
        
        db.commit()
        logger.info(f"✨ Successfully seeded {len(DEFAULT_LLM_MODELS)} LLM models")
        
        # Print summary
        print("\n" + "="*70)
        print("LLM MODELS SEEDED SUCCESSFULLY")
        print("="*70)
        for model_data in DEFAULT_LLM_MODELS:
            print(f"  • {model_data['display_name']:<25} ${model_data['typical_agent_cost']:.3f}/exec")
        print("="*70 + "\n")
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error seeding LLM models: {e}")
        raise
    finally:
        if should_close:
            db.close()


def main():
    """Main function to run seeding."""
    logging.basicConfig(level=logging.INFO)
    seed_llm_models()


if __name__ == "__main__":
    main()
