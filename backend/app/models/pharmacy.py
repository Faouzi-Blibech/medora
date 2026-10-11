"""Hospital pharmacy tables (data-model 1.7, pharmacy spec §3). Phase A: drugs, prescription_reviews."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (DDL, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
                        UniqueConstraint, event, func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

EMPTY_JSON = text("'[]'::jsonb")


class Drug(Base):
    """The hospital formulary (livret thérapeutique). Never deleted: `active = false` retires a drug."""

    __tablename__ = "drugs"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # d-0001
    dci: Mapped[str] = mapped_column(String)
    brand_names: Mapped[list] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON)
    form: Mapped[str] = mapped_column(String)  # tablet|capsule|syrup|injection|inhaler|patch|drops|other
    strength: Mapped[str] = mapped_column(String, default="", server_default="")
    unit_mg: Mapped[Decimal | None] = mapped_column(Numeric)
    max_daily_mg: Mapped[Decimal | None] = mapped_column(Numeric)
    atc_code: Mapped[str] = mapped_column(String, default="", server_default="")
    allergy_classes: Mapped[list] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON)
    interaction_groups: Mapped[list] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON)
    high_alert: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    min_stock: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class PrescriptionReview(Base):
    """One pharmacist decision (validated | changes_requested | rejected) with the checks seen at that moment."""

    __tablename__ = "prescription_reviews"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # pr-0001
    prescription_id: Mapped[str] = mapped_column(ForeignKey("prescriptions.id"), index=True)
    pharmacist_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String)
    comment: Mapped[str | None] = mapped_column(Text)
    checks_snapshot: Mapped[list] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StockLot(Base):
    __tablename__ = "stock_lots"
    __table_args__ = (CheckConstraint("quantity >= 0", name="ck_stock_lots_quantity_nonneg"),
                      UniqueConstraint("drug_id", "lot_number", name="uq_stock_lots_drug_lot"))
    id: Mapped[str] = mapped_column(String, primary_key=True)  # lot-0001
    drug_id: Mapped[str] = mapped_column(ForeignKey("drugs.id"), index=True)
    lot_number: Mapped[str] = mapped_column(String)
    expiry_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StockMovement(Base):
    """Append-only: a trigger refuses UPDATE and DELETE (like audit_log)."""

    __tablename__ = "stock_movements"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # sm-0001
    drug_id: Mapped[str] = mapped_column(ForeignKey("drugs.id"), index=True)
    lot_id: Mapped[str | None] = mapped_column(ForeignKey("stock_lots.id"))
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String)  # receipt | dispense | adjustment | expired | return
    ref_id: Mapped[str | None] = mapped_column(String)
    comment: Mapped[str | None] = mapped_column(Text)
    by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


STOCK_APPEND_ONLY_SQL = """
CREATE OR REPLACE FUNCTION stock_movements_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'stock_movements is append-only'; END $$;
CREATE TRIGGER stock_movements_append_only BEFORE UPDATE OR DELETE ON stock_movements
FOR EACH ROW EXECUTE FUNCTION stock_movements_append_only();
"""
event.listen(StockMovement.__table__, "after_create", DDL(STOCK_APPEND_ONLY_SQL))


class Dispensation(Base):
    __tablename__ = "dispensations"
    __table_args__ = (Index("ix_dispensations_ward_round_date", "ward", "round_date"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)  # disp-0001
    ward: Mapped[str] = mapped_column(String)
    round_date: Mapped[date] = mapped_column(Date)
    round_time: Mapped[str] = mapped_column(String)  # HH:MM Africa/Tunis
    status: Mapped[str] = mapped_column(String, default="sent", server_default="sent")  # sent | received
    prepared_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    received_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DispensationLine(Base):
    __tablename__ = "dispensation_lines"
    __table_args__ = (Index("uq_dispensation_lines_dose_id", "dose_id", unique=True),)
    id: Mapped[str] = mapped_column(String, primary_key=True)  # dl-000001
    dispensation_id: Mapped[str] = mapped_column(ForeignKey("dispensations.id"), index=True)
    # SET NULL: a rebuild may delete a future dose that was already sent; the line stays as the record
    dose_id: Mapped[str | None] = mapped_column(ForeignKey("med_doses.id", ondelete="SET NULL"))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    drug_id: Mapped[str | None] = mapped_column(ForeignKey("drugs.id"))
    lot_id: Mapped[str | None] = mapped_column(ForeignKey("stock_lots.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    med: Mapped[str] = mapped_column(Text)
