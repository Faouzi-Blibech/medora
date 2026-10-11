"""Radiograph reading endpoints (owner: Wali). Contract: api.md 1.14. The model drafts, a doctor confirms."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import check_patient_access, require_roles
from app.db import get_db
from app.errors import ApiError, forbidden, not_found
from app.ids import new_id
from app.models import ExamOrder, ExamResult, RadiographReading, User
from app.services import exams as E
from app.services import radiology as R
from app.services import storage
from app.services.audit import audit

router = APIRouter(tags=["radiology"])

IMAGE_TYPES = ("image/jpeg", "image/png")


class ConfirmIn(BaseModel):
    final_text: str = Field(min_length=1, max_length=20000)


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _load(db: Session, user: User, result_id: str, write: bool = False) -> tuple[ExamResult, RadiographReading]:
    res = db.get(ExamResult, result_id)
    if res is None:
        raise not_found("result")
    if not E.can_read_results(db, user, db.get(ExamOrder, res.exam_order_id), write=write):
        raise forbidden("not your patient")
    r = db.scalar(select(RadiographReading).where(RadiographReading.exam_result_id == res.id))
    if r is None:
        raise not_found("reading")
    return res, r


@router.get("/exam-results/{result_id}/reading")
def get_reading(result_id: str, request: Request, user: User = Depends(require_roles("doctor", "nurse")),
                db: Session = Depends(get_db)) -> dict:
    _, r = _load(db, user, result_id)
    if user.role == "doctor":
        audit(db, user, "read", "radiograph_reading", r.id, patient_id=r.patient_id, ip=_ip(request))
    out = R.to_out(db, r, user)
    db.commit()
    return out


@router.put("/exam-results/{result_id}/reading")
def confirm_reading(result_id: str, body: ConfirmIn, request: Request,
                    user: User = Depends(require_roles("doctor")), db: Session = Depends(get_db)) -> dict:
    text = body.final_text.strip()
    if not text:
        raise ApiError(422, "invalid", "final_text: must not be empty")
    _, r = _load(db, user, result_id, write=True)  # a read-only sharing grant never confirms
    R.confirm(db, r, user, text, datetime.now(UTC))
    audit(db, user, "update", "radiograph_reading", r.id, patient_id=r.patient_id, ip=_ip(request))
    out = R.to_out(db, r, user)
    db.commit()
    return out


@router.post("/patients/{patient_id}/radiographs", status_code=201)
async def upload_radiograph(patient_id: str, request: Request, file: UploadFile = File(...), title: str = Form(""),
                            user: User = Depends(require_roles("doctor")), db: Session = Depends(get_db)) -> dict:
    """The doctor attaches an outside radiograph: a done Imaging exam with a queued AI reading."""
    p = check_patient_access(db, user, patient_id, write=True, resource="radiograph", ip=_ip(request))
    data = await file.read(E.MAX_BYTES + 1)
    if file.content_type not in IMAGE_TYPES or len(data) > E.MAX_BYTES or not data:
        raise ApiError(422, "bad_file", "upload a JPEG or PNG of at most 15 MB")
    now = datetime.now(UTC)
    o = ExamOrder(id=new_id(db, "ex"), patient_id=p.id, appointment_id=None, code="xray_outside",
                  label=(title.strip() or "Outside X-ray")[:120], department="Imaging", status="done",
                  human_confirmed_by=user.id, ordered_at=now, done_at=now)
    db.add(o)
    rid, name = new_id(db, "er"), E.safe_name(file.filename or "")
    key = f"exams/{o.id}/{rid}/{name}"
    storage.put(key, data, file.content_type)
    result = ExamResult(id=rid, exam_order_id=o.id, patient_id=p.id, uploaded_by=user.id, file_key=key,
                        file_name=name, content_type=file.content_type, size_bytes=len(data), report_text="")
    db.add(result)
    db.flush()
    R.enqueue(db, result, o.label)
    audit(db, user, "create", "radiograph", rid, patient_id=p.id, ip=_ip(request))
    db.flush()
    out = E.to_out(db, o, user)
    db.commit()
    return out
