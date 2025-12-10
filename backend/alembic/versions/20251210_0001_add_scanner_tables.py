"""Add scanner tables and update pipelines

Revision ID: b8f3c2a1d9e5
Revises: 5e247e584ae0
Create Date: 2025-12-10 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b8f3c2a1d9e5'
down_revision: Union[str, None] = '5e247e584ae0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ScannerType Enum
    scanner_type_enum = postgresql.ENUM('manual', 'filter', 'api', name='scannertype', create_type=False)
    scanner_type_enum.create(op.get_bind(), checkfirst=True)
    
    # Create scanners table
    op.create_table(
        'scanners',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('scanner_type', scanner_type_enum, nullable=False, server_default='manual'),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('refresh_interval', sa.Integer(), nullable=True),
        sa.Column('last_refreshed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    
    # Create indexes on scanners table
    op.create_index(op.f('ix_scanners_id'), 'scanners', ['id'], unique=False)
    op.create_index(op.f('ix_scanners_user_id'), 'scanners', ['user_id'], unique=False)
    
    # Add new columns to pipelines table
    op.add_column('pipelines', sa.Column('scanner_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('pipelines', sa.Column('signal_subscriptions', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Create foreign key for scanner_id
    op.create_foreign_key('fk_pipelines_scanner_id', 'pipelines', 'scanners', ['scanner_id'], ['id'])
    
    # Create index on scanner_id
    op.create_index(op.f('ix_pipelines_scanner_id'), 'pipelines', ['scanner_id'], unique=False)


def downgrade() -> None:
    # Drop indexes and foreign keys on pipelines
    op.drop_index(op.f('ix_pipelines_scanner_id'), table_name='pipelines')
    op.drop_constraint('fk_pipelines_scanner_id', 'pipelines', type_='foreignkey')
    
    # Drop new columns from pipelines
    op.drop_column('pipelines', 'signal_subscriptions')
    op.drop_column('pipelines', 'scanner_id')
    
    # Drop scanners table indexes
    op.drop_index(op.f('ix_scanners_user_id'), table_name='scanners')
    op.drop_index(op.f('ix_scanners_id'), table_name='scanners')
    
    # Drop scanners table
    op.drop_table('scanners')
    
    # Drop ScannerType enum
    postgresql.ENUM(name='scannertype').drop(op.get_bind())

