from app.ai import assistant as A
from app.models import AiSummary, AuditLog
from tests.helpers import login


def test_triage_preview_stores_nothing(client, db):
    h = login(client, "doctor@medora.tn")
    before = db.query(AuditLog).count()
    r = client.post("/ai/triage", headers=h, json={"referral_text": "douleur thoracique", "symptoms": [], "age": 50})
    body = r.json()
    assert r.status_code == 200 and body["urgency"] == 5 and "chest_pain" in body["red_flags"]
    assert body["source"] in ("model", "rules") and {"reasons", "model_urgency", "confidence"} <= set(body)
    assert db.query(AuditLog).count() == before
    assert client.post("/ai/triage", headers=login(client, "patient@medora.tn"),
                       json={"referral_text": "x"}).status_code == 403
    assert client.post("/ai/triage", headers=h, json={"referral_text": ""}).status_code == 422


def test_summary_is_cached_and_audited(client, db):
    h = login(client, "doctor@medora.tn")
    r = client.get("/ai/summary/p-0001", headers=h)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["source"] == "rules" and s["summary"].startswith("Last 24h:") and s["human_confirmed_by"] is None
    assert s["based_on"]["vitals"] > 0 and s["based_on"]["notes"] == 0 and s["generated_at"].endswith("Z")
    assert {"interactions", "human_confirmed_by_name", "reviewed_at"} <= set(s)
    client.get("/ai/summary/p-0001", headers=h)
    assert db.query(AiSummary).filter_by(patient_id="p-0001").count() == 1
    assert db.query(AuditLog).filter_by(resource="ai_summary", patient_id="p-0001").count() == 2


def test_summary_review_and_undo(client):
    h = login(client, "doctor@medora.tn")
    assert client.post("/ai/summary/p-0001/review", headers=h).status_code == 404  # nothing generated yet
    client.get("/ai/summary/p-0001", headers=h)
    r = client.post("/ai/summary/p-0001/review", headers=h).json()
    assert r["human_confirmed_by"] == "u-0001" and r["human_confirmed_by_name"] == "Dr Trabelsi" and r["reviewed_at"]
    assert client.get("/ai/summary/p-0001", headers=h).json()["human_confirmed_by"] == "u-0001"
    u = client.delete("/ai/summary/p-0001/review", headers=h).json()
    assert u["human_confirmed_by"] is None and u["reviewed_at"] is None


def test_summary_access(client):
    h = login(client, "doctor@medora.tn")
    assert client.get("/ai/summary/p-0007", headers=h).status_code == 403
    for email in ("nurse@medora.tn", "admin@medora.tn", "patient@medora.tn"):
        assert client.get("/ai/summary/p-0001", headers=login(client, email)).status_code == 403
    assert client.get("/ai/summary/p-9999", headers=h).status_code == 404


def test_assistant_answers_from_own_record(client, db, monkeypatch):
    h = login(client, "patient@medora.tn")
    monkeypatch.setattr(A, "classify_intent", lambda q: ("my_vitals", 0.9, "model"))
    r = client.post("/ai/assistant", headers=h, json={"question": "what is my temperature?"})
    body = r.json()
    assert r.status_code == 200 and body["intent"] == "my_vitals" and body["source"] == "model"
    assert body["answer"].startswith("Your latest readings") and body["sources"] == ["vitals"]
    assert db.query(AuditLog).filter_by(resource="assistant", patient_id="p-0001").count() == 1
    monkeypatch.setattr(A, "classify_intent", lambda q: ("next_visit", 0.9, "model"))
    assert "no confirmed appointment" in client.post("/ai/assistant", headers=h, json={"question": "rdv?"}).json()["answer"]


def test_assistant_red_flag_and_roles(client):
    h = login(client, "patient@medora.tn")
    r = client.post("/ai/assistant", headers=h, json={"question": "j'ai une douleur thoracique"}).json()
    assert r["intent"] == "urgent" and r["answer"] == A.URGENT and "button" not in r["answer"]
    assert client.post("/ai/assistant", headers=login(client, "doctor@medora.tn"),
                       json={"question": "x"}).status_code == 403
