"""Object-level access control: appointments, exams (status vs results) and bedside-unit commands.

Product rule: a doctor sees a patient who is not theirs only through a pending ("requested") appointment, and only
that request's data (referral, triage, exam status). Exam results go to the ordering doctor, the attending doctor
and the appointment's booked doctor. Every read or write is audited."""

from datetime import UTC, datetime

import pytest

from app.auth.security import hash_password
from app.models import AuditLog, Device, MedDose, Prescription, Staff, User
from tests.helpers import login

CHEST = {"patient_id": "p-0001", "referral_text": "douleur thoracique depuis ce matin", "symptoms": ["chest pain"]}
PDF = ("ecg.pdf", b"%PDF-1.4 fake", "application/pdf")
SLOT = "2026-10-20T09:00:00Z"


@pytest.fixture()
def stored(monkeypatch):
    from app.services import storage

    files: dict[str, tuple[bytes, str]] = {}
    monkeypatch.setattr(storage, "put", lambda key, data, ct: files.__setitem__(key, (data, ct)))
    monkeypatch.setattr(storage, "get", lambda key: files[key][0])
    return files


@pytest.fixture()
def doc_b(client, db):
    """A second cardiology doctor who is NOT p-0001's attending doctor (u-0001 is)."""
    from app.config import get_settings

    db.add(User(id="u-0990", email="doctorb-acl@medora.tn", name="Dr Bouzid", role="doctor",
                password_hash=hash_password(get_settings().seed_password)))
    db.flush()
    db.add(Staff(user_id="u-0990", ward="Cardiology"))
    db.flush()
    r = client.post("/auth/login", json={"email": "doctorb-acl@medora.tn", "password": get_settings().seed_password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def doc_a(client):
    return login(client, "doctor@medora.tn")


@pytest.fixture()
def admin(client):
    return login(client, "admin@medora.tn")


def _request(client, admin, **over) -> dict:
    r = client.post("/appointments", headers=admin, json=dict(CHEST, **over))
    assert r.status_code == 201, r.text
    return r.json()


def _confirmed(client, admin) -> dict:
    """A confirmed (no longer pending) appointment for A's patient p-0001, booked with A."""
    a = _request(client, admin)
    r = client.post(f"/appointments/{a['id']}/confirm", headers=admin, json={"slot_at": SLOT, "doctor_id": "u-0001"})
    assert r.status_code == 200, r.text
    return r.json()


def _audits(db, **kw) -> int:
    return db.query(AuditLog).filter_by(**kw).count()


# -- 1. GET /appointments ------------------------------------------------------------------------------------------

def test_doctor_b_list_hides_confirmed_but_shows_requested(client, admin, doc_a, doc_b):
    confirmed = _confirmed(client, admin)
    pending = _request(client, admin, patient_id="p-0007")  # not A's patient either
    ids_b = {a["id"] for a in client.get("/appointments", headers=doc_b).json()}
    assert confirmed["id"] not in ids_b and pending["id"] in ids_b
    ids_a = {a["id"] for a in client.get("/appointments", headers=doc_a).json()}
    assert confirmed["id"] in ids_a and pending["id"] in ids_a


def test_doctor_b_list_by_patient_still_filtered(client, admin, doc_b):
    confirmed = _confirmed(client, admin)
    rows = client.get("/appointments?patient_id=p-0001", headers=doc_b).json()
    assert confirmed["id"] not in {a["id"] for a in rows}
    assert all(a["status"] == "requested" for a in rows)


def test_booked_doctor_sees_their_confirmed_appointment(client, admin, db, doc_b):
    a = _request(client, admin, patient_id="p-0007")  # not attending: nobody owns p-0007
    r = client.post(f"/appointments/{a['id']}/confirm", headers=admin, json={"slot_at": SLOT, "doctor_id": "u-0990"})
    assert r.status_code == 200
    assert a["id"] in {x["id"] for x in client.get("/appointments", headers=doc_b).json()}
    assert a["id"] not in {x["id"] for x in client.get("/appointments", headers=login(client, "doctor@medora.tn")).json()}


def test_admin_list_unchanged(client, admin):
    confirmed = _confirmed(client, admin)
    assert confirmed["id"] in {a["id"] for a in client.get("/appointments", headers=admin).json()}


# -- 2/3/4. appointment writes ---------------------------------------------------------------------------------------

def test_doctor_b_cannot_override_confirm_or_order_a_non_requested_appointment(client, admin, doc_b):
    a = _confirmed(client, admin)
    assert client.patch(f"/appointments/{a['id']}", headers=doc_b, json={"urgency_final": 1}).status_code == 403
    assert client.post(f"/appointments/{a['id']}/confirm", headers=doc_b,
                       json={"slot_at": "2026-10-21T09:00:00Z", "doctor_id": "u-0990"}).status_code == 403
    assert client.post(f"/appointments/{a['id']}/exams/order", headers=doc_b, json={"exam_ids": []}).status_code == 403
    assert client.post("/exams", headers=doc_b,
                       json={"patient_id": "p-0001", "appointment_id": a["id"], "code": "echo"}).status_code == 403
    assert client.get(f"/appointments/{a['id']}/exams", headers=doc_b).status_code == 403


def test_doctor_b_can_act_on_a_requested_appointment(client, admin, doc_b):
    a = _request(client, admin)
    assert client.patch(f"/appointments/{a['id']}", headers=doc_b, json={"urgency_final": 4}).status_code == 200
    exams = client.get(f"/appointments/{a['id']}/exams", headers=doc_b).json()
    assert exams and all(e["status"] == "suggested" for e in exams)
    r = client.post(f"/appointments/{a['id']}/exams/order", headers=doc_b, json={"exam_ids": [exams[0]["id"]]})
    assert r.status_code == 200
    assert client.post("/exams", headers=doc_b,
                       json={"patient_id": "p-0001", "appointment_id": a["id"], "code": "echo"}).status_code == 201
    r = client.post(f"/appointments/{a['id']}/confirm", headers=doc_b, json={"slot_at": SLOT, "doctor_id": "u-0990"})
    assert r.status_code == 200


def test_add_exam_without_appointment_still_needs_attending(client, doc_a, doc_b):
    body = {"patient_id": "p-0001", "code": "echo"}
    assert client.post("/exams", headers=doc_b, json=body).status_code == 403
    assert client.post("/exams", headers=doc_a, json=body).status_code == 201


def test_admin_may_override_and_confirm(client, admin):
    a = _confirmed(client, admin)
    assert client.patch(f"/appointments/{a['id']}", headers=admin, json={"urgency_final": 2}).status_code == 200


# -- 6. exam results vs status -------------------------------------------------------------------------------------

def _done_exam(client, admin, doc_a, stored):
    """A requested appointment for p-0001 with an ECG ordered by A and uploaded by the Cardiology nurse."""
    a = _request(client, admin)
    ecg = client.get(f"/appointments/{a['id']}/exams", headers=doc_a).json()[0]
    assert client.post(f"/appointments/{a['id']}/exams/order", headers=doc_a,
                       json={"exam_ids": [ecg["id"]]}).status_code == 200
    up = client.post(f"/exams/{ecg['id']}/results", headers=login(client, "nurse@medora.tn"),
                     files={"file": PDF}, data={"report_text": "sinus rhythm"})
    assert up.status_code == 200, up.text
    return a, ecg["id"], up.json()["results"][0]["id"]


def test_pool_doctor_sees_status_but_not_results(client, admin, doc_a, doc_b, stored):
    a, exam_id, result_id = _done_exam(client, admin, doc_a, stored)
    rows = client.get(f"/appointments/{a['id']}/exams", headers=doc_b).json()
    row = next(r for r in rows if r["id"] == exam_id)
    assert row["status"] == "done" and "results" not in row
    assert client.get(f"/exam-results/{result_id}/file", headers=doc_b).status_code == 403
    # the ordering doctor (also the attending one) still sees the results and the file
    mine = next(r for r in client.get(f"/appointments/{a['id']}/exams", headers=doc_a).json() if r["id"] == exam_id)
    assert mine["results"][0]["report_text"] == "sinus rhythm"
    assert client.get(f"/exam-results/{result_id}/file", headers=doc_a).status_code == 200


def test_orderer_and_booked_doctor_see_results_even_when_not_attending(client, admin, doc_a, doc_b, stored):
    a = _request(client, admin, patient_id="p-0007")  # nobody's patient
    ecg = client.get(f"/appointments/{a['id']}/exams", headers=doc_b).json()[0]["id"]
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc_b, json={"exam_ids": [ecg]})
    up = client.post(f"/exams/{ecg}/results", headers=login(client, "nurse@medora.tn"), files={"file": PDF})
    rid = up.json()["results"][0]["id"]
    assert client.get(f"/exam-results/{rid}/file", headers=doc_b).status_code == 200  # orderer
    assert client.get(f"/exam-results/{rid}/file", headers=doc_a).status_code == 403  # pool doctor
    # book A on the appointment: now A is the booked doctor
    client.post(f"/appointments/{a['id']}/confirm", headers=admin, json={"slot_at": SLOT, "doctor_id": "u-0001"})
    assert client.get(f"/exam-results/{rid}/file", headers=doc_a).status_code == 200  # booked doctor


def test_cancel_ordered_needs_results_level_ownership(client, admin, doc_a, doc_b):
    a = _request(client, admin)
    exams = client.get(f"/appointments/{a['id']}/exams", headers=doc_a).json()
    ordered = exams[0]["id"]
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc_a, json={"exam_ids": [ordered]})
    b = _request(client, admin)
    suggested = client.get(f"/appointments/{b['id']}/exams", headers=doc_a).json()[0]["id"]
    assert client.post(f"/exams/{ordered}/cancel", headers=doc_b).status_code == 403
    assert client.post(f"/exams/{suggested}/cancel", headers=doc_b).status_code == 200  # pool may cancel a suggestion
    assert client.post(f"/exams/{ordered}/cancel", headers=doc_a).status_code == 200


# -- 7. device commands ----------------------------------------------------------------------------------------------

def _cmd(client, h, body, device="bsu-001"):
    return client.post(f"/devices/{device}/command", headers=h, json=body)


def test_nurse_other_ward_and_doctor_b_cannot_command(client, doc_b, published):
    sent = len(published)
    assert _cmd(client, login(client, "nurse2@medora.tn"), {"type": "alert", "text": "hi"}).status_code == 403
    assert _cmd(client, doc_b, {"type": "alert", "text": "hi"}).status_code == 403
    assert len(published) == sent


def test_ward_nurse_and_attending_doctor_can_command_and_it_is_audited(client, db, doc_a, published):
    before = _audits(db, resource="device_command", patient_id="p-0001")
    assert _cmd(client, login(client, "nurse@medora.tn"), {"type": "alert", "text": "hi"}).status_code == 200
    assert _cmd(client, doc_a, {"type": "rotate_home"}).status_code == 200
    assert _audits(db, resource="device_command", patient_id="p-0001") == before + 2
    assert published[-1][0] == "hospital/device/bsu-001/command"


def test_command_to_unassigned_device_is_forbidden(client, db):
    db.add(Device(id="bsu-009", fw_version="0.1.0", online=False))
    db.flush()
    assert _cmd(client, login(client, "nurse@medora.tn"), {"type": "alert", "text": "hi"}, "bsu-009").status_code == 403
    assert _cmd(client, login(client, "doctor@medora.tn"), {"type": "alert", "text": "hi"}, "bsu-009").status_code == 403
    assert _cmd(client, login(client, "nurse@medora.tn"), {"type": "alert"}, "bsu-404").status_code == 404


def test_admin_command_but_not_dispense(client, admin, published):
    assert _cmd(client, admin, {"type": "alert", "text": "maintenance"}).status_code == 200
    assert _cmd(client, admin, {"type": "rotate_home"}).status_code == 200
    sent = len(published)
    assert _cmd(client, admin, {"type": "dispense_now", "dose_id": "whatever"}).status_code == 403
    assert len(published) == sent


def _foreign_dose(db) -> str:
    db.add(Prescription(id="rx-acl", patient_id="p-0002", doctor_id="u-0001", items=[], active=True))
    db.flush()
    db.add(MedDose(id="d-acl", prescription_id="rx-acl", patient_id="p-0002", scheduled_at=datetime.now(UTC),
                   time_of_day="08:00", meds=["X"], slot=1))
    db.flush()
    return "d-acl"


def test_dose_from_another_patient_is_422(client, db, published):
    dose = _foreign_dose(db)
    nurse = login(client, "nurse@medora.tn")
    sent = len(published)
    r = _cmd(client, nurse, {"type": "dispense_now", "dose_id": dose})
    assert r.status_code == 422 and r.json()["code"] == "invalid"
    assert _cmd(client, nurse, {"type": "dispense_now", "dose_id": "nope"}).status_code == 422
    assert len(published) == sent
    own = client.get("/patients/p-0001/doses", headers=nurse).json()[0]["id"]
    assert _cmd(client, nurse, {"type": "dispense_now", "dose_id": own}).status_code == 200


# -- audit -----------------------------------------------------------------------------------------------------------

def test_list_is_audited_with_or_without_patient_id(client, db, doc_b, admin):
    n = _audits(db, resource="appointments", user_id="u-0990")
    client.get("/appointments", headers=doc_b)
    assert _audits(db, resource="appointments", user_id="u-0990", resource_id="list") == 1
    client.get("/appointments?patient_id=p-0001", headers=doc_b)
    assert _audits(db, resource="appointments", user_id="u-0990") == n + 2
    assert _audits(db, resource="appointments", user_id="u-0990", resource_id="p-0001", patient_id="p-0001") == 1
    client.get("/appointments", headers=admin)
    assert _audits(db, resource="appointments", user_id="u-0004", resource_id="list") == 1


def test_waitlist_is_audited(client, db, doc_b, admin):
    client.get("/appointments/waitlist", headers=doc_b)
    client.get("/appointments/waitlist", headers=admin)
    assert _audits(db, resource="waitlist", user_id="u-0990", action="read") == 1
    assert _audits(db, resource="waitlist", user_id="u-0004", action="read") == 1


def test_override_confirm_and_order_are_audited(client, db, admin, doc_b):
    a = _request(client, admin)
    exam = client.get(f"/appointments/{a['id']}/exams", headers=doc_b).json()[0]["id"]
    client.patch(f"/appointments/{a['id']}", headers=doc_b, json={"urgency_final": 3})
    assert _audits(db, user_id="u-0990", action="update", resource="appointment", resource_id=a["id"],
                   patient_id="p-0001") == 1
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc_b, json={"exam_ids": [exam]})
    assert _audits(db, user_id="u-0990", resource="exam_order", resource_id=a["id"], patient_id="p-0001") == 1
    r = client.post(f"/appointments/{a['id']}/confirm", headers=doc_b, json={"slot_at": SLOT, "doctor_id": "u-0990"})
    assert r.status_code == 200
    assert _audits(db, user_id="u-0990", action="update", resource="appointment", resource_id=a["id"]) == 2


def test_add_exam_is_audited(client, db, admin, doc_b):
    a = _request(client, admin)
    r = client.post("/exams", headers=doc_b, json={"patient_id": "p-0001", "appointment_id": a["id"], "code": "echo"})
    assert r.status_code == 201
    assert _audits(db, user_id="u-0990", action="create", resource="exam", resource_id=r.json()["id"],
                   patient_id="p-0001") == 1
