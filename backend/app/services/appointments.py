"""Appointment business rules (owner: Faouzi). DB-free: callers pass rows whose attributes follow
docs/contracts/data-model.md (`appointments`, `patients`), load them and commit. Routers stay thin.
"""

from datetime import UTC, date, datetime

from app.ai.triage import triage

try:  # Hedi's no-show module; identical behaviour until it lands
    from app.ai.no_show import predict_no_show, rank_backfill
except ImportError:
    def predict_no_show(features: dict) -> float:
        return 0.20

    def rank_backfill(candidates: list[dict]) -> list[dict]:
        return sorted(candidates, key=lambda c: (-c["urgency"], c["no_show_prob"], c["created_at"]))


class Conflict(Exception):
    """Maps to HTTP 409 with {"code": code}."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _age(patient, today: date) -> int | None:
    dob = getattr(patient, "date_of_birth", None)
    if not dob:
        return None
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _urgency(a) -> int:
    return a.urgency_final if a.urgency_final is not None else a.urgency_ai


def new_appointment_fields(patient, referral_text: str, symptoms: list[str], *, today: date) -> dict:
    """Fields for a new `requested` appointment: triage + no-show probability."""
    age = _age(patient, today)
    t = triage(referral_text, symptoms, age)
    no_show = predict_no_show({"age": age or 0, "is_female": int(getattr(patient, "sex", "") == "F"),
                               "sms_received": int(bool(patient.telegram_chat_id or patient.email))})
    return {"patient_id": patient.id, "status": "requested", "referral_text": referral_text, "symptoms": symptoms,
            "urgency_ai": t.urgency, "urgency_final": None, "ai_suggested": t.model_dump(),
            "no_show_prob": no_show}


def follow_up_fields(patient, days: int, *, today: date) -> dict:
    return new_appointment_fields(patient, f"Post-discharge follow-up in {days} days", [], today=today)


def waitlist(appointments) -> list:
    """Requested appointments, human-final urgency over AI urgency, then oldest first."""
    return sorted((a for a in appointments if a.status == "requested"),
                  key=lambda a: (-_urgency(a), a.created_at))


def apply_override(a, urgency_final: int, *, user_id: str) -> None:
    if not 1 <= urgency_final <= 5:
        raise ValueError("urgency_final must be 1-5")
    a.urgency_final = urgency_final
    a.human_confirmed_by = user_id


def apply_confirm(a, *, slot_at: datetime, doctor_id: str, user_id: str, urgency_final: int | None = None) -> None:
    if a.status != "requested":
        raise Conflict("not_waiting", f"appointment is {a.status}")
    if urgency_final is not None:
        apply_override(a, urgency_final, user_id=user_id)
    a.status, a.slot_at, a.doctor_id = "confirmed", slot_at, doctor_id
    a.confirmed_by = a.human_confirmed_by = user_id


def apply_cancel(a) -> None:
    if a.status in ("cancelled", "done", "no_show"):
        raise Conflict("not_cancellable", f"appointment is {a.status}")
    a.status = "cancelled"


def apply_reply(a, reply: str, *, now: datetime) -> str:
    """Patient's answer to the W1 reminder."""
    if reply == "confirm":
        a.patient_confirmed_at = now
        return "confirmed"
    if reply == "cancel":
        apply_cancel(a)
        return "cancelled"
    raise ValueError("reply must be confirm or cancel")


def apply_backfill_accept(a, *, slot_at: datetime, doctor_id: str, slot_taken: bool) -> str:
    """Patient accepted a freed slot through W2. Booked by the system: confirmed_by stays empty."""
    if a.status != "requested":
        raise Conflict("not_waiting", f"appointment is {a.status}")
    if slot_taken:
        raise Conflict("slot_taken")
    a.status, a.slot_at, a.doctor_id = "confirmed", slot_at, doctor_id
    return "confirmed"


def confirmed_event(a, patient, *, doctor_name: str | None) -> dict:
    """`appointment.confirmed` payload (n8n-webhooks v1.2)."""
    return {"appointment_id": a.id, "patient_first_name": patient.first_name,
            "patient_telegram_chat_id": patient.telegram_chat_id, "patient_email": patient.email,
            "slot_at": _iso(a.slot_at), "doctor_name": doctor_name}


def cancelled_event(a, *, doctor_name: str | None, waiting: list[tuple]) -> dict:
    """`appointment.cancelled` payload with the best waiting `candidate` for the freed slot.

    `waiting`: (appointment, patient) pairs for requested appointments; the cancelled one is ignored.
    """
    candidate = None
    pool = {w.id: (w, p) for w, p in waiting if w.status == "requested" and w.id != a.id}
    if a.slot_at and pool:
        ranked = rank_backfill([{"appointment_id": w.id, "urgency": _urgency(w), "no_show_prob": w.no_show_prob or 0.0,
                                 "created_at": _iso(w.created_at)} for w, _ in pool.values()])
        w, p = pool[ranked[0]["appointment_id"]]
        candidate = {"appointment_id": w.id, "patient_first_name": p.first_name,
                     "patient_telegram_chat_id": p.telegram_chat_id, "patient_email": p.email}
    return {"appointment_id": a.id, "slot_at": _iso(a.slot_at), "doctor_id": a.doctor_id,
            "doctor_name": doctor_name, "candidate": candidate}
