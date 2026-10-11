"""Patient assistant (owner: Faouzi).

Scoped to the caller's own record: the router loads only that patient's rows and passes them in. No LLM: a
question is classified into one of five intents (patient-side urgency wording, keyword rules, then the small trained
char n-gram model, keyword rules again when the model is missing) and answered from templated sentences.
Red-flag questions never reach a model.
"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from app.ai import textclf
from app.ai.triage import _normalize, load_rules, match_red_flags, scan_rules

PATIENT_URGENT = Path(__file__).parent / "rules" / "patient_urgent.v1.json"

TUNIS = timezone(timedelta(hours=1))  # Africa/Tunis: UTC+1, no DST
DOSE_WORDS = ("dose", "medic", "pill", "tablet", "comprime", "traitement", "dwa", "دواء", "حبوب")
VISIT_WORDS = ("appointment", "rendez-vous", "rendez vous", "rdv", "visit", "consultation", "maw3ed", "موعد")
VITAL_WORDS = ("temperature", "température", "oxygen", "oxygène", "pulse", "pouls", "heart", "tension",
               "سخانة", "حرارة", "نبض", "skhana")
MIN_CONFIDENCE = 0.4
URGENT = "This could be urgent. Tell your nurse or any member of staff straight away."
ASK_STAFF = "I can't answer that. Please ask your nurse or doctor."
CRISIS = ("Please tell your nurse or any member of staff right now. You are not alone and help is here. "
          "In an emergency in Tunisia, call SAMU on 190.")


def _local(dt: datetime) -> datetime:
    return dt.astimezone(TUNIS)


def assistant_context(patient, doses_today: list, next_visit, latest_vital, *, now: datetime) -> dict:
    """The only data the assistant may use. Rows follow data-model.md (med_doses, appointments, vitals)."""
    now_hhmm = _local(now).strftime("%H:%M")
    upcoming = sorted((d for d in doses_today if d.status == "scheduled"), key=lambda d: d.time_of_day)
    nxt = next((d for d in upcoming if d.time_of_day >= now_hhmm), None)
    vit = None
    if latest_vital is not None:
        vit = {"hr": latest_vital.hr, "spo2": latest_vital.spo2, "temp": latest_vital.temp,
               "at": _local(latest_vital.ts).strftime("%H:%M")}
    visit = None
    if next_visit is not None and next_visit.slot_at is not None:
        v = _local(next_visit.slot_at)
        visit = f"{v:%A} {v.day} {v:%b} at {v:%H:%M}"
    return {"next_dose": {"time": nxt.time_of_day, "meds": list(nxt.meds)} if nxt else None,
            "next_visit": visit, "latest_vitals": vit, "names": [patient.first_name, patient.last_name]}


@lru_cache
def _urgent_rules() -> list[dict]:
    return load_rules(PATIENT_URGENT)


def _says_urgent(question: str) -> bool:
    """A call for a nurse, a fall, fainting, cannot breathe, bleeding or unbearable pain happening now."""
    return bool(scan_rules(_urgent_rules(), question)[0])


def _keyword_intents(question: str) -> list[str]:
    q = _normalize(question)
    topics = (("next_dose", DOSE_WORDS), ("next_visit", VISIT_WORDS), ("my_vitals", VITAL_WORDS))
    return [intent for intent, words in topics if any(_normalize(w) in q for w in words)]


def _rule_intent(question: str) -> str:
    hits = _keyword_intents(question)
    return hits[0] if hits else "ask_staff"


def classify_intent(question: str) -> tuple[str, float, str]:
    """(intent, confidence, source): patient-side urgency wording first, then a question naming exactly one topic is
    answered by keyword rules; otherwise the char n-gram model (below MIN_CONFIDENCE: ask_staff), else keyword rules."""
    if _says_urgent(question):
        return "urgent", 1.0, "rules"
    hits = _keyword_intents(question)
    if len(hits) == 1:
        return hits[0], 1.0, "rules"
    model = textclf.load("intent.v2")
    if model is None:
        return _rule_intent(question), 1.0, "rules"
    probs = textclf.predict_proba(model, _normalize(question))
    intent = max(probs, key=probs.get)
    conf = probs[intent]
    if conf < MIN_CONFIDENCE:
        intent = "ask_staff"
    return intent, conf, "model"


def _vitals_answer(ctx: dict) -> dict:
    v = ctx["latest_vitals"]
    parts = []
    if v:
        if v.get("hr") is not None:
            parts.append(f"heart rate {v['hr']} bpm")
        if v.get("spo2") is not None:
            parts.append(f"oxygen {v['spo2']}%")
        if v.get("temp") is not None:
            parts.append(f"temperature {v['temp']} °C")
    if not parts:
        return {"answer": "No readings yet today.", "sources": ["vitals"]}
    return {"answer": f"Your latest readings (at {v['at']}): {', '.join(parts)}.", "sources": ["vitals"]}


def answer(question: str, ctx: dict) -> dict:
    """POST /ai/assistant body: {"answer", "sources", "intent", "source"}."""
    flags = {f["id"] for f in match_red_flags(question)}
    if flags:
        text = CRISIS if "suicide_self_harm" in flags else URGENT
        return {"answer": text, "sources": ["safety_rules"], "intent": "urgent", "source": "rules"}
    intent, _conf, source = classify_intent(question)
    if intent == "urgent":
        out = {"answer": URGENT, "sources": ["safety_rules"]}
    elif intent == "next_dose":
        d = ctx["next_dose"]
        if d:
            out = {"answer": f"Your next dose is at {d['time']}: {', '.join(d['meds'])}.",
                   "sources": ["med_doses"]}
        else:
            out = {"answer": "You have no more doses scheduled today.", "sources": ["med_doses"]}
    elif intent == "next_visit":
        if ctx["next_visit"]:
            out = {"answer": f"Your next appointment is on {ctx['next_visit']}.", "sources": ["appointments"]}
        else:
            out = {"answer": "You have no confirmed appointment yet; the hospital will contact you.",
                   "sources": ["appointments"]}
    elif intent == "my_vitals":
        out = _vitals_answer(ctx)
    else:
        intent, out = "ask_staff", {"answer": ASK_STAFF, "sources": []}
    return {**out, "intent": intent, "source": source}
