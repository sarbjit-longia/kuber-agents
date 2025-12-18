"""add_llm_models_table

Revision ID: 20251218_0421
Revises: 20251218_0240
Create Date: 2025-12-18 04:21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '20251218_0421'
down_revision = '4c60eedcb074'  # add_executive_report_to_executions
branch_labels = None
depends_on = None


def upgrade():
    # Create llm_models table
    op.create_table(
        'llm_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('model_id', sa.String(), nullable=False, unique=True, index=True),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('max_tokens', sa.Integer(), nullable=False),
        sa.Column('supports_functions', sa.Boolean(), default=True),
        sa.Column('supports_vision', sa.Boolean(), default=False),
        sa.Column('cost_per_1k_input_tokens', sa.Float(), nullable=False),
        sa.Column('cost_per_1k_output_tokens', sa.Float(), nullable=False),
        sa.Column('typical_agent_cost', sa.Float(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('environment', sa.String(), default='all'),
        sa.Column('model_metadata', postgresql.JSONB, default={}),
    )
    
    # Create indexes
    op.create_index('idx_llm_models_model_id', 'llm_models', ['model_id'])
    op.create_index('idx_llm_models_is_active', 'llm_models', ['is_active'])
    
    # Seed with initial models
    op.execute("""
        INSERT INTO llm_models (
            id, model_id, provider, display_name, description,
            max_tokens, supports_functions, supports_vision,
            cost_per_1k_input_tokens, cost_per_1k_output_tokens,
            typical_agent_cost, is_active, is_default, environment, model_metadata
        ) VALUES
        -- GPT-3.5 Turbo (Default - Fast & Cheap)
        (
            gen_random_uuid(),
            'gpt-3.5-turbo',
            'openai',
            'GPT-3.5 Turbo',
            'Fast and cost-effective model for most tasks. Good for bias analysis and simple strategies.',
            16385,
            true,
            false,
            0.0005,  -- $0.0005 per 1K input tokens
            0.0015,  -- $0.0015 per 1K output tokens
            0.05,    -- Typical $0.05 per agent execution
            true,
            true,    -- Default model
            'all',   -- Available in all environments
            '{}'::jsonb
        ),
        -- GPT-4 (Premium - Best Quality)
        (
            gen_random_uuid(),
            'gpt-4',
            'openai',
            'GPT-4',
            'Most capable model with superior reasoning. Best for complex strategy generation and analysis.',
            8192,
            true,
            false,
            0.03,    -- $0.03 per 1K input tokens
            0.06,    -- $0.06 per 1K output tokens
            0.50,    -- Typical $0.50 per agent execution (10x more expensive)
            true,
            false,
            'all',   -- Available in all environments
            '{}'::jsonb
        ),
        -- GPT-4 Turbo (Balanced - Latest)
        (
            gen_random_uuid(),
            'gpt-4-turbo',
            'openai',
            'GPT-4 Turbo',
            'Latest GPT-4 model with improved speed and lower cost. Great balance of performance and price.',
            128000,
            true,
            true,    -- Supports vision
            0.01,    -- $0.01 per 1K input tokens
            0.03,    -- $0.03 per 1K output tokens
            0.20,    -- Typical $0.20 per agent execution
            true,
            false,
            'all',   -- Available in all environments
            '{}'::jsonb
        ),
        -- Local LM Studio (Free - For Testing - DEVELOPMENT ONLY)
        (
            gen_random_uuid(),
            'lmstudio-local',
            'local',
            'LM Studio (Local)',
            'Local LLM via LM Studio. Free but requires local setup. Good for development and testing.',
            4096,
            true,
            false,
            0.0,     -- Free
            0.0,     -- Free
            0.0,     -- Free
            true,
            false,
            'development',  -- ⚠️ Only available in development environment
            '{"requires_local_setup": true, "quality": "varies"}'::jsonb
        );
    """)


def downgrade():
    op.drop_index('idx_llm_models_is_active', table_name='llm_models')
    op.drop_index('idx_llm_models_model_id', table_name='llm_models')
    op.drop_table('llm_models')
