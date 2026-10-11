"""Patient assistant: answers from the caller's own record only, never diagnoses."""

from datetime import UTC, datetime
from types import SimpleNamespace as NS

import pytest

from app.ai import assistant as A

NOW = datetime(2026, 10, 8, 10, 30, tzinfo=UTC)  # 11:30 in Tunis


def ctx():
    patient = NS(first_name="Amira", last_name="Ben Salah")
    doses = [NS(time_of_day="08:00", meds=["Paracetamol 500mg"], status="taken"),
             NS(time_of_day="14:00", meds=["Amoxicillin 1g"], status="scheduled"),
             NS(time_of_day="20:00", meds=["Paracetamol 500mg"], status="scheduled")]
    visit = NS(slot_at=datetime(2026, 10, 12, 9, 0, tzinfo=UTC), status="confirmed")
    vital = NS(hr=82, spo2=97, temp=37.1, ts=datetime(2026, 10, 8, 10, 0, tzinfo=UTC))
    return A.assistant_context(patient, doses, visit, vital, now=NOW)


def force(monkeypatch, intent, conf=0.9, source="model"):
    monkeypatch.setattr(A, "classify_intent", lambda q: (intent, conf, source))


def test_context_picks_next_scheduled_dose_and_formats_tunis_time():
    c = ctx()
    assert c["next_dose"] == {"time": "14:00", "meds": ["Amoxicillin 1g"]}
    assert c["next_visit"] == "Monday 12 Oct at 10:00"
    assert c["latest_vitals"] == {"hr": 82, "spo2": 97, "temp": 37.1, "at": "11:00"}
    assert c["names"] == ["Amira", "Ben Salah"]


def test_red_flag_question_goes_to_staff_without_model(monkeypatch):
    def must_not_call(*a, **k):
        raise AssertionError("classifier must not be called for a red-flag question")
    monkeypatch.setattr(A, "classify_intent", must_not_call)
    out = A.answer("J'ai une douleur thoracique depuis 10 minutes", ctx())
    assert out["answer"] == A.URGENT and out["sources"] == ["safety_rules"]
    assert out["intent"] == "urgent" and out["source"] == "rules"


def test_urgent_intent(monkeypatch):
    force(monkeypatch, "urgent")
    out = A.answer("something", ctx())
    assert out["answer"] == A.URGENT and out["intent"] == "urgent" and out["source"] == "model"
    assert out["sources"] == ["safety_rules"]


def test_next_dose_intent(monkeypatch):
    force(monkeypatch, "next_dose")
    out = A.answer("x", ctx())
    assert "14:00" in out["answer"] and "Amoxicillin 1g" in out["answer"] and out["sources"] == ["med_doses"]
    assert out["intent"] == "next_dose"


def test_next_visit_intent(monkeypatch):
    force(monkeypatch, "next_visit")
    out = A.answer("x", ctx())
    assert "Monday 12 Oct at 10:00" in out["answer"] and out["sources"] == ["appointments"]


def test_my_vitals_intent(monkeypatch):
    force(monkeypatch, "my_vitals")
    out = A.answer("x", ctx())
    assert out["answer"] == ("Your latest readings (at 11:00): heart rate 82 bpm, oxygen 97%, "
                             "temperature 37.1 °C.")
    assert out["sources"] == ["vitals"]


def test_my_vitals_skips_missing_value(monkeypatch):
    force(monkeypatch, "my_vitals")
    c = ctx()
    c["latest_vitals"]["spo2"] = None
    out = A.answer("x", c)
    assert "oxygen" not in out["answer"] and "heart rate 82 bpm, temperature 37.1" in out["answer"]


def test_my_vitals_none_yet(monkeypatch):
    force(monkeypatch, "my_vitals")
    c = ctx()
    c["latest_vitals"] = None
    assert A.answer("x", c)["answer"] == "No readings yet today."


def test_ask_staff_intent(monkeypatch):
    force(monkeypatch, "ask_staff")
    out = A.answer("x", ctx())
    assert out["answer"] == A.ASK_STAFF and out["sources"] == [] and out["intent"] == "ask_staff"


@pytest.fixture()
def no_models(monkeypatch):
    monkeypatch.setattr(A.textclf, "load", lambda name: None)


@pytest.mark.parametrize("q,intent", [
    ("When is my next dose?", "next_dose"), ("C'est quand mon prochain médicament ?", "next_dose"),
    ("وقتاش الدواء الجاي", "next_dose"), ("mon prochain rendez-vous", "next_visit"),
    ("وقتاش الموعد", "next_visit"), ("quelle est ma température", "my_vitals"),
    ("شنو نبض متاعي", "my_vitals"), ("Is my illness serious?", "ask_staff")])
def test_keyword_path_with_no_models(no_models, q, intent):
    assert A.classify_intent(q) == (intent, 1.0, "rules")
    assert A.answer(q, ctx())["source"] == "rules"


def test_low_confidence_becomes_ask_staff(monkeypatch):
    monkeypatch.setattr(A.textclf, "load", lambda name: {})
    monkeypatch.setattr(A.textclf, "predict_proba",
                        lambda m, t: {"next_dose": 0.3, "next_visit": 0.25, "ask_staff": 0.25,
                                      "urgent": 0.1, "my_vitals": 0.1})
    assert A.classify_intent("whatever") == ("ask_staff", 0.3, "model")


def test_context_without_data():
    c = A.assistant_context(NS(first_name="X", last_name="Y"), [], None, None, now=NOW)
    assert c["next_dose"] is None and c["next_visit"] is None and c["latest_vitals"] is None


@pytest.mark.parametrize("question,intent", [
    ("What is my blood oxygen level today?", "my_vitals"),
    ("Do I have any more tablets to take this evening?", "next_dose"),
    ("Can I go on holiday after my operation?", "ask_staff"),
])
def test_shipped_intent_model_classifies_unseen_questions(question, intent):
    got, _conf, _source = A.classify_intent(question)  # one-topic questions are answered by keyword rules
    assert got == intent


@pytest.mark.parametrize("question", [
    "Please come quickly, I need a nurse now", "I'm going to faint", "I fell and I can't get up", "help!",
    "j'ai besoin d'une infirmière tout de suite", "au secours", "je vais m'évanouir", "je suis tombé dans la salle de bain",
    "الحقوني", "أريد ممرضة الآن", "سقطت وما نقدرش نوقف", "nheb infirmiere fisa3", "bech nghmi",
])
def test_patient_side_urgency_wording_is_urgent(no_models, question):
    assert A.classify_intent(question) == ("urgent", 1.0, "rules")
    out = A.answer(question, ctx())
    assert out["intent"] == "urgent" and out["answer"] in (A.URGENT, A.CRISIS)


@pytest.mark.parametrize("question", [
    "When is the doctor coming today?", "Can I have my medicine now?", "what time is my pill", "quand est mon rendez-vous",
    "doctor jey wa9tech tawa", "is parking free", "What did the doctor say about my results?",
])
def test_ordinary_questions_are_not_urgent(no_models, question):
    assert A.classify_intent(question)[0] != "urgent"
