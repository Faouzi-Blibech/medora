"""Doctor copilot: templated daily summary (optional LLM rewrite) + drug-interaction check.

Interactions come from a curated rule list, never from the LLM.

`summarize` is DB-free; `daily_summary(db, patient_id)` wraps it with the database models.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from app.ai.llm import LLMUnavailable, complete_json
from app.config import get_settings

RULES = Path(__file__).parent / "rules" / "interactions.v1.json"


class _LlmSummary(BaseModel):
    summary: str


@lru_cache
def _pairs() -> list[dict]:
    return json.loads(RULES.read_text(encoding="utf-8"))["pairs"]


def check_interactions(med_names: list[str]) -> list[dict]:
    meds = " | ".join(med_names).lower()
    return [{"drugs": p["drugs"], "severity": p["severity"], "note": p["note"]}
            for p in _pairs() if all(d in meds for d in p["drugs"])]


def _trend(vals: list) -> str:
    if len(vals) < 2 or not vals[0]:
        return "stable"
    first, last = vals[0], vals[-1]
    change = (last - first) / abs(first)
    return "rising" if change > 0.05 else "falling" if change < -0.05 else "stable"


def _range(vitals: list[dict], key: str) -> tuple | None:
    vals = [v[key] for v in vitals if v.get(key) is not None]
    return (min(vals), max(vals), vals[-1], _trend(vals)) if vals else None


def _stats_text(vitals: list[dict]) -> str:
    if not vitals:
        return "No vitals recorded in the last 24h."
    parts = []
    for key, label, unit in (("hr", "HR", ""), ("spo2", "SpO2", "%"), ("temp", "Temp", "°C")):
        r = _range(vitals, key)
        if r:
            parts.append(f"{label} {r[0]}–{r[1]}{unit} (latest {r[2]}{unit}, {r[3]})")
    news2 = _range(vitals, "news2")
    if news2:
        parts.append(f"max NEWS2 {news2[1]}")
    return "Last 24h: " + ", ".join(parts) + "."


def _notes_text(notes: list[str]) -> str:
    n = len(notes)
    text = f"{n} nurse note{'s' if n != 1 else ''}."
    if notes:
        latest = notes[-1]
        latest = latest[:117] + "..." if len(latest) > 120 else latest
        text += f' Latest: "{latest}".'
    return text


def template_summary(vitals: list[dict], notes: list[str], meds: list[str], interactions: list[dict]) -> str:
    lines = [_stats_text(vitals), _notes_text(notes), f"Active meds: {', '.join(meds) if meds else 'none'}."]
    lines += [f"Interaction ({i['severity']}): {' + '.join(i['drugs'])}: {i['note']}" for i in interactions]
    return "\n".join(lines)


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def summarize(vitals: list[dict], notes: list[str], meds: list[str], names: list[str]) -> dict:
    interactions = check_interactions(meds)
    summary, source = template_summary(vitals, notes, meds, interactions), "rules"
    if get_settings().llm_provider != "none":
        try:
            rewritten = complete_json("summary", summary, _LlmSummary, names=names).summary
            if _numbers(rewritten) <= _numbers(summary):  # no new or changed number may reach the doctor
                summary, source = rewritten, "llm"
        except LLMUnavailable:
            pass
    return {"summary": summary, "interactions": interactions, "source": source,
            "generated_at": datetime.now(UTC).isoformat()}


# --- GET /ai/summary/{patient_id} building blocks. Rows follow data-model.md (vitals, notes, prescriptions,
# ai_summaries); the router loads them (last 24 h) and stores summarize()'s output as an ai_summaries row.

CACHE_FOR = timedelta(minutes=10)


def summary_inputs(patient, vitals: list, notes: list, prescriptions: list) -> dict:
    """Turn DB rows into summarize() arguments: oldest-first vitals, non-empty notes, active med names."""
    return {
        "vitals": [{"hr": v.hr, "spo2": v.spo2, "temp": v.temp, "news2": v.news2} for v in vitals],
        "notes": [n.text.strip() for n in notes if n.text and n.text.strip()],
        "meds": [item["med"] for rx in prescriptions if rx.active for item in rx.items if item.get("med")],
        "names": [patient.first_name, patient.last_name],
    }


def is_fresh(summary_row, *, now: datetime) -> bool:
    """A stored summary is served from cache for 10 minutes."""
    return summary_row is not None and now - summary_row.created_at < CACHE_FOR


def apply_review(summary_row, *, user_id: str) -> None:
    """The doctor read the AI summary (human in the loop)."""
    summary_row.human_confirmed_by = user_id


def summary_payload(summary_row) -> dict:
    """Response body of GET /ai/summary (api.md v1.2)."""
    s = summary_row.ai_suggested
    return {"summary": s["summary"], "interactions": s["interactions"], "source": s["source"],
            "generated_at": summary_row.created_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "human_confirmed_by": summary_row.human_confirmed_by}
