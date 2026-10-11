from datetime import UTC, datetime, timedelta

from app.iot import ingest
from app.models import Alert, Staff
from tests.helpers import login

NOW = int(datetime.now(UTC).timestamp())


def vital(msg_id, **kw):
    return dict({"msg_id": msg_id, "ts": NOW + msg_id, "patient_id": "p-0001", "hr": 80, "spo2": 98,
                 "temp": 37.0}, **kw)


def test_critical_vital_opens_alert_and_emits(db, seeded, emitted):
    db.get(Staff, "u-0002").telegram_chat_id = "111"
    frames = ingest.handle(db, "bsu-001", "vitals", vital(1, hr=131, spo2=88, temp=39.2))
    a = db.query(Alert).filter_by(patient_id="p-0001", kind="news2").one()
    assert a.severity == "critical" and a.news2 == 8 and a.acked_by is None
    assert a.ai_suggested["source"] == "rules" and a.ai_suggested["parts"] == {"hr": 3, "spo2": 3, "temp": 2}
    assert "SpO2 88%" in a.message and "HR 131" in a.message
    af = next(f for f in frames if f["type"] == "alert")
    assert af["data"]["id"] == a.id and af["data"]["bed"] == "C-12" and af["scope"]["ward"] == "Cardiology"
    db.commit()  # events leave after the commit, as in the worker
    event, data = emitted[-1]
    assert event == "alert.critical"
    assert data == {"alert_id": a.id, "patient_first_name": "Amira", "bed": "C-12", "kind": "news2", "news2": 8,
                    "message": a.message, "nurse_chat_ids": ["111"], "doctor_chat_id": None}


def test_low_score_no_alert(db, seeded, emitted):
    ingest.handle(db, "bsu-001", "vitals", vital(2, hr=95))  # 1 point
    assert db.query(Alert).count() == 0 and emitted == []


def test_medium_alert_no_emit(db, seeded, emitted):
    ingest.handle(db, "bsu-001", "vitals", vital(3, hr=115, spo2=95))  # 2 + 1
    assert db.query(Alert).filter_by(kind="news2").one().severity == "medium"
    assert emitted == []


def test_open_alert_deduped(db, seeded):
    ingest.handle(db, "bsu-001", "vitals", vital(4, spo2=88))
    ingest.handle(db, "bsu-001", "vitals", vital(5, spo2=89))
    assert db.query(Alert).filter_by(kind="news2").count() == 1


def test_old_alert_does_not_dedupe(db, seeded):
    ingest.handle(db, "bsu-001", "vitals", vital(6, spo2=88))
    a = db.query(Alert).one()
    a.created_at = datetime.now(UTC) - timedelta(minutes=11)
    db.flush()
    ingest.handle(db, "bsu-001", "vitals", vital(7, spo2=88))
    assert db.query(Alert).filter_by(kind="news2").count() == 2


def test_trend_alert_when_news2_quiet(db, seeded):
    # seed history: HR 65-90; 50 bpm scores NEWS2 1 (low) but is far below this patient's baseline
    ingest.handle(db, "bsu-001", "vitals", vital(8, hr=50))
    t = db.query(Alert).filter_by(kind="trend").one()
    assert t.severity == "medium" and t.ai_suggested["param"] == "hr" and t.ai_suggested["z"] <= -3
    assert t.ai_suggested["source"] == "rules"


def test_list_and_ack(client, db):
    ingest.handle(db, "bsu-001", "vitals", vital(9, spo2=88))
    h = login(client, "nurse@medora.tn")
    rows = client.get("/alerts?status=open", headers=h).json()
    assert len(rows) == 1 and {"id", "patient_id", "device_id", "kind", "severity", "news2", "message",
                               "created_at", "acked_by", "acked_at"} <= set(rows[0])
    r = client.post(f"/alerts/{rows[0]['id']}/ack", headers=h)
    assert r.status_code == 200 and r.json()["acked_by"] == "u-0002" and r.json()["acked_at"]
    assert client.get("/alerts?status=open", headers=h).json() == []
    assert len(client.get("/alerts", headers=h).json()) == 1


def test_ack_other_ward_forbidden(client, db):
    ingest.handle(db, "bsu-001", "vitals", vital(10, spo2=88))
    aid = db.query(Alert).one().id
    assert client.post(f"/alerts/{aid}/ack", headers=login(client, "nurse2@medora.tn")).status_code == 403
    assert client.get("/alerts", headers=login(client, "nurse2@medora.tn")).json() == []


def test_ack_broadcasts_update(client, db, published):
    ingest.handle(db, "bsu-001", "vitals", vital(11, spo2=88))
    aid = db.query(Alert).one().id
    client.post(f"/alerts/{aid}/ack", headers=login(client, "doctor@medora.tn"))
    topic, f, _, _ = published[-1]
    assert topic == "ward/internal/ws" and f["type"] == "alert" and f["data"]["acked_by"] == "u-0001"


def test_admin_cannot_list_alerts(client):
    assert client.get("/alerts", headers=login(client, "admin@medora.tn")).status_code == 403
