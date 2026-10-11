"""n8n callbacks (owner: Faouzi). Contract: api.md → Integrations and n8n-webhooks.md v1.4 → Callbacks.

Authenticated by the `X-N8N-Secret` header only (no JWT); n8n is not the source of truth, so every callback
goes through the same appointment rules as the web app.
"""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError, not_found
from app.ids import new_id
from app.integrations import n8n
from app.models import Admission, AiSummary, Appointment, HealthEvent, Patient, User
from app.routers.appointments import cancel
from app.services import appointments as A
from app.services import health_calendar as H
from app.services.integrations import callback_secret_ok, digest_entries
from app.services.patients import latest_vital


def require_n8n(request: Request) -> None:
    if not callback_secret_ok(request.headers.get("X-N8N-Secret")):
        raise ApiError(401, "unauthorized", "missing or invalid X-N8N-Secret")


router = APIRouter(prefix="/integrations/n8n", tags=["integrations"], dependencies=[Depends(require_n8n)])


class ReplyIn(BaseModel):
    appointment_id: str
    reply: Literal["confirm", "cancel"]


class BackfillIn(BaseModel):
    appointment_id: str
    slot_at: datetime


class FollowUpIn(BaseModel):
    patient_id: str
    days: int = Field(default=14, ge=1, le=365)


def _appointment(db: Session, appointment_id: str) -> Appointment:
    a = db.get(Appointment, appointment_id)
    if a is None:
        raise not_found("appointment")
    return a


@router.post("/appointment-reply")
def appointment_reply(body: ReplyIn, db: Session = Depends(get_db)) -> dict:
    a = _appointment(db, body.appointment_id)
    if body.reply == "cancel":
        event = cancel(db, a)
        db.commit()
        n8n.emit("appointment.cancelled", event)
        return {"status": "cancelled"}
    A.apply_reply(a, "confirm", now=datetime.now(UTC))
    db.commit()
    return {"status": "confirmed"}


@router.post("/backfill-accept")
def backfill_accept(body: BackfillIn, db: Session = Depends(get_db)) -> dict:
    a = _appointment(db, body.appointment_id)
    freed = db.scalar(select(Appointment).where(Appointment.status == "cancelled",
                                                Appointment.slot_at == body.slot_at,
                                                Appointment.doctor_id.is_not(None))
                      .order_by(Appointment.created_at.desc()).limit(1))
    if freed is None:
        raise not_found("freed slot")
    taken = db.scalar(select(Appointment.id).where(Appointment.status == "confirmed",
                                                   Appointment.doctor_id == freed.doctor_id,
                                                   Appointment.slot_at == body.slot_at).limit(1))
    try:
        status = A.apply_backfill_accept(a, slot_at=body.slot_at, doctor_id=freed.doctor_id,
                                         slot_taken=taken is not None)
    except A.Conflict as e:
        raise ApiError(409, e.code, str(e)) from e
    db.commit()
    return {"status": status}


NOT_REVIEWED = "Summary not reviewed yet. Open Ward to review it."


def _summary_text(db: Session, p: Patient) -> str:
    """The latest AI summary a doctor has reviewed; unreviewed AI text never leaves the server."""
    stored = db.scalar(select(AiSummary).where(AiSummary.patient_id == p.id)
                       .order_by(AiSummary.created_at.desc()).limit(1))
    if stored is not None and stored.human_confirmed_by:
        return stored.ai_suggested["summary"]
    return NOT_REVIEWED


@router.get("/daily-digest")
def daily_digest(doctor_id: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    doctors = select(User).where(User.role == "doctor", User.status == "active").order_by(User.id)
    if doctor_id:
        doctors = doctors.where(User.id == doctor_id)
    doctors = db.scalars(doctors).all()
    wanted = {d.id: d for d in doctors}
    rows = []
    admitted = db.execute(select(Admission, Patient).join(Patient, Patient.id == Admission.patient_id)
                          .where(Admission.discharged_at.is_(None)).order_by(Admission.bed)).all()
    for adm, p in admitted:
        doctor = wanted.get(p.attending_doctor_id)
        if doctor is None:
            continue
        v = latest_vital(db, p.id)
        rows.append((doctor, p, adm.bed, v.news2 if v else None, _summary_text(db, p)))
    return digest_entries(rows, doctors=doctors)


@router.post("/follow-up")
def follow_up(body: FollowUpIn, db: Session = Depends(get_db)) -> dict:
    p = db.get(Patient, body.patient_id)
    if p is None:
        raise not_found("patient")
    a = Appointment(id=new_id(db, "a"), **A.follow_up_fields(p, body.days, today=datetime.now(UTC).date()))
    db.add(a)
    db.commit()
    return {"appointment_id": a.id, "status": a.status}


@router.get("/health-events/due")
def health_events_due(db: Session = Depends(get_db)) -> list[dict]:
    web = get_settings().web_url
    return [H.upcoming_payload(db, e, web) for e in H.due(db, H._today())]


@router.post("/health-events/{event_id}/announced")
def health_event_announced(event_id: str, db: Session = Depends(get_db)) -> dict:
    ev = db.get(HealthEvent, event_id)
    if ev is None:
        raise not_found("health event")
    if ev.announced_at is None:
        ev.announced_at = datetime.now(UTC)
        db.commit()
    return {"status": "announced"}
