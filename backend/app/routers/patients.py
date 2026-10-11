from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import (check_patient_access, doctor_patient_filter, nurse_patient_filter, nurse_scope,
                           require_roles)
from app.db import get_db
from app.errors import forbidden
from app.ids import new_id
from app.models import Note, Prescription, User, Vital
from app.schemas import (NoteIn, NoteOut, PatientListItem, PatientOut, PatientPatch, PatientSummary,
                         VitalOut)
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
