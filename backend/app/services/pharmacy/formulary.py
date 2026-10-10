"""The hospital formulary (livret thérapeutique): the seed file and catalogue helpers (pharmacy spec §3, §5)."""

import json
import re
from collections.abc import Iterable
from pathlib import Path

from decimal import Decimal

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.ids import new_id, reserve_upto
from app.models import Drug
from app.schemas import iso
from app.services.pharmacy.checks import DrugInfo, norm

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


_UNIT = r"(mg|mcg|[µμ]g|ug|iu|ml|g)"
_STRENGTH = re.compile(rf"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*{_UNIT}(?!\w)")


def _name(s: str) -> str:
    """Lower-case, no accents, "/" and "+" as spaces, and "500 mg" == "500mg": a digit followed by a unit is glued."""
    return re.sub(rf"(\d)\s+{_UNIT}(?!\w)", r"\1\2", norm(s))


def strengths(s: str) -> frozenset[tuple[float, str]]:
    """The (amount, unit) pairs a strength text carries, masses in mg: "1 g/125 mg" -> {(1000, mg), (125, mg)}."""
    out = set()
    for num, unit in _STRENGTH.findall(_name(s)):
        v = float(num.replace(",", "."))
        if unit == "g":
            out.add((v * 1000, "mg"))
        elif unit in ("µg", "μg", "mcg", "ug"):
            out.add((v / 1000, "mg"))
        else:
            out.add((v, unit))
    return frozenset((round(v, 6), u) for v, u in out)


def match_drug(med: str, drugs: Iterable) -> object | None:
    """The formulary drug a free-text medication ("Paracetamol 500mg") means, or None. `drugs` need `dci`,
    `brand_names` and `strength`. A name that starts with the DCI or a brand matches (the longest name wins). When
    the text carries a strength (1 g == 1000 mg), only a drug with that strength qualifies, so "Paracetamol 650mg" is
    None rather than the 500 mg tablet; with no strength in the text, the first of the drugs is the tie-break."""
    text = _name(med)
    wanted = strengths(text)
    best, best_hit = None, 0
    for d in drugs:
        names = [_name(d.dci), *(_name(b) for b in d.brand_names)]
        hit = max((len(n) for n in names if n and re.match(rf"{re.escape(n)}(?!\w)", text)), default=0)
        if not hit:
            continue
        have = strengths(getattr(d, "strength", "") or "")
        if wanted and have and not wanted <= have:
            continue
        if hit > best_hit:
            best, best_hit = d, hit
    return best


SEARCH_LIMIT = 50
NULLABLE = {"unit_mg", "max_daily_mg"}


def _num(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def drug_out(d: Drug) -> dict:
    return {"id": d.id, "dci": d.dci, "brand_names": list(d.brand_names or []), "form": d.form,
            "strength": d.strength, "unit_mg": _num(d.unit_mg), "max_daily_mg": _num(d.max_daily_mg),
            "atc_code": d.atc_code, "allergy_classes": list(d.allergy_classes or []),
            "interaction_groups": list(d.interaction_groups or []), "high_alert": d.high_alert,
            "min_stock": d.min_stock, "active": d.active, "created_at": iso(d.created_at),
            "updated_at": iso(d.updated_at)}


def _like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(db: Session, q: str, active: str) -> list[Drug]:
    """DCI or brand (substring) or ATC code (prefix), case-insensitive; `active` is true | false | all."""
    stmt = select(Drug)
    if active != "all":
        stmt = stmt.where(Drug.active.is_(active == "true"))
    q = q.strip()
    if q:
        sub, pre = f"%{_like(q)}%", f"{_like(q)}%"
        stmt = stmt.where(or_(Drug.dci.ilike(sub, escape="\\"), cast(Drug.brand_names, Text).ilike(sub, escape="\\"),
                              Drug.atc_code.ilike(pre, escape="\\")))
    return list(db.scalars(stmt.order_by(Drug.dci, Drug.strength, Drug.id).limit(SEARCH_LIMIT)))


def _duplicate(db: Session, dci: str, strength: str, form: str, exclude_id: str | None = None) -> bool:
    stmt = select(Drug.id).where(func.lower(Drug.dci) == dci.lower(), Drug.strength == strength, Drug.form == form)
    if exclude_id:
        stmt = stmt.where(Drug.id != exclude_id)
    return db.scalar(stmt.limit(1)) is not None


def create_drug(db: Session, data: dict) -> Drug:
    if _duplicate(db, data["dci"], data["strength"], data["form"]):
        raise ApiError(409, "conflict", "this drug, strength and form is already in the formulary")
    d = Drug(id=new_id(db, "d"), **data)
    db.add(d)
    db.flush()
    db.refresh(d)
    return d


def update_drug(db: Session, d: Drug, changes: dict) -> Drug:
    nulls = sorted(k for k, v in changes.items() if v is None and k not in NULLABLE)
    if nulls:
        raise ApiError(422, "invalid", f"{nulls[0]}: cannot be null")
    merged = {k: changes.get(k, getattr(d, k)) for k in ("dci", "strength", "form")}
    if _duplicate(db, merged["dci"], merged["strength"], merged["form"], exclude_id=d.id):
        raise ApiError(409, "conflict", "this drug, strength and form is already in the formulary")
    for k, v in changes.items():
        setattr(d, k, v)
    db.flush()
    db.refresh(d)
    return d


def to_info(d: Drug) -> DrugInfo:
    return DrugInfo(id=d.id, dci=d.dci, brand_names=tuple(d.brand_names or ()), atc_code=d.atc_code or "",
                    unit_mg=_num(d.unit_mg), max_daily_mg=_num(d.max_daily_mg),
                    allergy_classes=tuple(d.allergy_classes or ()),
                    interaction_groups=tuple(d.interaction_groups or ()), high_alert=bool(d.high_alert))


def drug_infos(db: Session, ids: set[str]) -> dict[str, DrugInfo]:
    """Formulary facts for these ids, inactive drugs included (a running prescription may still use one)."""
    if not ids:
        return {}
    return {d.id: to_info(d) for d in db.scalars(select(Drug).where(Drug.id.in_(ids)))}
