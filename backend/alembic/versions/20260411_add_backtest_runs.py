"""Add backtest_runs table

Revision ID: c1d2e3f4a5b6
Revises: b4c6d8e0f2a3
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c1d2e3f4a5b6"
down_revision = "b4c6d8e0f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("pipeline_id", sa.UUID(), nullable=True),
        sa.Column("pipeline_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.Enum("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", name="backtestrunstatus"), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("progress", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("equity_curve", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trades", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trades_count", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("actual_cost", sa.Float(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipelines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_backtest_runs_id"), "backtest_runs", ["id"], unique=False)
    op.create_index(op.f("ix_backtest_runs_pipeline_id"), "backtest_runs", ["pipeline_id"], unique=False)
    op.create_index(op.f("ix_backtest_runs_status"), "backtest_runs", ["status"], unique=False)
    op.create_index(op.f("ix_backtest_runs_user_id"), "backtest_runs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_backtest_runs_user_id"), table_name="backtest_runs")
    op.drop_index(op.f("ix_backtest_runs_status"), table_name="backtest_runs")
    op.drop_index(op.f("ix_backtest_runs_pipeline_id"), table_name="backtest_runs")
    op.drop_index(op.f("ix_backtest_runs_id"), table_name="backtest_runs")
    op.drop_table("backtest_runs")
