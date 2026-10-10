"""Hospital pharmacy tables (data-model 1.7, pharmacy spec §3). Phase A: drugs, prescription_reviews."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
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
