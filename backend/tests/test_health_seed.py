from app.health_seed import EVENTS, seed_health_events
from app.models import HealthEvent
from app.services.health_calendar import CATEGORIES, ROLES


def test_seed_shape():
    assert [e["id"] for e in EVENTS] == [f"he-{n:04d}" for n in range(1, 18)]
    for e in EVENTS:
        assert e["category"] in CATEGORIES and e["ends_on"] >= e["starts_on"]
        assert set(e["audience"]["roles"]) <= set(ROLES) and e["audience"]["roles"]
        for f in ("title", "description"):
            assert set(e[f]) == {"en", "fr", "ar"} and all(e[f][k].strip() for k in ("en", "fr", "ar"))


def test_seed_is_idempotent_and_keeps_edits(db, seeded):
    assert db.query(HealthEvent).count() == 17  # seed() already ran it
    ev = db.get(HealthEvent, "he-0001")
    ev.organizer = "Edited"
    db.flush()
    assert seed_health_events(db) == 0
    assert db.get(HealthEvent, "he-0001").organizer == "Edited"
    db.delete(db.get(HealthEvent, "he-0002"))
    db.flush()
    assert seed_health_events(db) == 1
