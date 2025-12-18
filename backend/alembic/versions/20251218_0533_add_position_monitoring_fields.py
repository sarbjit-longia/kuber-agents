"""add_position_monitoring_fields

Revision ID: 20251218_0533
Revises: 20251218_0421
Create Date: 2025-12-18 05:33

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251218_0533'
down_revision = '20251218_0421'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add MONITORING status to execution_status enum
    op.execute("""
        ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS 'monitoring';
    """)
    
    # Add position monitoring fields to executions table
    op.add_column('executions', sa.Column('execution_phase', sa.String(20), nullable=False, server_default='execute'))
    op.add_column('executions', sa.Column('next_check_at', sa.DateTime(), nullable=True))
    op.add_column('executions', sa.Column('monitor_interval_minutes', sa.Integer(), nullable=False, server_default='5'))


def downgrade() -> None:
    # Remove position monitoring fields
    op.drop_column('executions', 'monitor_interval_minutes')
    op.drop_column('executions', 'next_check_at')
    op.drop_column('executions', 'execution_phase')
    
    # Note: Cannot remove enum value in PostgreSQL easily, would require recreating the enum
