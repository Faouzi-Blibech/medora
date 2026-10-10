"""Prescription safety checks (pharmacy spec §4). Pure and deterministic: no database, no clock, no LLM.

The engine only flags; a pharmacist decides. `message` is English for logs; the web translates by `code` + `params`.
Rule files: app/rules/pharmacy/*.v1.json (illustrative, not a clinical reference; to be validated by the hospital's
pharmacists).

Safety principle: a missed danger is far worse than an extra warning, so matching is generous (substrings, stems,
language variants, Arabic clitics, free-text items resolved to the formulary) and malformed input degrades to
"unknown" instead of raising.
"""

import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parents[2] / "rules" / "pharmacy"
SEVERITY_RANK = {"critical": 0, "major": 1, "moderate": 2, "info": 3}
MIN_LATIN, MIN_ARABIC = 4, 3  # shortest name/term that may match by itself (noise guard)
# Words of a DCI or of an allergy text that say nothing about the drug.
NAME_STOP = frozenset({"acid", "acide", "chloride", "chlorure", "sodium", "sulfate", "phosphate", "forte", "retard",
                       "vial", "hydrochloride"})
TEXT_STOP = NAME_STOP | frozenset({
    "allergie", "allergies", "allergy", "allergic", "allergique", "allergiques", "hypersensibilite",
    "hypersensitivity", "sensibilite", "reaction", "reactions", "intolerance", "tablet", "tablets", "comprime",
    "comprimes", "capsule", "capsules", "gelule", "gelules", "injection", "injectable", "syrup", "sirop", "solution",
    "ampoule", "patient", "with", "from", "contre", "avec", "pour", "dans", "that", "drug", "medicament",
    "medication", "dose", "daily", "perfusion", "oral", "حساسيه", "تحسس"})
_CLITICS = "(?:وبال|ولل|وال|فال|بال|كال|لل|ال|و|ف|ب|ل|ك)"


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
    strength: str = ""  # only used to resolve a free-text medication ("Paracetamol 1 g")


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
    synonyms: tuple[tuple[str, str], ...]  # (normalised whole-word term, allergy class)
    interactions: tuple[InteractionRule, ...]
    elderly_dci: frozenset[str]
    elderly_min_age: int
    stems: tuple[tuple[str, str], ...] = ()  # (normalised substring of at least 5 letters, allergy class)
    names: dict = field(default_factory=dict)  # normalised DCI word -> language variants (normalised)
    duplicate_prefixes: tuple[tuple[str, ...], ...] = ()  # ATC prefixes that make one therapeutic class


_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
_AR_MARKS = re.compile("[ـً-ٰٟۖ-ۭ]")  # tatweel, harakat, small marks


def norm(s: str) -> str:
    """Casefold, drop accents, and collapse spaces/dashes/underscores/slashes/plus. Arabic: tatweel and harakat
    removed; alef forms -> ا, ى -> ي, ة -> ه. 'Pénicilline' -> 'penicilline', 'أسبرين' -> 'اسبرين',
    'beta_lactam' -> 'beta lactam'."""
    s = unicodedata.normalize("NFKD", (s or "").casefold()) if isinstance(s, str) else ""
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = _AR_MARKS.sub("", s).translate(_AR_MAP)
    return re.sub(r"[\s\-_/'+]+", " ", s).strip()


def _is_arabic(term: str) -> bool:
    return bool(term) and "؀" <= term[0] <= "ۿ"


@lru_cache(maxsize=None)
def _term_re(term: str) -> re.Pattern:
    """Whole-word search for a normalised term. An Arabic term may carry glued clitic prefixes (و ف ب ل ك ال لل بال
    وال فال) and its leading ال is optional ('للبنسلين' and 'البنسيلين' both find 'بنسيلين')."""
    if not _is_arabic(term):
        return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)")
    forms = {term}
    if term.startswith("ال") and len(term) - 2 >= MIN_ARABIC:
        forms.add(term[2:])
    alt = "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True))
    return re.compile(rf"(?<!\w){_CLITICS}{{0,2}}(?:{alt})(?!\w)")


def _contains(text: str, term: str) -> bool:
    """The (normalised) text contains the term: whole word for Arabic (with clitics), substring for Latin."""
    return bool(term) and (_term_re(term).search(text) is not None if _is_arabic(term) else term in text)


def _word_start(text: str, term: str) -> bool:
    """The term starts a word of the text ('warfarine 5 mg' starts with 'warfarin')."""
    if _is_arabic(term):
        return _term_re(term).search(text) is not None
    return re.search(rf"(?<!\w){re.escape(term)}", text) is not None


def _read(name: str) -> dict:
    return json.loads((RULES_DIR / name).read_text(encoding="utf-8"))


def _ok_name(term: str) -> bool:
    return len(term) >= (MIN_ARABIC if _is_arabic(term) else MIN_LATIN)


@lru_cache
def load_rules() -> Rules:
    doc = _read("allergy_synonyms.v1.json")
    pairs = tuple((norm(term), cls) for cls, terms in doc["classes"].items() for term in (cls, *terms))
    stems = tuple((norm(t), cls) for cls, ts in doc.get("stems", {}).items() for t in ts)
    names = {norm(k): tuple(v for v in (norm(x) for x in vs) if _ok_name(v)) for k, vs in
             doc.get("drug_names", {}).items()}
    inter_doc = _read("interactions.v1.json")
    inter = tuple(InteractionRule(p["groups"][0], p["groups"][1], p["severity"], p["note"])
                  for p in inter_doc["pairs"])
    dups = tuple(tuple(p.upper() for p in prefixes) for prefixes in inter_doc.get("duplicate_classes", {}).values())
    eld = _read("elderly_caution.v1.json")
    return Rules(pairs, inter, frozenset(norm(d) for d in eld["dci"]), int(eld["min_age"]), stems, names, dups)


def allergy_classes(allergy: str, rules: Rules) -> set[str]:
    """The allergy classes a text names: a synonym as a whole word (Arabic with clitics) or a stem anywhere."""
    text = norm(allergy)
    if not text:
        return set()
    found = {cls for term, cls in rules.synonyms if term and _term_re(term).search(text)}
    return found | {cls for stem, cls in rules.stems if stem and stem in text}


def _number(v) -> float | None:
    """A finite non-negative number from a number or a numeric string ('1,5' ok); anything else is unknown."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v.strip().replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) and x >= 0 else None


def daily_mg(item: dict, drug: DrugInfo, use_units: bool = True) -> float | None:
    """mg per day: `dose_mg` (per intake) or units_per_intake (fractions ok) x unit_mg, times the intakes per day.
    None (unknown, no dose check) when a value is not numeric, there is no mg data or no `times` (PRN)."""
    times = item.get("times")
    n = len(times) if isinstance(times, (list, tuple)) else 0
    if n == 0:
        return None
    if item.get("dose_mg") is not None:
        per = _number(item["dose_mg"])
    elif use_units and drug.unit_mg is not None:
        raw = item.get("units_per_intake")
        units = 1.0 if raw is None or raw == "" or raw == 0 else _number(raw)
        per = None if units is None else (units or 1.0) * float(drug.unit_mg)
    else:
        per = None
    return None if per is None else round(per * n, 6)  # rounded: 0.1 x 3 must not become 0.30000000000000004


def _duplicate(a: DrugInfo, b: DrugInfo, rules: Rules) -> str | None:
    if norm(a.dci) == norm(b.dci):
        return "same_dci"
    ka, kb = a.atc_code.upper(), b.atc_code.upper()
    if len(ka) >= 5 and ka[:5] == kb[:5]:
        return "same_atc_class"
    if any(ka.startswith(p) and kb.startswith(p) for prefixes in rules.duplicate_prefixes for p in prefixes):
        return "same_atc_class"  # one therapeutic class (e.g. all NSAIDs), different ATC5
    return None


def _interactions(a: DrugInfo, b: DrugInfo, rules: Rules) -> list[InteractionRule]:
    ga, gb = set(a.interaction_groups), set(b.interaction_groups)
    return [r for r in rules.interactions if (r.a in ga and r.b in gb) or (r.b in ga and r.a in gb)]


def _text(v) -> str:
    return v if isinstance(v, str) else ""


def _age(v) -> int | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        return int(float(v.strip())) if isinstance(v, str) else int(v)
    except (TypeError, ValueError, OverflowError):
        return None


class _Ctx:
    """Per-call state: patient allergies and their classes, plus caches of drug name terms."""

    def __init__(self, patient: PatientInfo, drugs: dict[str, DrugInfo], rules: Rules):
        self.drugs, self.rules = drugs, rules
        raw = getattr(patient, "allergies", None)
        raw = (raw,) if isinstance(raw, str) else (raw if isinstance(raw, (list, tuple, set, frozenset)) else ())
        self.allergies = [(a, norm(a)) for a in raw if isinstance(a, str) and norm(a)]
        self.age = _age(getattr(patient, "age", None))
        self.classes: dict[str, str] = {}
        for a, _ in self.allergies:
            for c in sorted(allergy_classes(a, rules)):
                self.classes.setdefault(c, a)
        self._terms: dict[str, tuple[str, ...]] = {}

    def terms(self, d: DrugInfo) -> tuple[str, ...]:
        """Names a text may use for the drug: DCI, its words, brands (and their first word), language variants."""
        if d.id not in self._terms:
            dci = norm(d.dci)
            words = [w for w in dci.split() if _ok_name(w) and w not in NAME_STOP]
            out = {dci, *words}
            for b in d.brand_names or ():
                nb = norm(b)
                out.add(nb)
                first = nb.split(" ")[0] if nb else ""
                if first not in NAME_STOP:
                    out.add(first)
            for key in (dci, *words):
                out.update(self.rules.names.get(key, ()))
            self._terms[d.id] = tuple(sorted(t for t in out if _ok_name(t)))
        return self._terms[d.id]

    def resolve(self, med: str, drug_id) -> tuple[DrugInfo | None, bool]:
        """(drug, exact). A known drug_id is exact; otherwise the free text is matched to the formulary: first by
        `formulary.match_drug` (exact), then by any DCI/brand/variant starting a word (not exact: the strength may
        differ, so units are not trusted for the dose check). (None, False) when nothing matches."""
        if isinstance(drug_id, str) and drug_id in self.drugs:
            return self.drugs[drug_id], True
        text = norm(med)
        if not text:
            return None, False
        from app.services.pharmacy.formulary import match_drug, strengths  # late: formulary imports this module

        d = match_drug(med, self.drugs.values())
        if d is not None:
            return d, True
        wanted = strengths(text)
        best, best_key = None, (0, 0)
        for cand in self.drugs.values():
            for t in self.terms(cand):
                if _word_start(text, t):
                    have = strengths(cand.strength)
                    key = (len(t), 1 if wanted and have and wanted <= have else 0)
                    if key > best_key:
                        best, best_key = cand, key
        return best, False

    def name_allergy(self, d: DrugInfo) -> str | None:
        """An allergy text that contains the drug's DCI, a brand or a language variant."""
        for t in self.terms(d):
            for a, n in self.allergies:
                if _contains(n, t):
                    return a
        return None

    def text_allergy(self, med: str) -> tuple[str, str] | None:
        """(allergy, class) for a medication that is not in the formulary: shared allergy class, or a significant word
        of the allergy and of the medication contained in one another."""
        text = norm(med)
        if not text:
            return None
        for c in sorted(allergy_classes(med, self.rules)):
            if c in self.classes:
                return self.classes[c], c
        words = [w for w in text.split() if _ok_name(w) and w not in TEXT_STOP and not w[0].isdigit()]
        for a, n in self.allergies:
            for w in n.split():
                if _ok_name(w) and w not in TEXT_STOP and not w[0].isdigit() and _contains(text, w):
                    return a, w
            for w in words:
                if _contains(n, w):
                    return a, w
        return None


def _single(i: int, item: dict, d: DrugInfo, ctx: _Ctx, exact: bool) -> list[Check]:
    """Checks that look at one item alone: allergy, daily dose, high alert, elderly."""
    med = _text(item.get("med"))
    out: list[Check] = []
    hit = next(((c, ctx.classes[c]) for c in d.allergy_classes if c in ctx.classes), None)
    if hit is None:  # an allergy written as the drug's own name, brand or a language variant
        named = ctx.name_allergy(d)
        hit = (norm(d.dci), named) if named else None
    if hit:
        out.append(Check("allergy", "critical", i, d.id, {"med": med, "allergy": hit[1], "class": hit[0]},
                         f"{d.dci}: the patient is allergic to {hit[1]} ({hit[0]})"))
    daily = daily_mg(item, d, use_units=exact) if d.max_daily_mg else None
    if daily is not None and daily > round(float(d.max_daily_mg), 6):
        sev = "critical" if daily > 2 * d.max_daily_mg else "major"
        out.append(Check("max_daily_dose", sev, i, d.id,
                         {"med": med, "daily_mg": daily, "max_daily_mg": d.max_daily_mg},
                         f"{d.dci}: {daily:g} mg/day is above the {d.max_daily_mg:g} mg/day maximum"))
    if d.high_alert:
        out.append(Check("high_alert", "info", i, d.id, {"med": med}, f"{d.dci}: high-alert drug, double-check"))
    if ctx.age is not None and ctx.age >= ctx.rules.elderly_min_age and norm(d.dci) in ctx.rules.elderly_dci:
        out.append(Check("elderly", "moderate", i, d.id, {"med": med, "age": ctx.age},
                         f"{d.dci}: use with caution at age {ctx.age}"))
    return out


def run_checks(patient: PatientInfo, items: list[dict], running: list[RunningItem], drugs: dict[str, DrugInfo],
               rules: Rules | None = None) -> list[Check]:
    """Every check for the candidate `items` against each other and the patient's other running prescriptions,
    most severe first (then by item index, then by code).

    An item with no (or an unknown) drug_id is a free-text medication: it is matched to the formulary by name. It
    always yields `non_formulary`; when it resolves to a formulary drug it is also checked like that drug (allergy,
    dose, interactions, duplicates, high alert), and when it does not, its text is still checked against the
    patient's allergies. Free-text running items are resolved the same way. Non-dict items are skipped."""
    rules = rules or load_rules()
    ctx = _Ctx(patient, drugs, rules)
    out: list[Check] = []
    cands: list[tuple[int, dict, DrugInfo]] = []
    for i, it in enumerate(items if isinstance(items, (list, tuple)) else ()):
        if not isinstance(it, dict):
            continue
        med = _text(it.get("med"))
        d, exact = ctx.resolve(med, it.get("drug_id"))
        known = isinstance(it.get("drug_id"), str) and it["drug_id"] in drugs
        if not known:
            params = {"med": med} if d is None else {"med": med, "matched_drug_id": d.id}
            out.append(Check("non_formulary", "moderate", i, None, params, f"{med}: not in the hospital formulary"))
        if d is None:
            hit = ctx.text_allergy(med)
            if hit:
                out.append(Check("allergy", "critical", i, None, {"med": med, "allergy": hit[0], "class": hit[1]},
                                 f"{med}: the patient may be allergic to {hit[0]} ({hit[1]})"))
            continue
        cands.append((i, it, d))
        out += _single(i, it, d, ctx, exact)
    others = []
    for r in running if isinstance(running, (list, tuple)) else ():
        if r is None:
            continue
        e, _ = ctx.resolve(_text(getattr(r, "med", "")), getattr(r, "drug_id", None))
        if e is not None:
            others.append((r, e))
    for n, (i, it, d) in enumerate(cands):
        med = _text(it.get("med"))
        partners = [(j, _text(jt.get("med")), e, None) for j, jt, e in cands[n + 1:]]
        partners += [(None, _text(getattr(r, "med", "")), e, getattr(r, "prescription_id", None))
                     for r, e in others]
        for j, other_med, e, rx_id in partners:
            with_ = {"with_med": other_med, "with_drug_id": e.id, "with_item_index": j,
                     "with_prescription_id": rx_id}
            reason = _duplicate(d, e, rules)
            if reason:
                out.append(Check("duplicate_therapy", "major", i, d.id, {"med": med, "reason": reason, **with_},
                                 f"{d.dci} duplicates {other_med} ({reason})"))
            for rule in _interactions(d, e, rules):
                out.append(Check("interaction", rule.severity, i, d.id,
                                 {"med": med, "groups": [rule.a, rule.b], "note": rule.note, **with_},
                                 f"{d.dci} + {other_med}: {rule.note}"))
    return sorted(out, key=lambda c: (SEVERITY_RANK[c.severity], c.item_index, c.code))
