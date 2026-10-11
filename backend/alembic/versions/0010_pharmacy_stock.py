"""Hospital pharmacy, Phase B: stock_lots, stock_movements (append-only), dispensations, dispensation_lines
(data-model 1.7)

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_lots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("drug_id", sa.String(), sa.ForeignKey("drugs.id"), nullable=False),
        sa.Column("lot_number", sa.String(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_stock_lots_quantity_nonneg"),
        sa.UniqueConstraint("drug_id", "lot_number", name="uq_stock_lots_drug_lot"),
    )
    op.create_index("ix_stock_lots_drug_id", "stock_lots", ["drug_id"])
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("drug_id", sa.String(), sa.ForeignKey("drugs.id"), nullable=False),
        sa.Column("lot_id", sa.String(), sa.ForeignKey("stock_lots.id"), nullable=True),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("ref_id", sa.String(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_stock_movements_drug_id", "stock_movements", ["drug_id"])
    # same SQL as app.models.pharmacy.STOCK_APPEND_ONLY_SQL (which covers create_all in tests)
    op.execute("""
CREATE OR REPLACE FUNCTION stock_movements_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'stock_movements is append-only'; END $$;
CREATE TRIGGER stock_movements_append_only BEFORE UPDATE OR DELETE ON stock_movements
FOR EACH ROW EXECUTE FUNCTION stock_movements_append_only();
""")
    op.create_table(
        "dispensations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("ward", sa.String(), nullable=False),
        sa.Column("round_date", sa.Date(), nullable=False),
        sa.Column("round_time", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="sent"),
        sa.Column("prepared_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("received_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_dispensations_ward_round_date", "dispensations", ["ward", "round_date"])
    op.create_table(
        "dispensation_lines",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dispensation_id", sa.String(), sa.ForeignKey("dispensations.id"), nullable=False),
        sa.Column("dose_id", sa.String(), sa.ForeignKey("med_doses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("patient_id", sa.String(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("drug_id", sa.String(), sa.ForeignKey("drugs.id"), nullable=True),
        sa.Column("lot_id", sa.String(), sa.ForeignKey("stock_lots.id"), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("med", sa.Text(), nullable=False),
    )
    op.create_index("ix_dispensation_lines_dispensation_id", "dispensation_lines", ["dispensation_id"])
    op.create_index("uq_dispensation_lines_dose_id", "dispensation_lines", ["dose_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_dispensation_lines_dose_id", table_name="dispensation_lines")
    op.drop_index("ix_dispensation_lines_dispensation_id", table_name="dispensation_lines")
    op.drop_table("dispensation_lines")
    op.drop_index("ix_dispensations_ward_round_date", table_name="dispensations")
    op.drop_table("dispensations")
    op.execute("DROP TRIGGER IF EXISTS stock_movements_append_only ON stock_movements")
    op.execute("DROP FUNCTION IF EXISTS stock_movements_append_only()")
    op.drop_index("ix_stock_movements_drug_id", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index("ix_stock_lots_drug_id", table_name="stock_lots")
    op.drop_table("stock_lots")
