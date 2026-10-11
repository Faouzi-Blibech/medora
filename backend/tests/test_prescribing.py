"""The doctor side (api 1.12 → Prescriptions): dry run, gate, urgent, override, versions, stop, shapes."""

from sqlalchemy import select

from app.models import AuditLog, MedDose, Patient, Prescription
from app.services import schedule
from tests.helpers import login, pharmacist

DOC = "doctor@medora.tn"
RX_OK = {"patient_id": "p-0001", "care_plan": "",
         "items": [{"med": "Omeprazole 20 mg", "drug_id": "d-0041", "times": ["20:00"], "slot": 3, "days": 3}]}
RX_ALLERGY = {"patient_id": "p-0001", "care_plan": "",
              "items": [{"med": "Amoxicillin 1 g", "drug_id": "d-0003", "dose_mg": 1000,
                         "times": ["08:00", "14:00", "20:00"], "days": 7}]}
DOCTOR_KEYS = {"id", "patient_id", "doctor_id", "items", "care_plan", "active", "created_at", "status", "urgent",
               "version", "replaces_id", "checks", "override_reason", "review_comment", "reviewed_by_name",
               "reviewed_at"}
PATIENT_KEYS = {"id", "patient_id", "doctor_id", "items", "care_plan", "active", "created_at", "status"}


def _post(client, body, **extra):
    return client.post("/prescriptions", headers=login(client, DOC), json={**body, **extra})


def _future(db, rx_id):
    return db.scalars(select(MedDose).where(MedDose.prescription_id == rx_id,
                                            MedDose.scheduled_at > schedule.now_utc())).all()


def _frames(published):
    return [p["data"] for t, p, *_ in published if t == "ward/internal/ws" and p.get("type") == "prescription_status"]


def test_check_is_a_dry_run(client, db):
    before = db.query(Prescription).count()
    r = client.post("/prescriptions/check", headers=login(client, DOC),
                    json={"patient_id": "p-0001", "items": RX_ALLERGY["items"]})
    assert r.status_code == 200, r.text
    checks = r.json()["checks"]
    assert [(c["code"], c["severity"], c["item_index"], c["drug_id"]) for c in checks] == [
        ("allergy", "critical", 0, "d-0003")]
    assert set(checks[0]) == {"code", "severity", "item_index", "drug_id", "params", "message"}
    assert db.query(Prescription).count() == before
    assert db.scalar(select(AuditLog.id).where(AuditLog.resource == "prescription_check",
                                               AuditLog.patient_id == "p-0001"))


def test_check_permissions(client):
    body = {"patient_id": "p-0001", "items": RX_OK["items"]}
    assert client.post("/prescriptions/check", headers=login(client, "nurse@medora.tn"), json=body).status_code == 403
    assert client.post("/prescriptions/check", headers=login(client, DOC),
                       json={**body, "patient_id": "p-0007"}).status_code == 403
    assert client.post("/prescriptions/check", headers=login(client, DOC),
                       json={**body, "patient_id": "p-9999"}).status_code == 404


def test_new_prescription_waits_for_the_pharmacist(client, db, published):
    r = _post(client, RX_OK)
    assert r.status_code == 201, r.text
    b = r.json()
    assert (b["status"], b["active"], b["urgent"], b["version"], b["replaces_id"], b["checks"]) == (
        "pending_pharmacy", False, False, 1, None, [])
    assert set(b) == DOCTOR_KEYS | {"schedule_version", "published_to_device"} and b["published_to_device"] is False
    assert db.query(MedDose).filter_by(prescription_id=b["id"]).count() == 0
    assert not [p for p in published if p[0].endswith("/schedule")]
    assert {"prescription_id": b["id"], "patient_id": "p-0001", "status": "pending_pharmacy",
            "urgent": False} in _frames(published)


def test_urgent_starts_now(client, db, published):
    b = _post(client, RX_OK, urgent=True).json()
    assert (b["status"], b["active"], b["urgent"], b["published_to_device"]) == ("pending_pharmacy", True, True, True)
    assert db.query(MedDose).filter_by(prescription_id=b["id"]).count() == 3
    assert [p for p in published if p[0] == "hospital/device/bsu-001/schedule"]


def test_critical_needs_an_override_reason(client, db):
    before = db.query(Prescription).count()
    for extra in ({}, {"override_reason": "   "}):
        r = _post(client, RX_ALLERGY, **extra)
        assert r.status_code == 422 and r.json()["code"] == "override_required"
    assert db.query(Prescription).count() == before
    b = _post(client, RX_ALLERGY, override_reason=" Severe infection ").json()
    assert (b["override_reason"], b["checks"][0]["code"], b["status"]) == (
        "Severe infection", "allergy", "pending_pharmacy")


def test_unknown_or_inactive_drug_is_422(client, db):
    ghost = [{"med": "Ghost", "drug_id": "d-9999", "times": ["08:00"]}]
    for url in ("/prescriptions/check", "/prescriptions"):
        r = client.post(url, headers=login(client, DOC), json={"patient_id": "p-0001", "care_plan": "", "items": ghost})
        assert r.status_code == 422 and r.json()["code"] == "unknown_drug"


def test_a_deactivated_drug_still_counts_for_running_prescriptions(client, db):
    ph = pharmacist(client, db)
    running = _post(client, RX_OK, urgent=True).json()
    assert client.patch("/drugs/d-0041", headers=ph, json={"active": False}).status_code == 200
    h = login(client, DOC)
    r = client.post("/prescriptions/check", headers=h, json={"patient_id": "p-0001", "items": RX_OK["items"]})
    assert r.status_code == 422 and r.json()["code"] == "unknown_drug"
    panto = [{"med": "Pantoprazole 40 mg", "drug_id": "d-0042", "times": ["08:00"]}]
    checks = client.post("/prescriptions/check", headers=h, json={"patient_id": "p-0001", "items": panto}).json()["checks"]
    assert [(c["code"], c["params"]["reason"], c["params"]["with_prescription_id"]) for c in checks] == [
        ("duplicate_therapy", "same_atc_class", running["id"])]


def test_a_version_that_never_ran_is_replaced_at_once(client, db):
    v1 = _post(client, RX_OK).json()
    v2 = _post(client, RX_OK, replaces_id=v1["id"]).json()
    assert (v2["version"], v2["replaces_id"], v2["status"]) == (2, v1["id"], "pending_pharmacy")
    assert db.get(Prescription, v1["id"]).status == "superseded"


def test_urgent_new_version_replaces_the_running_one_at_once(client, db):
    v1 = _post(client, RX_OK, urgent=True).json()
    v2 = _post(client, RX_OK, urgent=True, replaces_id=v1["id"]).json()
    assert v2["checks"] == []  # the replaced version is not a duplicate of its successor
    assert db.get(Prescription, v1["id"]).status == "superseded" and not db.get(Prescription, v1["id"]).active
    assert _future(db, v1["id"]) == [] and len(_future(db, v2["id"])) == 3


def test_replaces_id_rules(client, db):
    v1 = _post(client, RX_OK, urgent=True).json()
    v2 = _post(client, RX_OK, replaces_id=v1["id"]).json()
    assert db.get(Prescription, v1["id"]).status == "pending_pharmacy" and db.get(Prescription, v1["id"]).active
    again = _post(client, RX_OK, replaces_id=v1["id"])  # v1 already has a live newer version
    assert again.status_code == 409 and again.json()["code"] == "conflict"
    assert _post(client, RX_OK, replaces_id="rx-9999").status_code == 404
    other = _post(client, {**RX_OK, "patient_id": "p-0002"}).json()
    assert _post(client, RX_OK, replaces_id=other["id"]).status_code == 409
    assert client.patch(f"/prescriptions/{v2['id']}", headers=login(client, DOC), json={"active": False}).status_code == 200
    assert _post(client, RX_OK, replaces_id=v2["id"]).status_code == 409  # stopped is not live


def test_stop(client, db, published):
    h = login(client, DOC)
    rx = _post(client, RX_OK, urgent=True).json()
    r = client.patch(f"/prescriptions/{rx['id']}", headers=h, json={"active": False})
    assert r.status_code == 200 and (r.json()["status"], r.json()["active"]) == ("stopped", False)
    assert _future(db, rx["id"]) == []
    twice = client.patch(f"/prescriptions/{rx['id']}", headers=h, json={"active": False})
    assert twice.status_code == 409 and twice.json()["code"] == "bad_status"
    assert client.patch(f"/prescriptions/{rx['id']}", headers=h, json={"active": True}).status_code == 422
    pending = _post(client, RX_OK).json()
    assert client.patch(f"/prescriptions/{pending['id']}", headers=h, json={"active": False}).json()["status"] == "stopped"
    assert client.patch("/prescriptions/rx-9999", headers=h, json={"active": False}).status_code == 404


def test_get_shapes_by_role(client):
    _post(client, RX_OK)
    rows = client.get("/patients/p-0001/prescriptions", headers=login(client, DOC)).json()
    assert rows and all(set(r) == DOCTOR_KEYS for r in rows)
    assert all(set(r) == DOCTOR_KEYS for r in client.get("/patients/p-0001/prescriptions",
                                                          headers=login(client, "nurse@medora.tn")).json())
    mine = client.get("/patients/p-0001/prescriptions", headers=login(client, "patient@medora.tn")).json()
    assert mine and all(set(r) == PATIENT_KEYS for r in mine)


def test_ai_record_labels_a_pending_prescription(client, db):
    from app.services.record_sources import build

    rx = _post(client, RX_OK).json()
    src = next(s for s in build(db, db.get(Patient, "p-0001"), "doctor") if s.id == f"rx:{rx['id']}")
    assert src.text.startswith("Prescription pending pharmacy review:")


def test_every_new_prescription_is_pending_pharmacy_in_the_database(client, db):
    """Carried from the Task 1 review: the column's server default is 'validated' (backfill only)."""
    normal = _post(client, RX_OK).json()
    urgent = _post(client, RX_OK, urgent=True).json()
    v2 = _post(client, RX_OK, replaces_id=normal["id"]).json()
    for rid, is_urgent, active in ((normal["id"], False, False), (urgent["id"], True, True), (v2["id"], False, False)):
        db.expire_all()
        rx = db.get(Prescription, rid)
        assert (rx.urgent, rx.active) == (is_urgent, active)
        assert rx.status in ("pending_pharmacy", "superseded") and rx.status != "validated"
    assert db.get(Prescription, urgent["id"]).status == "pending_pharmacy"  # urgent: running, still in the queue
    assert db.get(Prescription, v2["id"]).status == "pending_pharmacy"
    assert db.query(MedDose).filter_by(prescription_id=urgent["id"]).count() == 3


def test_units_per_intake_is_1_to_10(client):
    for n, code in ((0, 422), (11, 422), (1, 201), (10, 201)):
        item = {**RX_OK["items"][0], "units_per_intake": n}
        # 10 units can exceed the daily maximum (a critical check), so give a reason: only the range is under test
        assert _post(client, {**RX_OK, "items": [item]}, override_reason="range test").status_code == code


def test_a_version_chain_cannot_fork(client, db):
    v1 = _post(client, RX_OK, urgent=True).json()
    v2 = _post(client, RX_OK, replaces_id=v1["id"]).json()  # non-urgent: v1 keeps running
    v3 = _post(client, RX_OK, replaces_id=v2["id"]).json()  # v2 never ran: superseded, v3 is live
    assert db.get(Prescription, v2["id"]).status == "superseded"
    stale = _post(client, RX_OK, urgent=True, replaces_id=v1["id"])  # a stale tab edits v1 again
    assert stale.status_code == 409 and stale.json()["code"] == "conflict"
    assert _post(client, RX_OK, replaces_id=v2["id"]).status_code == 409
    assert db.query(Prescription).filter_by(replaces_id=v1["id"]).count() == 1
    v4 = _post(client, RX_OK, replaces_id=v3["id"])
    assert v4.status_code == 201 and v4.json()["version"] == 4


def test_a_rejected_branch_does_not_block_a_new_version(client, db):
    ph = pharmacist(client, db)
    v1 = _post(client, RX_OK, urgent=True).json()
    v2 = _post(client, RX_OK, replaces_id=v1["id"]).json()
    r = client.post(f"/pharmacy/prescriptions/{v2['id']}/reject", headers=ph, json={"comment": "no"})
    assert r.status_code == 200
    assert _post(client, RX_OK, replaces_id=v1["id"]).status_code == 201


def test_stop_is_audited_with_the_prescription_and_checks_access_first(client, db):
    rx = _post(client, RX_OK).json()
    h = login(client, DOC)
    assert client.patch(f"/prescriptions/{rx['id']}", headers=h, json={"active": False}).status_code == 200
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "update", AuditLog.resource == "prescription",
                                               AuditLog.resource_id == rx["id"], AuditLog.patient_id == "p-0001"))
    before = db.query(AuditLog).count()
    assert client.patch(f"/prescriptions/{rx['id']}", headers=h, json={"active": False}).status_code == 409
    assert db.query(AuditLog).count() == before  # a refused request writes no audit row
    assert client.patch(f"/prescriptions/{rx['id']}", headers=login(client, "nurse@medora.tn"),
                        json={"active": False}).status_code == 403
