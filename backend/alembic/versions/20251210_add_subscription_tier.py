"""add subscription tier to users

Revision ID: 20251210_add_subscription_tier
Revises: 
Create Date: 2025-12-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251210_add_subscription_tier'
down_revision = 'b8f3c2a1d9e5'  # Previous migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create subscription tier enum
    subscription_tier_enum = postgresql.ENUM(
        'free', 'basic', 'pro', 'enterprise',
        name='subscriptiontier',
        create_type=True
    )
    subscription_tier_enum.create(op.get_bind(), checkfirst=True)
    
    # Add subscription fields to users table
    op.add_column('users', sa.Column('subscription_tier', sa.Enum('free', 'basic', 'pro', 'enterprise', name='subscriptiontier'), nullable=False, server_default='free'))
    op.add_column('users', sa.Column('max_active_pipelines', sa.Integer(), nullable=False, server_default='2'))
    op.add_column('users', sa.Column('subscription_expires_at', sa.DateTime(), nullable=True))
    
    # Create index
    op.create_index(op.f('ix_users_subscription_tier'), 'users', ['subscription_tier'], unique=False)


def downgrade() -> None:
    # Drop index
    op.drop_index(op.f('ix_users_subscription_tier'), table_name='users')
    
    # Drop columns
    op.drop_column('users', 'subscription_expires_at')
    op.drop_column('users', 'max_active_pipelines')
    op.drop_column('users', 'subscription_tier')
    
    # Drop enum
    subscription_tier_enum = postgresql.ENUM(
        'free', 'basic', 'pro', 'enterprise',
        name='subscriptiontier'
    )
    subscription_tier_enum.drop(op.get_bind(), checkfirst=True)

