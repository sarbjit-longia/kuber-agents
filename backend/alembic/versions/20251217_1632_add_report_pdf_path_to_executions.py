"""add_report_pdf_path_to_executions

Revision ID: 642e1fa6e7c6
Revises: 20251210_add_subscription_tier
Create Date: 2025-12-17 16:32:51.508661

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '642e1fa6e7c6'
down_revision = '20251210_add_subscription_tier'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add report_pdf_path column to executions table
    op.add_column('executions', sa.Column('report_pdf_path', sa.String(length=500), nullable=True))


def downgrade() -> None:
    # Remove report_pdf_path column from executions table
    op.drop_column('executions', 'report_pdf_path')

