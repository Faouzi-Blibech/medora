"""Pilot impact indicators: known rows in a window far from the seed data, exact medians and percentages."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import AiSummary, Alert, Admission, Appointment, MedDose, Note, Prescription, User, Vital
from app.services.impact import impact
from tests.helpers import login, make_patient

NOW = datetime(2025, 1, 31, 12, 0, tzinfo=UTC)  # seed data lives in 2026: nothing else falls in these windows
DAY, MIN = timedelta(days=1), timedelta(minutes=1)


def _user(db, email: str) -> User:
    return db.scalar(select(User).where(User.email == email))


def _populate(db):
    doctor, nurse = _user(db, "doctor@ward.tn"), _user(db, "nurse@ward.tn")
    p = make_patient(db, attending=doctor.id)
    db.add(Admission(id="adm-t001", patient_id=p.id, bed="T-1", admitted_at=NOW - 10 * DAY))

    t = NOW - DAY
    db.add_all([
        Alert(id="al-t001", patient_id=p.id, kind="news2", severity="high", message="x", created_at=t,
              acked_by=nurse.id, acked_at=t + 2 * MIN),
        Alert(id="al-t002", patient_id=p.id, kind="news2", severity="high", message="x", created_at=t,
              acked_by=nurse.id, acked_at=t + 10 * MIN),
        Alert(id="al-t003", patient_id=p.id, kind="news2", severity="critical", message="x", created_at=t),
        Alert(id="al-t004", patient_id=p.id, kind="call_nurse", severity="medium", message="x", created_at=t,
              acked_by=nurse.id, acked_at=t + 4 * MIN),
        Alert(id="al-t005", patient_id=p.id, kind="call_nurse", severity="low", message="x",
              created_at=NOW - 40 * DAY),  # previous period
    ])

    db.add(Prescription(id="rx-t001", patient_id=p.id, doctor_id=doctor.id, items=[]))
    db.flush()

    def dose(i: int, status: str, at: datetime, updated: datetime) -> MedDose:
        return MedDose(id=f"d-t{i:03d}", prescription_id="rx-t001", patient_id=p.id, scheduled_at=at,
                       time_of_day="08:00", meds=[], status=status, updated_at=updated)

    s = NOW - 2 * DAY
    db.add_all([
        dose(1, "taken", s, s + 10 * MIN),            # on time
        dose(2, "taken", s, s + 120 * MIN),           # taken, late
        dose(3, "missed", s, s + 30 * MIN),
        dose(4, "dispensed", s, s),                   # no outcome recorded
        dose(5, "scheduled", NOW - 10 * MIN, NOW),    # window still open: not judged yet
    ])

    c = NOW - 5 * DAY
    db.add_all([
        Appointment(id="a-t001", patient_id=p.id, status="confirmed", urgency_ai=3, created_at=c,
                    slot_at=c + 4 * DAY, doctor_id=doctor.id, confirmed_by=doctor.id, human_confirmed_by=doctor.id,
                    ai_suggested={"source": "rules"}),
        Appointment(id="a-t002", patient_id=p.id, status="confirmed", urgency_ai=2, created_at=c,
                    slot_at=c + 2 * DAY, doctor_id=doctor.id, ai_suggested={"source": "rules"}),  # backfill
        Appointment(id="a-t003", patient_id=p.id, status="cancelled", urgency_ai=1, created_at=c),
    ])

    v = NOW - DAY
    db.add_all([
        Vital(ts=v, device_id="bsu-t01", patient_id=p.id, news2=2, source="manual"),
        Vital(ts=v + MIN, device_id="bsu-t01", patient_id=p.id, news2=5, source="simulator"),
        Vital(ts=v + 2 * MIN, device_id="bsu-t01", patient_id=p.id, news2=8, source="device"),
    ])
    db.add_all([Note(id=f"n-t{i}", patient_id=p.id, author_id=nurse.id, text="ok", created_at=v) for i in range(3)])
    db.add_all([
        AiSummary(id="s-t001", patient_id=p.id, ai_suggested={"source": "rules"}, human_confirmed_by=doctor.id,
                  created_at=v),
        AiSummary(id="s-t002", patient_id=p.id, ai_suggested={"source": "rules"}, created_at=v),
    ])
    db.flush()


def _by_id(out: dict) -> dict:
    return {i["id"]: i for i in out["indicators"]}


def test_indicators_match_known_rows(seeded):
    _populate(seeded)
    out = impact(seeded, 30, now=NOW)
    ind = _by_id(out)

    assert out["days"] == 30 and out["data"] == "synthetic"
    assert out["patient_days"] == 10.0

    assert ind["alerts_total"]["value"] == 4 and ind["alerts_total"]["previous"] == 1
    assert ind["alerts_total"]["breakdown"] == {"low": 0, "medium": 1, "high": 2, "critical": 1}
    assert ind["ack_median_min"]["value"] == 4.0  # acked after 2, 4 and 10 min
    assert ind["ack_p90_min"]["value"] == 8.8  # linear interpolation: 4 + 0.8 * 6
    assert ind["ack_within_5min_pct"]["value"] == 33.3  # 1 of 3 high/critical, the open one counts as late

    assert ind["doses_due"]["value"] == 4
    assert ind["doses_taken_pct"]["value"] == 50.0
    assert ind["doses_missed_pct"]["value"] == 25.0
    assert ind["doses_on_time_pct"]["value"] == 25.0
    assert ind["missed_per_patient_day"]["value"] == 0.1

    assert ind["requests_received"]["value"] == 3
    assert ind["request_to_slot_days"]["value"] == 3.0  # median of 2 and 4 days
    assert ind["cancellations"]["value"] == 1
    assert ind["backfill_refills"]["value"] == 1
    assert ind["request_to_booking_hours"]["status"] == "not_recorded"
    assert ind["request_to_booking_hours"]["value"] is None
    assert ind["no_show_rate_pct"]["status"] == "not_recorded"

    assert ind["vitals_per_patient_day"]["value"] == 0.3
    assert ind["vitals_automated_pct"]["value"] == 66.7
    assert ind["vitals_automated_pct"]["breakdown"] == {"manual": 1, "simulator": 1, "device": 1}
    assert ind["news2_medium_high_pct"]["breakdown"] == {"low": 1, "medium": 1, "high": 1}

    assert ind["nurse_notes_per_shift"]["value"] == 0.03  # 3 notes over 90 shifts
    assert ind["ai_reviewed_pct"]["value"] == 50.0  # 2 summaries + 2 triaged requests, 2 reviewed
    assert ind["ai_reviewed_pct"]["breakdown"] == {"reviewed": 2, "pending": 2}

    # empty denominators give no value, not zero
    assert ind["ack_median_min"]["previous"] is None
    assert ind["doses_taken_pct"]["previous"] is None


def test_no_show_rate_once_attendance_is_recorded(seeded):
    _populate(seeded)
    p = seeded.scalar(select(Appointment.patient_id).where(Appointment.id == "a-t001"))
    for i, status in enumerate(["done", "done", "done", "no_show"]):
        seeded.add(Appointment(id=f"a-t1{i}", patient_id=p, status=status, urgency_ai=3, created_at=NOW - 9 * DAY,
                               slot_at=NOW - 3 * DAY, confirmed_by=_user(seeded, "doctor@ward.tn").id))
    seeded.flush()
    ind = _by_id(impact(seeded, 7, now=NOW))
    assert ind["no_show_rate_pct"]["status"] == "ok"
    assert ind["no_show_rate_pct"]["value"] == 25.0


def test_admin_only(client):
    r = client.get("/admin/impact?days=7", headers=login(client, "admin@ward.tn"))
    assert r.status_code == 200
    body = r.json()
    assert body["days"] == 7 and len(body["indicators"]) > 10
    assert "first_name" not in r.text and "last_name" not in r.text
    for email in ("doctor@ward.tn", "nurse@ward.tn", "patient@ward.tn"):
        assert client.get("/admin/impact", headers=login(client, email)).status_code == 403
    assert client.get("/admin/impact").status_code == 401
    assert client.get("/admin/impact?days=0", headers=login(client, "admin@ward.tn")).status_code == 422
