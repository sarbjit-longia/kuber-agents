"""add_pipeline_state_column_to_executions

Revision ID: a1b2c3d4e5f6
Revises: 58e10e31a8de
Create Date: 2026-02-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '58e10e31a8de'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add pipeline_state JSONB column to executions table.
    # This stores the full PipelineState snapshot so monitoring and reconciliation
    # tasks can round-trip the state without lossy reconstruction from execution.result.
    op.add_column('executions', sa.Column('pipeline_state', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('executions', 'pipeline_state')
