"""add_needs_reconciliation_status

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-20 14:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add NEEDS_RECONCILIATION to ExecutionStatus enum
    op.execute("ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS 'NEEDS_RECONCILIATION'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values directly
    # To downgrade, you would need to recreate the enum type
    pass
