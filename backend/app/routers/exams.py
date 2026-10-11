"""Single-visit exams (owner: Faouzi): suggested at request time, ordered by a doctor, results uploaded by the
performing department's nurse. Contract: api.md 1.8; events: n8n-webhooks 1.3. Rules: app/services/exams.py."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.exams import catalogue
from app.auth.deps import can_see_appointment, check_appointment_access, check_patient_access, require_roles, staff_ward
from app.db import get_db
from app.errors import ApiError, forbidden, not_found
from app.ids import new_id
from app.integrations import n8n
from app.models import Appointment, ExamOrder, ExamResult, Patient, User
from app.services import exams as E
from app.services import radiology as R
from app.services import storage
from app.services.audit import audit

router = APIRouter(tags=["exams"])


class OrderIn(BaseModel):
    exam_ids: list[str]


class ExamIn(BaseModel):
    patient_id: str
    appointment_id: str | None = None
    code: str


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _bad_status(e: E.BadStatus) -> ApiError:
    return ApiError(409, "bad_status", str(e))


def _exam(db: Session, exam_id: str) -> ExamOrder:
    o = db.get(ExamOrder, exam_id)
    if o is None:
        raise not_found("exam")
    return o


def _visible(db: Session, user: User, rows) -> list[ExamOrder]:
    return [o for o in rows if E.can_read(db, user, o)]


@router.get("/exams/catalogue")
def exam_catalogue(user: User = Depends(require_roles("doctor"))) -> list[dict]:
    return [{"code": c, "label": v["label"], "department": v["department"]} for c, v in catalogue().items()]


@router.get("/appointments/{appointment_id}/exams")
def appointment_exams(appointment_id: str, request: Request,
                      user: User = Depends(require_roles("doctor", "admin", "patient")),
                      db: Session = Depends(get_db)) -> list[dict]:
    a = db.get(Appointment, appointment_id)
    if a is None:
        raise not_found("appointment")
    if not can_see_appointment(db, user, a):
        raise forbidden("not your appointment")
    rows = _visible(db, user, db.scalars(select(ExamOrder).where(ExamOrder.appointment_id == a.id)
                                         .order_by(ExamOrder.id)).all())
    audit(db, user, "read", "exams", a.id, patient_id=a.patient_id, ip=_ip(request))
    out = [E.to_out(db, o, user) for o in rows]
    db.commit()
    return out


@router.get("/patients/{patient_id}/exams")
def patient_exams(patient_id: str, request: Request, user: User = Depends(require_roles("doctor", "nurse", "patient")),
                  db: Session = Depends(get_db)) -> list[dict]:
    check_patient_access(db, user, patient_id, resource="exams", ip=_ip(request))
    rows = db.scalars(select(ExamOrder).where(ExamOrder.patient_id == patient_id,
                                              ExamOrder.status != "cancelled").order_by(ExamOrder.id)).all()
    out = [E.to_out(db, o, user) for o in _visible(db, user, rows)]
    db.commit()
    return out


@router.get("/exams")
def worklist(request: Request, status: str | None = None, user: User = Depends(require_roles("nurse", "admin")),
             db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(ExamOrder).order_by(ExamOrder.ordered_at, ExamOrder.id)
    if user.role == "nurse":
        stmt = stmt.where(ExamOrder.department == (staff_ward(db, user) or ""))
    if status:
        stmt = stmt.where(ExamOrder.status == status)
    rows = db.scalars(stmt).all()
    audit(db, user, "read", "exam_worklist", status or "", ip=_ip(request))
    out = [E.to_out(db, o, user) for o in rows]
    db.commit()
    return out


@router.post("/appointments/{appointment_id}/exams/order")
def order_selected(appointment_id: str, body: OrderIn, request: Request,
                   user: User = Depends(require_roles("doctor")), db: Session = Depends(get_db)) -> list[dict]:
    a = db.get(Appointment, appointment_id)
    if a is None:
        raise not_found("appointment")
    check_appointment_access(db, user, a, write=True, resource="exam_order", ip=_ip(request))
    rows = db.scalars(select(ExamOrder).where(ExamOrder.appointment_id == a.id).order_by(ExamOrder.id)).all()
    by_id = {o.id: o for o in rows}
    if any(i not in by_id for i in body.exam_ids):
        raise ApiError(422, "invalid", "exam_ids: not an exam of this appointment")
    now = datetime.now(UTC)
    ordered = []
    try:
        for i in body.exam_ids:
            E.order(by_id[i], user_id=user.id, now=now)
            ordered.append(by_id[i])
        for o in rows:
            if o.status == "suggested":
                E.cancel(o)
    except E.BadStatus as e:
        db.rollback()
        raise _bad_status(e) from e
    db.flush()
    event = E.ordered_event(db.get(Patient, a.patient_id), a.id, ordered) if ordered else None
    out = [E.to_out(db, o, user) for o in rows]
    db.commit()
    if event:
        n8n.emit("exam.ordered", event)
    return out


@router.post("/exams", status_code=201)
def add_exam(body: ExamIn, request: Request, user: User = Depends(require_roles("doctor")),
             db: Session = Depends(get_db)) -> dict:
    item = catalogue().get(body.code)
    if item is None:
        raise ApiError(422, "invalid", "code: not in the exam catalogue")
    p = db.get(Patient, body.patient_id)
    if p is None:
        raise not_found("patient")
    if body.appointment_id:
        a = db.get(Appointment, body.appointment_id)
        if a is None or a.patient_id != p.id:
            raise ApiError(422, "invalid", "appointment_id: not this patient's appointment")
        if not can_see_appointment(db, user, a, write=True):
            raise forbidden("not your appointment")
    elif p.attending_doctor_id != user.id:
        raise forbidden("not your patient")
    o = ExamOrder(id=new_id(db, "ex"), patient_id=p.id, appointment_id=body.appointment_id, code=body.code,
                  label=item["label"], department=item["department"], status="ordered", ai_suggested=None,
                  human_confirmed_by=user.id, ordered_at=datetime.now(UTC))
    db.add(o)
    db.flush()
    db.refresh(o)
    audit(db, user, "create", "exam", o.id, patient_id=p.id, ip=_ip(request))
    event = E.ordered_event(p, body.appointment_id, [o])
    out = E.to_out(db, o, user)
    db.commit()
    n8n.emit("exam.ordered", event)
    return out


@router.post("/exams/{exam_id}/cancel")
def cancel_exam(exam_id: str, request: Request, user: User = Depends(require_roles("doctor")),
                db: Session = Depends(get_db)) -> dict:
    o = _exam(db, exam_id)
    allowed = E.can_read(db, user, o) if o.status == "suggested" else E.can_read_results(db, user, o)
    if not allowed:
        raise forbidden("not your patient")
    try:
        E.cancel(o)
    except E.BadStatus as e:
        raise _bad_status(e) from e
    audit(db, user, "update", "exam", o.id, patient_id=o.patient_id, ip=_ip(request))
    db.flush()
    out = E.to_out(db, o, user)
    db.commit()
    return out


@router.post("/exams/{exam_id}/results")
async def upload_result(exam_id: str, request: Request, file: UploadFile = File(...), report_text: str = Form(""),
                        user: User = Depends(require_roles("nurse")), db: Session = Depends(get_db)) -> dict:
    o = _exam(db, exam_id)
    if not E.can_upload(db, user, o):
        raise forbidden("not your department")
    if o.status != "ordered":
        raise _bad_status(E.BadStatus(f"exam is {o.status}"))
    data = await file.read(E.MAX_BYTES + 1)
    if file.content_type not in E.ALLOWED_TYPES or len(data) > E.MAX_BYTES or not data:
        raise ApiError(422, "bad_file", "upload a PDF, JPEG or PNG of at most 15 MB")
    rid, name = new_id(db, "er"), E.safe_name(file.filename or "")
    key = f"exams/{o.id}/{rid}/{name}"
    storage.put(key, data, file.content_type)
    result = ExamResult(id=rid, exam_order_id=o.id, patient_id=o.patient_id, uploaded_by=user.id, file_key=key,
                        file_name=name, content_type=file.content_type, size_bytes=len(data),
                        report_text=report_text.strip()[:2000])
    db.add(result)
    if R.is_radiograph(o.code, file.content_type):
        db.flush()
        R.enqueue(db, result, o.label)
    E.mark_done(o, now=datetime.now(UTC))
    audit(db, user, "create", "exam_result", rid, patient_id=o.patient_id, ip=_ip(request))
    db.flush()
    event = None
    if o.appointment_id:
        still = db.scalar(select(ExamOrder.id).where(ExamOrder.appointment_id == o.appointment_id,
                                                     ExamOrder.status == "ordered").limit(1))
        if still is None:
            event = E.results_ready_event(db, o.appointment_id, db.get(Patient, o.patient_id), o.human_confirmed_by)
    out = E.to_out(db, o, user)
    db.commit()
    if event:
        n8n.emit("exam.results_ready", event)
    return out


REPORT_TYPES = (*E.ALLOWED_TYPES, "text/plain")


@router.post("/patients/{patient_id}/reports", status_code=201)
async def upload_report(patient_id: str, request: Request, file: UploadFile = File(...), title: str = Form(""),
                        report_text: str = Form(""), user: User = Depends(require_roles("doctor")),
                        db: Session = Depends(get_db)) -> dict:
    """The doctor attaches a report (an outside letter, a lab printout...) to the patient's case. It is stored as
    a done exam of department "Report", so it shows with the exams and the chat assistants can read its text."""
    p = check_patient_access(db, user, patient_id, write=True, resource="report", ip=_ip(request))
    data = await file.read(E.MAX_BYTES + 1)
    if file.content_type not in REPORT_TYPES or len(data) > E.MAX_BYTES or not data:
        raise ApiError(422, "bad_file", "upload a PDF, JPEG, PNG or text file of at most 15 MB")
    text = report_text.strip()
    if file.content_type == "text/plain":
        text = (text + "\n" + data.decode("utf-8", errors="replace")).strip()
    now = datetime.now(UTC)
    o = ExamOrder(id=new_id(db, "ex"), patient_id=p.id, appointment_id=None, code="report",
                  label=(title.strip() or E.safe_name(file.filename or "report"))[:120], department="Report",
                  status="done", human_confirmed_by=user.id, ordered_at=now, done_at=now)
    db.add(o)
    rid, name = new_id(db, "er"), E.safe_name(file.filename or "")
    key = f"exams/{o.id}/{rid}/{name}"
    storage.put(key, data, file.content_type)
    db.add(ExamResult(id=rid, exam_order_id=o.id, patient_id=p.id, uploaded_by=user.id, file_key=key, file_name=name,
                      content_type=file.content_type, size_bytes=len(data), report_text=text[:20000]))
    audit(db, user, "create", "report", rid, patient_id=p.id, ip=_ip(request))
    db.flush()
    out = E.to_out(db, o, user)
    db.commit()
    return out


@router.get("/exam-results/{result_id}/file")
def result_file(result_id: str, request: Request, user: User = Depends(require_roles("doctor", "nurse")),
                db: Session = Depends(get_db)) -> Response:
    r = db.get(ExamResult, result_id)
    if r is None:
        raise not_found("result")
    if not E.can_read_results(db, user, db.get(ExamOrder, r.exam_order_id)):
        raise forbidden("not your patient")
    audit(db, user, "read", "exam_result", r.id, patient_id=r.patient_id, ip=_ip(request))
    db.commit()
    return Response(storage.get(r.file_key), media_type=r.content_type,
                    headers={"Content-Disposition": f'inline; filename="{r.file_name}"',
                             "X-Content-Type-Options": "nosniff"})
