"""Nurse shift handover (owner: Faouzi): an SBAR draft per patient from the record of the last N hours.

Rules only (thresholds in rules/handover.v1.json), so it always works offline. With an LLM configured, the
narrative paragraph may be rewritten through app/ai/llm.py (prompt prompts/handover.v1.md); any failure, or a
rewrite that adds or changes a number, keeps the rules text. The structured SBAR sections never come from the LLM.
Not clinically validated: the outgoing nurse reads and confirms every draft (`human_confirmed_by`).

Everything here is DB-free: the router loads the rows and passes plain dicts.
"""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.ai.llm import LLMUnavailable, complete_json
from app.config import get_settings

RULES = Path(__file__).parent / "rules" / "handover.v1.json"
TUNIS = ZoneInfo("Africa/Tunis")
LANG_NAMES = {"en": "English", "fr": "French", "ar": "Arabic"}


@lru_cache
def rules() -> dict:
    return json.loads(RULES.read_text(encoding="utf-8"))


def window_hours(hours: int | None) -> int:
    """The requested window if allowed (8, 12 or 24 h), else the default (12 h)."""
    r = rules()
    return hours if hours in r["windows_hours"] else r["default_window_hours"]


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _hhmm(dt: datetime) -> str:
    return dt.astimezone(TUNIS).strftime("%H:%M")


def _trend(vals: list, pct: float) -> str:
    if len(vals) < 2 or not vals[0]:
        return "stable"
    change = (vals[-1] - vals[0]) / abs(vals[0])
    return "rising" if change > pct else "falling" if change < -pct else "stable"


def _news2_trend(vals: list[int], delta: int) -> str | None:
    if not vals:
        return None
    if len(vals) < 2:
        return "stable"
    d = vals[-1] - vals[0]
    return "rising" if d >= delta else "falling" if d <= -delta else "stable"


def _range(vitals: list[dict], key: str, pct: float) -> dict | None:
    vals = [v[key] for v in vitals if v.get(key) is not None]
    if not vals:
        return None
    return {"min": min(vals), "max": max(vals), "latest": vals[-1], "trend": _trend(vals, pct)}


def build(patient: dict, *, vitals: list[dict], doses: list[dict], alerts: list[dict], notes: list[dict],
          meds: list[dict], care_plans: list[str], exams: list[dict], now: datetime, hours: int) -> dict:
    """The structured SBAR draft. `vitals` oldest first and inside the window; `doses` scheduled from the window
    start to `upcoming_dose_hours` ahead; `alerts` raised in the window or still open; `notes` in the window;
    `exams` ordered and not done."""
    r = rules()
    since = now - timedelta(hours=hours)
    news2_vals = [v["news2"] for v in vitals if v.get("news2") is not None]
    news2_trend = _news2_trend(news2_vals, r["news2_rising_delta"])
    latest_vital = vitals[-1] if vitals else None

    situation = {"bed": patient.get("bed"), "ward": patient.get("ward"), "reason": patient.get("reason") or "",
                 "admitted_at": _iso(patient.get("admitted_at")),
                 "latest_news2": news2_vals[-1] if news2_vals else None, "news2_trend": news2_trend,
                 "latest_vital_at": _iso(latest_vital["ts"]) if latest_vital else None}
    background = {"allergies": list(patient.get("allergies") or []), "meds": meds,
                  "care_plans": [c for c in care_plans if c]}

    overdue_before = now - timedelta(minutes=r["dose_overdue_after_min"])
    past = [d for d in doses if since <= d["scheduled_at"] <= now]
    given = [d for d in past if d["status"] == "taken"]
    missed = [d for d in past if d["status"] == "missed"
              or (d["status"] in ("scheduled", "dispensed") and d["scheduled_at"] < overdue_before)]
    upcoming_until = now + timedelta(hours=r["upcoming_dose_hours"])
    upcoming = sorted((d for d in doses if now < d["scheduled_at"] <= upcoming_until and d["status"] != "taken"),
                      key=lambda d: d["scheduled_at"])

    raised = [a for a in alerts if a["created_at"] >= since]
    open_alerts = sorted((a for a in alerts if a.get("acked_at") is None), key=lambda a: a["created_at"])
    window_notes = sorted((n for n in notes if n.get("text", "").strip()), key=lambda n: n["created_at"])

    def dose_out(d: dict) -> dict:
        return {"id": d["id"], "scheduled_at": _iso(d["scheduled_at"]), "time": _hhmm(d["scheduled_at"]),
                "meds": list(d.get("meds") or []), "status": d["status"]}

    assessment = {
        "vitals": {"count": len(vitals), "hr": _range(vitals, "hr", r["vital_trend_pct"]),
                   "spo2": _range(vitals, "spo2", r["vital_trend_pct"]),
                   "temp": _range(vitals, "temp", r["vital_trend_pct"]),
                   "news2": ({"min": min(news2_vals), "max": max(news2_vals), "latest": news2_vals[-1],
                              "trend": news2_trend} if news2_vals else None)},
        "alerts": {"raised": len(raised), "acked": sum(1 for a in raised if a.get("acked_at") is not None),
                   "open": [{"id": a["id"], "kind": a["kind"], "severity": a["severity"], "message": a["message"],
                             "created_at": _iso(a["created_at"])} for a in open_alerts]},
        "doses": {"given": len(given), "missed": [dose_out(d) for d in missed]},
        "notes": [{"text": n["text"].strip(), "author_name": n.get("author_name"), "created_at": _iso(n["created_at"])}
                  for n in window_notes[-r["max_notes"]:]],
        "notes_count": len(window_notes),
    }

    recs: list[dict] = []
    latest = situation["latest_news2"]
    if latest is not None and latest >= r["news2_high"]:
        recs.append({"code": "news2_high", "params": {"score": latest}})
    if news2_trend == "rising":
        recs.append({"code": "news2_rising", "params": {"from": news2_vals[0], "to": news2_vals[-1]}})
    for a in open_alerts:
        recs.append({"code": "open_alert", "params": {"kind": a["kind"], "severity": a["severity"],
                                                      "time": _hhmm(a["created_at"]), "at": _iso(a["created_at"])}})
    for d in missed:
        recs.append({"code": "missed_dose", "params": {"time": _hhmm(d["scheduled_at"]),
                                                       "meds": ", ".join(d.get("meds") or [])}})
    if not vitals:
        recs.append({"code": "no_vitals", "params": {"hours": hours}})
    for e in exams:
        recs.append({"code": "pending_exam", "params": {"label": e["label"]}})
    for d in upcoming:
        recs.append({"code": "next_dose", "params": {"time": _hhmm(d["scheduled_at"]),
                                                     "meds": ", ".join(d.get("meds") or [])}})
    if not recs:
        recs.append({"code": "routine", "params": {}})

    return {"patient": {k: patient.get(k) for k in ("id", "first_name", "last_name", "ward", "bed", "age", "sex")},
            "window": {"hours": hours, "from": _iso(since), "to": _iso(now)},
            "situation": situation, "background": background, "assessment": assessment,
            "recommendations": recs, "upcoming_doses": [dose_out(d) for d in upcoming]}


# --- narrative (English rules text; the optional LLM may only rewrite it) ---------------------------------------

_REC_TEXT = {
    "news2_high": "NEWS2 is {score}: keep the doctor informed and observe closely.",
    "news2_rising": "NEWS2 rising ({from} to {to}): reassess sooner.",
    "open_alert": "Open {severity} {kind} alert since {time}: follow it up.",
    "missed_dose": "Dose at {time} not confirmed ({meds}): re-check with the patient.",
    "no_vitals": "No vitals in the last {hours}h: take a set of observations.",
    "pending_exam": "Exam pending: {label}.",
    "next_dose": "Next dose at {time}: {meds}.",
    "routine": "No open issue: continue the current plan.",
}


def _fmt_range(label: str, rg: dict | None, unit: str = "") -> str | None:
    if not rg:
        return None
    return f"{label} {rg['min']}-{rg['max']}{unit} (latest {rg['latest']}{unit}, {rg['trend']})"


def narrative(d: dict) -> str:
    s, b, a = d["situation"], d["background"], d["assessment"]
    where = ", ".join(x for x in (f"Bed {s['bed']}" if s["bed"] else "No bed", s["ward"]) if x)
    news2 = (f"Latest NEWS2 {s['latest_news2']} ({s['news2_trend']})." if s["latest_news2"] is not None
             else "No NEWS2 in the window.")
    lines = [f"S: {where}. Reason: {s['reason'] or 'not recorded'}. {news2}"]
    meds = "; ".join(f"{m['med']} ({', '.join(m['times'])})" if m.get("times") else m["med"] for m in b["meds"])
    lines.append(f"B: Allergies: {', '.join(b['allergies']) or 'none recorded'}. Active meds: {meds or 'none'}.")
    v = a["vitals"]
    parts = [p for p in (_fmt_range("HR", v["hr"]), _fmt_range("SpO2", v["spo2"], "%"),
                         _fmt_range("Temp", v["temp"], "°C")) if p]
    vit = f"{v['count']} vital sets: " + ", ".join(parts) + "." if parts else "No vitals recorded."
    al = a["alerts"]
    text = (f"A: Last {d['window']['hours']}h: {vit} Alerts: {al['raised']} raised, {al['acked']} acknowledged, "
            f"{len(al['open'])} open. Doses: {a['doses']['given']} given, {len(a['doses']['missed'])} not confirmed. "
            f"{a['notes_count']} nurse note{'s' if a['notes_count'] != 1 else ''}.")
    if a["notes"]:
        latest = a["notes"][-1]["text"]
        text += f' Latest: "{latest[:117] + "..." if len(latest) > 120 else latest}".'
    lines.append(text)
    lines.append("R: " + " ".join(_REC_TEXT[r["code"]].format(**r["params"]) for r in d["recommendations"]))
    return "\n".join(lines)


class _LlmNarrative(BaseModel):
    narrative: str


_cache: dict[str, str] = {}
_CACHE_MAX = 256


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def rewrite(text: str, *, names: list[str], lang: str | None = None) -> tuple[str, str]:
    """(narrative, source). The LLM rewrite is kept only if it adds or changes no number."""
    if get_settings().llm_provider == "none":
        return text, "rules"
    key = hashlib.sha256(f"{lang}\n{text}".encode()).hexdigest()
    if key in _cache:
        return _cache[key], "llm"
    prompt = text + (f"\n\nWrite the handover in {LANG_NAMES[lang]}." if lang in LANG_NAMES else "")
    try:
        out = complete_json("handover", prompt, _LlmNarrative, names=names).narrative.strip()
    except LLMUnavailable:
        return text, "rules"
    if not out or not _numbers(out) <= _numbers(text):
        return text, "rules"
    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[key] = out
    return out, "llm"


def draft(patient: dict, *, names: list[str], lang: str | None = None, **data) -> dict:
    """build() + the narrative, with `source: rules|llm` (AI-output convention)."""
    d = build(patient, **data)
    d["narrative"], d["source"] = rewrite(narrative(d), names=names, lang=lang)
    return d
