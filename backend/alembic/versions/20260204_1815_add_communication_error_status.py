"""add_communication_error_status

Revision ID: 97f79fade921
Revises: 20260121_remove_seeds
Create Date: 2026-02-04 18:15:15.811139

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '97f79fade921'
down_revision = '20260121_remove_seeds'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add COMMUNICATION_ERROR to ExecutionStatus enum
    op.execute("ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS 'COMMUNICATION_ERROR'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values directly
    # To downgrade, you would need to recreate the enum type
    pass

