"""Give existing prescription items a `drug_id` (pharmacy spec §3 backfill). Kept apart from formulary.py, whose
`match_drug` does the name matching."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Drug, Prescription
from app.services.pharmacy.formulary import match_drug


def backfill_drug_ids(db: Session) -> int:
    """Set `drug_id` on every prescription item that has no such key yet (null when nothing matches). Returns how
    many prescriptions changed. JSONB: the list is reassigned so SQLAlchemy sees the change."""
    drugs = list(db.scalars(select(Drug).where(Drug.active.is_(True))))
    changed = 0
    for rx in db.scalars(select(Prescription)):
        if all("drug_id" in it for it in rx.items):
            continue
        rx.items = [it if "drug_id" in it else {**it, "drug_id": getattr(match_drug(it.get("med", ""), drugs), "id", None)}
                    for it in rx.items]
        changed += 1
    db.flush()
    return changed
