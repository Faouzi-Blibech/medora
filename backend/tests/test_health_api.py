from app.models import AuditLog, HealthEvent
from tests.helpers import login

NEW = {"title": {"en": "Local vaccination day", "fr": "Journée de vaccination", "ar": "يوم التلقيح"},
       "category": "vaccination", "starts_on": "2026-11-20", "ends_on": "2026-11-20",
       "audience": {"roles": ["patient"], "sex": None, "min_age": None, "max_age": None}}


def test_list_needs_login(client):
    assert client.get("/health-events").status_code == 401


def test_list_window_and_flags(client):
    pat = login(client, "patient@ward.tn")
    r = client.get("/health-events?from=2026-10-01&to=2026-11-30", headers=pat)
    assert r.status_code == 200
    ids = [e["id"] for e in r.json()]
    assert ids[:2] == ["he-0001", "he-0002"] and "he-0007" not in ids
    rose = next(e for e in r.json() if e["id"] == "he-0001")
    movember = next(e for e in r.json() if e["id"] == "he-0004")
    assert rose["matches_me"] is True and rose["following"] is True and movember["matches_me"] is False


def test_prefs_get_put(client):
    pat = login(client, "patient@ward.tn")
    assert client.get("/me/health-prefs", headers=pat).json()["following"]["screening"] is True
    r = client.put("/me/health-prefs", headers=pat, json={"following": {"screening": False}})
    assert r.status_code == 200 and r.json()["following"]["screening"] is False
    ev = client.get("/health-events?from=2026-10-01&to=2026-10-31", headers=pat).json()
    assert next(e for e in ev if e["id"] == "he-0001")["following"] is False


def test_prefs_unknown_category_422(client):
    pat = login(client, "patient@ward.tn")
    r = client.put("/me/health-prefs", headers=pat, json={"following": {"vaccination": False, "astrology": False}})
    assert r.status_code == 422
    assert client.get("/me/health-prefs", headers=pat).json()["following"]["vaccination"] is True


def test_only_admin_writes(client):
    doc = login(client, "doctor@ward.tn")
    assert client.post("/health-events", headers=doc, json=NEW).status_code == 403
    assert client.delete("/health-events/he-0001", headers=doc).status_code == 403
    assert client.post("/health-events/he-0001/notify", headers=doc).status_code == 403


def test_admin_create_patch_delete(client, db):
    adm = login(client, "admin@ward.tn")
    r = client.post("/health-events", headers=adm, json=NEW)
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["id"].startswith("he-") and ev["description"] == {"en": "", "fr": "", "ar": ""}
    assert ev["notify_days_before"] == 3
    r = client.patch(f"/health-events/{ev['id']}", headers=adm, json={"organizer": "Ward"})
    assert r.status_code == 200 and r.json()["organizer"] == "Ward"
    assert client.delete(f"/health-events/{ev['id']}", headers=adm).status_code == 204
    assert client.patch(f"/health-events/{ev['id']}", headers=adm, json={"organizer": "x"}).status_code == 404


def test_bad_dates(client):
    adm = login(client, "admin@ward.tn")
    r = client.post("/health-events", headers=adm, json=dict(NEW, ends_on="2026-11-19"))
    assert r.status_code == 422 and r.json()["code"] == "bad_dates"
    r = client.patch("/health-events/he-0005", headers=adm, json={"ends_on": "2026-11-01"})  # starts 11-14
    assert r.status_code == 422 and r.json()["code"] == "bad_dates"


def test_bad_audience(client):
    adm = login(client, "admin@ward.tn")
    bad = dict(NEW, audience={"roles": [], "sex": None, "min_age": None, "max_age": None})
    assert client.post("/health-events", headers=adm, json=bad).status_code == 422
    bad = dict(NEW, audience={"roles": ["patient"], "sex": None, "min_age": 50, "max_age": 40})
    assert client.post("/health-events", headers=adm, json=bad).status_code == 422


def test_moving_start_clears_announced(client, db):
    from datetime import UTC, datetime
    db.get(HealthEvent, "he-0005").announced_at = datetime.now(UTC)
    db.flush()
    adm = login(client, "admin@ward.tn")
    r = client.patch("/health-events/he-0005", headers=adm, json={"starts_on": "2026-11-13"})
    assert r.status_code == 200 and r.json()["announced_at"] is None


def test_notify_now(client, db, emitted):
    adm = login(client, "admin@ward.tn")
    r = client.post("/health-events/he-0001/notify", headers=adm)
    assert r.status_code == 200
    (event, data), = [e for e in emitted if e[0] == "health_event.upcoming"]
    assert data["event_id"] == "he-0001" and r.json() == {"recipients": data["recipient_count"]}
    assert any(p["first_name"] == "Amira" for p in data["recipients"])
    assert db.get(HealthEvent, "he-0001").announced_at is not None
    assert db.query(AuditLog).filter_by(action="notify", resource="health_event", resource_id="he-0001").count() == 1


import pytest  # noqa: E402


@pytest.mark.parametrize("field", ["title", "description", "category", "starts_on", "ends_on", "audience",
                                   "notify_days_before"])
def test_patch_null_on_required_field_422(client, db, field):
    adm = login(client, "admin@ward.tn")
    before = client.get("/health-events?from=2026-01-01&to=2027-12-31", headers=adm).json()
    r = client.patch("/health-events/he-0005", headers=adm, json={field: None})
    assert r.status_code == 422 and r.json()["code"] == "invalid"
    after = client.get("/health-events?from=2026-01-01&to=2027-12-31", headers=adm).json()
    assert after == before


def test_patch_null_organizer_ok(client):
    adm = login(client, "admin@ward.tn")
    r = client.patch("/health-events/he-0005", headers=adm, json={"organizer": None})
    assert r.status_code == 200 and r.json()["organizer"] is None
