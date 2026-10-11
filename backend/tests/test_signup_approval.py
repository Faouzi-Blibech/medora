"""Approving a sign-up request: role change, patient link or create, doctor scope (signup-v2 brief)."""

from sqlalchemy import select

from app.models import AuditLog, Patient, Staff, User
from tests.helpers import login, make_patient, make_user


def _pending(db, email="req.t@medora.tn", *, role="patient", doctor=None, name="Amira Test Gharbi"):
    u = make_user(db, email, role=None, status="pending", requested_doctor_id=doctor, name=name)
    u.requested_role = role
    db.flush()
    return u


def _approve(client, who, uid, **body):
    return client.post(f"/users/{uid}/approve", headers=login(client, who), json=body)


def test_pending_list_has_requested_role_and_doctor(client, db):
    a = _pending(db, role="nurse", doctor="u-0001")
    rows = client.get("/users", headers=login(client, "admin@medora.tn")).json()
    row = next(r for r in rows if r["id"] == a.id)
    assert (row["requested_role"], row["requested_doctor_id"]) == ("nurse", "u-0001")


def test_admin_links_a_patient_to_an_existing_record(client, db):
    rec = make_patient(db, attending="u-0001")
    a = _pending(db)
    r = _approve(client, "admin@medora.tn", a.id, role="patient", patient_id=rec.id)
    assert r.status_code == 200 and (r.json()["role"], r.json()["status"]) == ("patient", "active")
    assert db.get(User, a.id).patient_id == rec.id
    h = login(client, "req.t@medora.tn")
    assert client.get(f"/patients/{rec.id}", headers=h).status_code == 200
    audit = db.scalars(select(AuditLog).where(AuditLog.resource == "user", AuditLog.resource_id == a.id)).all()
    assert any(row.patient_id == rec.id for row in audit)


def test_link_to_a_record_that_already_has_an_account_is_409(client, db):
    a = _pending(db)
    r = _approve(client, "admin@medora.tn", a.id, role="patient", patient_id="p-0001")  # patient@medora.tn owns it
    assert r.status_code == 409 and r.json()["code"] == "conflict"
    assert db.get(User, a.id).status == "pending"


def test_a_record_whose_account_was_disabled_can_be_linked_again(client, db):
    db.get(User, "u-0005").status = "disabled"
    a = _pending(db)
    assert _approve(client, "admin@medora.tn", a.id, role="patient", patient_id="p-0001").status_code == 200


def test_link_to_a_missing_record_is_404(client, db):
    a = _pending(db)
    assert _approve(client, "admin@medora.tn", a.id, role="patient", patient_id="p-9999").status_code == 404


def test_patient_id_with_another_role_is_422(client, db):
    a = _pending(db, role="nurse")
    assert _approve(client, "admin@medora.tn", a.id, role="nurse", patient_id="p-0002").status_code == 422


def test_admin_creates_a_record_with_the_requested_doctor_as_attending(client, db):
    a = _pending(db, doctor="u-0001")
    assert _approve(client, "admin@medora.tn", a.id, role="patient").status_code == 200
    p = db.get(Patient, db.get(User, a.id).patient_id)
    assert (p.first_name, p.last_name, p.attending_doctor_id) == ("Amira", "Test Gharbi", "u-0001")
    assert (p.ward, p.date_of_birth, p.allergies, p.history) == (None, None, [], "")
    created = db.scalars(select(AuditLog).where(AuditLog.action == "create", AuditLog.resource == "patient",
                                                 AuditLog.resource_id == p.id)).all()
    assert len(created) == 1


def test_admin_creates_a_record_without_attending_when_no_doctor_was_asked(client, db):
    a = _pending(db, name="Mononym")
    assert _approve(client, "admin@medora.tn", a.id, role="patient").status_code == 200
    p = db.get(Patient, db.get(User, a.id).patient_id)
    assert (p.first_name, p.last_name, p.attending_doctor_id) == ("Mononym", "", None)


def test_admin_ignores_a_requested_doctor_who_was_disabled_since(client, db):
    d = make_user(db, "gone.t@medora.tn", role="doctor", ward="Cardiology")
    a = _pending(db, doctor=d.id)
    d.status = "disabled"
    db.flush()
    _approve(client, "admin@medora.tn", a.id, role="patient")
    assert db.get(Patient, db.get(User, a.id).patient_id).attending_doctor_id is None


def test_doctor_creating_a_record_becomes_its_attending(client, db):
    a = _pending(db, doctor="u-0001")
    assert _approve(client, "doctor@medora.tn", a.id, role="patient").status_code == 200
    p = db.get(Patient, db.get(User, a.id).patient_id)
    assert p.attending_doctor_id == "u-0001"
    assert client.get(f"/patients/{p.id}", headers=login(client, "doctor@medora.tn")).status_code == 200


def test_doctor_links_only_his_own_unlinked_record(client, db):
    mine = make_patient(db, attending="u-0001")
    other_doc = make_user(db, "doc2.t@medora.tn", role="doctor", ward="Cardiology")
    theirs = make_patient(db, attending=other_doc.id)
    unowned = make_patient(db)
    a = _pending(db, doctor="u-0001")
    for rec in (theirs, unowned):
        assert _approve(client, "doctor@medora.tn", a.id, role="patient", patient_id=rec.id).status_code == 403
    assert _approve(client, "doctor@medora.tn", a.id, role="patient", patient_id="p-0001").status_code == 409
    assert _approve(client, "doctor@medora.tn", a.id, role="patient", patient_id=mine.id).status_code == 200


def test_doctor_approves_a_nurse_into_his_team(client, db):
    a = _pending(db, role="nurse", doctor="u-0001")
    r = _approve(client, "doctor@medora.tn", a.id, role="nurse")
    assert (r.json()["role"], r.json()["supervisor_id"]) == ("nurse", "u-0001")
    assert db.get(User, a.id).patient_id is None


def test_doctor_cannot_approve_a_request_that_did_not_name_him(client, db):
    other_doc = make_user(db, "doc2.t@medora.tn", role="doctor", ward="Cardiology")
    for i, doctor in enumerate((None, other_doc.id)):
        a = _pending(db, f"r{i}.t@medora.tn", doctor=doctor)
        assert _approve(client, "doctor@medora.tn", a.id, role="patient").status_code == 403
        assert db.get(User, a.id).status == "pending"


def test_doctor_cannot_approve_a_doctor_or_an_admin(client, db):
    unnamed = _pending(db, "d1.t@medora.tn", role="doctor")
    assert _approve(client, "doctor@medora.tn", unnamed.id, role="doctor").status_code == 403
    named = _pending(db, "d2.t@medora.tn", role="nurse", doctor="u-0001")
    for role in ("doctor", "admin"):
        assert _approve(client, "doctor@medora.tn", named.id, role=role).status_code == 403
    assert db.get(User, named.id).status == "pending"


def test_only_admin_approves_doctors_and_admins(client, db):
    d = _pending(db, "d1.t@medora.tn", role="doctor")
    r = _approve(client, "admin@medora.tn", d.id, role="doctor", ward="Cardiology")
    assert (r.json()["role"], r.json()["ward"]) == ("doctor", "Cardiology")
    assert db.get(Staff, d.id).supervisor_id is None
    adm = _pending(db, "a1.t@medora.tn", role="nurse")
    assert _approve(client, "admin@medora.tn", adm.id, role="admin").json()["role"] == "admin"
    assert db.get(Staff, adm.id) is None


def test_approver_may_change_the_requested_role(client, db):
    a = _pending(db, role="nurse", doctor="u-0001")
    r = _approve(client, "doctor@medora.tn", a.id, role="patient")
    assert r.json()["role"] == "patient" and db.get(User, a.id).patient_id is not None
    assert db.get(Staff, a.id) is None


def test_unlinked_filter_lists_records_without_an_account(client, db):
    free = make_patient(db, attending="u-0001", first="Free")
    admin, doc = login(client, "admin@medora.tn"), login(client, "doctor@medora.tn")
    ids = {p["id"] for p in client.get("/patients?unlinked=true", headers=admin).json()}
    assert free.id in ids and "p-0001" not in ids
    mine = {p["id"] for p in client.get("/patients?unlinked=true&q=Free", headers=doc).json()}
    assert mine == {free.id}
    db.get(User, "u-0005").status = "disabled"
    db.flush()
    assert "p-0001" in {p["id"] for p in client.get("/patients?unlinked=true", headers=admin).json()}
    assert "p-0001" in {p["id"] for p in client.get("/patients", headers=admin).json()}  # default list unchanged
