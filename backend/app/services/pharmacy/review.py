"""What the pharmacist reads (pharmacy spec §2, §5): the worklist, one prescription under review, the counts.
The patient part is a minimal projection (name, age, sex, ward, bed, allergies), never the full record. Routers
write the audit rows."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Admission, Patient, Prescription, PrescriptionReview, User
from app.schemas import iso
from app.services import schedule
from app.services.pharmacy import workflow as W
from app.services.pharmacy.checks import SEVERITY_RANK

WORKLIST_LIMIT = 200


def bed_of(db: Session, patient_id: str) -> str | None:
    return db.scalar(select(Admission.bed).where(Admission.patient_id == patient_id,
                                                 Admission.discharged_at.is_(None)))


def user_name(db: Session, user_id: str | None) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return u.name if u else None


def patient_view(db: Session, p: Patient) -> dict:
    return {"id": p.id, "name": f"{p.first_name} {p.last_name}".strip(),
            "age": W.age_on(p.date_of_birth, schedule.today_local()), "sex": p.sex, "ward": p.ward,
            "bed": bed_of(db, p.id), "allergies": list(p.allergies or [])}


def max_severity(checks: list[dict]) -> str | None:
    found = [c.get("severity") for c in checks if c.get("severity") in SEVERITY_RANK]
    return min(found, key=SEVERITY_RANK.__getitem__, default=None)


def _sort_key(rx: Prescription) -> tuple:
    sev = max_severity(rx.checks or [])
    return (not rx.urgent, SEVERITY_RANK.get(sev, len(SEVERITY_RANK)) if sev else len(SEVERITY_RANK),
            rx.created_at, rx.id)


def worklist_item(db: Session, rx: Prescription) -> dict:
    checks = rx.checks or []
    return {"prescription": W.rx_out(db, rx), "patient": patient_view(db, db.get(Patient, rx.patient_id)),
            "doctor_name": user_name(db, rx.doctor_id), "checks": checks, "urgent": rx.urgent,
            "waiting_since": iso(rx.created_at), "max_severity": max_severity(checks)}


def worklist(db: Session, status: str) -> list[dict]:
    """`status`: pending_pharmacy | changes_requested (urgent first, then the oldest, so the cap never drops the
    ones that waited longest) | all (every status, newest 200). Shown urgent first, then the highest stored
    severity, then the oldest."""
    stmt = select(Prescription)
    if status == "all":
        stmt = stmt.order_by(Prescription.created_at.desc(), Prescription.id.desc())
    else:
        stmt = stmt.where(Prescription.status == status).order_by(Prescription.urgent.desc(),
                                                                  Prescription.created_at, Prescription.id)
    rows = db.scalars(stmt.limit(WORKLIST_LIMIT)).all()
    return [worklist_item(db, r) for r in sorted(rows, key=_sort_key)]


def review_out(db: Session, r: PrescriptionReview) -> dict:
    return {"id": r.id, "prescription_id": r.prescription_id, "pharmacist_id": r.pharmacist_id,
            "pharmacist_name": user_name(db, r.pharmacist_id), "decision": r.decision, "comment": r.comment,
            "checks_snapshot": r.checks_snapshot or [], "created_at": iso(r.created_at)}


def detail(db: Session, rx: Prescription) -> dict:
    p = db.get(Patient, rx.patient_id)
    ancestors = W.chain(db, rx)
    exclude = {rx.id, *(a.id for a in ancestors)}
    running = db.scalars(select(Prescription).where(Prescription.patient_id == p.id, W.running_clause(),
                                                    Prescription.id.not_in(exclude))
                         .order_by(Prescription.created_at, Prescription.id)).all()
    history = db.scalars(select(PrescriptionReview).where(PrescriptionReview.prescription_id.in_(exclude))
                         .order_by(PrescriptionReview.created_at.desc(), PrescriptionReview.id.desc())).all()
    replaces = db.get(Prescription, rx.replaces_id) if rx.replaces_id else None
    return {"prescription": W.rx_out(db, rx), "patient": patient_view(db, p),
            "doctor_name": user_name(db, rx.doctor_id), "running": [W.rx_out(db, r) for r in running],
            "checks": [c.as_dict() for c in W.checks_for(db, p, rx.items, exclude)],
            "history": [review_out(db, r) for r in history],
            "replaces": W.rx_out(db, replaces) if replaces else None}


def summary(db: Session) -> dict:
    pending = db.scalars(select(Prescription).where(Prescription.status == "pending_pharmacy")).all()
    changes = db.scalar(select(func.count()).select_from(Prescription)
                        .where(Prescription.status == "changes_requested"))
    return {"pending": len(pending), "urgent_pending": sum(1 for r in pending if r.urgent),
            "critical_pending": sum(1 for r in pending if max_severity(r.checks or []) == "critical"),
            "changes_requested": changes or 0}
