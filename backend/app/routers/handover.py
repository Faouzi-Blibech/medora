"""Nurse shift handover routes (owner: Faouzi). Contract: api.md → Shift handover (1.15).

GET drafts an SBAR handover per patient from the last N hours (rules; optional LLM narrative). The outgoing nurse
confirms it; the confirmed draft is stored in `handovers` with `human_confirmed_by` (AI-output convention).
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai import handover as H
from app.auth.deps import (check_patient_access, doctor_patient_filter, nurse_patient_filter, nurse_scope,
                           require_roles)
from app.db import get_db
from app.errors import forbidden
from app.ids import new_id
from app.models import Alert, ExamOrder, Handover, MedDose, Note, Patient, Prescription, User, Vital
from app.services import patients as P
from app.services.audit import audit

router = APIRouter(prefix="/handover", tags=["handover"])
LANG = "^(en|fr|ar)$"


class ConfirmIn(BaseModel):
    hours: int = Field(default=12, ge=1, le=48)
    lang: str | None = Field(default=None, pattern=LANG)


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _names(db: Session, ids: set[str]) -> dict[str, str]:
    ids = {i for i in ids if i}
    return {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


def _draft(db: Session, p: Patient, *, now: datetime, hours: int, lang: str | None) -> tuple[dict, bool]:
    """(SBAR draft, had any activity in the window)."""
    since = now - timedelta(hours=hours)
    upcoming = now + timedelta(hours=H.rules()["upcoming_dose_hours"])
    adm = P.active_admission(db, p.id)
    vitals = db.scalars(select(Vital).where(Vital.patient_id == p.id, Vital.ts >= since, Vital.ts <= now)
                        .order_by(Vital.ts)).all()
    doses = db.scalars(select(MedDose).where(MedDose.patient_id == p.id, MedDose.scheduled_at >= since,
                                             MedDose.scheduled_at <= upcoming).order_by(MedDose.scheduled_at)).all()
    alerts = db.scalars(select(Alert).where(Alert.patient_id == p.id,
                                            or_(Alert.created_at >= since, Alert.acked_at.is_(None)))
                        .order_by(Alert.created_at)).all()
    notes = db.scalars(select(Note).where(Note.patient_id == p.id, Note.created_at >= since)
                       .order_by(Note.created_at)).all()
    rxs = db.scalars(select(Prescription).where(Prescription.patient_id == p.id, Prescription.active.is_(True))
                     .order_by(Prescription.created_at)).all()
    exams = db.scalars(select(ExamOrder).where(ExamOrder.patient_id == p.id, ExamOrder.status == "ordered")
                       .order_by(ExamOrder.ordered_at)).all()
    authors = _names(db, {n.author_id for n in notes})
    patient = {"id": p.id, "first_name": p.first_name, "last_name": p.last_name, "ward": p.ward,
               "bed": adm.bed if adm else None, "age": P.age(p.date_of_birth), "sex": p.sex,
               "reason": p.history or "", "allergies": p.allergies or [],
               "admitted_at": adm.admitted_at if adm else None}
    d = H.draft(
        patient, names=[p.first_name, p.last_name], lang=lang, now=now, hours=hours,
        vitals=[{"ts": v.ts, "hr": v.hr, "spo2": v.spo2, "temp": v.temp, "news2": v.news2} for v in vitals],
        doses=[{"id": d.id, "scheduled_at": d.scheduled_at, "meds": d.meds, "status": d.status} for d in doses],
        alerts=[{"id": a.id, "kind": a.kind, "severity": a.severity, "message": a.message,
                 "created_at": a.created_at, "acked_at": a.acked_at} for a in alerts],
        notes=[{"text": n.text, "author_name": authors.get(n.author_id), "created_at": n.created_at} for n in notes],
        meds=[{"med": i["med"], "times": list(i.get("times") or [])} for rx in rxs for i in rx.items if i.get("med")],
        care_plans=[rx.care_plan for rx in rxs], exams=[{"label": e.label} for e in exams])
    active = bool(vitals or notes or [a for a in alerts if a.created_at >= since]
                  or [x for x in doses if x.scheduled_at <= now])
    return d, active


def _confirmation(db: Session, p: Patient, *, now: datetime, hours: int) -> dict | None:
    """The latest handover confirmed for this patient within the window, if any."""
    row = db.scalar(select(Handover).where(Handover.patient_id == p.id,
                                           Handover.created_at >= now - timedelta(hours=hours))
                    .order_by(Handover.created_at.desc(), Handover.id.desc()).limit(1))
    if row is None:
        return None
    return {"id": row.id, "human_confirmed_by": row.human_confirmed_by,
            "human_confirmed_by_name": _names(db, {row.human_confirmed_by}).get(row.human_confirmed_by),
            "confirmed_at": _iso(row.created_at), "window_hours": row.window_hours,
            "source": (row.ai_suggested or {}).get("source")}


def _out(draft: dict, confirmation: dict | None, now: datetime) -> dict:
    return {**draft, "generated_at": _iso(now), "confirmation": confirmation}


@router.get("")
def list_handovers(request: Request, ward: str | None = None, hours: int = Query(default=12, ge=1, le=48),
                   lang: str | None = Query(default=None, pattern=LANG),
                   user: User = Depends(require_roles("nurse", "doctor")), db: Session = Depends(get_db)) -> dict:
    """Nurse: her ward (and her supervisor doctor's patients); doctor: his patients. Admitted patients, plus anyone
    in scope with activity in the window. Each patient included is an audited record read."""
    hours = H.window_hours(hours)
    if user.role == "nurse":
        own, sup = nurse_scope(db, user)
        if ward and own and ward != own and not sup:
            raise forbidden("another ward")
        found = P.search(db, where=nurse_patient_filter(db, user), ward=ward)
    else:
        found = P.search(db, where=doctor_patient_filter(db, user), ward=ward)
    now = datetime.now(UTC)
    items = []
    for p in found:
        d, active = _draft(db, p, now=now, hours=hours, lang=lang)
        if d["patient"]["bed"] is None and not active:
            continue
        audit(db, user, "read", "handover", p.id, patient_id=p.id, ip=_ip(request))
        items.append(_out(d, _confirmation(db, p, now=now, hours=hours), now))
    # most urgent first: highest NEWS2, then bed
    items.sort(key=lambda h: (-(h["situation"]["latest_news2"] if h["situation"]["latest_news2"] is not None else -1),
                              h["patient"]["bed"] or "~", h["patient"]["id"]))
    db.commit()
    return {"window_hours": hours, "generated_at": _iso(now), "items": items}


@router.post("/{patient_id}/confirm")
def confirm_handover(patient_id: str, request: Request, body: ConfirmIn | None = None,
                     user: User = Depends(require_roles("nurse")), db: Session = Depends(get_db)) -> dict:
    """The outgoing nurse read the draft and hands it over: stores it with who confirmed it and when."""
    body = body or ConfirmIn()
    p = check_patient_access(db, user, patient_id, write=True, resource="handover", ip=_ip(request))
    hours = H.window_hours(body.hours)
    now = datetime.now(UTC)
    d, _ = _draft(db, p, now=now, hours=hours, lang=body.lang)
    row = Handover(id=new_id(db, "ho"), patient_id=p.id, ward=p.ward, window_hours=hours,
                   ai_suggested={**d, "generated_at": _iso(now)}, human_confirmed_by=user.id, created_at=now)
    db.add(row)
    db.flush()
    out = _out(d, _confirmation(db, p, now=now, hours=hours), now)
    db.commit()
    return out
