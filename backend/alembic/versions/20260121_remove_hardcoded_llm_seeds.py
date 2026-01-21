"""Remove hardcoded LLM model seeds from migration (use seed file instead)

This migration removes the hardcoded INSERT statements from the llm_models table creation.
Going forward, LLM models should be populated using the seed_database.py script.

Revision ID: 20260121_remove_seeds
Revises: 20251218_0533
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260121_remove_seeds'
down_revision = '20251218_0533'
branch_labels = None
depends_on = None


def upgrade():
    """
    This migration intentionally does nothing.
    
    The old migration (20251218_0421) had hardcoded INSERT statements.
    We've now moved to a cleaner approach using seed_database.py.
    
    This migration serves as documentation that we've changed our approach.
    Run `python seed_database.py` after migrations to populate LLM models.
    """
    pass


def downgrade():
    """No downgrade needed."""
    pass
