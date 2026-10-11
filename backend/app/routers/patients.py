from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import (check_patient_access, doctor_patient_filter, nurse_patient_filter, nurse_scope,
                           require_roles)
from app.db import get_db
from app.ai.early_warning import score_news2
from app.errors import ApiError, forbidden
from app.ids import new_id
from app.iot import publisher
from app.iot.ingest import frame
from app.models import Admission, Note, Prescription, User, Vital
from app.schemas import (NoteIn, NoteOut, PatientListItem, PatientOut, PatientPatch, PatientSummary,
                         VitalIn, VitalOut, iso)
from app.services import patients as P
from app.services.audit import audit
from app.services.pharmacy import workflow as W

router = APIRouter(prefix="/patients", tags=["patients"])

NURSE_PATCHABLE = {"allergies"}  # api.md: nurse (ward; allergies + notes only); notes have their own route
MAX_VITALS = 5000


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("")
def list_patients(request: Request, ward: str | None = None, q: str | None = None, unlinked: bool = False,
                  user: User = Depends(require_roles("doctor", "nurse", "admin")),
                  db: Session = Depends(get_db)):
    if user.role == "admin":
        rows = [PatientListItem(**P.list_item(db, p)) for p in P.search(db, ward=ward, q=q, unlinked=unlinked)]
    else:
        if user.role == "nurse":
            own, sup = nurse_scope(db, user)
            if ward and own and ward != own and not sup:
                raise forbidden("another ward")
            found = P.search(db, where=nurse_patient_filter(db, user), ward=ward, q=q, unlinked=unlinked)
        else:
            found = P.search(db, where=doctor_patient_filter(db, user), ward=ward, q=q, unlinked=unlinked)
        rows = [PatientSummary(**P.summary(db, p)) for p in found]
        rows.sort(key=lambda r: (-(r.latest_news2 if r.latest_news2 is not None else -1), r.id))
    audit(db, user, "read", "patient_list", ward or "", ip=_ip(request))
    db.commit()
    return [r.model_dump(mode="json") for r in rows]


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: str, request: Request, user: User = Depends(require_roles("doctor", "nurse", "patient")),
                db: Session = Depends(get_db)):
    p = check_patient_access(db, user, patient_id, ip=_ip(request))
    out = PatientOut(**P.detail(db, p))
    db.commit()
    return out


@router.patch("/{patient_id}", response_model=PatientOut)
def patch_patient(patient_id: str, body: PatientPatch, request: Request,
                  user: User = Depends(require_roles("doctor", "nurse")), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_unset=True)
    if user.role == "nurse" and set(changes) - NURSE_PATCHABLE:
        raise forbidden("nurses may only edit allergies")
    p = check_patient_access(db, user, patient_id, write=True, ip=_ip(request))
    for k, v in changes.items():
        setattr(p, k, v)
    db.flush()
    out = PatientOut(**P.detail(db, p))
    db.commit()
    return out


@router.get("/{patient_id}/vitals", response_model=list[VitalOut])
def get_vitals(patient_id: str, request: Request, from_: datetime | None = Query(None, alias="from"),
               to: datetime | None = None, user: User = Depends(require_roles("doctor", "nurse", "patient")),
               db: Session = Depends(get_db)):
    check_patient_access(db, user, patient_id, resource="vitals", ip=_ip(request))
    to = to or datetime.now(UTC)
    from_ = from_ or to - timedelta(hours=24)
    rows = db.scalars(select(Vital).where(Vital.patient_id == patient_id, Vital.ts >= from_, Vital.ts <= to)
                      .order_by(Vital.ts.desc()).limit(MAX_VITALS)).all()
    db.commit()
    return list(reversed(rows))  # newest MAX_VITALS, returned oldest first


@router.post("/{patient_id}/vitals", response_model=VitalOut, status_code=201)
def record_vitals(patient_id: str, body: VitalIn, request: Request,
                  user: User = Depends(require_roles("doctor", "nurse")), db: Session = Depends(get_db)):
    """A reading taken by hand at the bedside: stored as source `manual`, scored and alerted like a feed reading."""
    if body.hr is None and body.spo2 is None and body.temp is None:
        raise ApiError(422, "invalid", "enter at least one value")
    check_patient_access(db, user, patient_id, write=True, resource="vitals", ip=_ip(request))
    from app.services import alerts  # late import, as in iot.ingest

    ts = datetime.now(UTC).replace(microsecond=0)
    device_id = db.scalar(select(Admission.device_id).where(Admission.patient_id == patient_id,
                                                            Admission.discharged_at.is_(None))) or "manual"
    if db.get(Vital, (ts, f"manual:{user.id}")) is not None:
        raise ApiError(409, "conflict", "a reading was just saved; wait a second")
    news = score_news2(body.hr, body.spo2, body.temp)
    v = Vital(ts=ts, device_id=f"manual:{user.id}", patient_id=patient_id, hr=body.hr, spo2=body.spo2,
              temp=body.temp, nurse_id=user.id, news2=news.score, source="manual")
    db.add(v)
    db.flush()
    frames = [frame(db, "vital", {"patient_id": patient_id, "device_id": v.device_id, "ts": iso(ts), "hr": v.hr,
                                  "spo2": v.spo2, "temp": v.temp, "news2": news.score}, patient_id)]
    frames += alerts.on_vital(db, patient_id, device_id, news, body.hr, body.spo2, body.temp)
    out = VitalOut.model_validate(v)
    db.commit()
    for f in frames:
        publisher.publish_ws_frame(f)
    return out


@router.get("/{patient_id}/prescriptions")
def get_prescriptions(patient_id: str, request: Request,
                      user: User = Depends(require_roles("doctor", "nurse", "patient")),
                      db: Session = Depends(get_db)) -> list[dict]:
    check_patient_access(db, user, patient_id, resource="prescription", ip=_ip(request))
    rows = db.scalars(select(Prescription).where(Prescription.patient_id == patient_id)
                      .order_by(Prescription.created_at.desc(), Prescription.id.desc())).all()
    out = [W.rx_out(db, r, for_patient=user.role == "patient") for r in rows]
    db.commit()
    return out


def _note_out(db: Session, n: Note) -> NoteOut:
    author = db.get(User, n.author_id)
    return NoteOut(id=n.id, author_id=n.author_id, author_role=author.role if author else None,
                   author_name=author.name if author else None, text=n.text, created_at=n.created_at)


@router.get("/{patient_id}/notes", response_model=list[NoteOut])
def get_notes(patient_id: str, request: Request, user: User = Depends(require_roles("doctor", "nurse")),
              db: Session = Depends(get_db)):
    check_patient_access(db, user, patient_id, resource="note", ip=_ip(request))
    rows = db.scalars(select(Note).where(Note.patient_id == patient_id)
                      .order_by(Note.created_at.desc(), Note.id.desc())).all()
    out = [_note_out(db, n) for n in rows]
    db.commit()
    return out


@router.post("/{patient_id}/notes", response_model=NoteOut, status_code=201)
def add_note(patient_id: str, body: NoteIn, request: Request,
             user: User = Depends(require_roles("doctor", "nurse")), db: Session = Depends(get_db)):
    check_patient_access(db, user, patient_id, write=True, resource="note", ip=_ip(request))
    n = Note(id=new_id(db, "n"), patient_id=patient_id, author_id=user.id, text=body.text.strip())
    db.add(n)
    db.flush()
    db.refresh(n)
    out = _note_out(db, n)
    db.commit()
    return out
