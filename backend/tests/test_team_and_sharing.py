from datetime import UTC, datetime, timedelta

from app.models import PatientAccess
from app.services import alerts as AL
from app.ws.hub import Client, wants
from tests.helpers import login, make_patient, make_user


def _setup(db):
    team = make_user(db, "team.t@medora.tn", role="nurse", supervisor_id="u-0001")
    doc2 = make_user(db, "doc2.t@medora.tn", role="doctor", ward="Cardiology")
    mine = make_patient(db, attending="u-0001", ward="Cardiology")
    theirs = make_patient(db, attending=doc2.id, ward="Cardiology")
    return team, doc2, mine, theirs


def test_team_nurse_sees_only_her_doctors_patients(client, db):
    _, _, mine, theirs = _setup(db)
    h = login(client, "team.t@medora.tn")
    assert client.get(f"/patients/{mine.id}", headers=h).status_code == 200
    assert client.get(f"/patients/{theirs.id}", headers=h).status_code == 403
    ids = {r["id"] for r in client.get("/patients", headers=h).json()}
    assert mine.id in ids and theirs.id not in ids


def test_team_nurse_gets_her_doctors_alerts_only(client, db):
    _, _, mine, theirs = _setup(db)
    a1 = AL.create_alert(db, mine.id, None, "trend", "medium", None, "test mine", None)
    a2 = AL.create_alert(db, theirs.id, None, "trend", "medium", None, "test theirs", None)
    ids = {a["id"] for a in client.get("/alerts", headers=login(client, "team.t@medora.tn")).json()}
    assert a1.id in ids and a2.id not in ids


def test_team_nurse_ward_screens_are_empty_not_errors(client, db):
    _setup(db)
    h = login(client, "team.t@medora.tn")
    assert client.get("/exams", headers=h).json() == []
    r = client.get("/patients?ward=Nowhere", headers=h)
    assert r.status_code == 200 and r.json() == []


def test_ward_nurse_unchanged(client):
    rows = client.get("/patients", headers=login(client, "nurse@medora.tn")).json()
    assert rows and {r["ward"] for r in rows} == {"Cardiology"}


def test_ws_routes_doctor_frames_to_his_team_nurse():
    team = Client(ws=None, user_id="u-x", role="nurse", ward=None, supervisor_id="u-0001")
    assert wants(team, {"type": "alert", "scope": {"ward": "Cardiology", "doctor_id": "u-0001"}})
    assert not wants(team, {"type": "alert", "scope": {"ward": "Cardiology", "doctor_id": "u-0999"}})
    ward_nurse = Client(ws=None, user_id="u-y", role="nurse", ward="Cardiology")
    assert wants(ward_nurse, {"type": "alert", "scope": {"ward": "Cardiology", "doctor_id": "u-0999"}})


def test_share_gives_access_until_revoked(client, db):
    _, doc2, _, _ = _setup(db)
    h2, h1 = login(client, "doc2.t@medora.tn"), login(client, "doctor@medora.tn")
    assert client.get("/patients/p-0001", headers=h2).status_code == 403
    r = client.post("/patients/p-0001/access", headers=h1, json={"doctor_id": doc2.id})
    assert r.status_code == 200 and r.json()["doctor_id"] == doc2.id
    assert client.get("/patients/p-0001", headers=h2).status_code == 200
    assert "p-0001" in {p["id"] for p in client.get("/patients", headers=h2).json()}
    assert [g["doctor_id"] for g in client.get("/patients/p-0001/access", headers=h1).json()] == [doc2.id]
    assert client.delete(f"/patients/p-0001/access/{doc2.id}", headers=h1).status_code == 204
    assert client.get("/patients/p-0001", headers=h2).status_code == 403


def test_expired_grant_gives_nothing(client, db):
    _, doc2, _, _ = _setup(db)
    now = datetime.now(UTC)
    db.add(PatientAccess(id="pa-9001", patient_id="p-0001", user_id=doc2.id, granted_by="u-0001",
                         created_at=now - timedelta(days=31), expires_at=now - timedelta(days=1)))
    db.flush()
    assert client.get("/patients/p-0001", headers=login(client, "doc2.t@medora.tn")).status_code == 403


def test_only_attending_or_admin_can_share(client, db):
    _, doc2, _, _ = _setup(db)
    body = {"doctor_id": doc2.id}
    assert client.post("/patients/p-0001/access", headers=login(client, "doc2.t@medora.tn"), json=body).status_code == 403
    assert client.post("/patients/p-0001/access", headers=login(client, "nurse@medora.tn"), json=body).status_code == 403
    assert client.post("/patients/p-0001/access", headers=login(client, "admin@medora.tn"), json=body).status_code == 200


def test_share_validation(client, db):
    _, doc2, _, _ = _setup(db)
    h1 = login(client, "doctor@medora.tn")
    far = (datetime.now(UTC) + timedelta(days=400)).isoformat()
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    for body in ({"doctor_id": doc2.id, "expires_at": far}, {"doctor_id": doc2.id, "expires_at": past},
                 {"doctor_id": "u-0002"}, {"doctor_id": "u-0001"}):
        assert client.post("/patients/p-0001/access", headers=h1, json=body).status_code == 422, body


# ---- fix round 1 ----
from sqlalchemy import select  # noqa: E402

from app.models import Appointment, AuditLog, ExamOrder, Staff  # noqa: E402


def _share(client, doc2, **extra):
    return client.post("/patients/p-0001/access", headers=login(client, "doctor@medora.tn"),
                       json={"doctor_id": doc2.id, **extra})


def _audits(db, resource):
    return [(a.action, a.resource_id) for a in db.scalars(
        select(AuditLog).where(AuditLog.resource == resource).order_by(AuditLog.id))]


def test_share_revoke_and_list_are_audited(client, db):
    _, doc2, _, _ = _setup(db)
    h1 = login(client, "doctor@medora.tn")
    grant_id = _share(client, doc2)
    assert grant_id.status_code == 200
    client.get("/patients/p-0001/access", headers=h1)
    client.delete(f"/patients/p-0001/access/{doc2.id}", headers=h1)
    actions = [a for a, _ in _audits(db, "patient_access")]
    assert actions == ["create", "read", "delete"]
    row = db.scalars(select(AuditLog).where(AuditLog.resource == "patient_access")).first()
    assert row.patient_id == "p-0001" and row.user_id == "u-0001"


def test_expired_and_revoked_grants_are_excluded_from_lists(client, db):
    _, doc2, _, _ = _setup(db)
    h2, h1 = login(client, "doc2.t@medora.tn"), login(client, "doctor@medora.tn")
    now = datetime.now(UTC)
    alert = AL.create_alert(db, "p-0001", None, "trend", "medium", None, "shared alert", None)
    db.add(PatientAccess(id="pa-9002", patient_id="p-0001", user_id=doc2.id, granted_by="u-0001",
                         created_at=now - timedelta(days=31), expires_at=now - timedelta(days=1)))
    db.flush()
    assert "p-0001" not in {p["id"] for p in client.get("/patients", headers=h2).json()}
    assert alert.id not in {a["id"] for a in client.get("/alerts", headers=h2).json()}
    _share(client, doc2)
    assert "p-0001" in {p["id"] for p in client.get("/patients", headers=h2).json()}
    assert alert.id in {a["id"] for a in client.get("/alerts", headers=h2).json()}
    client.delete(f"/patients/p-0001/access/{doc2.id}", headers=h1)
    assert "p-0001" not in {p["id"] for p in client.get("/patients", headers=h2).json()}
    assert alert.id not in {a["id"] for a in client.get("/alerts", headers=h2).json()}


def test_shared_doctor_cannot_reshare(client, db):
    _, doc2, _, _ = _setup(db)
    doc3 = make_user(db, "doc3.t@medora.tn", role="doctor", ward="Cardiology")
    _share(client, doc2)
    r = client.post("/patients/p-0001/access", headers=login(client, "doc2.t@medora.tn"), json={"doctor_id": doc3.id})
    assert r.status_code == 403


def test_share_defaults_to_about_30_days(client, db):
    _, doc2, _, _ = _setup(db)
    exp = datetime.fromisoformat(_share(client, doc2).json()["expires_at"].replace("Z", "+00:00"))
    assert timedelta(days=29, hours=23) < exp - datetime.now(UTC) <= timedelta(days=30)


def test_second_share_replaces_the_first(client, db):
    _, doc2, _, _ = _setup(db)
    _share(client, doc2)
    _share(client, doc2, expires_at=(datetime.now(UTC) + timedelta(days=5)).isoformat())
    live = client.get("/patients/p-0001/access", headers=login(client, "doctor@medora.tn")).json()
    assert [g["doctor_id"] for g in live] == [doc2.id]
    rows = db.scalars(select(PatientAccess).where(PatientAccess.user_id == doc2.id)).all()
    assert len(rows) == 2 and sum(r.revoked_at is None for r in rows) == 1


def test_shared_doctor_reads_exams_and_appointments_until_revoked(client, db):
    _, doc2, _, _ = _setup(db)
    h2, h1 = login(client, "doc2.t@medora.tn"), login(client, "doctor@medora.tn")
    appt = Appointment(id="ap-9001", patient_id="p-0001", status="confirmed", urgency_ai=2, doctor_id=None)
    db.add(appt)
    db.flush()
    db.add(ExamOrder(id="ex-9001", patient_id="p-0001", appointment_id=appt.id, code="ecg", label="ECG",
                     department="Cardiology", status="ordered", human_confirmed_by="u-0001",
                     ordered_at=datetime.now(UTC)))
    db.flush()
    assert client.get(f"/appointments/{appt.id}/exams", headers=h2).status_code == 403
    assert client.get("/appointments?patient_id=p-0001", headers=h2).json() == []
    _share(client, doc2)
    # the work queue (no patient_id) is attending-only; one shared patient's list and single reads work
    assert appt.id not in {a["id"] for a in client.get("/appointments", headers=h2).json()}
    assert client.get("/appointments?patient_id=p-0001", headers=h2).json()[0]["id"] == appt.id
    r = client.get(f"/appointments/{appt.id}/exams", headers=h2)
    assert r.status_code == 200 and [e["id"] for e in r.json()] == ["ex-9001"]
    assert [e["id"] for e in client.get("/patients/p-0001/exams", headers=h2).json()] == ["ex-9001"]
    client.delete(f"/patients/p-0001/access/{doc2.id}", headers=h1)
    assert client.get("/appointments?patient_id=p-0001", headers=h2).json() == []
    assert client.get(f"/appointments/{appt.id}/exams", headers=h2).status_code == 403
    assert client.get("/patients/p-0001/exams", headers=h2).status_code == 403


def test_ws_frames_reach_a_shared_doctor():
    shared = Client(ws=None, user_id="u-s", role="doctor", ward=None)
    scope = {"ward": "Cardiology", "doctor_id": "u-0001", "shared_with": ["u-s"]}
    assert wants(shared, {"type": "alert", "scope": scope})
    assert not wants(shared, {"type": "alert", "scope": dict(scope, shared_with=[])})


def test_scope_lists_only_live_grants(client, db):
    from app.iot.ingest import scope_for

    _, doc2, _, _ = _setup(db)
    assert "shared_with" not in scope_for(db, "p-0001")
    _share(client, doc2)
    assert scope_for(db, "p-0001")["shared_with"] == [doc2.id]


def test_chat_ids_include_team_nurses_once(client, db):
    from app.services.alerts import chat_ids

    team, _, mine, _ = _setup(db)
    ward_nurse = make_user(db, "wn.t@medora.tn", role="nurse", ward="Cardiology", supervisor_id="u-0001")
    db.get(Staff, team.id).telegram_chat_id = "T1"
    db.get(Staff, ward_nurse.id).telegram_chat_id = "W1"
    db.flush()
    nurses, _doc = chat_ids(db, mine)
    assert "T1" in nurses and "W1" in nurses and len(nurses) == len(set(nurses))
    assert nurses.count("W1") == 1


# ---- read-only sharing ----
def test_shared_doctor_is_read_only(client, db):
    _, doc2, _, _ = _setup(db)
    h2, h1 = login(client, "doc2.t@medora.tn"), login(client, "doctor@medora.tn")
    appt = Appointment(id="ap-9002", patient_id="p-0001", status="confirmed", urgency_ai=2, doctor_id=None)
    db.add(appt)
    db.flush()
    assert _share(client, doc2).status_code == 200

    # reads stay open
    assert client.get("/patients/p-0001", headers=h2).status_code == 200
    assert client.get("/patients/p-0001/notes", headers=h2).status_code == 200
    assert client.get("/patients/p-0001/exams", headers=h2).status_code == 200
    assert client.get("/appointments?patient_id=p-0001", headers=h2).status_code == 200

    # every write is refused
    rx = {"patient_id": "p-0001", "items": [{"med": "Aspirin", "times": ["08:00"]}]}
    exam = {"patient_id": "p-0001", "appointment_id": appt.id, "code": "ecg"}
    confirm = {"slot_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(), "doctor_id": doc2.id}
    for r in (client.post("/patients/p-0001/notes", headers=h2, json={"text": "hi"}),
              client.post("/prescriptions", headers=h2, json=rx),
              client.patch("/patients/p-0001", headers=h2, json={"allergies": ["x"]}),
              client.patch(f"/appointments/{appt.id}", headers=h2, json={"urgency_final": 3}),
              client.post(f"/appointments/{appt.id}/confirm", headers=h2, json=confirm),
              client.post("/exams", headers=h2, json=exam),
              client.post("/exams", headers=h2, json={"patient_id": "p-0001", "code": "ecg"}),
              client.post(f"/appointments/{appt.id}/exams/order", headers=h2, json={"exam_ids": []})):
        assert r.status_code == 403, r.request.url

    # the attending doctor still writes
    assert client.post("/patients/p-0001/notes", headers=h1, json={"text": "hi"}).status_code in (200, 201)
    assert client.patch("/patients/p-0001", headers=h1, json={"allergies": ["x"]}).status_code == 200
    assert client.patch(f"/appointments/{appt.id}", headers=h1, json={"urgency_final": 3}).status_code == 200
