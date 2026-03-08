"""add_sms_consent_fields

Revision ID: 9a1c3e5f7b2d
Revises: 7f2a9b4c8d1e
Create Date: 2026-03-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '9a1c3e5f7b2d'
down_revision = '7f2a9b4c8d1e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add SMS consent fields to users table
    op.add_column('users', sa.Column('sms_consent', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('sms_consent_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('sms_phone', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('sms_consent_method', sa.String(length=50), nullable=True))

    # Create sms_consent_log audit table
    op.create_table(
        'sms_consent_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('phone_number', sa.String(length=20), nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('consent_given', sa.Boolean(), nullable=False),
        sa.Column('consent_method', sa.String(length=50), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('sms_consent_log')
    op.drop_column('users', 'sms_consent_method')
    op.drop_column('users', 'sms_phone')
    op.drop_column('users', 'sms_consent_at')
    op.drop_column('users', 'sms_consent')
