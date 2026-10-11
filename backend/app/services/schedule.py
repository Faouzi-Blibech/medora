"""Prescriptions → med_doses → the retained MQTT `schedule` (data-model.md → med_doses, mqtt-topics.md).

Dose times are wall-clock HH:MM in Africa/Tunis, which is UTC+1 with no DST, so a fixed offset is exact
(and needs no tzdata on Windows laptops).
"""

import logging
from datetime import UTC, date, datetime, time, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ids import new_id
from app.iot import publisher
from app.models import Admission, Device, MedDose, Patient, Prescription

log = logging.getLogger("medora.schedule")
TUNIS = timezone(timedelta(hours=1), "Africa/Tunis")
MAX_DOSES = 8


def now_utc() -> datetime:
    return datetime.now(UTC)


def today_local() -> date:
    return now_utc().astimezone(TUNIS).date()


def local_to_utc(day: date, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(day, time(h, m), TUNIS).astimezone(UTC)


def course_start(rx: Prescription) -> datetime:
    """When the course starts (pharmacy spec §2): at once for an urgent prescription or one that predates the
    pharmacy gate, else when the pharmacist validated it, so no dose is ever born overdue."""
    written = rx.created_at or now_utc()
    if not rx.urgent and rx.reviewed_at is not None:
        return max(rx.reviewed_at, written)
    return written


def rebuild_doses(db: Session, prescription: Prescription) -> list[MedDose]:
    """Make the prescription's doses match its items. When active: `days × times` rows from course_start(rx) on (a
    time already past on day 0 moves to the end of the course). Future `scheduled` rows that are no longer wanted
    (all of them once inactive) are deleted; rows that still match (same time, slot and meds) keep their ids, so a
    device or a nurse screen holding a dose id stays valid across a rebuild. Idempotent."""
    rx = prescription
    future = list(db.scalars(select(MedDose).where(MedDose.prescription_id == rx.id, MedDose.status == "scheduled",
                                                   MedDose.scheduled_at > now_utc())))
    if not rx.active:
        _drop(db, future)
        return []
    existing = {(d.scheduled_at, d.slot, tuple(d.meds)): d
                for d in db.scalars(select(MedDose).where(MedDose.prescription_id == rx.id))}
    written = course_start(rx)
    start = written.astimezone(TUNIS).date()
    out: list[MedDose] = []
    for item in rx.items:
        days = int(item.get("days", 1))
        candidates = sorted(at for i in range(days + 1) for hhmm in item["times"]
                            if (at := local_to_utc(start + timedelta(days=i), hhmm)) >= written)
        for at in candidates[:days * len(item["times"])]:
            hhmm = at.astimezone(TUNIS).strftime("%H:%M")
            key = (at, item.get("slot"), (item["med"],))
            dose = existing.get(key)
            if dose is None:
                dose = MedDose(id=new_id(db, "d", 6), prescription_id=rx.id, patient_id=rx.patient_id,
                               scheduled_at=at, time_of_day=hhmm, meds=[item["med"]], slot=item.get("slot"),
                               status="scheduled")
                db.add(dose)
                existing[key] = dose
            out.append(dose)
    keep = {d.id for d in out}
    _drop(db, [d for d in future if d.id not in keep])
    db.flush()
    return out


def _drop(db: Session, doses: list[MedDose]) -> None:
    if doses:
        db.execute(delete(MedDose).where(MedDose.id.in_([d.id for d in doses])))
    db.flush()


def todays_doses(db: Session, patient_id: str) -> list[MedDose]:
    day = today_local()
    lo, hi = local_to_utc(day, "00:00"), local_to_utc(day + timedelta(days=1), "00:00")
    return list(db.scalars(select(MedDose).join(Prescription, Prescription.id == MedDose.prescription_id)
                           .where(MedDose.patient_id == patient_id, Prescription.active.is_(True),
                                  MedDose.scheduled_at >= lo, MedDose.scheduled_at < hi)
                           .order_by(MedDose.scheduled_at, MedDose.slot, MedDose.id)))


def upcoming_doses(db: Session, patient_id: str) -> list[MedDose]:
    """Active-prescription doses from local midnight today on, earliest first."""
    lo = local_to_utc(today_local(), "00:00")
    return list(db.scalars(select(MedDose).join(Prescription, Prescription.id == MedDose.prescription_id)
                           .where(MedDose.patient_id == patient_id, Prescription.active.is_(True),
                                  MedDose.scheduled_at >= lo)
                           .order_by(MedDose.scheduled_at, MedDose.slot, MedDose.id)))


def build_schedule_payload(db: Session, patient_id: str | None) -> dict:
    """The MQTT `schedule` body without `schedule_version` (the push sets it). One entry per distinct
    (time, slot) of the active doses from today on, using the earliest occurrence's dose_id (today's,
    or the next day's when today's was never due), meds merged, sorted by time, at most 8."""
    p = db.get(Patient, patient_id) if patient_id else None
    if p is None:
        return {"patient_id": None, "patient_first_name": None, "doses": []}
    entries: dict[tuple[str, int | None], dict] = {}
    for d in upcoming_doses(db, p.id):
        e = entries.setdefault((d.time_of_day, d.slot),
                               {"dose_id": d.id, "time": d.time_of_day, "meds": [], "slot": d.slot,
                                "_at": d.scheduled_at})
        if d.scheduled_at == e["_at"]:
            e["meds"] += [m for m in d.meds if m not in e["meds"]]
    ordered = sorted(entries.values(), key=lambda e: (e["time"], e["slot"] or 0))
    if len(ordered) > MAX_DOSES:
        log.warning("schedule for %s has %d entries; dropped %s (device limit %d)", p.id, len(ordered),
                    ", ".join(e["time"] for e in ordered[MAX_DOSES:]), MAX_DOSES)
    doses = ordered[:MAX_DOSES]
    for e in doses:
        del e["_at"]
    return {"patient_id": p.id, "patient_first_name": p.first_name, "doses": doses}


def _publish(db: Session, device: Device, payload: dict) -> bool:
    device.schedule_version = (device.schedule_version or 0) + 1
    db.flush()
    return publisher.publish_schedule(device.id, {"schedule_version": device.schedule_version, **payload})


def device_of(db: Session, patient_id: str) -> Device | None:
    device_id = db.scalar(select(Admission.device_id).where(Admission.patient_id == patient_id,
                                                            Admission.discharged_at.is_(None)))
    return db.get(Device, device_id) if device_id else None


def push_schedule(db: Session, patient_id: str) -> bool:
    """Publish the patient's schedule (retained, QoS 1) to their bedside unit. False if no device."""
    dev = device_of(db, patient_id)
    if dev is None:
        return False
    return _publish(db, dev, build_schedule_payload(db, patient_id))


def push_unassigned(db: Session, device_id: str) -> bool:
    dev = db.get(Device, device_id)
    return _publish(db, dev, build_schedule_payload(db, None)) if dev else False
