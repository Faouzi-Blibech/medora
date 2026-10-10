"""The hospital formulary (livret thérapeutique): the seed file and catalogue helpers (pharmacy spec §3, §5)."""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ids import reserve_upto
from app.models import Drug

FORMULARY = Path(__file__).resolve().parents[2] / "data" / "pharmacy" / "formulary.v1.json"
DRUG_FIELDS = ("dci", "brand_names", "form", "strength", "unit_mg", "max_daily_mg", "atc_code", "allergy_classes",
               "interaction_groups", "high_alert", "min_stock")


def formulary_entries(path: Path = FORMULARY) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["drugs"]


def load_formulary(db: Session, path: Path = FORMULARY) -> int:
    """Insert the file's drugs that are not in the table yet (matched by id). Never overwrites: a pharmacist's edits
    win. Advances the `d` sequence (shared with dose ids) past the file's ids. Returns how many rows were inserted."""
    entries = formulary_entries(path)
    have = set(db.scalars(select(Drug.id)))
    added = 0
    for e in entries:
        if e["id"] not in have:
            db.add(Drug(id=e["id"], active=True, **{k: e[k] for k in DRUG_FIELDS}))
            added += 1
    db.flush()
    reserve_upto(db, "d", max(int(e["id"].split("-")[1]) for e in entries))
    return added
