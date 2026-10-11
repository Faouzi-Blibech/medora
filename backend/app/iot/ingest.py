"""MQTT ingestion as pure functions of (db, device_id, kind, payload) → WS frames (mqtt-topics.md v1.1).

The worker owns the broker loop and the commit; everything here is testable without a broker.
Each returned frame is the api.md WS envelope plus a routing `scope` {patient_id, ward, doctor_id, shared_with}.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ai.early_warning import score_news2
from app.models import Admission, Device, IngestedMessage, Patient, PatientAccess, Staff, Vital
from app.schemas import iso

log = logging.getLogger("medora.ingest")

KINDS = {"vitals", "events", "status"}
VITAL_SOURCES = {"device", "simulator", "manual"}


def shared_doctor_ids(db: Session, patient_id: str) -> list[str]:
    """Doctors holding an active sharing grant for this patient (one query per frame, not per socket)."""
    return list(db.scalars(select(PatientAccess.user_id).where(
        PatientAccess.patient_id == patient_id, PatientAccess.revoked_at.is_(None),
        PatientAccess.expires_at > datetime.now(UTC))))


def scope_for(db: Session, patient_id: str | None) -> dict:
    p = db.get(Patient, patient_id) if patient_id else None
    scope = {"patient_id": p.id if p else None, "ward": p.ward if p else None,
             "doctor_id": p.attending_doctor_id if p else None}
    shared = shared_doctor_ids(db, p.id) if p else []
    if shared:  # only present when a grant is live, so the plain scope shape is unchanged
        scope["shared_with"] = shared
    return scope


def frame(db: Session, type_: str, data: dict, patient_id: str | None) -> dict:
    return {"type": type_, "data": data, "scope": scope_for(db, patient_id)}


def active_patient_for_device(db: Session, device_id: str) -> str | None:
    return db.scalar(select(Admission.patient_id).where(Admission.device_id == device_id,
                                                        Admission.discharged_at.is_(None)))


def _ts(payload: dict) -> datetime:
    try:
        return datetime.fromtimestamp(int(payload["ts"]), UTC)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return datetime.now(UTC).replace(microsecond=0)


def _first_time(db: Session, device_id: str, msg_id: int) -> bool:
    """Dedupe on (device_id, msg_id): True only the first time this pair is seen."""
    row = db.execute(insert(IngestedMessage).values(device_id=device_id, msg_id=msg_id)
                     .on_conflict_do_nothing().returning(IngestedMessage.msg_id)).first()
    return row is not None


def _touch_device(db: Session, device_id: str, msg_id: int | None = None) -> Device:
    dev = db.get(Device, device_id)
    if dev is None:  # auto-register unknown devices
        dev = Device(id=device_id, online=True, schedule_version=0, schedule_acked_version=0)
        db.add(dev)
    dev.last_seen = datetime.now(UTC)
    if msg_id is not None and (dev.last_msg_id is None or msg_id > dev.last_msg_id):
        dev.last_msg_id = msg_id
    db.flush()
    return dev


def _num(v, cast):
    try:
        return None if v is None else cast(v)
    except (TypeError, ValueError):
        return None


def _vitals(db: Session, device_id: str, p: dict) -> list[dict]:
    ts = _ts(p)
    # The active admission decides whose vitals these are: a device with a stale schedule (after a
    # discharge or a move) must not keep charging readings and alerts to its previous patient.
    patient_id = active_patient_for_device(db, device_id)
    claimed = p.get("patient_id")
    if claimed and claimed != patient_id:
        log.warning("vitals from %s claim %s but the device is assigned to %s: using the admission",
                    device_id, claimed, patient_id)
    nurse_id = None
    if p.get("nurse_rfid"):
        uid = str(p["nurse_rfid"]).upper()
        nurse_id = db.scalar(select(Staff.user_id).where(func.upper(Staff.rfid_uid) == uid))
        if nurse_id is None:
            log.warning("unknown nurse RFID %s on %s: vital kept without nurse", uid, device_id)
    hr, spo2, temp = _num(p.get("hr"), int), _num(p.get("spo2"), int), _num(p.get("temp"), float)
    news = score_news2(hr, spo2, temp)
    # The bedside unit has no sensors (mqtt-topics v1.1): MQTT vitals come from the simulator
    source = p.get("source") if p.get("source") in VITAL_SOURCES else "simulator"
    inserted = db.execute(insert(Vital).values(ts=ts, device_id=device_id, patient_id=patient_id, hr=hr,
                                               spo2=spo2, temp=temp, nurse_id=nurse_id, news2=news.score,
                                               source=source)
                          .on_conflict_do_nothing().returning(Vital.ts)).first()
    if inserted is None:
        log.warning("vitals from %s at %s already stored (same second): skipped", device_id, ts)
        return []
    data = {"patient_id": patient_id, "device_id": device_id, "ts": iso(ts), "hr": hr, "spo2": spo2,
            "temp": temp, "news2": news.score}
    frames = [frame(db, "vital", data, patient_id)]
    if patient_id:
        from app.services import alerts  # late import: alerts imports ingest helpers

        frames += alerts.on_vital(db, patient_id, device_id, news, hr, spo2, temp)
    return frames


def _status(db: Session, device_id: str, p: dict) -> list[dict]:
    known = db.get(Device, device_id) is not None
    dev = _touch_device(db, device_id)
    was_online = known and bool(dev.online)
    dev.online = bool(p.get("online"))
    if p.get("fw_version"):
        dev.fw_version = str(p["fw_version"])
    db.flush()
    patient_id = active_patient_for_device(db, device_id)
    data = {"device_id": device_id, "online": dev.online, "ts": iso(dev.last_seen)}
    frames = [frame(db, "device_status", data, patient_id)]
    # alert on the online → offline transition only (the retained last-will is re-delivered on reconnect)
    if was_online and not dev.online and patient_id:
        from app.services import alerts

        bed = db.scalar(select(Admission.bed).where(Admission.patient_id == patient_id,
                                                    Admission.discharged_at.is_(None)))
        a = alerts.create_alert(db, patient_id, device_id, "device_offline", "medium", None,
                                f"Bedside unit {device_id} (bed {bed}) went offline", None)
        frames.append(alerts.frame(db, a))
    return frames


def handle(db: Session, device_id: str, kind: str, payload: dict) -> list[dict]:
    """Ingest one message. Returns the WS frames to relay after the caller commits ([] = nothing new)."""
    if kind not in KINDS or not isinstance(payload, dict):
        return []
    if kind == "status":  # retained/last-will: no msg_id, no dedupe
        return _status(db, device_id, payload)
    msg_id = _num(payload.get("msg_id"), int)
    if msg_id is None:
        log.warning("%s from %s without a valid msg_id: dropped", kind, device_id)
        return []
    if not _first_time(db, device_id, msg_id):
        return []
    dev = _touch_device(db, device_id, msg_id)
    dev.online = True
    if kind == "vitals":
        return _vitals(db, device_id, payload)
    from app.iot import events  # Task 7

    return events.handle(db, device_id, payload)
