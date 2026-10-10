"""The hospital formulary (livret thérapeutique): the seed file and catalogue helpers (pharmacy spec §3, §5)."""

import json
import re
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ids import reserve_upto
from app.models import Drug
from app.services.pharmacy.checks import norm

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


def _name(s: str) -> str:
    """Lower-case, no accents, and "500 mg" == "500mg": a digit followed by a unit is glued together."""
    return re.sub(r"(\d)\s+(mg|g|µg|mcg|ug|iu|ml)\b", r"\1\2", norm(s))


def match_drug(med: str, drugs: Iterable) -> object | None:
    """The formulary drug a free-text medication ("Paracetamol 500mg") means, or None. `drugs` need `dci`,
    `brand_names` and `strength`. A name that starts with the DCI or a brand matches; when several strengths of
    the same DCI qualify, the one whose strength appears in the text wins (the longest DCI/brand name first)."""
    text = _name(med)
    best, best_key = None, (0, 0)
    for d in drugs:
        names = [_name(d.dci), *(_name(b) for b in d.brand_names)]
        hit = max((len(n) for n in names if n and re.match(rf"{re.escape(n)}(?!\w)", text)), default=0)
        if not hit:
            continue
        strength = _name(d.strength)
        key = (hit, 1 if strength and re.search(rf"(?<!\w){re.escape(strength)}(?!\w)", text) else 0)
        if key > best_key:
            best, best_key = d, key
    return best
