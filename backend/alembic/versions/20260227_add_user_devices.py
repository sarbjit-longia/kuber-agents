"""Add user_devices table for push notifications

Revision ID: 7f2a9b4c8d1e
Revises: 3e8b43af1b5b
Create Date: 2026-02-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '7f2a9b4c8d1e'
down_revision = '3e8b43af1b5b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_devices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('device_token', sa.String(512), unique=True, nullable=False, index=True),
        sa.Column('platform', sa.String(10), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('user_devices')
