from app.models import AuditLog
from tests.helpers import login


def test_patient_cannot_read_other(client):
    h = login(client, "patient@medora.tn")
    assert client.get("/patients/p-0001", headers=h).status_code == 200
    assert client.get("/patients/p-0002", headers=h).status_code == 403


def test_nurse_other_ward_forbidden(client):
    h = login(client, "nurse2@medora.tn")  # Internal Medicine
    assert client.get("/patients/p-0001", headers=h).status_code == 403
    assert client.get("/patients/p-0007", headers=h).status_code == 200


def test_doctor_only_own_patients(client):
    h = login(client, "doctor@medora.tn")
    assert client.get("/patients/p-0001", headers=h).status_code == 200
    assert client.get("/patients/p-0007", headers=h).status_code == 403


def test_unknown_patient_404(client):
    r = client.get("/patients/p-9999", headers=login(client, "doctor@medora.tn"))
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_admin_cannot_read_clinical(client):
    h = login(client, "admin@medora.tn")
    assert client.get("/patients/p-0001/vitals", headers=h).status_code == 403
    assert client.get("/patients/p-0001", headers=h).status_code == 403


def test_read_writes_audit(client, db):
    h = login(client, "doctor@medora.tn")
    before = db.query(AuditLog).count()
    client.get("/patients/p-0001", headers=h)
    assert db.query(AuditLog).count() == before + 1
    row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    assert (row.user_id, row.action, row.patient_id) == ("u-0001", "read", "p-0001")


def test_forbidden_read_not_audited_as_read(client, db):
    h = login(client, "patient@medora.tn")
    before = db.query(AuditLog).filter_by(action="read").count()
    client.get("/patients/p-0002", headers=h)
    assert db.query(AuditLog).filter_by(action="read").count() == before
