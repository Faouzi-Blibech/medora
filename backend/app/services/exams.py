"""Exam-order rules (owner: Faouzi): status machine, who may read or upload, response and event shapes.
Spec: docs/superpowers/specs/2026-10-09-single-visit-and-case-notebook-design.md §4."""

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import can_access, has_grant, staff_ward
from app.models import Appointment, ExamResult, Patient, RadiographReading, Staff, User
from app.schemas import iso
from app.services import accounts

ALLOWED_TYPES = ("application/pdf", "image/jpeg", "image/png")
MAX_BYTES = 15 * 1024 * 1024


class BadStatus(Exception):
    """Maps to HTTP 409 {"code": "bad_status"}."""


def suggested_fields(patient_id: str, appointment_id: str, suggestion: dict) -> list[dict]:
    reason = "Suggested by the exam rules for: " + ", ".join(suggestion["bundles"])
    return [{"patient_id": patient_id, "appointment_id": appointment_id, "code": e["code"], "label": e["label"],
             "department": e["department"], "status": "suggested",
             "ai_suggested": {"source": suggestion["source"], "bundles": suggestion["bundles"], "reason": reason}}
            for e in suggestion["exams"]]


def order(o, *, user_id: str, now: datetime) -> None:
    if o.status != "suggested":
        raise BadStatus(f"exam is {o.status}")
    o.status, o.human_confirmed_by, o.ordered_at = "ordered", user_id, now


def cancel(o) -> None:
    if o.status not in ("suggested", "ordered"):
        raise BadStatus(f"exam is {o.status}")
    o.status = "cancelled"


def mark_done(o, *, now: datetime) -> None:
    if o.status != "ordered":
        raise BadStatus(f"exam is {o.status}")
    o.status, o.done_at = "done", now


def counts(orders: list) -> dict:
    s = [o.status for o in orders]
    return {"exams_total": s.count("ordered") + s.count("done"), "exams_done": s.count("done"),
            "exams_suggested": s.count("suggested")}


def can_read_results(db: Session, user: User, o, write: bool = False) -> bool:
    """Exam RESULTS (report text, files). Doctors: the orderer, the attending doctor or the appointment's booked
    doctor, never the pending-request pool; a read-only sharing grant counts for reads, never for `write`.
    Nurses: their department or ward. Patients and admin: never."""
    if user.role == "doctor":
        p = db.get(Patient, o.patient_id)
        a = db.get(Appointment, o.appointment_id) if o.appointment_id else None
        return (p is not None and (p.attending_doctor_id == user.id or (not write and has_grant(db, user.id, p.id)))) or (
            o.human_confirmed_by == user.id) or (
            a is not None and a.doctor_id == user.id)
    if user.role == "nurse":
        p = db.get(Patient, o.patient_id)
        return o.department == staff_ward(db, user) or (p is not None and can_access(db, user, p))
    return False


def can_read(db: Session, user: User, o) -> bool:
    """Exam STATUS and suggestions. Doctors additionally see every exam of a pending request (the pool)."""
    if user.role == "doctor":
        a = db.get(Appointment, o.appointment_id) if o.appointment_id else None
        return can_read_results(db, user, o) or (a is not None and a.status == "requested")
    if user.role == "nurse":
        p = db.get(Patient, o.patient_id)
        return o.department == staff_ward(db, user) or (p is not None and can_access(db, user, p))
    if user.role == "patient":
        return user.patient_id == o.patient_id and o.status in ("ordered", "done")
    return user.role == "admin"


def can_upload(db: Session, user: User, o) -> bool:
    return user.role == "nurse" and o.department == staff_ward(db, user)


def _name(db: Session, user_id: str | None) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return u.name if u else None


def _reading(db: Session, result) -> dict | None:
    rr = db.scalar(select(RadiographReading).where(RadiographReading.exam_result_id == result.id))
    if rr is None:
        return None
    return {"id": rr.id, "status": rr.status, "confirmed": rr.final_text is not None}


def to_out(db: Session, o, viewer: User) -> dict:
    if viewer.role == "admin":  # spec §4: admin reads status only, no patient identity, files or AI fields
        return {"id": o.id, "appointment_id": o.appointment_id, "department": o.department, "status": o.status}
    p = db.get(Patient, o.patient_id)
    out = {"id": o.id, "patient_id": o.patient_id, "appointment_id": o.appointment_id, "code": o.code,
           "label": o.label, "department": o.department, "status": o.status, "ai_suggested": o.ai_suggested,
           "human_confirmed_by": o.human_confirmed_by, "ordered_at": iso(o.ordered_at), "done_at": iso(o.done_at),
           "created_at": iso(o.created_at), "patient_name": f"{p.first_name} {p.last_name}" if p else None}
    if viewer.role in ("doctor", "nurse") and can_read_results(db, viewer, o):
        rows = db.scalars(select(ExamResult).where(ExamResult.exam_order_id == o.id)
                          .order_by(ExamResult.created_at)).all()
        out["results"] = [{"id": r.id, "file_name": r.file_name, "content_type": r.content_type,
                           "size_bytes": r.size_bytes, "report_text": r.report_text,
                           "uploaded_by_name": _name(db, r.uploaded_by),
                           "created_at": iso(r.created_at), "reading": _reading(db, r)} for r in rows]
    if viewer.role == "patient":
        out.pop("ai_suggested")
        out.pop("human_confirmed_by")
    return out


def ordered_event(patient, appointment_id: str | None, orders: list) -> dict:
    return {"appointment_id": appointment_id, "patient_first_name": patient.first_name,
            "patient_telegram_chat_id": patient.telegram_chat_id, "patient_email": patient.email,
            "exams": [{"label": o.label, "department": o.department} for o in orders]}


def results_ready_event(db: Session, appointment_id: str, patient, doctor_id: str | None) -> dict:
    doctor = accounts.active_doctor(db, doctor_id)  # a disabled doctor gets no patient data
    staff = db.get(Staff, doctor_id) if doctor else None
    return {"appointment_id": appointment_id, "patient_first_name": patient.first_name, "doctor_id": doctor_id,
            "doctor_name": doctor.name if doctor else None, "doctor_email": doctor.email if doctor else None,
            "doctor_chat_id": staff.telegram_chat_id if staff else None}


def safe_name(name: str) -> str:
    base = re.split(r"[\\/]", name or "")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._")
    return cleaned[:120] or "file"
