"""Prescribing (api.md 1.12 → Prescriptions). The life cycle lives in app/services/pharmacy/workflow.py."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import can_access, check_patient_access, require_roles
from app.db import get_db
from app.errors import forbidden, not_found
from app.iot import publisher
from app.models import Patient, User
from app.schemas import PrescriptionCheckIn, PrescriptionIn, PrescriptionPatch
from app.services.audit import audit
from app.services.pharmacy import workflow as W

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _finish(db: Session, out: W.Outcome) -> dict:
    """Doses + device schedule, then commit, then the WS frames (never for a rolled-back change)."""
    sent, version = W.apply_doses(db, out)
    frames = W.status_frames(db, out)
    body = {**W.rx_out(db, out.rx), "schedule_version": version, "published_to_device": sent}
    db.commit()
    for f in frames:
        publisher.publish_ws_frame(f)
    return body


@router.post("/check")
def check(body: PrescriptionCheckIn, request: Request, user: User = Depends(require_roles("doctor")),
          db: Session = Depends(get_db)) -> dict:
    """Dry run while the doctor types: the warnings the pharmacist will see. Writes only the audit row."""
    patient = db.get(Patient, body.patient_id)
    if patient is None:
        raise not_found("patient")
    if not can_access(db, user, patient, write=True):
        raise forbidden("not your patient")
    items = [i.model_dump() for i in body.items]
    W.ensure_drugs(db, items)
    old = W.replace_target(db, body.replaces_id, patient.id, lock_row=False) if body.replaces_id else None
    checks = W.checks_for(db, patient, items, W.exclusions(db, old))
    audit(db, user, "read", "prescription_check", patient.id, patient_id=patient.id, ip=_ip(request))
    db.commit()
    return {"checks": [c.as_dict() for c in checks]}


@router.post("", status_code=201)
def create(body: PrescriptionIn, request: Request, user: User = Depends(require_roles("doctor")),
           db: Session = Depends(get_db)) -> dict:
    patient = check_patient_access(db, user, body.patient_id, write=True, resource="prescription", ip=_ip(request))
    out = W.create(db, user, patient, body)
    audit(db, user, "create", "prescription", out.rx.id, patient_id=patient.id, ip=_ip(request))
    for prev in out.touched[1:]:
        audit(db, user, "update", "prescription", prev.id, patient_id=patient.id, ip=_ip(request))
    return _finish(db, out)


@router.patch("/{rx_id}")
def stop(rx_id: str, body: PrescriptionPatch, request: Request, user: User = Depends(require_roles("doctor")),
         db: Session = Depends(get_db)) -> dict:
    rx = W.lock(db, rx_id)
    check_patient_access(db, user, rx.patient_id, write=True, resource="prescription", ip=_ip(request))
    return _finish(db, W.stop(db, rx))
