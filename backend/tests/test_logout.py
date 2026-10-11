from sqlalchemy import select

from app.models import AuditLog
from tests.helpers import login


def test_logout_is_audited(client, db):
    h = login(client, "nurse@medora.tn")
    assert client.post("/auth/logout", headers=h).status_code == 204
    assert db.scalar(select(AuditLog).where(AuditLog.action == "logout", AuditLog.resource_id == "u-0002"))


def test_logout_needs_a_session(client):
    assert client.post("/auth/logout").status_code == 401
