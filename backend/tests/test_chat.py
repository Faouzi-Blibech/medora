"""Role chat assistants: retrieval, answer checks, access and the doctor's report upload."""

import pytest

from app.ai import chat, rag
from tests.helpers import login

NOTE = rag.Source("note:n-1", "note", "Note by Nurse Ines · 08 Oct", "2026-10-08T20:40:00Z",
                  "Patient slept well. Troponin sample sent at 21:00. Fièvre à 38.2 la nuit.")
EXAM = rag.Source("result:er-1", "report", "Report: Chest X-ray", "2026-10-09T08:00:00Z",
                  "Chest X-ray: no consolidation, heart size normal.")
AR = rag.Source("note:n-2", "note", "Note", None, "المريضة تشكو من حمى خفيفة منذ الصباح.")


def llm(monkeypatch, answer: str, citations: list[int], found: bool = True):
    monkeypatch.setattr(chat, "get_settings", lambda: type("S", (), {"llm_provider": "groq"})())
    monkeypatch.setattr(chat, "complete_json",
                        lambda *a, **k: chat._LlmChat(answer=answer, citations=citations, found=found))


def test_passages_split_long_text():
    long = rag.Source("note:x", "note", "t", None, " ".join(f"Sentence number {i} is here." for i in range(300)))
    ps = rag.passages([long])
    assert len(ps) > 5 and all(len(p.text) <= rag.MAX_PASSAGE for p in ps)


def test_rank_finds_sources_and_folds_accents_and_arabic():
    ps = rag.passages([NOTE, EXAM, AR])
    assert rag.rank("what did the chest x-ray show?", ps)[0].source.id == "result:er-1"
    assert rag.rank("fievre", ps)[0].source.id == "note:n-1"
    assert rag.rank("حمى", ps)[0].source.id == "note:n-2"
    assert rag.rank("dialysis", ps) == []


def test_context_keeps_unmatched_passages_for_cross_language_questions():
    ctx = rag.context("ما هي نتيجة الأشعة؟", rag.passages([NOTE, EXAM]))
    assert {p.source.id for p in ctx} == {"note:n-1", "result:er-1"}


def test_without_llm_staff_get_matching_passages():
    out = chat.answer("doctor", "chest x-ray", [NOTE, EXAM], names=["Amira"])
    assert out["source"] == "rules" and out["citations"][0]["source_id"] == "result:er-1"


def test_patient_red_flag_never_reaches_the_llm(monkeypatch):
    llm(monkeypatch, "should not be used [1]", [1])
    out = chat.answer("patient", "I want to kill myself", [NOTE], names=["Amira"])
    assert out["urgent"] and out["answer"] == chat.assistant.CRISIS


def test_llm_answer_with_valid_citations_is_used(monkeypatch):
    llm(monkeypatch, "The chest X-ray shows no consolidation [1].", [1])
    out = chat.answer("doctor", "chest x-ray?", [NOTE, EXAM], names=["Amira"])
    assert out["source"] == "llm" and out["citations"][0]["source_id"] == "result:er-1"


@pytest.mark.parametrize("answer, cites", [
    ("No consolidation [9].", [9]),            # unknown passage
    ("No consolidation.", []),                 # cites nothing
])
def test_bad_llm_answers_fall_back_to_passages(monkeypatch, answer, cites):
    llm(monkeypatch, answer, cites)
    assert chat.answer("doctor", "chest x-ray", [NOTE, EXAM], names=["Amira"])["source"] == "rules"


def test_numbers_not_in_the_record_are_flagged_for_staff_and_blocked_for_patients(monkeypatch):
    llm(monkeypatch, "Temperature 39.5 overnight, consider COVID-19 [1].", [1])
    out = chat.answer("doctor", "fever?", [NOTE, EXAM], names=["Amira"])
    assert out["source"] == "llm" and out["unverified"] == ["39.5"]
    assert chat.answer("patient", "fever?", [NOTE], names=["Amira"])["source"] == "rules"


def test_llm_may_say_the_record_has_no_answer(monkeypatch):
    llm(monkeypatch, "The record has no dialysis information.", [], found=False)
    out = chat.answer("nurse", "dialysis schedule?", [NOTE, EXAM], names=["Amira"])
    assert out["source"] == "llm" and out["citations"] == []


def test_chat_api_roles_and_storage(client):
    doc = login(client, "doctor@medora.tn")
    r = client.post("/ai/chat", headers=doc, json={"patient_id": "p-0001", "question": "Summarise the stay"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"].startswith("nb-") and body["source"] == "rules"
    assert client.post("/ai/chat", headers=doc, json={"question": "hi"}).status_code == 422
    nurse = login(client, "nurse@medora.tn")
    assert client.post("/ai/chat", headers=nurse, json={"patient_id": "p-0001", "question": "meds due?"}).status_code == 200
    pat = login(client, "patient@medora.tn")
    r = client.post("/ai/chat", headers=pat, json={"question": "When is my next dose?"})
    assert r.status_code == 200 and r.json()["answer"]
    admin = login(client, "admin@medora.tn")
    assert client.post("/ai/chat", headers=admin, json={"patient_id": "p-0001", "question": "x"}).status_code == 403


def test_doctor_uploads_a_report_that_the_chat_reads(client, monkeypatch):
    from app.services import storage

    files = {}
    monkeypatch.setattr(storage, "put", lambda key, data, ct: files.__setitem__(key, data))
    doc = login(client, "doctor@medora.tn")
    r = client.post("/patients/p-0001/reports", headers=doc, data={"title": "Echo report"},
                    files={"file": ("echo.txt", b"Ejection fraction 35 percent, dilated left ventricle.", "text/plain")})
    assert r.status_code == 201, r.text
    out = client.post("/ai/chat", headers=doc, json={"patient_id": "p-0001", "question": "ejection fraction"}).json()
    assert any("Ejection fraction 35" in c["text"] for c in out["citations"])
    nurse = login(client, "nurse@medora.tn")
    assert client.post("/patients/p-0001/reports", headers=nurse,
                       files={"file": ("x.txt", b"x", "text/plain")}).status_code == 403


def test_conversations_mentions_history_and_ownership(client):
    doc = login(client, "doctor@medora.tn")
    c = client.post("/ai/conversations", headers=doc, json={}).json()
    assert c["id"].startswith("cv-") and c["messages"] == []
    r = client.post(f"/ai/conversations/{c['id']}/messages", headers=doc,
                    json={"question": "Summarise the stay", "patient_id": "p-0001"})
    assert r.status_code == 200, r.text
    assert r.json()["message"]["patient"]["id"] == "p-0001" and r.json()["conversation"]["title"]
    # the patient stays attached to the conversation until another is mentioned or it is cleared
    r = client.post(f"/ai/conversations/{c['id']}/messages", headers=doc, json={"question": "And the notes?"})
    assert r.json()["message"]["patient"]["id"] == "p-0001"
    r = client.post(f"/ai/conversations/{c['id']}/messages", headers=doc,
                    json={"question": "What is the usual dose of paracetamol?", "clear_patient": True})
    assert r.json()["message"]["patient"] is None and r.json()["message"]["source"] == "rules"
    full = client.get(f"/ai/conversations/{c['id']}", headers=doc).json()
    assert [m["role"] for m in full["messages"]] == ["user", "assistant"] * 3
    assert [x["id"] for x in client.get("/ai/conversations", headers=doc).json()][0] == c["id"]
    nurse = login(client, "nurse@medora.tn")
    assert client.get(f"/ai/conversations/{c['id']}", headers=nurse).status_code == 404
    assert client.post("/ai/conversations", headers=login(client, "patient@medora.tn"), json={}).status_code == 403
    assert client.delete(f"/ai/conversations/{c['id']}", headers=doc).status_code == 204
    assert client.get(f"/ai/conversations/{c['id']}", headers=doc).status_code == 404
