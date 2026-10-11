from datetime import date

from app.config import get_settings
from app.models import HealthEvent
from app.services import health_calendar as H


def _n8n() -> dict:
    return {"X-N8N-Secret": get_settings().n8n_callback_secret}


def test_due_needs_secret(client):
    assert client.get("/integrations/n8n/health-events/due").status_code == 401


def test_due_lists_payloads(client, monkeypatch):
    monkeypatch.setattr(H, "_today", lambda: date(2026, 10, 8))
    r = client.get("/integrations/n8n/health-events/due", headers=_n8n())
    assert r.status_code == 200
    ids = [p["event_id"] for p in r.json()]
    assert "he-0001" in ids and "he-0002" in ids and "he-0003" not in ids  # flu starts 10-15, notify 3 days
    assert all("recipients" in p and "web_url" in p for p in r.json())


def test_announced_is_idempotent(client, db):
    r = client.post("/integrations/n8n/health-events/he-0002/announced", headers=_n8n())
    assert r.status_code == 200 and r.json() == {"status": "announced"}
    first = db.get(HealthEvent, "he-0002").announced_at
    client.post("/integrations/n8n/health-events/he-0002/announced", headers=_n8n())
    assert db.get(HealthEvent, "he-0002").announced_at == first
    assert client.post("/integrations/n8n/health-events/he-9999/announced", headers=_n8n()).status_code == 404
