"""add langfuse trace id to executions

Revision ID: 20260415_langfuse_trace
Revises: 20260414_strategy_market
Create Date: 2026-04-15 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260415_langfuse_trace"
down_revision = "20260414_strategy_market"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("executions", sa.Column("langfuse_trace_id", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_executions_langfuse_trace_id"), "executions", ["langfuse_trace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_executions_langfuse_trace_id"), table_name="executions")
    op.drop_column("executions", "langfuse_trace_id")
