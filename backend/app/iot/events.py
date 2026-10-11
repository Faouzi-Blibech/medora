"""Device events (mqtt-topics.md → events): dose lifecycle, call nurse, nurse tap, schedule ack."""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations import n8n
from app.iot.ingest import active_patient_for_device, frame
from app.models import Admission, Device, MedDose, Patient, Staff, User
from app.schemas import iso
from app.services import accounts, alerts
from app.services.audit import audit
from app.services.schedule import TUNIS

log = logging.getLogger("medora.events")

# A dose only moves forward: a replayed `dose_missed` never undoes a `dose_taken`
RANK = {"scheduled": 0, "dispensed": 1, "missed": 2, "taken": 3}
DOSE_EVENTS = {"dose_dispensed": "dispensed", "dose_taken": "taken", "dose_missed": "missed"}


def _event_ts(p: dict) -> datetime:
    try:
        return datetime.fromtimestamp(int(p["ts"]), UTC)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return datetime.now(UTC)


def _occurrence(db: Session, dose: MedDose, at: datetime) -> MedDose:
    """The device repeats a schedule daily with the dose_id of the day it was published. Map an event
    to the occurrence of the same prescription, time and slot on the event's local date."""
    day = at.astimezone(TUNIS).date()
    if dose.scheduled_at.astimezone(TUNIS).date() == day:
        return dose
    sibling = db.scalars(select(MedDose).where(MedDose.prescription_id == dose.prescription_id,
                                               MedDose.time_of_day == dose.time_of_day,
                                               MedDose.slot.is_(None) if dose.slot is None
                                               else MedDose.slot == dose.slot)).all()
    same_day = [d for d in sibling if d.scheduled_at.astimezone(TUNIS).date() == day]
    return same_day[0] if same_day else dose


def _dose_event(db: Session, device_id: str, p: dict, status: str) -> list[dict]:
    dose = db.get(MedDose, str(p.get("dose_id") or ""))
    if dose is None:
        log.warning("%s for unknown dose %s from %s", status, p.get("dose_id"), device_id)
        return []
    if dose.patient_id != active_patient_for_device(db, device_id):
        log.warning("dose %s is not for the patient on %s: ignored", dose.id, device_id)
        return []
    at = _event_ts(p)
    dose = _occurrence(db, dose, at)
    # merged schedule entries share one dose_id: move every dose of that (time, slot) together
    group = db.scalars(select(MedDose).where(MedDose.patient_id == dose.patient_id,
                                             MedDose.scheduled_at == dose.scheduled_at,
                                             MedDose.slot.is_(None) if dose.slot is None
                                             else MedDose.slot == dose.slot)).all()
    changed = [d for d in group if RANK[status] > RANK.get(d.status, 0)]
    if not changed:
        return []
    method = p.get("method") if status == "taken" and p.get("method") in ("ir", "button") else None
    for d in changed:
        d.status = status
        if method:
            d.taken_method = method
        d.updated_at = datetime.now(UTC)
    db.flush()
    frames = [frame(db, "dose_event", {"patient_id": dose.patient_id, "dose_id": dose.id, "status": status,
                                       "method": method, "ts": iso(at)}, dose.patient_id)]
    if status == "missed":
        frames += _missed(db, device_id, dose, changed)
    return frames


def _missed(db: Session, device_id: str, dose: MedDose, group: list[MedDose]) -> list[dict]:
    p = db.get(Patient, dose.patient_id)
    meds = [m for d in group for m in d.meds]
    when = dose.scheduled_at.astimezone(TUNIS).strftime("%H:%M")
    a = alerts.create_alert(db, p.id, device_id, "dose_missed", "medium", None,
                            f"Missed dose at {when}: {', '.join(meds)}", None)
    nurses, doctor_chat = alerts.chat_ids(db, p)
    doctor = accounts.active_doctor(db, p.attending_doctor_id)
    n8n.emit_after_commit(db, "dose.missed", {"dose_id": dose.id, "patient_id": p.id, "patient_first_name": p.first_name,
                             "bed": _bed(db, p.id), "meds": meds, "scheduled_at": iso(dose.scheduled_at),
                             "nurse_chat_ids": nurses, "doctor_chat_id": doctor_chat,
                             "doctor_email": doctor.email if doctor else None})
    return [alerts.frame(db, a)]


def _bed(db: Session, patient_id: str) -> str | None:
    return db.scalar(select(Admission.bed).where(Admission.patient_id == patient_id,
                                                 Admission.discharged_at.is_(None)))


def _call_nurse(db: Session, device_id: str, p: dict) -> list[dict]:
    patient_id = active_patient_for_device(db, device_id)
    if patient_id is None:
        log.warning("call_nurse from %s with no admitted patient", device_id)
        return []
    bed = _bed(db, patient_id)
    a = alerts.create_alert(db, patient_id, device_id, "call_nurse", "high", None,
                            f"Patient called the nurse (bed {bed})", None)
    data = {"patient_id": patient_id, "device_id": device_id, "bed": bed, "ts": iso(_event_ts(p))}
    return [frame(db, "call_nurse", data, patient_id), alerts.frame(db, a)]


def _nurse_tap(db: Session, device_id: str, p: dict) -> list[dict]:
    uid = str(p.get("rfid_uid") or "").upper()
    nurse = db.scalar(select(User).join(Staff, Staff.user_id == User.id)
                      .where(func.upper(Staff.rfid_uid) == uid)) if uid else None
    patient_id = active_patient_for_device(db, device_id)
    if nurse is None:
        log.warning("nurse_tap with unknown RFID %s on %s", uid, device_id)
        return []
    audit(db, nurse, "read", "nurse_tap", device_id, patient_id=patient_id)
    return []


def _schedule_ack(db: Session, device_id: str, p: dict) -> list[dict]:
    try:
        v = int(p.get("schedule_version"))
    except (TypeError, ValueError):
        return []
    dev = db.get(Device, device_id)
    if dev and v > (dev.schedule_acked_version or 0):
        dev.schedule_acked_version = v
        db.flush()
    return []


def handle(db: Session, device_id: str, payload: dict) -> list[dict]:
    kind = payload.get("type")
    if kind in DOSE_EVENTS:
        return _dose_event(db, device_id, payload, DOSE_EVENTS[kind])
    handler = {"call_nurse": _call_nurse, "nurse_tap": _nurse_tap, "schedule_ack": _schedule_ack}.get(kind)
    if handler is None:
        log.info("unknown event type %r from %s ignored", kind, device_id)
        return []
    return handler(db, device_id, payload)
