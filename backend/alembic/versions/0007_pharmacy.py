"""Hospital pharmacy, Phase A: drugs (formulary), prescription review status, prescription_reviews (data-model 1.7)

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

EMPTY = sa.text("'[]'::jsonb")
RX_COLUMNS = ("review_comment", "reviewed_at", "reviewed_by", "override_reason", "checks", "replaces_id", "version",
              "urgent", "status")


def upgrade() -> None:
    op.create_table(
        "drugs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dci", sa.String(), nullable=False),
        sa.Column("brand_names", postgresql.JSONB(), nullable=False, server_default=EMPTY),
        sa.Column("form", sa.String(), nullable=False),
        sa.Column("strength", sa.String(), nullable=False, server_default=""),
        sa.Column("unit_mg", sa.Numeric(), nullable=True),
        sa.Column("max_daily_mg", sa.Numeric(), nullable=True),
        sa.Column("atc_code", sa.String(), nullable=False, server_default=""),
        sa.Column("allergy_classes", postgresql.JSONB(), nullable=False, server_default=EMPTY),
        sa.Column("interaction_groups", postgresql.JSONB(), nullable=False, server_default=EMPTY),
        sa.Column("high_alert", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("min_stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("prescriptions", sa.Column("status", sa.String(), nullable=False, server_default="validated"))
    op.add_column("prescriptions", sa.Column("urgent", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("prescriptions", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("prescriptions", sa.Column("replaces_id", sa.String(), sa.ForeignKey("prescriptions.id"),
                                             nullable=True))
    op.add_column("prescriptions", sa.Column("checks", postgresql.JSONB(), nullable=False, server_default=EMPTY))
    op.add_column("prescriptions", sa.Column("override_reason", sa.Text(), nullable=True))
    op.add_column("prescriptions", sa.Column("reviewed_by", sa.String(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("prescriptions", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("prescriptions", sa.Column("review_comment", sa.Text(), nullable=True))
    # backfill (spec §3): running prescriptions predate the gate and count as validated; stopped ones are stopped.
    # drug_id in items and reviewed_by need the formulary and the seed pharmacist: app/seed.py fills them.
    op.execute("UPDATE prescriptions SET status = CASE WHEN active THEN 'validated' ELSE 'stopped' END")
    op.create_index("ix_prescriptions_status", "prescriptions", ["status"])
    op.create_table(
        "prescription_reviews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("prescription_id", sa.String(), sa.ForeignKey("prescriptions.id"), nullable=False),
        sa.Column("pharmacist_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("checks_snapshot", postgresql.JSONB(), nullable=False, server_default=EMPTY),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_prescription_reviews_prescription_id", "prescription_reviews", ["prescription_id"])


def downgrade() -> None:
    op.drop_index("ix_prescription_reviews_prescription_id", table_name="prescription_reviews")
    op.drop_table("prescription_reviews")
    op.drop_index("ix_prescriptions_status", table_name="prescriptions")
    for col in RX_COLUMNS:
        op.drop_column("prescriptions", col)
    op.drop_table("drugs")
