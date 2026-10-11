from datetime import date

from app.models import HealthEvent, HealthEventPref


def test_event_roundtrip(db, seeded):
    ev = HealthEvent(id="he-9001", title={"en": "T", "fr": "T", "ar": "T"}, description={"en": "", "fr": "", "ar": ""},
                     category="screening", starts_on=date(2026, 10, 1), ends_on=date(2026, 10, 31),
                     audience={"roles": ["patient"], "sex": "F", "min_age": 40, "max_age": None})
    db.add(ev)
    db.flush()
    got = db.get(HealthEvent, "he-9001")
    assert got.notify_days_before == 3 and got.announced_at is None and got.audience["sex"] == "F"


def test_pref_roundtrip(db, seeded):
    db.add(HealthEventPref(user_id="u-0005", category="screening", following=False))
    db.flush()
    assert db.get(HealthEventPref, ("u-0005", "screening")).following is False
