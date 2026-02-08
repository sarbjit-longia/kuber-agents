"""add_telegram_notification_fields

Revision ID: 58e10e31a8de
Revises: 3f30c8fed13e
Create Date: 2026-02-08 07:39:05.555091

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '58e10e31a8de'
down_revision = '3f30c8fed13e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add Telegram fields to users table
    op.add_column('users', sa.Column('telegram_bot_token', sa.String(length=200), nullable=True))
    op.add_column('users', sa.Column('telegram_chat_id', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('telegram_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    
    # Add notification fields to pipelines table
    op.add_column('pipelines', sa.Column('notification_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('pipelines', sa.Column('notification_events', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove notification fields from pipelines table
    op.drop_column('pipelines', 'notification_events')
    op.drop_column('pipelines', 'notification_enabled')
    
    # Remove Telegram fields from users table
    op.drop_column('users', 'telegram_enabled')
    op.drop_column('users', 'telegram_chat_id')
    op.drop_column('users', 'telegram_bot_token')

