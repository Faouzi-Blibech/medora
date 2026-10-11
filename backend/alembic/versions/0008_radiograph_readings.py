"""radiograph readings: radiograph_readings (data-model 1.8)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'radiograph_readings',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('exam_result_id', sa.String(), sa.ForeignKey('exam_results.id'), nullable=False),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='queued'),
        sa.Column('hint', sa.String(), nullable=False, server_default=''),
        sa.Column('ai_suggested', postgresql.JSONB(), nullable=True),
        sa.Column('final_text', sa.Text(), nullable=True),
        sa.Column('human_confirmed_by', sa.String(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('exam_result_id'),
    )
    op.create_index('ix_radiograph_readings_patient_id', 'radiograph_readings', ['patient_id'])
    op.create_index('ix_radiograph_readings_status', 'radiograph_readings', ['status'])


def downgrade() -> None:
    op.drop_index('ix_radiograph_readings_status', table_name='radiograph_readings')
    op.drop_index('ix_radiograph_readings_patient_id', table_name='radiograph_readings')
    op.drop_table('radiograph_readings')
