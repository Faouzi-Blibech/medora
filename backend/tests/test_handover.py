from datetime import UTC, datetime, timedelta

from app.ai import handover as H
from app.ai.llm import LLMUnavailable
from app.models import Alert, AuditLog, Handover, MedDose, Note, Vital
from tests.helpers import login, make_patient, make_user

NOW = datetime(2026, 10, 11, 18, 0, tzinfo=UTC)
PATIENT = {"id": "p-0001", "first_name": "Amira", "last_name": "Ben Salah", "ward": "Cardiology", "bed": "C-12",
           "age": 54, "sex": "F", "reason": "Hypertension", "allergies": ["penicillin"], "admitted_at": NOW}


def _data(**over) -> dict:
    data = {"vitals": [{"ts": NOW - timedelta(hours=h), "hr": 80, "spo2": 97, "temp": 36.8, "news2": 0}
                       for h in (6, 4, 2)],
            "doses": [], "alerts": [], "notes": [], "meds": [{"med": "Amlodipine 5mg", "times": ["08:00"]}],
            "care_plans": ["Monitor blood pressure"], "exams": [], "now": NOW, "hours": 12}
    return {**data, **over}


def _codes(d: dict) -> list[str]:
    return [r["code"] for r in d["recommendations"]]


# --- rules (DB-free) ----------------------------------------------------------------------------------------------

def test_quiet_patient_gets_routine_recommendation():
    d = H.build(PATIENT, **_data())
    assert d["situation"]["bed"] == "C-12" and d["situation"]["latest_news2"] == 0
    assert d["situation"]["news2_trend"] == "stable" and d["background"]["allergies"] == ["penicillin"]
    assert d["assessment"]["vitals"]["count"] == 3 and d["assessment"]["vitals"]["hr"]["trend"] == "stable"
    assert _codes(d) == ["routine"]
    assert d["window"] == {"hours": 12, "from": "2026-10-11T06:00:00Z", "to": "2026-10-11T18:00:00Z"}


def test_rising_news2_and_high_score():
    vitals = [{"ts": NOW - timedelta(hours=h), "hr": hr, "spo2": 95, "temp": 37.5, "news2": n}
              for h, hr, n in ((6, 85, 1), (3, 105, 3), (1, 120, 5))]
    d = H.build(PATIENT, **_data(vitals=vitals))
    assert d["situation"]["news2_trend"] == "rising"
    assert _codes(d)[:2] == ["news2_high", "news2_rising"]
    assert d["recommendations"][1]["params"] == {"from": 1, "to": 5}
    assert d["assessment"]["vitals"]["hr"] == {"min": 85, "max": 120, "latest": 120, "trend": "rising"}


def test_missed_and_upcoming_doses():
    doses = [
        {"id": "d-1", "scheduled_at": NOW - timedelta(hours=10), "meds": ["Amlodipine 5mg"], "status": "taken"},
        {"id": "d-2", "scheduled_at": NOW - timedelta(hours=4), "meds": ["Paracetamol 500mg"], "status": "missed"},
        {"id": "d-3", "scheduled_at": NOW - timedelta(hours=2), "meds": ["Aspirin"], "status": "scheduled"},  # overdue
        {"id": "d-4", "scheduled_at": NOW - timedelta(minutes=20), "meds": ["X"], "status": "scheduled"},  # not yet
        {"id": "d-5", "scheduled_at": NOW + timedelta(hours=2), "meds": ["Paracetamol 500mg"], "status": "scheduled"},
    ]
    d = H.build(PATIENT, **_data(doses=doses))
    assert d["assessment"]["doses"]["given"] == 1
    assert [m["id"] for m in d["assessment"]["doses"]["missed"]] == ["d-2", "d-3"]
    assert _codes(d) == ["missed_dose", "missed_dose", "next_dose"]
    assert d["recommendations"][0]["params"] == {"time": "15:00", "meds": "Paracetamol 500mg"}  # Tunis time
    assert d["recommendations"][2]["params"]["time"] == "21:00"


def test_open_alerts_notes_exams_and_no_vitals():
    alerts = [{"id": "al-1", "kind": "trend", "severity": "medium", "message": "HR trend", "created_at": NOW
               - timedelta(hours=30), "acked_at": None},
              {"id": "al-2", "kind": "news2", "severity": "high", "message": "NEWS2 6", "created_at": NOW
               - timedelta(hours=2), "acked_at": NOW - timedelta(hours=1)}]
    notes = [{"text": "Slept well", "author_name": "Nurse Ines", "created_at": NOW - timedelta(hours=3)}]
    d = H.build(PATIENT, **_data(vitals=[], alerts=alerts, notes=notes, exams=[{"label": "ECG"}]))
    a = d["assessment"]
    assert a["alerts"]["raised"] == 1 and a["alerts"]["acked"] == 1 and [x["id"] for x in a["alerts"]["open"]] == ["al-1"]
    assert a["notes"][0]["text"] == "Slept well" and a["notes_count"] == 1
    assert _codes(d) == ["open_alert", "no_vitals", "pending_exam"]
    text = H.narrative(d)
    assert text.startswith("S: Bed C-12, Cardiology. Reason: Hypertension.") and '"Slept well"' in text
    assert "Exam pending: ECG." in text and "\nR: " in text


def test_llm_rewrite_kept_only_without_new_numbers(monkeypatch):
    monkeypatch.setattr(H, "get_settings", lambda: type("S", (), {"llm_provider": "groq"})())
    H._cache.clear()
    calls = []

    def fake(name, text, schema, names):
        calls.append((name, text, names))
        return schema(narrative="Bed C-12, NEWS2 0, stable. Continue the plan.")

    monkeypatch.setattr(H, "complete_json", fake)
    d = H.draft(PATIENT, names=["Amira", "Ben Salah"], lang="fr", **_data())
    assert d["source"] == "llm" and d["narrative"].startswith("Bed C-12") and calls[0][0] == "handover"
    assert "French" in calls[0][1] and calls[0][2] == ["Amira", "Ben Salah"]
    H._cache.clear()
    monkeypatch.setattr(H, "complete_json", lambda *a, **k: H._LlmNarrative(narrative="NEWS2 9, call 15."))
    assert H.draft(PATIENT, names=[], **_data())["source"] == "rules"

    def down(*a, **k):
        raise LLMUnavailable("offline")

    H._cache.clear()
    monkeypatch.setattr(H, "complete_json", down)
    d = H.draft(PATIENT, names=[], **_data())
    assert d["source"] == "rules" and d["narrative"].startswith("S: ")


def test_window_hours():
    assert [H.window_hours(h) for h in (8, 12, 24, 5, None)] == [8, 12, 24, 12, 12]


# --- API --------------------------------------------------------------------------------------------------------

def test_nurse_gets_her_ward_drafts_audited(client, db):
    h = login(client, "nurse@ward.tn")
    r = client.get("/handover?hours=12", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window_hours"] == 12 and body["generated_at"].endswith("Z")
    ids = [i["patient"]["id"] for i in body["items"]]
    assert ids == ["p-0001"]  # the seed admits only p-0001; the other Cardiology patients are quiet
    item = body["items"][0]
    assert item["source"] == "rules" and item["confirmation"] is None and item["narrative"].startswith("S: Bed C-12")
    assert item["situation"]["bed"] == "C-12" and item["situation"]["latest_news2"] == 0
    assert item["background"]["allergies"] == ["penicillin"] and item["assessment"]["vitals"]["count"] >= 40
    assert {m["med"] for m in item["background"]["meds"]} == {"Amlodipine 5mg", "Paracetamol 500mg"}
    assert db.query(AuditLog).filter_by(resource="handover", patient_id="p-0001", action="read").count() == 1


def test_handover_flags_missed_dose_and_rising_news2(client, db):
    now = datetime.now(UTC)
    db.add(MedDose(id="d-900001", prescription_id="rx-0001", patient_id="p-0001", scheduled_at=now - timedelta(hours=3),
                   time_of_day="00:00", meds=["Amlodipine 5mg"], status="missed"))
    for k, n in enumerate((1, 3, 5)):
        db.add(Vital(ts=now - timedelta(minutes=30 - 10 * k), device_id="bsu-001", patient_id="p-0001",
                     hr=100 + 10 * k, spo2=94, temp=37.8, news2=n, source="manual"))
    db.add(Note(id="n-9001", patient_id="p-0001", author_id="u-0002", text="Patient feels dizzy"))
    db.flush()
    item = client.get("/handover", headers=login(client, "nurse@ward.tn")).json()["items"][0]
    codes = [r["code"] for r in item["recommendations"]]
    assert "missed_dose" in codes and "news2_rising" in codes and "news2_high" in codes
    assert item["assessment"]["notes"][-1] == {"text": "Patient feels dizzy", "author_name": "Nurse Ines",
                                               "created_at": item["assessment"]["notes"][-1]["created_at"]}


def test_nurse_scoping_and_roles(client, db):
    p = make_patient(db, ward="Internal Medicine", first="Rim", last="Test")
    db.add(Alert(id="al-9001", patient_id=p.id, kind="news2", severity="high", news2=6, message="NEWS2 6"))
    db.flush()
    ids = [i["patient"]["id"] for i in client.get("/handover", headers=login(client, "nurse@ward.tn")).json()["items"]]
    assert p.id not in ids
    other = [i["patient"]["id"] for i in client.get("/handover", headers=login(client, "nurse2@ward.tn")).json()["items"]]
    assert p.id in other and "p-0001" not in other  # an open alert puts a non-admitted patient on the list
    assert client.get("/handover?ward=Internal%20Medicine", headers=login(client, "nurse@ward.tn")).status_code == 403
    for email in ("patient@ward.tn", "admin@ward.tn"):
        assert client.get("/handover", headers=login(client, email)).status_code == 403
    doc = client.get("/handover", headers=login(client, "doctor@ward.tn"))
    assert doc.status_code == 200 and [i["patient"]["id"] for i in doc.json()["items"]] == ["p-0001"]


def test_confirm_stores_who_and_when(client, db):
    h = login(client, "nurse@ward.tn")
    r = client.post("/handover/p-0001/confirm", headers=h, json={"hours": 8})
    assert r.status_code == 200, r.text
    c = r.json()["confirmation"]
    assert c["human_confirmed_by"] == "u-0002" and c["human_confirmed_by_name"] == "Nurse Ines"
    assert c["confirmed_at"].endswith("Z") and c["window_hours"] == 8 and c["source"] == "rules"
    row = db.query(Handover).filter_by(patient_id="p-0001").one()
    assert row.ai_suggested["source"] == "rules" and row.ai_suggested["window"]["hours"] == 8
    assert row.human_confirmed_by == "u-0002" and row.ward == "Cardiology"
    listed = client.get("/handover?hours=8", headers=h).json()["items"][0]
    assert listed["confirmation"]["id"] == row.id
    assert db.query(AuditLog).filter_by(resource="handover", action="update", patient_id="p-0001").count() == 1


def test_confirm_access(client, db):
    assert client.post("/handover/p-0007/confirm", headers=login(client, "nurse@ward.tn")).status_code == 403
    assert client.post("/handover/p-9999/confirm", headers=login(client, "nurse@ward.tn")).status_code == 404
    for email in ("doctor@ward.tn", "patient@ward.tn", "admin@ward.tn"):
        assert client.post("/handover/p-0001/confirm", headers=login(client, email)).status_code == 403
    make_user(db, "team@ward.tn", role="nurse", supervisor_id="u-0001")  # a doctor's team nurse, no ward
    assert client.post("/handover/p-0001/confirm", headers=login(client, "team@ward.tn")).status_code == 200
