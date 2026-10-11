"""Business rules for appointments independent of the DB.

Fakes carry the exact attribute names of docs/contracts/data-model.md, so Wali's ORM rows drop in at link time.
"""

from datetime import UTC, date, datetime
from types import SimpleNamespace as NS

import pytest

from app.services import appointments as S

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)


def patient(pid="p-0003", first="Sami", last="Gharbi", **kw):
    base = dict(id=pid, first_name=first, last_name=last, date_of_birth=date(1970, 1, 1), sex="M",
                email="sami@example.tn", telegram_chat_id="555", history="")
    base.update(kw)
    return NS(**base)


def appt(aid, urgency_ai=3, urgency_final=None, created=NOW, status="requested", **kw):
    base = dict(id=aid, patient_id="p-0003", status=status, urgency_ai=urgency_ai, urgency_final=urgency_final,
                created_at=created, slot_at=None, doctor_id=None, confirmed_by=None, human_confirmed_by=None,
                patient_confirmed_at=None, no_show_prob=0.2, ai_suggested={}, referral_text="", symptoms=[])
    base.update(kw)
    return NS(**base)


def test_request_runs_triage_with_red_flag():
    f = S.new_appointment_fields(patient(), "douleur thoracique depuis hier", [], today=NOW.date())
    assert f["status"] == "requested" and f["urgency_ai"] == 5
    assert f["ai_suggested"]["source"] == "model" and "chest_pain" in f["ai_suggested"]["red_flags"]
    assert 0.0 <= f["no_show_prob"] <= 1.0


def test_waitlist_uses_final_over_ai_then_oldest():
    a = appt("a-1", urgency_ai=5, created=datetime(2026, 10, 3, tzinfo=UTC))
    b = appt("a-2", urgency_ai=2, urgency_final=5, created=datetime(2026, 10, 1, tzinfo=UTC))
    c = appt("a-3", urgency_ai=4)
    d = appt("a-4", urgency_ai=5, status="confirmed")
    assert [x.id for x in S.waitlist([a, b, c, d])] == ["a-2", "a-1", "a-3"]


def test_override_sets_final_and_confirmer():
    a = appt("a-1", urgency_ai=2)
    S.apply_override(a, 5, user_id="u-0004")
    assert a.urgency_final == 5 and a.human_confirmed_by == "u-0004"


@pytest.mark.parametrize("bad", [0, 6])
def test_override_rejects_out_of_range(bad):
    with pytest.raises(ValueError):
        S.apply_override(appt("a-1"), bad, user_id="u-0004")


def test_confirm_sets_booking_fields():
    a = appt("a-1")
    slot = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    S.apply_confirm(a, slot_at=slot, doctor_id="u-0001", user_id="u-0004", urgency_final=4)
    assert (a.status, a.slot_at, a.doctor_id, a.confirmed_by, a.human_confirmed_by, a.urgency_final) == \
        ("confirmed", slot, "u-0001", "u-0004", "u-0004", 4)


def test_confirm_twice_conflicts():
    a = appt("a-1", status="confirmed")
    with pytest.raises(S.Conflict) as e:
        S.apply_confirm(a, slot_at=NOW, doctor_id="u-0001", user_id="u-0004")
    assert e.value.code == "not_waiting"


def test_reply_confirm_and_cancel():
    a = appt("a-1", status="confirmed")
    assert S.apply_reply(a, "confirm", now=NOW) == "confirmed" and a.patient_confirmed_at == NOW
    b = appt("a-2", status="confirmed")
    assert S.apply_reply(b, "cancel", now=NOW) == "cancelled" and b.status == "cancelled"
    with pytest.raises(ValueError):
        S.apply_reply(appt("a-3"), "maybe", now=NOW)


def test_confirmed_event_shape():
    a = appt("a-1", status="confirmed", slot_at=datetime(2026, 10, 12, 9, 0, tzinfo=UTC))
    ev = S.confirmed_event(a, patient(), doctor_name="Dr Trabelsi")
    assert ev == {"appointment_id": "a-1", "patient_first_name": "Sami", "patient_telegram_chat_id": "555",
                  "patient_email": "sami@example.tn", "slot_at": "2026-10-12T09:00:00Z", "doctor_name": "Dr Trabelsi"}


def test_cancelled_event_offers_best_waiting_candidate():
    freed = appt("a-1", status="cancelled", slot_at=datetime(2026, 10, 12, 9, 0, tzinfo=UTC), doctor_id="u-0001")
    waiting = [
        (appt("a-5", urgency_ai=3, no_show_prob=0.1), patient("p-0005", "Lina", "B")),
        (appt("a-6", urgency_ai=5, no_show_prob=0.4), patient("p-0006", "Omar", "C", telegram_chat_id=None)),
        (appt("a-7", urgency_ai=5, no_show_prob=0.2), patient("p-0007", "Rim", "D")),
    ]
    ev = S.cancelled_event(freed, doctor_name="Dr Trabelsi", waiting=waiting)
    assert ev["appointment_id"] == "a-1" and ev["slot_at"] == "2026-10-12T09:00:00Z" and ev["doctor_id"] == "u-0001"
    assert ev["candidate"] == {"appointment_id": "a-7", "patient_first_name": "Rim",
                               "patient_telegram_chat_id": "555", "patient_email": "sami@example.tn"}


def test_cancelled_event_without_slot_or_waiting_has_no_candidate():
    no_slot = appt("a-1", status="cancelled")
    assert S.cancelled_event(no_slot, doctor_name=None, waiting=[(appt("a-5"), patient())])["candidate"] is None
    freed = appt("a-2", status="cancelled", slot_at=NOW)
    assert S.cancelled_event(freed, doctor_name=None, waiting=[])["candidate"] is None


def test_backfill_accept_rules():
    slot = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    a = appt("a-7")
    assert S.apply_backfill_accept(a, slot_at=slot, doctor_id="u-0001", slot_taken=False) == "confirmed"
    assert a.status == "confirmed" and a.slot_at == slot and a.confirmed_by is None
    with pytest.raises(S.Conflict) as e:
        S.apply_backfill_accept(appt("a-8"), slot_at=slot, doctor_id="u-0001", slot_taken=True)
    assert e.value.code == "slot_taken"
    with pytest.raises(S.Conflict) as e:
        S.apply_backfill_accept(appt("a-9", status="cancelled"), slot_at=slot, doctor_id="u-0001", slot_taken=False)
    assert e.value.code == "not_waiting"


def test_follow_up_fields_go_through_triage():
    f = S.follow_up_fields(patient(), days=14, today=NOW.date())
    assert f["status"] == "requested" and f["referral_text"] == "Post-discharge follow-up in 14 days"
    assert 1 <= f["urgency_ai"] <= 5 and f["ai_suggested"]["source"] == "model"
