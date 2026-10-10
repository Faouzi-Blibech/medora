"""The pharmacist's routes (api.md 1.12 → Pharmacist). Pharmacist only; every prescription read is audited with
its patient."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.db import get_db
from app.errors import not_found
from app.iot import publisher
from app.models import Prescription, User
from app.schemas import CommentIn, ValidateIn
from app.services.audit import audit
from app.services.pharmacy import review as R
from app.services.pharmacy import workflow as W

router = APIRouter(prefix="/pharmacy", tags=["pharmacy"])
PHARMACIST = require_roles("pharmacist")


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("/worklist")
def worklist(request: Request, status: Literal["pending_pharmacy", "changes_requested", "all"] = "pending_pharmacy",
             user: User = Depends(PHARMACIST), db: Session = Depends(get_db)) -> list[dict]:
    rows = R.worklist(db, status)
    for w in rows:
        audit(db, user, "read", "prescription", w["prescription"]["id"], patient_id=w["patient"]["id"],
              ip=_ip(request))
    db.commit()
    return rows


@router.get("/summary")
def summary(user: User = Depends(PHARMACIST), db: Session = Depends(get_db)) -> dict:
    out = R.summary(db)  # counts only, no patient data
    db.commit()
    return out


@router.get("/prescriptions/{rx_id}")
def review(rx_id: str, request: Request, user: User = Depends(PHARMACIST), db: Session = Depends(get_db)) -> dict:
    rx = db.get(Prescription, rx_id)
    if rx is None:
        raise not_found("prescription")
    out = R.detail(db, rx)
    audit(db, user, "read", "prescription", rx.id, patient_id=rx.patient_id, ip=_ip(request))
    db.commit()
    return out


def _decide(db: Session, user: User, request: Request, rx_id: str, decision: str, comment: str | None,
            acknowledged: bool = False) -> dict:
    out = W.decide(db, user, rx_id, decision, comment, acknowledged=acknowledged)
    W.apply_doses(db, out)
    audit(db, user, "update", "prescription", out.rx.id, patient_id=out.rx.patient_id, ip=_ip(request))
    W.emit_review(db, out.rx, decision, comment)
    frames = W.status_frames(db, out)
    body = W.rx_out(db, out.rx)
    db.commit()
    for f in frames:
        publisher.publish_ws_frame(f)
    return body


@router.post("/prescriptions/{rx_id}/validate")
def validate(rx_id: str, body: ValidateIn, request: Request, user: User = Depends(PHARMACIST),
             db: Session = Depends(get_db)) -> dict:
    return _decide(db, user, request, rx_id, "validated", body.comment, body.acknowledged)


@router.post("/prescriptions/{rx_id}/request-changes")
def request_changes(rx_id: str, body: CommentIn, request: Request, user: User = Depends(PHARMACIST),
                    db: Session = Depends(get_db)) -> dict:
    return _decide(db, user, request, rx_id, "changes_requested", body.comment)


@router.post("/prescriptions/{rx_id}/reject")
def reject(rx_id: str, body: CommentIn, request: Request, user: User = Depends(PHARMACIST),
           db: Session = Depends(get_db)) -> dict:
    return _decide(db, user, request, rx_id, "rejected", body.comment)
