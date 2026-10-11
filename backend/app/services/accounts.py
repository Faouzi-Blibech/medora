"""Who may approve, reject, disable and enable whom (spec §6.2–6.5, signup-v2).

Hospital admin: any account, any role (only the admin approves a pharmacist). Doctor: only requests that name him, only as patient or nurse (a nurse joins
his team; a patient is linked to one of his records or gets a new record with him as attending), and only his team
members afterwards. Routers call these and then audit + commit."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError, forbidden, not_found
from app.ids import new_id
from app.models import Patient, Staff, User
from app.schemas import iso

ROLES = ("patient", "nurse", "doctor", "pharmacist", "admin")
DOCTOR_MAY_APPROVE = ("patient", "nurse")


def active_doctor(db: Session, user_id: str | None) -> User | None:
    """The user if he is an active doctor: the only kind that may receive patient data (alerts, digest, results)."""
    u = db.get(User, user_id) if user_id else None
    return u if u is not None and u.role == "doctor" and u.status == "active" else None


def _decided_by_admin(db: Session, target: User) -> bool:
    """Was the current disabled/rejected status set by an admin (or by someone unknown: rows from before 0005)?"""
    by = db.get(User, target.status_changed_by) if target.status_changed_by else None
    return by is None or by.role == "admin"


def can_review(approver: User, target: User) -> bool:
    if approver.role == "admin":
        return True
    return approver.role == "doctor" and target.requested_doctor_id == approver.id


def has_account(db: Session, patient_id: str) -> bool:
    """A patient record is taken while a non-disabled account is linked to it."""
    return db.scalar(select(User.id).where(User.patient_id == patient_id, User.status != "disabled")
                     .limit(1)) is not None


def _split_name(name: str) -> tuple[str, str]:
    first, _, last = name.strip().partition(" ")
    return first, last.strip()


def _patient_record(db: Session, approver: User, target: User, patient_id: str | None) -> tuple[Patient, bool]:
    """(record to link, created?). An existing record must be free; a doctor may only link his own patients."""
    if patient_id:
        p = db.get(Patient, patient_id, with_for_update=True)  # the lock serialises two approvals of one record
        if p is None:
            raise not_found("patient")
        if approver.role == "doctor" and p.attending_doctor_id != approver.id:
            raise forbidden("not your patient")
        if has_account(db, p.id):
            raise ApiError(409, "conflict", "this patient record already has an account")
        return p, False
    if approver.role == "doctor":
        attending = approver.id
    else:
        wanted = active_doctor(db, target.requested_doctor_id)
        attending = wanted.id if wanted else None
    first, last = _split_name(target.name)
    p = Patient(id=new_id(db, "p"), first_name=first, last_name=last, allergies=[], history="",
                attending_doctor_id=attending)
    db.add(p)
    db.flush()
    return p, True


def approve(db: Session, approver: User, target: User, role: str, ward: str | None, *, now: datetime,
            patient_id: str | None = None) -> tuple[Patient | None, bool]:
    """Activates the account. Returns (the patient record it was linked to, whether that record was just created)."""
    if not can_review(approver, target):
        raise forbidden("this request is not addressed to you")
    if role not in ROLES:
        raise ApiError(422, "invalid", "role: patient, nurse, doctor, pharmacist or admin")
    if patient_id and role != "patient":
        raise ApiError(422, "invalid", "patient_id: only for the patient role")
    if target.status not in ("pending", "rejected"):
        raise ApiError(409, "bad_status", f"account is {target.status}")
    if approver.role == "doctor":
        if target.status == "rejected" and _decided_by_admin(db, target):
            raise forbidden("the hospital admin rejected this request")
        if role not in DOCTOR_MAY_APPROVE:
            raise forbidden("a doctor can only approve patients and nurses")
        ward, supervisor = None, approver.id
    else:
        supervisor = target.requested_doctor_id if role == "nurse" else None
    patient, created = _patient_record(db, approver, target, patient_id) if role == "patient" else (None, False)
    target.role, target.status, target.approved_by, target.approved_at = role, "active", approver.id, now
    target.status_changed_by = None
    target.patient_id = patient.id if patient else None
    if role in ("doctor", "nurse"):
        st = db.get(Staff, target.id)
        if st is None:
            st = Staff(user_id=target.id)
            db.add(st)
        st.ward, st.supervisor_id = ward, supervisor if role == "nurse" else None
    db.flush()
    return patient, created


def reject(approver: User, target: User) -> None:
    if not can_review(approver, target):
        raise forbidden("this request is not addressed to you")
    if target.status != "pending":
        raise ApiError(409, "bad_status", f"account is {target.status}")
    target.status, target.status_changed_by = "rejected", approver.id


def can_manage(db: Session, actor: User, target: User) -> bool:
    if actor.id == target.id:
        return False
    if actor.role == "admin":
        return True
    st = db.get(Staff, target.id)
    return actor.role == "doctor" and st is not None and st.supervisor_id == actor.id


def set_active(db: Session, actor: User, target: User, active: bool) -> None:
    if not can_manage(db, actor, target):
        raise forbidden("you cannot manage this account")
    if active:
        if target.status != "disabled" or target.role is None:
            raise ApiError(409, "bad_status", f"account is {target.status}")
        if actor.role == "doctor" and _decided_by_admin(db, target):
            raise forbidden("the hospital admin disabled this account")
        target.status, target.status_changed_by = "active", None
    else:
        if target.status == "disabled":
            raise ApiError(409, "bad_status", "account is already disabled")
        target.status, target.status_changed_by = "disabled", actor.id


def admin_out(db: Session, u: User) -> dict:
    st = db.get(Staff, u.id)
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "status": u.status,
            "ward": st.ward if st else None, "supervisor_id": st.supervisor_id if st else None}


def pending_out(db: Session, u: User) -> dict:
    doc = db.get(User, u.requested_doctor_id) if u.requested_doctor_id else None
    return {"id": u.id, "name": u.name, "email": u.email, "note": u.requested_note,
            "requested_role": u.requested_role,
            "requested_doctor_id": u.requested_doctor_id, "requested_doctor_name": doc.name if doc else None,
            "status": u.status, "created_at": iso(u.created_at)}
