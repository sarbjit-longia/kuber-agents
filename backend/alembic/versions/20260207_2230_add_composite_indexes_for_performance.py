"""add_composite_indexes_for_performance

Adds composite indexes to improve query performance for common queries:
1. executions (pipeline_id, status) - for checking running executions
2. executions (user_id, status) - for user reconciliation
3. executions (status, started_at) - for cleanup tasks
4. executions (status, created_at) - for cleanup tasks
5. executions (pipeline_id, completed_at) - for rate limiting

Revision ID: 3f30c8fed13e
Revises: ffddd94fe476
Create Date: 2026-02-07 22:30:34.410001

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3f30c8fed13e'
down_revision = 'ffddd94fe476'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add composite indexes for common query patterns
    
    # 1. For check_scheduled_pipelines: Find running executions by pipeline
    op.create_index(
        'ix_executions_pipeline_status',
        'executions',
        ['pipeline_id', 'status'],
        unique=False
    )
    
    # 2. For reconcile_user_trades: Find monitoring executions by user
    op.create_index(
        'ix_executions_user_status',
        'executions',
        ['user_id', 'status'],
        unique=False
    )
    
    # 3. For cleanup_stale_running_executions: Find stale in-flight executions
    op.create_index(
        'ix_executions_status_started_at',
        'executions',
        ['status', 'started_at'],
        unique=False
    )
    
    # 4. For cleanup_old_executions: Find old completed/failed executions
    op.create_index(
        'ix_executions_status_created_at',
        'executions',
        ['status', 'created_at'],
        unique=False
    )
    
    # 5. For periodic pipeline rate limiting: Find last completed execution
    op.create_index(
        'ix_executions_pipeline_completed_at',
        'executions',
        ['pipeline_id', 'completed_at'],
        unique=False
    )


def downgrade() -> None:
    # Drop composite indexes in reverse order
    op.drop_index('ix_executions_pipeline_completed_at', table_name='executions')
    op.drop_index('ix_executions_status_created_at', table_name='executions')
    op.drop_index('ix_executions_status_started_at', table_name='executions')
    op.drop_index('ix_executions_user_status', table_name='executions')
    op.drop_index('ix_executions_pipeline_status', table_name='executions')

