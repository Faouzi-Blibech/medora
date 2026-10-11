from datetime import datetime

from sqlalchemy import REAL, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    status: Mapped[str] = mapped_column(String, default="requested")
    referral_text: Mapped[str] = mapped_column(Text, default="")
    symptoms: Mapped[list] = mapped_column(JSONB, default=list)
    urgency_ai: Mapped[int] = mapped_column(Integer)
    urgency_final: Mapped[int | None] = mapped_column(Integer)
    ai_suggested: Mapped[dict | None] = mapped_column(JSONB)
    human_confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    doctor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    slot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    no_show_prob: Mapped[float | None] = mapped_column(Float)
    patient_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Prescription(Base):
    __tablename__ = "prescriptions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    items: Mapped[list] = mapped_column(JSONB)  # [{med, drug_id?, dose_mg?, units_per_intake, times[], slot, days}]
    care_plan: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # pharmacy (data-model 1.7): pending_pharmacy | validated | changes_requested | rejected | stopped | superseded.
    # `active` above is derived: validated, or pending_pharmacy + urgent (services/pharmacy/workflow.py keeps it).
    status: Mapped[str] = mapped_column(String, default="validated", server_default="validated", index=True)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    replaces_id: Mapped[str | None] = mapped_column(ForeignKey("prescriptions.id"))
    checks: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    override_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(Text)


class MedDose(Base):
    __tablename__ = "med_doses"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    prescription_id: Mapped[str] = mapped_column(ForeignKey("prescriptions.id"))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    time_of_day: Mapped[str] = mapped_column(String)  # HH:MM Africa/Tunis
    meds: Mapped[list] = mapped_column(JSONB)
    slot: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="scheduled")  # scheduled|dispensed|taken|missed
    taken_method: Mapped[str | None] = mapped_column(String)  # ir | button
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class Vital(Base):
    """TimescaleDB hypertable on `ts`: the time column is part of the PK, as Timescale requires."""

    __tablename__ = "vitals"
    __table_args__ = (Index("ix_vitals_patient_ts", "patient_id", text("ts DESC")),)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    device_id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str | None] = mapped_column(String)
    hr: Mapped[int | None] = mapped_column(Integer)
    spo2: Mapped[int | None] = mapped_column(Integer)
    temp: Mapped[float | None] = mapped_column(REAL)
    nurse_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    news2: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String, default="device")  # device | simulator | manual


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"))
    device_id: Mapped[str | None] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # news2|trend|call_nurse|dose_missed|device_offline
    severity: Mapped[str] = mapped_column(String)  # low|medium|high|critical
    news2: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    ai_suggested: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acked_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
