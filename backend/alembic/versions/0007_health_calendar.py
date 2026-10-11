"""health calendar: health_events + health_event_prefs (data-model 1.7)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'health_events',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('title', postgresql.JSONB(), nullable=False),
        sa.Column('description', postgresql.JSONB(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('starts_on', sa.Date(), nullable=False),
        sa.Column('ends_on', sa.Date(), nullable=False),
        sa.Column('audience', postgresql.JSONB(), nullable=False),
        sa.Column('notify_days_before', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('organizer', sa.String(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('announced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_health_events_starts_on', 'health_events', ['starts_on'])
    op.create_table(
        'health_event_prefs',
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('category', sa.String(), primary_key=True),
        sa.Column('following', sa.Boolean(), nullable=False, server_default='true'),
    )


def downgrade() -> None:
    op.drop_table('health_event_prefs')
    op.drop_index('ix_health_events_starts_on', table_name='health_events')
    op.drop_table('health_events')
