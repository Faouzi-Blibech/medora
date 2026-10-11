"""The 4th staff role (pharmacy spec §2): sign-up, admin-only approval, login, WebSocket."""

from sqlalchemy import select

from app.models import Staff, User
from tests.helpers import login, make_user

GOOD = "a-Long-and-unusual-passphrase-42"


def _reg(client, **over):
    body = {"name": "Salma Test", "email": "salma.t@ward.tn", "password": GOOD, "role": "pharmacist"}
    return client.post("/auth/register", json={**body, **over})


def _user(db, email):
    return db.scalar(select(User).where(User.email == email))


def test_pharmacist_can_be_requested(client, db):
    assert _reg(client).status_code == 202
    u = _user(db, "salma.t@ward.tn")
    assert (u.requested_role, u.role, u.status) == ("pharmacist", None, "pending")


def test_a_pharmacist_request_cannot_name_a_doctor(client, db):
    r = _reg(client, requested_doctor_id="u-0001")
    assert r.status_code == 422 and r.json()["code"] == "invalid"
    assert _user(db, "salma.t@ward.tn") is None


def test_only_the_admin_approves_a_pharmacist(client, db):
    named = make_user(db, "ph.req@ward.tn", role=None, status="pending", requested_doctor_id="u-0001")
    named.requested_role = "pharmacist"
    db.flush()
    r = client.post(f"/users/{named.id}/approve", headers=login(client, "doctor@ward.tn"), json={"role": "pharmacist"})
    assert r.status_code == 403
    r = client.post(f"/users/{named.id}/approve", headers=login(client, "admin@ward.tn"),
                    json={"role": "pharmacist", "ward": "Cardiology"})
    assert r.status_code == 200 and (r.json()["role"], r.json()["status"], r.json()["ward"]) == (
        "pharmacist", "active", None)
    assert db.get(Staff, named.id) is None
    bad = make_user(db, "x.req@ward.tn", role=None, status="pending")
    assert client.post(f"/users/{bad.id}/approve", headers=login(client, "admin@ward.tn"),
                       json={"role": "chemist"}).status_code == 422


def test_an_approved_pharmacist_logs_in_and_connects(client, db):
    make_user(db, "ph.ok@ward.tn", role="pharmacist")
    h = login(client, "ph.ok@ward.tn")
    assert client.get("/me", headers=h).json()["role"] == "pharmacist"
    token = h["Authorization"].split()[1]
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
