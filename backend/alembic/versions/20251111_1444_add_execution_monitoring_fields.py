"""add_execution_monitoring_fields

Revision ID: 24be6be9d078
Revises: 655ec350a488
Create Date: 2025-11-11 14:44:48.170356

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '24be6be9d078'
down_revision = '655ec350a488'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to executions table
    op.add_column('executions', sa.Column('mode', sa.String(20), nullable=False, server_default='paper'))
    op.add_column('executions', sa.Column('logs', JSONB, nullable=True))
    op.add_column('executions', sa.Column('agent_states', JSONB, nullable=True))
    op.add_column('executions', sa.Column('cost_breakdown', JSONB, nullable=True))
    
    # Add PAUSED status to enum (if not already there)
    # Note: Adding enum values in PostgreSQL requires special handling
    op.execute("ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS 'paused'")


def downgrade() -> None:
    # Remove new columns
    op.drop_column('executions', 'cost_breakdown')
    op.drop_column('executions', 'agent_states')
    op.drop_column('executions', 'logs')
    op.drop_column('executions', 'mode')
    
    # Note: Removing enum values is complex in PostgreSQL and typically not done
    # as it could break existing data

