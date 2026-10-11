from datetime import UTC, datetime, timedelta

from app.models import AccessCode, PatientAccess, Staff, User
from tests.helpers import make_patient, make_user


def test_existing_style_user_defaults_to_active(seeded):
    u = seeded.get(User, "u-0001")
    assert u.status == "active" and u.failed_logins == 0 and u.locked_until is None


def test_pending_user_has_no_role_and_remembers_the_request(seeded):
    u = make_user(seeded, "new@medora.tn", role=None, status="pending", requested_doctor_id="u-0001")
    assert u.role is None and u.status == "pending" and u.requested_doctor_id == "u-0001"


def test_staff_supervisor(seeded):
    u = make_user(seeded, "team@medora.tn", role="nurse", supervisor_id="u-0001")
    assert seeded.get(Staff, u.id).supervisor_id == "u-0001"


def test_access_code_and_grant_rows(seeded):
    now = datetime.now(UTC)
    p = make_patient(seeded, attending="u-0001")
    seeded.add(AccessCode(id="ac-9001", purpose="reset", code_hash="x" * 64, user_id="u-0002",
                          issued_by="u-0004", expires_at=now + timedelta(hours=48)))
    seeded.add(PatientAccess(id="pa-9001", patient_id=p.id, user_id="u-0001", granted_by="u-0004",
                             expires_at=now + timedelta(days=30)))
    seeded.flush()
    assert seeded.get(AccessCode, "ac-9001").used_at is None
    assert seeded.get(PatientAccess, "pa-9001").revoked_at is None
