"""add trigger mode and scanner tickers to pipelines

Revision ID: 5e247e584ae0
Revises: a2c9d1bf14d7
Create Date: 2025-12-09 23:24:20.185378

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '5e247e584ae0'
down_revision = 'a2c9d1bf14d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type for trigger_mode
    op.execute("CREATE TYPE triggermode AS ENUM ('signal', 'periodic')")
    
    # Add trigger_mode column with default value 'periodic'
    op.add_column(
        'pipelines',
        sa.Column('trigger_mode', sa.Enum('signal', 'periodic', name='triggermode'), 
                  nullable=False, server_default='periodic')
    )
    
    # Add scanner_tickers column (JSONB array)
    op.add_column(
        'pipelines',
        sa.Column('scanner_tickers', JSONB, nullable=True)
    )
    
    # Create index on trigger_mode for faster signal-based pipeline lookups
    op.create_index('ix_pipelines_trigger_mode', 'pipelines', ['trigger_mode'])


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_pipelines_trigger_mode', table_name='pipelines')
    
    # Drop columns
    op.drop_column('pipelines', 'scanner_tickers')
    op.drop_column('pipelines', 'trigger_mode')
    
    # Drop enum type
    op.execute("DROP TYPE triggermode")
