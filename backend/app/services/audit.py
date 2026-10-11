"""Append-only audit trail. Every read of a patient record goes through here (privacy rule)."""

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def audit(db: Session, user: User | None, action: str, resource: str, resource_id: str,
          patient_id: str | None = None, ip: str = "") -> None:
    db.add(AuditLog(user_id=user.id if user else None, role=user.role if user else None, action=action,
                    resource=resource, resource_id=resource_id or "", patient_id=patient_id, ip=ip or ""))
    db.flush()
