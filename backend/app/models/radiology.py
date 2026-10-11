from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RadiographReading(Base):
    """AI draft reading of one radiograph image, confirmed by a doctor (data-model 1.8)."""

    __tablename__ = "radiograph_readings"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    exam_result_id: Mapped[str] = mapped_column(ForeignKey("exam_results.id"), unique=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    status: Mapped[str] = mapped_column(String, index=True, default="queued", server_default="queued")
    hint: Mapped[str] = mapped_column(String, default="", server_default="")
    ai_suggested: Mapped[dict | None] = mapped_column(JSONB)
    final_text: Mapped[str | None] = mapped_column(Text)
    human_confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
