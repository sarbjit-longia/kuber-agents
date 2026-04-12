"""add backtest events

Revision ID: 20260412_add_backtest_events
Revises: c1d2e3f4a5b6
Create Date: 2026-04-12 18:55:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260412_add_backtest_events"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["executions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipelines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["backtest_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_backtest_events_created_at"), "backtest_events", ["created_at"], unique=False)
    op.create_index(op.f("ix_backtest_events_event_type"), "backtest_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_backtest_events_execution_id"), "backtest_events", ["execution_id"], unique=False)
    op.create_index(op.f("ix_backtest_events_id"), "backtest_events", ["id"], unique=False)
    op.create_index(op.f("ix_backtest_events_pipeline_id"), "backtest_events", ["pipeline_id"], unique=False)
    op.create_index(op.f("ix_backtest_events_run_id"), "backtest_events", ["run_id"], unique=False)
    op.create_index(op.f("ix_backtest_events_symbol"), "backtest_events", ["symbol"], unique=False)
    op.create_index(op.f("ix_backtest_events_user_id"), "backtest_events", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_backtest_events_user_id"), table_name="backtest_events")
    op.drop_index(op.f("ix_backtest_events_symbol"), table_name="backtest_events")
    op.drop_index(op.f("ix_backtest_events_run_id"), table_name="backtest_events")
    op.drop_index(op.f("ix_backtest_events_pipeline_id"), table_name="backtest_events")
    op.drop_index(op.f("ix_backtest_events_id"), table_name="backtest_events")
    op.drop_index(op.f("ix_backtest_events_execution_id"), table_name="backtest_events")
    op.drop_index(op.f("ix_backtest_events_event_type"), table_name="backtest_events")
    op.drop_index(op.f("ix_backtest_events_created_at"), table_name="backtest_events")
    op.drop_table("backtest_events")
