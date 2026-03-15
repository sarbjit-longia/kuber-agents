"""Add pipeline schedule and user timezone columns.

Revision ID: 20260314_schedule
Revises: 20260308_sms_consent
Create Date: 2026-03-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "a3b5d7e9f1c2"
down_revision = "9a1c3e5f7b2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # User timezone
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(50), nullable=False, server_default="America/New_York"),
    )

    # Pipeline schedule fields
    op.add_column(
        "pipelines",
        sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "pipelines",
        sa.Column("schedule_start_time", sa.String(5), nullable=True),
    )
    op.add_column(
        "pipelines",
        sa.Column("schedule_end_time", sa.String(5), nullable=True),
    )
    op.add_column(
        "pipelines",
        sa.Column("schedule_days", JSONB, nullable=True),
    )
    op.add_column(
        "pipelines",
        sa.Column(
            "liquidate_on_deactivation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("pipelines", "liquidate_on_deactivation")
    op.drop_column("pipelines", "schedule_days")
    op.drop_column("pipelines", "schedule_end_time")
    op.drop_column("pipelines", "schedule_start_time")
    op.drop_column("pipelines", "schedule_enabled")
    op.drop_column("users", "timezone")
