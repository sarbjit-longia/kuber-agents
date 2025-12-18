"""add_executive_report_to_executions

Revision ID: 4c60eedcb074
Revises: 642e1fa6e7c6
Create Date: 2025-12-18 02:40:38.071888

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '4c60eedcb074'
down_revision = '642e1fa6e7c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add executive_report column to executions table
    op.add_column('executions', sa.Column('executive_report', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Remove executive_report column from executions table
    op.drop_column('executions', 'executive_report')

