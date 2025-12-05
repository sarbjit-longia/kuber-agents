"""add execution reports column

Revision ID: 20251204_0001
Revises: 20251111_1444_add_execution_monitoring_fields
Create Date: 2025-12-04 00:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a2c9d1bf14d7"
down_revision: Union[str, None] = "24be6be9d078"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "executions",
        sa.Column("reports", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb")),
    )
    op.alter_column("executions", "reports", server_default=None)


def downgrade() -> None:
    op.drop_column("executions", "reports")

