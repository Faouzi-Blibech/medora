"""Pharmacist side (api 1.12 → Pharmacist): decisions, side effects, worklist, detail, summary, permissions."""

from datetime import date, timedelta

import pytest
from sqlalchemy import event, select

from app.models import AuditLog, MedDose, Prescription, PrescriptionReview
from app.services import schedule
from app.services.pharmacy.workflow import age_on
from app.ws.hub import Client, wants
from tests.helpers import login, pharmacist

DOC = "doctor@ward.tn"
RX_OK = {"patient_id": "p-0001", "care_plan": "",
         "items": [{"med": "Omeprazole 20 mg", "drug_id": "d-0041", "times": ["20:00"], "slot": 3, "days": 3}]}
RX_MAJOR = {"patient_id": "p-0002", "care_plan": "",
            "items": [{"med": "Ibuprofen 400 mg", "drug_id": "d-0018", "units_per_intake": 2,
                       "times": ["06:00", "12:00", "18:00", "23:00"], "days": 2}]}
RX_ALLERGY = {"patient_id": "p-0001", "care_plan": "",
              "items": [{"med": "Amoxicillin 1 g", "drug_id": "d-0003", "dose_mg": 1000,
                         "times": ["08:00", "14:00", "20:00"], "days": 7}]}
AZI = {"patient_id": "p-0001", "care_plan": "",
       "items": [{"med": "Azithromycin 250 mg", "drug_id": "d-0006", "units_per_intake": 2, "times": ["08:00"],
                  "days": 3}]}


def _rx(client, body, **extra):
    r = client.post("/prescriptions", headers=login(client, DOC), json={**body, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _act(client, h, rx_id, action, **body):
    return client.post(f"/pharmacy/prescriptions/{rx_id}/{action}", headers=h, json=body)


def _future(db, rx_id):
    return db.scalars(select(MedDose).where(MedDose.prescription_id == rx_id,
                                            MedDose.scheduled_at > schedule.now_utc())).all()


def _schedules(published):
    return [p for t, p, *_ in published if t.endswith("/schedule")]


def _frames(published):
    return [p["data"] for t, p, *_ in published if t == "ward/internal/ws" and p.get("type") == "prescription_status"]


def test_validate_without_checks_is_one_click(client, db, published, emitted):
    rx = _rx(client, RX_OK)
    assert _future(db, rx["id"]) == []
    ph = pharmacist(client, db)
    r = _act(client, ph, rx["id"], "validate")
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["status"], b["active"], b["reviewed_by_name"], b["review_comment"]) == (
        "validated", True, "Pharm Test", None)
    assert len(_future(db, rx["id"])) == 3
    assert any(d["time"] == "20:00" and "Omeprazole 20 mg" in d["meds"] for d in _schedules(published)[-1]["doses"])
    review = db.scalars(select(PrescriptionReview).where(PrescriptionReview.prescription_id == rx["id"])).one()
    assert (review.decision, review.checks_snapshot) == ("validated", [])
    assert ("prescription.review", {"prescription_id": rx["id"], "patient_id": "p-0001", "decision": "validated",
                                    "comment": None, "doctor_email": "doctor@ward.tn",
                                    "doctor_chat_id": None}) in emitted
    assert {"prescription_id": rx["id"], "patient_id": "p-0001", "status": "validated",
            "urgent": False} in _frames(published)
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "update", AuditLog.resource == "prescription",
                                               AuditLog.resource_id == rx["id"], AuditLog.role == "pharmacist"))


def test_checks_need_acknowledgement(client, db):
    rx = _rx(client, RX_MAJOR)
    assert [(c["code"], c["severity"]) for c in rx["checks"]] == [("max_daily_dose", "major")]
    ph = pharmacist(client, db)
    r = _act(client, ph, rx["id"], "validate", acknowledged=False)
    assert r.status_code == 422 and r.json()["code"] == "ack_required"
    assert db.get(Prescription, rx["id"]).status == "pending_pharmacy"
    r = _act(client, ph, rx["id"], "validate", acknowledged=True, comment="dose reduced on the ward")
    assert r.status_code == 200 and r.json()["review_comment"] == "dose reduced on the ward"


def test_second_decision_is_409(client, db):
    rx = _rx(client, RX_OK)
    ph = pharmacist(client, db)
    assert _act(client, ph, rx["id"], "validate").status_code == 200
    for action, body in (("validate", {}), ("reject", {"comment": "late"}), ("request-changes", {"comment": "x"})):
        r = _act(client, ph, rx["id"], action, **body)
        assert r.status_code == 409 and r.json()["code"] == "bad_status"


def test_request_changes_and_reject_need_a_comment(client, db, emitted):
    rx = _rx(client, RX_OK)
    ph = pharmacist(client, db)
    for bad in ({}, {"comment": ""}, {"comment": "   "}, {"comment": "x" * 501}):
        assert client.post(f"/pharmacy/prescriptions/{rx['id']}/request-changes", headers=ph,
                           json=bad).status_code == 422
        assert client.post(f"/pharmacy/prescriptions/{rx['id']}/reject", headers=ph, json=bad).status_code == 422
    r = _act(client, ph, rx["id"], "request-changes", comment="allergie pénicilline → azithromycine")
    assert (r.json()["status"], r.json()["review_comment"]) == (
        "changes_requested", "allergie pénicilline → azithromycine")
    assert emitted[-1][0] == "prescription.review" and emitted[-1][1]["decision"] == "changes_requested"


def test_reject_gives_nothing(client, db):
    rx = _rx(client, RX_OK)
    r = _act(client, pharmacist(client, db), rx["id"], "reject", comment="not indicated")
    assert (r.json()["status"], r.json()["active"]) == ("rejected", False)
    assert db.query(MedDose).filter_by(prescription_id=rx["id"]).count() == 0
    mine = client.get("/patients/p-0001/prescriptions", headers=login(client, DOC)).json()
    assert next(x for x in mine if x["id"] == rx["id"])["review_comment"] == "not indicated"


def test_urgent_then_rejected_cancels_future_doses(client, db, published):
    rx = _rx(client, RX_OK, urgent=True)
    assert len(_future(db, rx["id"])) == 3
    n = len(_schedules(published))
    r = _act(client, pharmacist(client, db), rx["id"], "reject", comment="wrong patient")
    assert (r.json()["status"], r.json()["active"]) == ("rejected", False)
    assert _future(db, rx["id"]) == [] and len(_schedules(published)) == n + 1
    assert all("Omeprazole 20 mg" not in d["meds"] for d in _schedules(published)[-1]["doses"])


def test_supersede_keeps_v1_until_v2_is_validated(client, db, published):
    ph = pharmacist(client, db)
    v1 = _rx(client, RX_OK)
    _act(client, ph, v1["id"], "validate")
    v1_doses = {d.id for d in _future(db, v1["id"])}
    twice = {**RX_OK, "items": [{**RX_OK["items"][0], "times": ["08:00", "20:00"]}]}
    v2 = _rx(client, twice, replaces_id=v1["id"])
    assert (v2["version"], v2["replaces_id"], v2["status"], v2["checks"]) == (2, v1["id"], "pending_pharmacy", [])
    assert db.get(Prescription, v1["id"]).status == "validated" and {d.id for d in _future(db, v1["id"])} == v1_doses
    assert _act(client, ph, v2["id"], "validate").status_code == 200
    old = db.get(Prescription, v1["id"])
    assert (old.status, old.active) == ("superseded", False)
    assert _future(db, v1["id"]) == [] and len(_future(db, v2["id"])) == 6
    assert {"prescription_id": v1["id"], "patient_id": "p-0001", "status": "superseded",
            "urgent": False} in _frames(published)


def test_rejected_v2_leaves_v1_running(client, db):
    ph = pharmacist(client, db)
    v1 = _rx(client, RX_OK)
    _act(client, ph, v1["id"], "validate")
    v2 = _rx(client, RX_OK, replaces_id=v1["id"])
    _act(client, ph, v2["id"], "reject", comment="keep the current one")
    assert db.get(Prescription, v1["id"]).status == "validated" and len(_future(db, v1["id"])) == 3


def test_demo_path_changes_then_resubmit(client, db):
    ph = pharmacist(client, db)
    v1 = _rx(client, RX_ALLERGY, override_reason="Severe infection; allergy history unclear")
    _act(client, ph, v1["id"], "request-changes", comment="allergie pénicilline → azithromycine")
    v2 = _rx(client, AZI, replaces_id=v1["id"])
    assert db.get(Prescription, v1["id"]).status == "superseded" and v2["checks"] == []
    assert _act(client, ph, v2["id"], "validate").status_code == 200  # no checks: one click
    d = client.get(f"/pharmacy/prescriptions/{v2['id']}", headers=ph).json()
    # newest first; inside one test transaction now() is constant, so the review id breaks the tie
    assert [(h["prescription_id"], h["decision"]) for h in d["history"]] == [
        (v2["id"], "validated"), (v1["id"], "changes_requested")]


def test_decision_after_the_doctor_moved_on_is_409(client, db):
    ph = pharmacist(client, db)
    rx = _rx(client, RX_OK)
    assert client.patch(f"/prescriptions/{rx['id']}", headers=login(client, DOC),
                        json={"active": False}).status_code == 200
    r = _act(client, ph, rx["id"], "validate")
    assert r.status_code == 409 and r.json()["code"] == "bad_status"
    old = _rx(client, RX_OK)
    _rx(client, RX_OK, replaces_id=old["id"])  # old never ran: superseded at once
    r = _act(client, ph, old["id"], "request-changes", comment="x")
    assert r.status_code == 409 and db.get(Prescription, old["id"]).status == "superseded"


def test_decisions_lock_the_prescription_row(client, db):
    rx = _rx(client, RX_OK)
    ph = pharmacist(client, db)
    seen: list[str] = []

    def spy(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    conn = db.connection()
    event.listen(conn, "before_cursor_execute", spy)
    try:
        assert _act(client, ph, rx["id"], "validate").status_code == 200
    finally:
        event.remove(conn, "before_cursor_execute", spy)
    assert any("FROM prescriptions" in s and "FOR UPDATE" in s for s in seen)


def test_worklist_order_projection_and_audit(client, db):
    normal = _rx(client, RX_OK)
    critical = _rx(client, RX_ALLERGY, override_reason="reason")
    urgent = _rx(client, {**RX_OK, "patient_id": "p-0003"}, urgent=True)
    ph = pharmacist(client, db)
    rows = client.get("/pharmacy/worklist", headers=ph).json()
    ids = {normal["id"], critical["id"], urgent["id"]}
    assert [w["prescription"]["id"] for w in rows if w["prescription"]["id"] in ids] == [
        urgent["id"], critical["id"], normal["id"]]
    w = next(w for w in rows if w["prescription"]["id"] == critical["id"])
    assert set(w) == {"prescription", "patient", "doctor_name", "checks", "urgent", "waiting_since", "max_severity"}
    assert w["patient"] == {"id": "p-0001", "name": "Amira Ben Salah",
                            "age": age_on(date(1972, 3, 14), schedule.today_local()), "sex": "F",
                            "ward": "Cardiology", "bed": "C-12", "allergies": ["penicillin"]}
    assert (w["max_severity"], w["doctor_name"], w["urgent"]) == ("critical", "Dr Trabelsi", False)
    audited = set(db.scalars(select(AuditLog.resource_id).where(AuditLog.action == "read",
                                                                AuditLog.resource == "prescription",
                                                                AuditLog.role == "pharmacist")))
    assert ids <= audited
    _act(client, ph, normal["id"], "request-changes", comment="x")
    changes = client.get("/pharmacy/worklist?status=changes_requested", headers=ph).json()
    assert changes and all(x["prescription"]["status"] == "changes_requested" for x in changes)
    assert normal["id"] in {x["prescription"]["id"] for x in client.get("/pharmacy/worklist?status=all",
                                                                       headers=ph).json()}
    assert client.get("/pharmacy/worklist?status=validated", headers=ph).status_code == 422


def test_review_detail(client, db):
    ph = pharmacist(client, db)
    v1 = _rx(client, RX_OK)
    _act(client, ph, v1["id"], "validate")
    v2 = _rx(client, {**RX_OK, "items": [{**RX_OK["items"][0], "times": ["08:00"]}]}, replaces_id=v1["id"])
    d = client.get(f"/pharmacy/prescriptions/{v2['id']}", headers=ph).json()
    assert set(d) == {"prescription", "patient", "doctor_name", "running", "checks", "history", "replaces"}
    assert d["replaces"]["id"] == v1["id"] and v1["id"] not in {r["id"] for r in d["running"]}
    assert "rx-0001" in {r["id"] for r in d["running"]} and d["checks"] == []
    assert [h["decision"] for h in d["history"]] == ["validated"]
    assert set(d["history"][0]) == {"id", "prescription_id", "pharmacist_id", "pharmacist_name", "decision",
                                    "comment", "checks_snapshot", "created_at"}
    assert db.scalar(select(AuditLog.id).where(AuditLog.resource == "prescription", AuditLog.resource_id == v2["id"],
                                               AuditLog.action == "read", AuditLog.patient_id == "p-0001"))
    assert client.get("/pharmacy/prescriptions/rx-9999", headers=ph).status_code == 404


def test_summary_counts(client, db):
    ph = pharmacist(client, db)
    before = client.get("/pharmacy/summary", headers=ph).json()
    assert {"pending", "urgent_pending", "critical_pending", "changes_requested"} <= set(before)
    _rx(client, RX_OK)
    _rx(client, RX_ALLERGY, override_reason="r")
    _rx(client, {**RX_OK, "patient_id": "p-0003"}, urgent=True)
    c = _rx(client, {**RX_OK, "patient_id": "p-0002"})
    _act(client, ph, c["id"], "request-changes", comment="x")
    after = client.get("/pharmacy/summary", headers=ph).json()
    assert {k: after[k] - before[k] for k in ("pending", "urgent_pending", "critical_pending",
                                              "changes_requested")} == {
        "pending": 3, "urgent_pending": 1, "critical_pending": 1, "changes_requested": 1}


def test_pharmacists_get_prescription_status_frames_only():
    ph = Client(ws=None, user_id="u-0008", role="pharmacist", ward=None)
    assert wants(ph, {"type": "prescription_status", "data": {}, "scope": {"ward": "Cardiology"}})
    for t in ("vital", "alert", "dose_event", "device_status", "call_nurse"):
        assert not wants(ph, {"type": t, "data": {}, "scope": {"ward": "Cardiology", "doctor_id": "u-0001"}})


def test_doses_start_at_validation_not_at_writing(db, seeded):
    midnight = schedule.local_to_utc(schedule.today_local(), "00:00")
    noon = schedule.local_to_utc(schedule.today_local(), "12:00")
    items = [{"med": "Z", "times": ["08:00", "20:00"], "slot": None, "days": 1}]
    late = Prescription(id="rx-9300", patient_id="p-0002", doctor_id="u-0001", items=items, care_plan="",
                        status="validated", active=True, urgent=False, created_at=midnight, reviewed_at=noon)
    urgent = Prescription(id="rx-9301", patient_id="p-0002", doctor_id="u-0001", items=items, care_plan="",
                          status="validated", active=True, urgent=True, created_at=midnight, reviewed_at=noon)
    db.add_all([late, urgent])
    db.flush()
    late_doses = schedule.rebuild_doses(db, late)
    assert len(late_doses) == 2 and all(d.scheduled_at >= noon for d in late_doses)
    urgent_doses = schedule.rebuild_doses(db, urgent)
    assert len(urgent_doses) == 2 and min(d.scheduled_at for d in urgent_doses) < noon  # started when written


def test_nurse_cannot_give_a_leftover_dose_of_a_cancelled_prescription(client, db):
    db.add(Prescription(id="rx-9302", patient_id="p-0001", doctor_id="u-0001", care_plan="", status="rejected",
                        active=False, urgent=True, items=[{"med": "Z", "times": ["08:00"], "slot": None, "days": 1}]))
    db.flush()
    db.add(MedDose(id="d-rej001", prescription_id="rx-9302", patient_id="p-0001",
                   scheduled_at=schedule.now_utc() - timedelta(hours=1), time_of_day="08:00", meds=["Z"], slot=None,
                   status="scheduled"))
    db.flush()
    r = client.post("/doses/d-rej001/given", headers=login(client, "nurse@ward.tn"))
    assert r.status_code == 409 and r.json()["code"] == "bad_status"
    assert db.get(MedDose, "d-rej001").status == "scheduled"


@pytest.mark.parametrize("email", ["doctor@ward.tn", "nurse@ward.tn", "admin@ward.tn", "patient@ward.tn"])
def test_only_pharmacists_use_pharmacy_routes(client, db, email):
    rx = _rx(client, RX_OK)
    h = login(client, email)
    base = f"/pharmacy/prescriptions/{rx['id']}"
    for method, url, body in (("GET", "/pharmacy/worklist", None), ("GET", "/pharmacy/summary", None),
                              ("GET", base, None), ("POST", f"{base}/validate", {}),
                              ("POST", f"{base}/request-changes", {"comment": "x"}),
                              ("POST", f"{base}/reject", {"comment": "x"})):
        assert client.request(method, url, headers=h, json=body).status_code == 403, (email, url)


def test_pharmacist_cannot_prescribe_or_read_records(client, db):
    ph = pharmacist(client, db)
    rx = _rx(client, RX_OK)
    assert client.post("/prescriptions", headers=ph, json=RX_OK).status_code == 403
    assert client.post("/prescriptions/check", headers=ph, json=RX_OK).status_code == 403
    assert client.patch(f"/prescriptions/{rx['id']}", headers=ph, json={"active": False}).status_code == 403
    for url in ("/patients", "/patients/p-0001", "/patients/p-0001/vitals", "/patients/p-0001/notes",
                "/patients/p-0001/prescriptions", "/patients/p-0001/doses"):
        assert client.get(url, headers=ph).status_code == 403, url
