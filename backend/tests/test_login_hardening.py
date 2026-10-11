from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, User
from tests.helpers import login, make_user

WRONG = "wrong-password-123"


def _post(client, email, pw):
    return client.post("/auth/login", json={"email": email, "password": pw})


def test_unknown_email_and_wrong_password_look_the_same(client):
    a, b = _post(client, "nobody@medora.tn", WRONG), _post(client, "doctor@medora.tn", WRONG)
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_pending_message_only_with_the_right_password(client, db):
    make_user(db, "pending@medora.tn", role=None, status="pending")
    assert _post(client, "pending@medora.tn", WRONG).status_code == 401
    r = _post(client, "pending@medora.tn", "ward1234")
    assert r.status_code == 403 and r.json()["code"] == "account_pending"


@pytest.mark.parametrize("status,code", [("disabled", "account_disabled"), ("rejected", "account_rejected")])
def test_inactive_accounts(client, db, status, code):
    make_user(db, f"{status}@medora.tn", status=status)
    r = _post(client, f"{status}@medora.tn", "ward1234")
    assert r.status_code == 403 and r.json()["code"] == code


def test_five_failures_lock_then_unlock(client, db):
    for _ in range(5):
        assert _post(client, "nurse@medora.tn", WRONG).status_code == 401
    r = _post(client, "nurse@medora.tn", "ward1234")
    assert r.status_code == 423 and r.json()["code"] == "account_locked"
    db.get(User, "u-0002").locked_until = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert _post(client, "nurse@medora.tn", "ward1234").status_code == 200
    assert db.get(User, "u-0002").failed_logins == 0


def test_failures_and_lockout_are_audited(client, db):
    for _ in range(5):
        _post(client, "nurse@medora.tn", WRONG)
    actions = db.scalars(select(AuditLog.action).where(AuditLog.resource_id == "u-0002")).all()
    assert actions.count("login_failed") == 5 and "lockout" in actions


def test_disabled_user_token_dies_on_next_request(client, db):
    h = login(client, "nurse@medora.tn")
    assert client.get("/me", headers=h).status_code == 200
    db.get(User, "u-0002").status = "disabled"
    db.flush()
    assert client.get("/me", headers=h).status_code == 401


def test_failed_login_rate_limit_per_ip(client):
    codes = [_post(client, f"ghost{i}@medora.tn", WRONG).status_code for i in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    # once blocked, even the right password is not checked (no oracle for a guesser)
    assert _post(client, "doctor@medora.tn", "ward1234").status_code == 429


def test_successful_logins_do_not_count(client):
    for _ in range(15):  # a hospital behind one public IP
        assert _post(client, "doctor@medora.tn", "ward1234").status_code == 200
