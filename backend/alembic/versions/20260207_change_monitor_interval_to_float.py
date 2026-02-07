"""change_monitor_interval_to_float

Revision ID: 20260207_float_interval
Revises: 97f79fade921
Create Date: 2026-02-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260207_float_interval'
down_revision = '97f79fade921'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change monitor_interval_minutes from Integer to Float
    # to support sub-minute intervals (e.g., 0.25 = 15 seconds)
    op.alter_column(
        'executions',
        'monitor_interval_minutes',
        type_=sa.Float(),
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default='5',
    )


def downgrade() -> None:
    # Revert back to Integer
    op.alter_column(
        'executions',
        'monitor_interval_minutes',
        type_=sa.Integer(),
        existing_type=sa.Float(),
        existing_nullable=False,
        existing_server_default='5',
    )
