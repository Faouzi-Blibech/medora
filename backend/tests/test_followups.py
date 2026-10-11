"""Deferred review minors and the api 1.5 staff list."""

import logging
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.iot import ingest, publisher
from app.models import Admission, AuditLog, Prescription, Staff, User
from app.services import schedule
from tests.helpers import login

NOW = int(datetime.now(UTC).timestamp())


# 6: a nurse without a ward sees nothing (and no 500)
def test_wardless_nurse_sees_nothing(client, db):
    db.get(Staff, "u-0003").ward = None
    db.flush()
    h = login(client, "nurse2@ward.tn")
    r = client.get("/patients", headers=h)
    assert r.status_code == 200 and r.json() == []
    assert client.get("/alerts", headers=h).json() == []


# 9: the partial unique indexes live on the models, so every schema enforces them
def test_one_active_admission_per_patient(db, seeded):
    db.add(Admission(id="adm-9999", patient_id="p-0001", bed="C-99"))
    with pytest.raises(IntegrityError):
        db.flush()


# 10: audit_log is append-only in the database
def test_audit_log_append_only(db, seeded):
    db.add(AuditLog(user_id="u-0001", role="doctor", action="read", resource="patient", resource_id="p-0001"))
    db.flush()
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(text("UPDATE audit_log SET action = 'x'"))
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(text("DELETE FROM audit_log"))


# 11: a doctor's discharge writes one audit row
def test_doctor_discharge_audited_once(client, db):
    h = login(client, "doctor@ward.tn")
    before = db.query(AuditLog).filter_by(action="update", patient_id="p-0001").count()
    client.post("/admissions/adm-0001/discharge", headers=h)
    assert db.query(AuditLog).filter_by(action="update", patient_id="p-0001").count() == before + 1


# 12: a QoS 0 frame published while disconnected is reported as not sent
def test_qos0_without_connection_is_not_sent(monkeypatch, caplog):
    class Info:
        rc = publisher.mqtt.MQTT_ERR_NO_CONN

    class Down:
        def publish(self, *a, **k):
            return Info()

    monkeypatch.setattr(publisher, "_client", Down())
    with caplog.at_level(logging.WARNING, "ward.publisher"):
        assert publisher.publish_ws_frame({"type": "vital"}) is False
    assert publisher.publish_schedule("bsu-001", {}) is True  # QoS 1 is queued by paho until reconnect
    assert "not connected" in caplog.text


# 13: an unknown alert status filter is a 422
def test_alert_status_validated(client):
    h = login(client, "nurse@ward.tn")
    assert client.get("/alerts?status=closed", headers=h).status_code == 422
    assert client.get("/alerts?status=all", headers=h).status_code == 200


# 15: the 8-dose cap is logged, not silent
def test_schedule_cap_logged(db, seeded, caplog):
    rx = Prescription(id="rx-9200", patient_id="p-0001", doctor_id="u-0001", active=True, care_plan="",
                      created_at=schedule.local_to_utc(schedule.today_local(), "00:00"),
                      items=[{"med": f"M{i}", "times": [f"{8 + i:02d}:30"], "slot": None, "days": 1}
                             for i in range(9)])
    db.add(rx)
    db.flush()
    schedule.rebuild_doses(db, rx)
    with caplog.at_level(logging.WARNING, "ward.schedule"):
        assert len(schedule.build_schedule_payload(db, "p-0001")["doses"]) == 8
    assert "dropped" in caplog.text


# api 1.5: GET /staff (admin)
def test_staff_list(client):
    h = login(client, "admin@ward.tn")
    rows = client.get("/staff", headers=h).json()
    assert {r["id"] for r in rows} == {"u-0001", "u-0002", "u-0003", "u-0004", "u-0006", "u-0007", "u-0008"}
    ines = next(r for r in rows if r["id"] == "u-0002")
    assert ines == {"id": "u-0002", "name": "Nurse Ines", "email": "nurse@ward.tn", "role": "nurse", "status": "active",
                    "ward": "Cardiology", "scope": "Cardiology", "last_login_at": None}
    admin = next(r for r in rows if r["id"] == "u-0004")
    assert admin["last_login_at"] is not None and admin["scope"] == "All wards"
    assert client.get("/staff", headers=login(client, "nurse@ward.tn")).status_code == 403


def test_staff_excludes_patients(client, db):
    rows = client.get("/staff", headers=login(client, "admin@ward.tn")).json()
    patient_ids = {u.id for u in db.query(User).filter_by(role="patient")}
    assert not patient_ids & {r["id"] for r in rows}


def test_ingest_vitals_unaffected(db, seeded):
    assert ingest.handle(db, "bsu-001", "vitals", {"msg_id": 1, "ts": NOW, "hr": 80, "spo2": 98, "temp": 37.0})
