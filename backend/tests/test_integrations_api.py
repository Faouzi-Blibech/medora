from app.config import get_settings
from app.models import Appointment
from tests.helpers import login

SLOT = "2026-10-20T09:00:00Z"


def _n8n() -> dict:
    return {"X-N8N-Secret": get_settings().n8n_callback_secret}


def _free_slot(client) -> None:
    """a-0001 booked with Dr Trabelsi, then cancelled: SLOT is free again."""
    admin = login(client, "admin@medora.tn")
    client.post("/appointments/a-0001/confirm", headers=admin, json={"slot_at": SLOT, "doctor_id": "u-0001"})
    client.post("/appointments/a-0001/cancel", headers=admin)


def test_callbacks_need_the_secret(client):
    assert client.get("/integrations/n8n/daily-digest").status_code == 401
    r = client.get("/integrations/n8n/daily-digest", headers={"X-N8N-Secret": "wrong"})
    assert r.status_code == 401 and r.json()["code"] == "unauthorized"
    jwt = login(client, "admin@medora.tn")
    assert client.post("/integrations/n8n/follow-up", headers=jwt, json={"patient_id": "p-0001"}).status_code == 401


def test_backfill_accept(client, db):
    _free_slot(client)
    body = {"appointment_id": "a-0002", "slot_at": SLOT}
    r = client.post("/integrations/n8n/backfill-accept", headers=_n8n(), json=body)
    assert r.status_code == 200 and r.json() == {"status": "confirmed"}
    a = db.get(Appointment, "a-0002")
    assert a.status == "confirmed" and a.doctor_id == "u-0001" and a.confirmed_by is None
    again = client.post("/integrations/n8n/backfill-accept", headers=_n8n(), json=body)
    assert again.status_code == 409 and again.json()["code"] == "not_waiting"
    taken = client.post("/integrations/n8n/backfill-accept", headers=_n8n(), json={"appointment_id": "a-0003",
                                                                                     "slot_at": SLOT})
    assert taken.status_code == 409 and taken.json()["code"] == "slot_taken"
    nowhere = {"appointment_id": "a-0003", "slot_at": "2026-11-01T09:00:00Z"}
    assert client.post("/integrations/n8n/backfill-accept", headers=_n8n(), json=nowhere).status_code == 404


def test_appointment_reply(client, db, emitted):
    admin = login(client, "admin@medora.tn")
    client.post("/appointments/a-0001/confirm", headers=admin, json={"slot_at": SLOT, "doctor_id": "u-0001"})
    r = client.post("/integrations/n8n/appointment-reply", headers=_n8n(),
                    json={"appointment_id": "a-0001", "reply": "confirm"})
    assert r.status_code == 200 and db.get(Appointment, "a-0001").patient_confirmed_at is not None
    r = client.post("/integrations/n8n/appointment-reply", headers=_n8n(),
                    json={"appointment_id": "a-0001", "reply": "cancel"})
    assert r.status_code == 200 and r.json() == {"status": "cancelled"}
    assert emitted[-1][0] == "appointment.cancelled" and emitted[-1][1]["candidate"] is not None
    missing = client.post("/integrations/n8n/appointment-reply", headers=_n8n(),
                          json={"appointment_id": "a-9999", "reply": "confirm"})
    assert missing.status_code == 404


def test_daily_digest(client):
    rows = client.get("/integrations/n8n/daily-digest", headers=_n8n()).json()
    assert len(rows) == 1 and rows[0]["doctor"] == {"id": "u-0001", "name": "Dr Trabelsi", "email": "doctor@medora.tn"}
    # Amira (p-0001) and Youssef (p-0005, patient2@medora.tn) are the admitted cardiology patients
    assert sorted(x["name"] for x in rows[0]["patients"]) == ["Amira", "Youssef"]
    p = next(x for x in rows[0]["patients"] if x["name"] == "Amira")
    # First name only; an unreviewed AI summary never leaves the server.
    assert p["name"] == "Amira" and p["bed"] == "C-12" and p["news2"] == 0
    assert p["summary"] == "Summary not reviewed yet. Open Medora to review it."
    assert client.get("/integrations/n8n/daily-digest?doctor_id=u-0001", headers=_n8n()).json() == rows
    assert client.get("/integrations/n8n/daily-digest?doctor_id=u-0002", headers=_n8n()).json() == []


def test_follow_up_creates_a_triaged_request(client, db):
    r = client.post("/integrations/n8n/follow-up", headers=_n8n(), json={"patient_id": "p-0001", "days": 14})
    assert r.status_code == 200 and r.json()["status"] == "requested"
    a = db.get(Appointment, r.json()["appointment_id"])
    assert a.referral_text == "Post-discharge follow-up in 14 days" and a.ai_suggested["source"] in ("model", "rules")
    assert client.post("/integrations/n8n/follow-up", headers=_n8n(), json={"patient_id": "p-9999"}).status_code == 404
    assert client.post("/integrations/n8n/follow-up", headers=_n8n(),
                       json={"patient_id": "p-0001", "days": 0}).status_code == 422
