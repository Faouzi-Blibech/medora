"""Regression tests for the whole-branch review findings."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.iot import ingest, worker
from app.models import Alert, Device, MedDose, Prescription, Vital
from app.services import schedule
from tests.helpers import login

NOW = int(datetime.now(UTC).timestamp())


# 1: moving a patient to another device clears the old one
def test_move_patient_unassigns_old_device(client, db, published):
    db.add(Device(id="bsu-002", online=True, schedule_version=0, schedule_acked_version=0))
    db.flush()
    r = client.post("/devices/bsu-002/assign", headers=login(client, "admin@medora.tn"),
                    json={"patient_id": "p-0001", "bed": "C-13"})
    assert r.status_code == 200
    by_topic = {t: p for t, p, _, _ in published}
    assert by_topic["hospital/device/bsu-001/schedule"]["patient_id"] is None
    assert by_topic["hospital/device/bsu-002/schedule"]["patient_id"] == "p-0001"


# 2: the active admission decides whose vitals they are
def test_stale_device_vitals_not_charged_to_discharged_patient(client, db):
    client.post("/admissions/adm-0001/discharge", headers=login(client, "admin@medora.tn"))
    ingest.handle(db, "bsu-001", "vitals", {"msg_id": 1, "ts": NOW, "patient_id": "p-0001", "hr": 135,
                                            "spo2": 87, "temp": 39.3})
    v = db.scalars(select(Vital).where(Vital.device_id == "bsu-001", Vital.ts == datetime.fromtimestamp(NOW, UTC)))
    assert v.one().patient_id is None
    assert db.query(Alert).count() == 0


def test_payload_patient_mismatch_uses_admission(db, seeded):
    ingest.handle(db, "bsu-001", "vitals", {"msg_id": 2, "ts": NOW + 1, "patient_id": "p-0007", "hr": 80,
                                            "spo2": 98, "temp": 37.0})
    v = db.scalars(select(Vital).where(Vital.ts == datetime.fromtimestamp(NOW + 1, UTC))).one()
    assert v.patient_id == "p-0001"


# 3: no dose is created before the prescription was written
def test_no_past_doses_and_full_course(db, seeded):
    rx = Prescription(id="rx-9100", patient_id="p-0001", doctor_id="u-0001", active=True, care_plan="",
                      items=[{"med": "X", "times": ["00:01", "23:59"], "slot": None, "days": 2}],
                      created_at=schedule.local_to_utc(schedule.today_local(), "12:00"))
    db.add(rx)
    db.flush()
    doses = schedule.rebuild_doses(db, rx)
    assert len(doses) == 4
    assert all(d.scheduled_at >= rx.created_at for d in doses)


def test_schedule_lists_next_occurrence_when_today_is_past(db, seeded):
    rx = Prescription(id="rx-9101", patient_id="p-0001", doctor_id="u-0001", active=True, care_plan="",
                      items=[{"med": "Y", "times": ["00:01"], "slot": 4, "days": 1}],
                      created_at=schedule.local_to_utc(schedule.today_local(), "12:00"))
    db.add(rx)
    db.flush()
    schedule.rebuild_doses(db, rx)
    entry = next(d for d in schedule.build_schedule_payload(db, "p-0001")["doses"] if d["slot"] == 4)
    dose = db.get(MedDose, entry["dose_id"])
    assert dose.scheduled_at.astimezone(schedule.TUNIS).date() == schedule.today_local() + timedelta(days=1)


# 4: validation errors use the {detail, code} envelope
def test_422_envelope(client):
    r = client.post("/auth/login", json={"email": "doctor@medora.tn"})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str) and r.json()["code"] == "invalid"


# 5: null on a NOT NULL field is a 422, not a 500
def test_patch_null_rejected(client):
    h = login(client, "doctor@medora.tn")
    assert client.patch("/patients/p-0002", headers=h, json={"history": None}).status_code == 422
    assert client.patch("/patients/p-0002", headers=h, json={"first_name": None}).status_code == 422


# 7: an ack is not undone seconds later by the same ongoing deterioration
def test_recently_acked_alert_not_reopened(client, db):
    def bad(i):
        ingest.handle(db, "bsu-001", "vitals", {"msg_id": 100 + i, "ts": NOW + 100 + i, "patient_id": "p-0001",
                                                "hr": 80, "spo2": 88, "temp": 37.0})
    bad(0)
    aid = db.query(Alert).one().id
    client.post(f"/alerts/{aid}/ack", headers=login(client, "nurse@medora.tn"))
    bad(1)
    assert db.query(Alert).filter_by(kind="news2").count() == 1


# 14: the worker waits for the migrated schema
def test_schema_ready(engine):
    assert worker.schema_ready(engine) is True
