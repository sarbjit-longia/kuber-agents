"""Add cost_per_1m_cached_tokens to llm_models.

Revision ID: b4c6d8e0f2a3
Revises: a3b5d7e9f1c2
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "b4c6d8e0f2a3"
down_revision = "a3b5d7e9f1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_models",
        sa.Column("cost_per_1m_cached_tokens", sa.Float(), nullable=False, server_default="0.0"),
    )


def downgrade() -> None:
    op.drop_column("llm_models", "cost_per_1m_cached_tokens")
