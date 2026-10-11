"""nurse shift handovers: handovers (data-model 1.10)

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "handovers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("ward", sa.String(), nullable=True),
        sa.Column("window_hours", sa.Integer(), nullable=False),
        sa.Column("ai_suggested", postgresql.JSONB(), nullable=False),
        sa.Column("human_confirmed_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_handovers_patient_id", "handovers", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_handovers_patient_id", table_name="handovers")
    op.drop_table("handovers")
