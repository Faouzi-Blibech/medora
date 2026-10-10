"""Prescription safety checks (pharmacy spec §4). Pure and deterministic: no database, no clock, no LLM.

The engine only flags; a pharmacist decides. `message` is English for logs; the web translates by `code` + `params`.
Rule files: app/rules/pharmacy/*.v1.json (illustrative, not a clinical reference; to be validated by the hospital's
pharmacists).
"""

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parents[2] / "rules" / "pharmacy"
SEVERITY_RANK = {"critical": 0, "major": 1, "moderate": 2, "info": 3}


@dataclass(frozen=True)
class DrugInfo:
    """The formulary facts the checks need (one `drugs` row)."""

    id: str
    dci: str
    brand_names: tuple[str, ...] = ()
    atc_code: str = ""
    unit_mg: float | None = None
    max_daily_mg: float | None = None
    allergy_classes: tuple[str, ...] = ()
    interaction_groups: tuple[str, ...] = ()
    high_alert: bool = False


@dataclass(frozen=True)
class PatientInfo:
    age: int | None
    allergies: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunningItem:
    """One item of another running prescription of the same patient."""

    prescription_id: str
    med: str
    drug_id: str | None


@dataclass(frozen=True)
class Check:
    code: str
    severity: str  # critical | major | moderate | info
    item_index: int
    drug_id: str | None
    params: dict = field(default_factory=dict)
    message: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class InteractionRule:
    a: str
    b: str
    severity: str
    note: str


@dataclass(frozen=True)
class Rules:
    synonyms: tuple[tuple[str, str], ...]  # (normalised term, allergy class)
    interactions: tuple[InteractionRule, ...]
    elderly_dci: frozenset[str]
    elderly_min_age: int


def norm(s: str) -> str:
    """Casefold, drop accents and Arabic marks, and collapse spaces/dashes/underscores: 'Pénicilline' → 'penicilline',
    'أسبرين' → 'اسبرين', 'beta_lactam' → 'beta lactam'."""
    s = unicodedata.normalize("NFKD", (s or "").casefold())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[\s\-_/']+", " ", s).strip()


def _read(name: str) -> dict:
    return json.loads((RULES_DIR / name).read_text(encoding="utf-8"))


@lru_cache
def load_rules() -> Rules:
    syn = _read("allergy_synonyms.v1.json")["classes"]
    pairs = tuple((norm(term), cls) for cls, terms in syn.items() for term in (cls, *terms))
    inter = tuple(InteractionRule(p["groups"][0], p["groups"][1], p["severity"], p["note"])
                  for p in _read("interactions.v1.json")["pairs"])
    eld = _read("elderly_caution.v1.json")
    return Rules(pairs, inter, frozenset(norm(d) for d in eld["dci"]), int(eld["min_age"]))


def allergy_classes(allergy: str, rules: Rules) -> set[str]:
    """The allergy classes a patient's allergy text names (whole-word match of any synonym, any language)."""
    text = norm(allergy)
    return {cls for term, cls in rules.synonyms
            if term and (text == term or re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text))}


def daily_mg(item: dict, drug: DrugInfo) -> float | None:
    """mg per day: `dose_mg` (per intake) or units_per_intake × unit_mg, times the intakes per day."""
    per = item.get("dose_mg")
    if per is None and drug.unit_mg is not None:
        per = int(item.get("units_per_intake") or 1) * drug.unit_mg
    return None if per is None else float(per) * len(item.get("times") or [])


def _duplicate(a: DrugInfo, b: DrugInfo) -> str | None:
    if norm(a.dci) == norm(b.dci):
        return "same_dci"
    if len(a.atc_code) >= 5 and a.atc_code[:5] == b.atc_code[:5]:
        return "same_atc_class"
    return None


def _interactions(a: DrugInfo, b: DrugInfo, rules: Rules) -> list[InteractionRule]:
    ga, gb = set(a.interaction_groups), set(b.interaction_groups)
    return [r for r in rules.interactions if (r.a in ga and r.b in gb) or (r.b in ga and r.a in gb)]


def _single(i: int, item: dict, d: DrugInfo, patient: PatientInfo, patient_classes: dict[str, str],
            rules: Rules) -> list[Check]:
    """Checks that look at one item alone: allergy, daily dose, high alert, elderly."""
    med = item.get("med", "")
    out: list[Check] = []
    hit = next(((c, patient_classes[c]) for c in d.allergy_classes if c in patient_classes), None)
    if hit is None:  # an allergy written as the drug's own name or brand
        names = {norm(d.dci), *(norm(b) for b in d.brand_names)}
        direct = next((a for a in patient.allergies if norm(a) in names), None)
        hit = (norm(d.dci), direct) if direct else None
    if hit:
        out.append(Check("allergy", "critical", i, d.id, {"med": med, "allergy": hit[1], "class": hit[0]},
                         f"{d.dci}: the patient is allergic to {hit[1]} ({hit[0]})"))
    daily = daily_mg(item, d) if d.max_daily_mg else None
    if daily is not None and daily > d.max_daily_mg:
        sev = "critical" if daily > 2 * d.max_daily_mg else "major"
        out.append(Check("max_daily_dose", sev, i, d.id,
                         {"med": med, "daily_mg": daily, "max_daily_mg": d.max_daily_mg},
                         f"{d.dci}: {daily:g} mg/day is above the {d.max_daily_mg:g} mg/day maximum"))
    if d.high_alert:
        out.append(Check("high_alert", "info", i, d.id, {"med": med}, f"{d.dci}: high-alert drug, double-check"))
    if patient.age is not None and patient.age >= rules.elderly_min_age and norm(d.dci) in rules.elderly_dci:
        out.append(Check("elderly", "moderate", i, d.id, {"med": med, "age": patient.age},
                         f"{d.dci}: use with caution at age {patient.age}"))
    return out


def run_checks(patient: PatientInfo, items: list[dict], running: list[RunningItem], drugs: dict[str, DrugInfo],
               rules: Rules | None = None) -> list[Check]:
    """Every check for the candidate `items` against each other and the patient's other running prescriptions,
    most severe first (then by item index, then by code). Items without a known drug are only `non_formulary`."""
    rules = rules or load_rules()
    patient_classes: dict[str, str] = {}
    for a in patient.allergies:
        for c in sorted(allergy_classes(a, rules)):
            patient_classes.setdefault(c, a)
    out: list[Check] = []
    cands: list[tuple[int, dict, DrugInfo]] = []
    for i, it in enumerate(items):
        d = drugs.get(it.get("drug_id") or "")
        if d is None:
            med = it.get("med", "")
            out.append(Check("non_formulary", "moderate", i, None, {"med": med},
                             f"{med}: not in the hospital formulary"))
            continue
        cands.append((i, it, d))
        out += _single(i, it, d, patient, patient_classes, rules)
    others = [(r, drugs[r.drug_id]) for r in running if r.drug_id and r.drug_id in drugs]
    for n, (i, it, d) in enumerate(cands):
        med = it.get("med", "")
        partners = [(j, jt.get("med", ""), e, None) for j, jt, e in cands[n + 1:]]
        partners += [(None, r.med, e, r.prescription_id) for r, e in others]
        for j, other_med, e, rx_id in partners:
            with_ = {"with_med": other_med, "with_drug_id": e.id, "with_item_index": j,
                     "with_prescription_id": rx_id}
            reason = _duplicate(d, e)
            if reason:
                out.append(Check("duplicate_therapy", "major", i, d.id, {"med": med, "reason": reason, **with_},
                                 f"{d.dci} duplicates {other_med} ({reason})"))
            for rule in _interactions(d, e, rules):
                out.append(Check("interaction", rule.severity, i, d.id,
                                 {"med": med, "groups": [rule.a, rule.b], "note": rule.note, **with_},
                                 f"{d.dci} + {other_med}: {rule.note}"))
    return sorted(out, key=lambda c: (SEVERITY_RANK[c.severity], c.item_index, c.code))
