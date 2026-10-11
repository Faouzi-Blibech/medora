"""A disabled or rejected account stops receiving patient data; a doctor cannot undo an admin's decision."""

from datetime import UTC, datetime

import pytest
from starlette.websockets import WebSocketDisconnect

from app.iot import ingest
from app.models import Patient, Staff, User
from app.services import alerts
from app.services import exams as E
from tests.helpers import login, make_user

SLOT = "2026-10-20T09:00:00Z"


def _token(client, email):
    return login(client, email)["Authorization"].split()[1]


# --- who disabled / rejected -------------------------------------------------------------------------------

def test_doctor_cannot_enable_an_account_an_admin_disabled(client, db):
    team = make_user(db, "team.t@medora.tn", role="nurse", supervisor_id="u-0001")
    doc, admin = login(client, "doctor@medora.tn"), login(client, "admin@medora.tn")
    assert client.post(f"/users/{team.id}/disable", headers=admin).json()["status"] == "disabled"
    r = client.post(f"/users/{team.id}/enable", headers=doc)
    assert r.status_code == 403 and db.get(User, team.id).status == "disabled"
    assert client.post(f"/users/{team.id}/enable", headers=admin).json()["status"] == "active"


def test_doctor_can_enable_what_he_disabled_himself(client, db):
    team = make_user(db, "team.t@medora.tn", role="nurse", supervisor_id="u-0001")
    doc = login(client, "doctor@medora.tn")
    client.post(f"/users/{team.id}/disable", headers=doc)
    assert db.get(User, team.id).status_changed_by == "u-0001"
    assert client.post(f"/users/{team.id}/enable", headers=doc).json()["status"] == "active"
    assert db.get(User, team.id).status_changed_by is None


def test_a_disabled_account_of_unknown_origin_is_admin_only(client, db):
    team = make_user(db, "team.t@medora.tn", role="nurse", supervisor_id="u-0001", status="disabled")  # as before 0005
    assert client.post(f"/users/{team.id}/enable", headers=login(client, "doctor@medora.tn")).status_code == 403
    assert client.post(f"/users/{team.id}/enable", headers=login(client, "admin@medora.tn")).status_code == 200


def test_doctor_cannot_approve_a_request_an_admin_rejected(client, db):
    a = make_user(db, "a.t@medora.tn", role=None, status="pending", requested_doctor_id="u-0001")
    doc, admin = login(client, "doctor@medora.tn"), login(client, "admin@medora.tn")
    assert client.post(f"/users/{a.id}/reject", headers=admin).json()["status"] == "rejected"
    r = client.post(f"/users/{a.id}/approve", headers=doc, json={"role": "nurse"})
    assert r.status_code == 403 and db.get(User, a.id).status == "rejected"
    assert client.post(f"/users/{a.id}/approve", headers=admin, json={"role": "nurse"}).status_code == 200


def test_doctor_can_approve_a_request_he_rejected_himself(client, db):
    a = make_user(db, "a.t@medora.tn", role=None, status="pending", requested_doctor_id="u-0001")
    doc = login(client, "doctor@medora.tn")
    assert client.post(f"/users/{a.id}/reject", headers=doc).json()["status"] == "rejected"
    assert client.post(f"/users/{a.id}/approve", headers=doc, json={"role": "nurse"}).status_code == 200
    assert db.get(User, a.id).status_changed_by is None


# --- open sockets and every recipient ----------------------------------------------------------------------

def test_disable_closes_the_open_websocket(client, db):
    admin = login(client, "admin@medora.tn")
    token = _token(client, "nurse@medora.tn")
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
        assert client.post("/users/u-0002/disable", headers=admin).status_code == 200
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_disable_leaves_other_users_sockets_open(client):
    admin = login(client, "admin@medora.tn")
    token = _token(client, "doctor@medora.tn")
    with client.websocket_connect(f"/ws?token={token}") as ws:
        assert client.post("/users/u-0002/disable", headers=admin).status_code == 200
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_a_disabled_user_cannot_open_a_websocket(client, db):
    token = _token(client, "nurse@medora.tn")  # a token issued while active
    db.get(User, "u-0002").status = "disabled"
    db.flush()
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/ws?token={token}") as ws:
            ws.receive_json()
    assert e.value.code == 4401


def test_inactive_users_are_not_telegram_recipients(db, seeded):
    db.get(Staff, "u-0001").telegram_chat_id = "D1"
    db.get(Staff, "u-0002").telegram_chat_id = "N1"
    p = db.get(Patient, "p-0001")  # Cardiology, attending u-0001
    assert alerts.chat_ids(db, p) == (["N1"], "D1")
    db.get(User, "u-0001").status = "disabled"
    db.get(User, "u-0002").status = "disabled"
    db.flush()
    assert alerts.chat_ids(db, p) == ([], None)


def test_critical_alert_event_skips_a_disabled_doctor(db, seeded, emitted):
    db.get(Staff, "u-0001").telegram_chat_id = "D1"
    db.get(User, "u-0001").status = "disabled"
    ts = int(datetime.now(UTC).timestamp())
    ingest.handle(db, "bsu-001", "vitals", {"msg_id": 1, "ts": ts, "patient_id": "p-0001", "hr": 131, "spo2": 88,
                                            "temp": 39.2})
    db.commit()
    event, data = emitted[-1]
    assert event == "alert.critical" and data["doctor_chat_id"] is None


def test_results_ready_event_skips_a_disabled_doctor(db, seeded):
    db.get(Staff, "u-0001").telegram_chat_id = "D1"
    p = db.get(Patient, "p-0001")
    ev = E.results_ready_event(db, "a-0001", p, "u-0001")
    assert (ev["doctor_chat_id"], ev["doctor_email"]) == ("D1", "doctor@medora.tn")
    db.get(User, "u-0001").status = "disabled"
    db.flush()
    ev = E.results_ready_event(db, "a-0001", p, "u-0001")
    assert (ev["doctor_chat_id"], ev["doctor_email"], ev["doctor_name"]) == (None, None, None)


def test_daily_digest_skips_a_disabled_doctor(client, db):
    from app.config import get_settings

    h = {"X-N8N-Secret": get_settings().n8n_callback_secret}
    assert len(client.get("/integrations/n8n/daily-digest", headers=h).json()) == 1
    db.get(User, "u-0001").status = "disabled"
    db.flush()
    assert client.get("/integrations/n8n/daily-digest", headers=h).json() == []
    assert client.get("/integrations/n8n/daily-digest?doctor_id=u-0001", headers=h).json() == []


def test_confirm_with_an_inactive_doctor_is_422(client, db):
    admin = login(client, "admin@medora.tn")
    body = {"slot_at": SLOT, "doctor_id": "u-0001"}
    db.get(User, "u-0001").status = "disabled"
    db.flush()
    r = client.post("/appointments/a-0001/confirm", headers=admin, json=body)
    assert r.status_code == 422 and r.json()["code"] == "invalid"
    db.get(User, "u-0001").status = "active"
    db.flush()
    assert client.post("/appointments/a-0001/confirm", headers=admin, json=body).status_code == 200
