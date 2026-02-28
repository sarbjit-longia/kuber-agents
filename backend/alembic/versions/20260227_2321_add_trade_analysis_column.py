"""add_trade_analysis_column

Revision ID: 3e8b43af1b5b
Revises: a3f8d1c2e4b5
Create Date: 2026-02-27 23:21:20.553783

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '3e8b43af1b5b'
down_revision = 'a3f8d1c2e4b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('executions', sa.Column('trade_analysis', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('executions', 'trade_analysis')
