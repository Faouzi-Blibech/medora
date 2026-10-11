"""Weather-health alerts (owner: Faouzi): the hospital city's forecast turned into alerts with the groups most at
risk and advice for staff and patients in Arabic, French and English. Pure rules from
rules/weather_health.v1.json (illustrative thresholds, not clinically validated). No network, no DB."""

import json
from functools import lru_cache
from pathlib import Path

from app.ai.triage import _normalize

RULES = Path(__file__).parent / "rules" / "weather_health.v1.json"
SEVERITY_ORDER = {"high": 0, "moderate": 1}


@lru_cache
def _rules() -> dict:
    data = json.loads(RULES.read_text(encoding="utf-8"))
    for g in data["groups"].values():
        g["norm"] = [_normalize(k) for k in g.get("keywords", [])]
    return data


def _fmt(v: float) -> str:
    return f"{v:.0f}" if abs(v - round(v)) < 0.05 else f"{v:.1f}"


def _hits(rule: dict, day: dict, prev: dict | None) -> float | None:
    v = day.get(rule["metric"])
    if v is None:
        return None
    op, limit = rule["op"], rule["value"]
    if op.startswith("delta"):
        p = prev.get(rule["metric"]) if prev else None
        if p is None:
            return None
        d = v - p
        return d if (op == "delta>=" and d >= limit) or (op == "delta<=" and d <= limit) else None
    return v if (op == ">=" and v >= limit) or (op == "<=" and v <= limit) else None


def evaluate(days: list[dict]) -> list[dict]:
    """days: oldest first, the first one is yesterday (for the day-to-day change). Returns alerts for the others,
    soonest and most severe first: {id, date, severity, value, groups, title, staff, patient} (texts per language)."""
    rules = _rules()["rules"]
    out = []
    for i in range(1, len(days)):
        day, prev = days[i], days[i - 1]
        fired: dict[str, float] = {}
        for r in rules:
            v = _hits(r, day, prev)
            if v is not None:
                fired[r["id"]] = v
        for r in rules:
            if r["id"] not in fired or any(u in fired for u in r.get("unless", [])):
                continue
            value = _fmt(fired[r["id"]])
            out.append({"id": r["id"], "date": day["date"], "severity": r["severity"], "value": value,
                        "groups": r["groups"], "title": {k: t.replace("{value}", value) for k, t in r["title"].items()},
                        "staff": r["staff"], "patient": r["patient"]})
    return sorted(out, key=lambda a: (a["date"], SEVERITY_ORDER[a["severity"]]))


def patient_groups(age: int | None, text: str) -> set[str]:
    """Risk groups for a patient from their age and history/referral text (keyword match, accents folded)."""
    t = _normalize(text or "")
    out = set()
    for name, g in _rules()["groups"].items():
        if age is not None and ("min_age" in g and age >= g["min_age"] or "max_age" in g and age <= g["max_age"]):
            out.add(name)
        elif any(k in t for k in g["norm"]):
            out.add(name)
    return out
