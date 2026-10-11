from datetime import date

import pytest

from app.models import HealthEvent
from app.services import health_calendar as H
from tests.helpers import make_patient, make_user

EV = dict(
    title={"en": "Octobre Rose", "fr": "Octobre Rose", "ar": "أكتوبر الوردي"},
    description={"en": "", "fr": "", "ar": ""},
    category="screening",
)


def _ev(db, id_="he-9001", starts=date(2026, 10, 1), ends=date(2026, 10, 31), **aud):
    audience = {
        "roles": ["patient", "doctor", "nurse", "admin"],
        "sex": None,
        "min_age": None,
        "max_age": None,
    }
    audience.update(aud)
    ev = HealthEvent(id=id_, starts_on=starts, ends_on=ends, audience=audience, notify_days_before=3, **EV)
    db.add(ev)
    db.flush()
    return ev


def _patient_user(db, email, sex, dob):
    p = make_patient(db, first="Salma")
    p.sex, p.date_of_birth = sex, dob
    u = make_user(db, email, role="patient", name="Salma Test")
    u.patient_id = p.id
    db.flush()
    return u, p


def test_age_on_birthday_boundary():
    assert H.age_on(date(1986, 10, 2), date(2026, 10, 1)) == 39
    assert H.age_on(date(1986, 10, 1), date(2026, 10, 1)) == 40


def test_role_must_be_in_audience(db, seeded):
    ev = _ev(db, roles=["patient"])
    doctor = make_user(db, "d9@ward.tn", role="doctor")
    assert H.matches(doctor, None, ev) is False


def test_sex_and_age_apply_to_patients(db, seeded):
    ev = _ev(db, sex="F", min_age=40)
    woman, wp = _patient_user(db, "w@x.tn", "F", date(1980, 1, 1))
    young, yp = _patient_user(db, "y@x.tn", "F", date(1995, 1, 1))
    man, mp = _patient_user(db, "m@x.tn", "M", date(1960, 1, 1))
    assert H.matches(woman, wp, ev) and not H.matches(young, yp, ev) and not H.matches(man, mp, ev)


def test_staff_ignore_sex_and_age(db, seeded):
    ev = _ev(db, sex="F", min_age=40)
    nurse = make_user(db, "n9@ward.tn", role="nurse")
    assert H.matches(nurse, None, ev) is True


def test_unknown_sex_or_birth_date_does_not_match_limited_event(db, seeded):
    u1, p1 = _patient_user(db, "a@x.tn", None, date(1970, 1, 1))
    u2, p2 = _patient_user(db, "b@x.tn", "F", None)
    assert not H.matches(u1, p1, _ev(db, "he-9002", sex="F"))
    assert not H.matches(u2, p2, _ev(db, "he-9003", min_age=40))
    assert H.matches(u2, p2, _ev(db, "he-9004"))  # no limits: everyone with the role


def test_max_age(db, seeded):
    ev = _ev(db, sex="F", min_age=11, max_age=13, starts=date(2027, 4, 5), ends=date(2027, 4, 30))
    girl, gp = _patient_user(db, "g@x.tn", "F", date(2014, 6, 1))  # 12 on 2027-04-05
    teen, tp = _patient_user(db, "t@x.tn", "F", date(2012, 1, 1))  # 15
    assert H.matches(girl, gp, ev) and not H.matches(teen, tp, ev)


def test_prefs_default_and_opt_out(db, seeded):
    assert H.prefs(db, "u-0005") == {c: True for c in H.CATEGORIES}
    out = H.set_prefs(db, "u-0005", {"screening": False})
    assert out["screening"] is False and out["vaccination"] is True
    assert H.set_prefs(db, "u-0005", {"screening": True})["screening"] is True


def test_set_prefs_rejects_unknown_category_without_writing(db, seeded):
    with pytest.raises(ValueError):
        H.set_prefs(db, "u-0005", {"vaccination": False, "astrology": False})
    assert H.prefs(db, "u-0005")["vaccination"] is True


def test_recipients_match_follow_and_active(db, seeded):
    ev = _ev(db, roles=["patient", "nurse"], sex="F", min_age=40)
    # seed: u-0005 is Amira (F, 1972) → match; nurses u-0002/3/6/7 → match
    ids = {u.id for u, _ in H.recipients(db, ev)}
    assert "u-0005" in ids and "u-0002" in ids and "u-0001" not in ids  # doctor not in roles
    H.set_prefs(db, "u-0002", {"screening": False})
    make_user(db, "off@ward.tn", role="nurse", status="disabled")
    make_user(db, "pend@ward.tn", role=None, status="pending")
    ids = {u.email for u, _ in H.recipients(db, ev)}
    assert "nurse@ward.tn" not in ids and "off@ward.tn" not in ids and "pend@ward.tn" not in ids


def test_payload_first_names_only(db, seeded):
    ev = _ev(db, roles=["patient", "doctor"])
    p = H.upcoming_payload(db, ev, "http://web")
    assert p["event_id"] == "he-9001" and p["web_url"] == "http://web/calendar"
    assert p["recipient_count"] == len(p["recipients"])
    amira = next(r for r in p["recipients"] if r["role"] == "patient")
    assert amira["first_name"] == "Amira" and set(amira) == {"first_name", "role", "email", "lang"}
    doc = next(r for r in p["recipients"] if r["role"] == "doctor")
    assert doc["first_name"] == "Trabelsi"  # "Dr Trabelsi": title dropped


def test_due_window(db, seeded):
    ev = _ev(db, starts=date(2026, 10, 10), ends=date(2026, 10, 10))
    assert ev not in H.due(db, date(2026, 10, 6))  # 4 days before, notify 3
    assert ev in H.due(db, date(2026, 10, 7))
    assert ev in H.due(db, date(2026, 10, 10))
    assert ev not in H.due(db, date(2026, 10, 11))  # over
    from datetime import UTC, datetime

    ev.announced_at = datetime.now(UTC)
    assert ev not in H.due(db, date(2026, 10, 8))


def test_to_out_shape(db, seeded):
    ev = _ev(db)
    out = H.to_out(ev, matches_me=True, following=False)
    assert out["starts_on"] == "2026-10-01" and out["matches_me"] is True and out["following"] is False
    assert out["announced_at"] is None
