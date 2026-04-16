"""add strategies marketplace

Revision ID: 20260414_strategy_market
Revises: 20260412_add_backtest_events
Create Date: 2026-04-14 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260414_strategy_market"
down_revision = "20260412_add_backtest_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_pipeline_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("publication_status", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("style", sa.String(length=64), nullable=True),
        sa.Column("difficulty", sa.String(length=32), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("markets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("timeframes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk_notes", sa.Text(), nullable=True),
        sa.Column("markdown_content", sa.Text(), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("frontmatter", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("published_version", sa.Integer(), nullable=False),
        sa.Column("published_markdown_content", sa.Text(), nullable=True),
        sa.Column("published_frontmatter", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("published_normalized_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("vote_count", sa.Integer(), nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_pipeline_id"], ["pipelines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_strategies_id"), "strategies", ["id"], unique=False)
    op.create_index(op.f("ix_strategies_user_id"), "strategies", ["user_id"], unique=False)
    op.create_index(op.f("ix_strategies_source_pipeline_id"), "strategies", ["source_pipeline_id"], unique=False)
    op.create_index(op.f("ix_strategies_slug"), "strategies", ["slug"], unique=False)
    op.create_index(op.f("ix_strategies_visibility"), "strategies", ["visibility"], unique=False)
    op.create_index(op.f("ix_strategies_publication_status"), "strategies", ["publication_status"], unique=False)
    op.create_index(op.f("ix_strategies_category"), "strategies", ["category"], unique=False)
    op.create_index(op.f("ix_strategies_style"), "strategies", ["style"], unique=False)

    op.create_table(
        "strategy_votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_id", "user_id", name="uq_strategy_votes_strategy_user"),
    )
    op.create_index(op.f("ix_strategy_votes_id"), "strategy_votes", ["id"], unique=False)
    op.create_index(op.f("ix_strategy_votes_strategy_id"), "strategy_votes", ["strategy_id"], unique=False)
    op.create_index(op.f("ix_strategy_votes_user_id"), "strategy_votes", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_strategy_votes_user_id"), table_name="strategy_votes")
    op.drop_index(op.f("ix_strategy_votes_strategy_id"), table_name="strategy_votes")
    op.drop_index(op.f("ix_strategy_votes_id"), table_name="strategy_votes")
    op.drop_table("strategy_votes")
    op.drop_index(op.f("ix_strategies_style"), table_name="strategies")
    op.drop_index(op.f("ix_strategies_category"), table_name="strategies")
    op.drop_index(op.f("ix_strategies_publication_status"), table_name="strategies")
    op.drop_index(op.f("ix_strategies_visibility"), table_name="strategies")
    op.drop_index(op.f("ix_strategies_slug"), table_name="strategies")
    op.drop_index(op.f("ix_strategies_source_pipeline_id"), table_name="strategies")
    op.drop_index(op.f("ix_strategies_user_id"), table_name="strategies")
    op.drop_index(op.f("ix_strategies_id"), table_name="strategies")
    op.drop_table("strategies")
