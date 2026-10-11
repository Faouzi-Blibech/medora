"""Pilot impact indicators (api.md 1.18): what a pilot ward would track, measured from the database.

Aggregates only: no patient names or ids leave this module. Each indicator is computed for the period
[now - days, now) and for the previous period of equal length, so the UI can show a trend.
An indicator the data model cannot measure is returned with `status: "not_recorded"` and no value.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, exists, func, select, union_all
from sqlalchemy.orm import Session

from app.models import AiSummary, Alert, Admission, Appointment, MedDose, NotebookEntry, Note, User, Vital

DOSE_WINDOW = timedelta(minutes=30)  # a dose is `missed` 30 min after its time (mqtt-topics.md)
ACK_TARGET = timedelta(minutes=5)
SHIFTS_PER_DAY = 3  # 8-hour shifts
SEVERITIES = ("low", "medium", "high", "critical")
SOURCES = ("manual", "simulator", "device")
BOOKED = ("confirmed", "done", "no_show")


def _ratio(num: float | None, den: float | None, scale: float = 1.0, nd: int = 1) -> float | None:
    if num is None or not den:
        return None
    return round(num / den * scale, nd)


def _pct(num, den):
    return _ratio(num, den, 100.0)


def _r(x: float | None, nd: int = 1) -> float | None:
    return None if x is None else round(float(x), nd)


def _alerts(db: Session, start: datetime, end: datetime, now: datetime) -> dict:
    in_window = and_(Alert.created_at >= start, Alert.created_at < end)
    by_sev = dict(db.execute(select(Alert.severity, func.count()).where(in_window).group_by(Alert.severity)).all())
    secs = func.extract("epoch", Alert.acked_at - Alert.created_at)
    med, p90 = db.execute(select(func.percentile_cont(0.5).within_group(secs),
                                 func.percentile_cont(0.9).within_group(secs))
                          .where(in_window, Alert.acked_at.is_not(None))).one()
    # high/critical alerts old enough to have had their 5 minutes; an open one counts as not acknowledged in time
    urgent, fast = db.execute(select(
        func.count(),
        func.count().filter(Alert.acked_at <= Alert.created_at + ACK_TARGET),
    ).where(in_window, Alert.severity.in_(("high", "critical")), Alert.created_at <= now - ACK_TARGET)).one()
    return {
        "alerts_total": sum(by_sev.values()),
        "alerts_by_severity": {s: by_sev.get(s, 0) for s in SEVERITIES},
        "ack_median_min": _ratio(med, 60),
        "ack_p90_min": _ratio(p90, 60),
        "ack_within_5min_pct": _pct(fast, urgent),
    }


def _patient_days(db: Session, start: datetime, end: datetime) -> float:
    """Sum of the admitted time overlapping [start, end), in days."""
    stop = func.coalesce(Admission.discharged_at, end)
    secs = func.extract("epoch", func.least(stop, end) - func.greatest(Admission.admitted_at, start))
    total = db.scalar(select(func.sum(secs)).where(Admission.admitted_at < end, stop > start))
    return float(total or 0) / 86400


def _doses(db: Session, start: datetime, end: datetime, now: datetime, patient_days: float) -> dict:
    # doses whose 30-minute window had closed: still-open doses are not judged yet
    due = and_(MedDose.scheduled_at >= start, MedDose.scheduled_at < end, MedDose.scheduled_at <= now - DOSE_WINDOW)
    total, taken, missed, on_time = db.execute(select(
        func.count(),
        func.count().filter(MedDose.status == "taken"),
        func.count().filter(MedDose.status == "missed"),
        func.count().filter(MedDose.status == "taken", MedDose.updated_at <= MedDose.scheduled_at + DOSE_WINDOW),
    ).where(due)).one()
    return {
        "doses_due": total,
        "doses_taken_pct": _pct(taken, total),
        "doses_missed_pct": _pct(missed, total),
        "doses_on_time_pct": _pct(on_time, total),
        "missed_per_patient_day": _ratio(missed, patient_days, nd=2) if total else None,
    }


def _appointments(db: Session, start: datetime, end: datetime, attendance_recorded: bool) -> dict:
    received = and_(Appointment.created_at >= start, Appointment.created_at < end)
    total, cancelled, refilled = db.execute(select(
        func.count(),
        func.count().filter(Appointment.status == "cancelled"),
        # a backfill booking is made by the system: slot set, confirmed_by empty (services/appointments.py)
        func.count().filter(Appointment.status.in_(BOOKED), Appointment.slot_at.is_not(None),
                            Appointment.confirmed_by.is_(None)),
    ).where(received)).one()
    wait = func.extract("epoch", Appointment.slot_at - Appointment.created_at) / 86400
    wait_median = db.scalar(select(func.percentile_cont(0.5).within_group(wait))
                            .where(received, Appointment.status.in_(BOOKED), Appointment.slot_at.is_not(None)))
    no_show_rate = None
    if attendance_recorded:
        seen = and_(Appointment.slot_at >= start, Appointment.slot_at < end)
        ns, attended = db.execute(select(func.count().filter(Appointment.status == "no_show"),
                                         func.count().filter(Appointment.status.in_(("done", "no_show"))))
                                  .where(seen)).one()
        no_show_rate = _pct(ns, attended)
    return {
        "requests_received": total,
        "request_to_slot_days": _r(wait_median),
        "cancellations": cancelled,
        "backfill_refills": refilled,
        "no_show_rate_pct": no_show_rate,
    }


def _vitals(db: Session, start: datetime, end: datetime, patient_days: float) -> dict:
    in_window = and_(Vital.ts >= start, Vital.ts < end)
    rows = dict(db.execute(select(Vital.source, func.count()).where(in_window).group_by(Vital.source)).all())
    total = sum(rows.values())
    band = case((Vital.news2 >= 7, "high"), (Vital.news2 >= 5, "medium"), else_="low")
    bands = dict(db.execute(select(band, func.count()).where(in_window, Vital.news2.is_not(None))
                            .group_by(band)).all())
    scored = sum(bands.values())
    on_patient = db.scalar(select(func.count()).where(in_window, Vital.patient_id.is_not(None))) or 0
    return {
        "vitals_per_patient_day": _ratio(on_patient, patient_days),
        "vitals_automated_pct": _pct(rows.get("device", 0) + rows.get("simulator", 0), total),
        "vitals_by_source": {s: rows.get(s, 0) for s in SOURCES},
        "news2_medium_high_pct": _pct(bands.get("medium", 0) + bands.get("high", 0), scored),
        "news2_bands": {b: bands.get(b, 0) for b in ("low", "medium", "high")},
    }


def _workload(db: Session, start: datetime, end: datetime, days: int) -> dict:
    notes = db.scalar(select(func.count()).select_from(Note).join(User, User.id == Note.author_id)
                      .where(User.role == "nurse", Note.created_at >= start, Note.created_at < end)) or 0
    parts = [select(m.created_at.label("at"), (m.human_confirmed_by.is_not(None)).label("ok"))
             .where(m.created_at >= start, m.created_at < end) for m in (AiSummary, NotebookEntry)]
    parts.append(select(Appointment.created_at.label("at"), (Appointment.human_confirmed_by.is_not(None)).label("ok"))
                 .where(Appointment.created_at >= start, Appointment.created_at < end,
                        Appointment.ai_suggested.is_not(None)))
    u = union_all(*parts).subquery()
    total, reviewed = db.execute(select(func.count(), func.count().filter(u.c.ok.is_(True)))
                                 .select_from(u)).one()
    return {
        "nurse_notes_per_shift": _ratio(notes, days * SHIFTS_PER_DAY, nd=2),
        "ai_reviewed_pct": _pct(reviewed, total),
        "ai_review": {"reviewed": reviewed, "pending": total - reviewed},
    }


def _window(db: Session, start: datetime, end: datetime, now: datetime, days: int, attendance: bool) -> dict:
    pd = _patient_days(db, start, end)
    return {**_alerts(db, start, end, now), **_doses(db, start, end, now, pd),
            **_appointments(db, start, end, attendance), **_vitals(db, start, end, pd),
            **_workload(db, start, end, days), "patient_days": round(pd, 1)}


# (id, group, unit, better: which direction is good (None = context, not a target), breakdown key)
INDICATORS = [
    ("alerts_total", "alerts", "count", None, "alerts_by_severity"),
    ("ack_median_min", "alerts", "minutes", "lower", None),
    ("ack_p90_min", "alerts", "minutes", "lower", None),
    ("ack_within_5min_pct", "alerts", "pct", "higher", None),
    ("doses_due", "medication", "count", None, None),
    ("doses_taken_pct", "medication", "pct", "higher", None),
    ("doses_missed_pct", "medication", "pct", "lower", None),
    ("doses_on_time_pct", "medication", "pct", "higher", None),
    ("missed_per_patient_day", "medication", "rate", "lower", None),
    ("requests_received", "appointments", "count", None, None),
    ("request_to_booking_hours", "appointments", "hours", "lower", None),
    ("request_to_slot_days", "appointments", "days", "lower", None),
    ("cancellations", "appointments", "count", "lower", None),
    ("backfill_refills", "appointments", "count", "higher", None),
    ("no_show_rate_pct", "appointments", "pct", "lower", None),
    ("vitals_per_patient_day", "monitoring", "rate", "higher", None),
    ("vitals_automated_pct", "monitoring", "pct", "higher", "vitals_by_source"),
    ("news2_medium_high_pct", "monitoring", "pct", None, "news2_bands"),
    ("nurse_notes_per_shift", "workload", "rate", None, None),
    ("ai_reviewed_pct", "workload", "pct", "higher", "ai_review"),
]
# no column stores when a request was booked (slot_at is the appointment time, not the booking time);
# no_show_rate_pct is also not_recorded until some workflow writes `done`/`no_show`
NEVER_RECORDED = {"request_to_booking_hours"}


def impact(db: Session, days: int, now: datetime | None = None) -> dict:
    now = (now or datetime.now(UTC)).replace(microsecond=0)
    start, prev_start = now - timedelta(days=days), now - timedelta(days=2 * days)
    attendance = bool(db.scalar(select(exists().where(Appointment.status.in_(("done", "no_show"))))))
    cur = _window(db, start, now, now, days, attendance)
    prev = _window(db, prev_start, start, now, days, attendance)
    out = []
    for key, group, unit, better, breakdown in INDICATORS:
        recorded = key not in NEVER_RECORDED and (key != "no_show_rate_pct" or attendance)
        out.append({
            "id": key, "group": group, "unit": unit, "better": better,
            "status": "ok" if recorded else "not_recorded",
            "value": cur.get(key) if recorded else None,
            "previous": prev.get(key) if recorded else None,
            "breakdown": cur[breakdown] if breakdown else None,
        })
    return {
        "days": days,
        "period": {"from": _iso(start), "to": _iso(now)},
        "previous_period": {"from": _iso(prev_start), "to": _iso(start)},
        "patient_days": cur["patient_days"],
        "data": "synthetic",
        "indicators": out,
    }


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")

