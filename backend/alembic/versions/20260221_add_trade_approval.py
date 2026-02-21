"""Add trade approval fields to executions and pipelines

Revision ID: a3f8d1c2e4b5
Revises: (head)
Create Date: 2026-02-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'a3f8d1c2e4b5'
down_revision = None  # will be auto-set by alembic
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add AWAITING_APPROVAL to ExecutionStatus enum
    op.execute("ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS 'AWAITING_APPROVAL'")

    # Add approval columns to executions table
    op.add_column('executions', sa.Column('approval_status', sa.String(20), nullable=True))
    op.add_column('executions', sa.Column('approval_requested_at', sa.DateTime(), nullable=True))
    op.add_column('executions', sa.Column('approval_responded_at', sa.DateTime(), nullable=True))
    op.add_column('executions', sa.Column('approval_token', sa.String(64), nullable=True))
    op.add_column('executions', sa.Column('approval_expires_at', sa.DateTime(), nullable=True))
    op.create_index('ix_executions_approval_token', 'executions', ['approval_token'], unique=True)

    # Add approval columns to pipelines table
    op.add_column('pipelines', sa.Column('require_approval', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('pipelines', sa.Column('approval_modes', sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column('pipelines', sa.Column('approval_timeout_minutes', sa.Integer(), nullable=False, server_default='15'))
    op.add_column('pipelines', sa.Column('approval_channels', sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column('pipelines', sa.Column('approval_phone', sa.String(20), nullable=True))


def downgrade() -> None:
    # Remove pipeline columns
    op.drop_column('pipelines', 'approval_phone')
    op.drop_column('pipelines', 'approval_channels')
    op.drop_column('pipelines', 'approval_timeout_minutes')
    op.drop_column('pipelines', 'approval_modes')
    op.drop_column('pipelines', 'require_approval')

    # Remove execution columns
    op.drop_index('ix_executions_approval_token', 'executions')
    op.drop_column('executions', 'approval_expires_at')
    op.drop_column('executions', 'approval_token')
    op.drop_column('executions', 'approval_responded_at')
    op.drop_column('executions', 'approval_requested_at')
    op.drop_column('executions', 'approval_status')

    # Note: Cannot remove enum value in PostgreSQL without recreating the type
