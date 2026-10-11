from app.models import Appointment
from tests.helpers import login

SLOT = "2026-10-20T09:00:00Z"
REQ = {"patient_id": "p-0001", "referral_text": "douleur thoracique depuis ce matin", "symptoms": ["chest pain"]}
HIDDEN = {"urgency_ai", "triage", "no_show_prob", "ai_suggested"}


def _confirm(client, h, appointment_id, slot=SLOT, **extra):
    return client.post(f"/appointments/{appointment_id}/confirm", headers=h,
                       json={"slot_at": slot, "doctor_id": "u-0001", **extra})


def test_patient_requests_own_appointment_and_sees_no_score(client):
    h = login(client, "patient@medora.tn")
    r = client.post("/appointments", headers=h, json=REQ)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"].startswith("a-") and body["status"] == "requested" and body["patient_id"] == "p-0001"
    assert not HIDDEN & set(body)
    assert client.post("/appointments", headers=h, json=dict(REQ, patient_id="p-0002")).status_code == 403
    mine = client.get("/appointments", headers=h).json()
    assert [a["id"] for a in mine] == [body["id"]] and not HIDDEN & set(mine[0])
    assert client.get("/appointments?patient_id=p-0002", headers=h).status_code == 403


def test_admin_request_runs_triage(client):
    r = client.post("/appointments", headers=login(client, "admin@medora.tn"), json=REQ)
    body = r.json()
    assert r.status_code == 201 and body["urgency_ai"] == 5 and "chest_pain" in body["triage"]["red_flags"]
    assert body["triage"]["source"] in ("model", "rules") and body["ai_suggested"]["urgency"] == 5
    assert body["patient_name"] == "Amira Ben Salah" and body["specialty"] == "Cardiology"
    assert client.post("/appointments", headers=login(client, "doctor@medora.tn"), json=REQ).status_code == 403


def test_waitlist_order_and_roles(client):
    rows = client.get("/appointments/waitlist", headers=login(client, "doctor@medora.tn")).json()
    assert len(rows) == 10 and all(r["status"] == "requested" for r in rows)
    keys = [(-(r["urgency_final"] or r["urgency_ai"]), r["created_at"]) for r in rows]
    assert keys == sorted(keys)
    assert client.get("/appointments/waitlist", headers=login(client, "nurse@medora.tn")).status_code == 403
    assert client.get("/appointments/waitlist", headers=login(client, "patient@medora.tn")).status_code == 403


def test_override_records_the_human(client):
    h = login(client, "admin@medora.tn")
    r = client.patch("/appointments/a-0004", headers=h, json={"urgency_final": 4})
    assert r.status_code == 200 and r.json()["urgency_final"] == 4
    assert r.json()["human_confirmed_by"] == "u-0004" and r.json()["human_confirmed_by_name"] == "Hela Mejri"
    assert client.patch("/appointments/a-0004", headers=h, json={"urgency_final": 7}).status_code == 422
    assert client.patch("/appointments/a-9999", headers=h, json={"urgency_final": 3}).status_code == 404


def test_confirm_emits_and_guards_the_slot(client, emitted):
    h = login(client, "admin@medora.tn")
    r = _confirm(client, h, "a-0001", urgency_final=5)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "confirmed" and body["confirmed_by"] == "u-0004" and body["doctor_name"] == "Dr Trabelsi"
    event, data = emitted[-1]
    assert event == "appointment.confirmed" and data["appointment_id"] == "a-0001" and data["slot_at"] == SLOT
    assert data["doctor_name"] == "Dr Trabelsi" and "last_name" not in data
    assert _confirm(client, h, "a-0001").json()["code"] == "not_waiting"
    taken = _confirm(client, h, "a-0002")
    assert taken.status_code == 409 and taken.json()["code"] == "slot_taken"
    bad = client.post("/appointments/a-0002/confirm", headers=h, json={"slot_at": SLOT, "doctor_id": "u-0002"})
    assert bad.status_code == 422
    assert _confirm(client, login(client, "patient@medora.tn"), "a-0002").status_code == 403


def test_cancel_frees_the_slot_for_the_best_candidate(client, db, emitted):
    h = login(client, "admin@medora.tn")
    _confirm(client, h, "a-0001")
    r = client.post("/appointments/a-0001/cancel", headers=h, json={"reason": "travel"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    event, data = emitted[-1]
    assert event == "appointment.cancelled" and data["slot_at"] == SLOT and data["doctor_id"] == "u-0001"
    top = client.get("/appointments/waitlist", headers=h).json()[0]
    assert data["candidate"]["appointment_id"] == top["id"]
    again = client.post("/appointments/a-0001/cancel", headers=h)
    assert again.status_code == 409 and again.json()["code"] == "not_cancellable"


def test_patient_reply_confirm_and_cancel(client, db, emitted):
    patient = login(client, "patient@medora.tn")
    a = client.post("/appointments", headers=patient, json=REQ).json()
    _confirm(client, login(client, "admin@medora.tn"), a["id"])
    r = client.post(f"/appointments/{a['id']}/reply", headers=patient, json={"reply": "confirm"})
    assert r.status_code == 200 and r.json()["patient_confirmed_at"]
    r = client.post(f"/appointments/{a['id']}/reply", headers=patient, json={"reply": "cancel"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and not HIDDEN & set(r.json())
    assert emitted[-1][0] == "appointment.cancelled"
    assert client.post("/appointments/a-0001/reply", headers=patient, json={"reply": "confirm"}).status_code == 403
    assert client.post("/appointments/a-0001/cancel", headers=patient).status_code == 403
    assert client.post(f"/appointments/{a['id']}/reply", headers=patient, json={"reply": "maybe"}).status_code == 422
    assert db.get(Appointment, "a-0001").status == "requested"
