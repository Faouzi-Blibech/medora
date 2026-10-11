"""Dispensing (api 1.12 → Dispensing and stock): round view, FEFO transaction, idempotence, nurse receipt."""

from sqlalchemy import select

from app.models import Dispensation, DispensationLine, MedDose, Prescription, StockLot, StockMovement
from app.services import schedule
from tests.helpers import login, make_drug, make_lot, pharmacist

DOC = "doctor@ward.tn"


def _urgent(client, patient_id, drug=None, units=1, times=("22:00",)):
    item = {"med": f"{drug.dci} {drug.strength}" if drug else "Herbal tea", "drug_id": drug.id if drug else None,
            "units_per_intake": units, "times": list(times), "days": 2}
    r = client.post("/prescriptions", headers=login(client, DOC),
                    json={"patient_id": patient_id, "care_plan": "", "items": [item], "urgent": True})
    assert r.status_code == 201, r.text
    return r.json()


def _first(db, rx_id) -> MedDose:
    return min(db.scalars(select(MedDose).where(MedDose.prescription_id == rx_id)), key=lambda d: d.scheduled_at)


def _round(db, rx_id) -> tuple[str, str, str]:
    d = _first(db, rx_id)
    return d.scheduled_at.astimezone(schedule.TUNIS).date().isoformat(), d.time_of_day, d.id


def _dispense(client, h, day, hhmm, lines, ward="Cardiology"):
    return client.post("/pharmacy/dispensations", headers=h,
                       json={"ward": ward, "date": day, "round_time": hhmm, "lines": lines})


def test_round_view_lists_due_doses_with_a_fefo_suggestion(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    make_lot(db, drug, "OLD", 40, 10)
    make_lot(db, drug, "NEW", 200, 10)
    make_lot(db, drug, "DEAD", -1, 10)
    rx = _urgent(client, "p-0001", drug, units=2)
    day, hhmm, dose_id = _round(db, rx["id"])
    rows = client.get("/pharmacy/dispensing", headers=ph, params={"date": day, "round": hhmm, "ward": "Cardiology"})
    assert rows.status_code == 200, rows.text
    w = rows.json()
    assert [x["ward"] for x in w] == ["Cardiology"]
    p = w[0]["patients"][0]
    assert (p["id"], p["name"], p["bed"]) == ("p-0001", "Amira Ben Salah", "C-12")
    d = next(x for x in p["doses"] if x["dose_id"] == dose_id)
    assert (d["drug_id"], d["quantity"], d["suggested_lot"]["lot_number"], d["on_hand"], d["dispensed"]) == (
        drug.id, 2, "OLD", 20, False)
    assert set(d) == {"dose_id", "prescription_id", "med", "drug_id", "quantity", "suggested_lot", "on_hand",
                      "dispensed"}


def test_dispense_decrements_the_fefo_lot(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    old = make_lot(db, drug, "OLD", 40, 10)
    make_lot(db, drug, "NEW", 200, 10)
    rx = _urgent(client, "p-0001", drug, units=2)
    day, hhmm, dose_id = _round(db, rx["id"])
    r = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}])
    assert r.status_code == 201, r.text
    disp = r.json()
    assert (disp["status"], disp["prepared_by_name"], disp["round_time"]) == ("sent", "Pharm Test", hhmm)
    assert (disp["lines"][0]["lot_number"], disp["lines"][0]["quantity"], disp["lines"][0]["bed"]) == ("OLD", 2, "C-12")
    assert db.get(StockLot, old.id).quantity == 8
    sm = db.scalars(select(StockMovement).where(StockMovement.lot_id == old.id)).one()
    assert (sm.reason, sm.delta, sm.ref_id) == ("dispense", -2, disp["id"])
    view = client.get("/pharmacy/dispensing", headers=ph, params={"date": day, "round": hhmm}).json()
    assert next(x for w in view for p in w["patients"] for x in p["doses"] if x["dose_id"] == dose_id)["dispensed"]


def test_an_explicit_lot_is_used(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    make_lot(db, drug, "OLD", 40, 10)
    new = make_lot(db, drug, "NEW", 200, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    assert _dispense(client, ph, day, hhmm, [{"dose_id": dose_id, "lot_id": new.id}]).status_code == 201
    assert db.get(StockLot, new.id).quantity == 9


def test_insufficient_stock_writes_nothing(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    lot = make_lot(db, drug, "OLD", 40, 1)
    rx = _urgent(client, "p-0001", drug, units=2)
    day, hhmm, dose_id = _round(db, rx["id"])
    before = db.query(Dispensation).count()
    r = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}])
    assert r.status_code == 409 and r.json()["code"] == "insufficient_stock" and r.json()["drug_id"] == drug.id
    assert db.get(StockLot, lot.id).quantity == 1 and db.query(Dispensation).count() == before
    assert db.query(StockMovement).filter_by(drug_id=drug.id).count() == 0


def test_already_dispensed(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    lot = make_lot(db, drug, "OLD", 40, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    assert _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}]).status_code == 201
    r = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}])
    assert r.status_code == 409 and r.json()["code"] == "already_dispensed"
    assert db.get(StockLot, lot.id).quantity == 9


def test_lines_share_a_lot_without_going_negative(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    old = make_lot(db, drug, "OLD", 40, 3)
    new = make_lot(db, drug, "NEW", 200, 10)
    a = _urgent(client, "p-0001", drug, units=2)
    b = _urgent(client, "p-0002", drug, units=2)
    day, hhmm, da = _round(db, a["id"])
    _, _, dbb = _round(db, b["id"])
    r = _dispense(client, ph, day, hhmm, [{"dose_id": da}, {"dose_id": dbb}])
    assert r.status_code == 201, r.text
    assert [ln["lot_number"] for ln in r.json()["lines"]] == ["OLD", "NEW"]
    assert (db.get(StockLot, old.id).quantity, db.get(StockLot, new.id).quantity) == (1, 8)


def test_lines_outside_the_round_are_422(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    make_lot(db, drug, "OLD", 40, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    assert _dispense(client, ph, day, "06:00", [{"dose_id": dose_id}]).status_code == 422
    assert _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}], ward="Internal Medicine").status_code == 422
    assert _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}, {"dose_id": dose_id}]).status_code == 422
    assert _dispense(client, ph, day, hhmm, [{"dose_id": "d-999999"}]).status_code == 404


def test_non_formulary_dose_is_sent_without_stock(client, db):
    ph = pharmacist(client, db)
    rx = _urgent(client, "p-0001")
    day, hhmm, dose_id = _round(db, rx["id"])
    r = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}])
    assert r.status_code == 201 and (r.json()["lines"][0]["drug_id"], r.json()["lines"][0]["lot_id"]) == (None, None)


def test_nurse_lists_and_receives_her_ward_delivery(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    make_lot(db, drug, "OLD", 40, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    disp = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}]).json()
    nurse, other = login(client, "nurse@ward.tn"), login(client, "nurse2@ward.tn")
    assert disp["id"] in {d["id"] for d in client.get("/dispensations", headers=nurse, params={"date": day}).json()}
    assert client.get("/dispensations", headers=other, params={"date": day, "ward": "Cardiology"}).status_code == 403
    assert client.post(f"/dispensations/{disp['id']}/receive", headers=other).status_code == 403
    r = client.post(f"/dispensations/{disp['id']}/receive", headers=nurse)
    assert r.status_code == 200 and (r.json()["status"], r.json()["received_by"]) == ("received", "u-0002")
    assert client.post(f"/dispensations/{disp['id']}/receive", headers=nurse).json()["status"] == "received"
    assert disp["id"] in {d["id"] for d in client.get("/dispensations", headers=ph, params={"date": day}).json()}


def test_dose_pharmacy_field(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    make_lot(db, drug, "OLD", 40, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    nurse = login(client, "nurse@ward.tn")

    def status():
        rows = client.get("/patients/p-0001/doses", headers=nurse, params={"date": day}).json()
        return {r["id"]: r["pharmacy"] for r in rows}

    assert status()[dose_id] == "none"
    disp = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}]).json()
    assert status()[dose_id] == "sent"
    client.post(f"/dispensations/{disp['id']}/receive", headers=nurse)
    assert status()[dose_id] == "received" and set(status().values()) <= {"none", "sent", "received"}


def test_rebuild_after_dispensing_keeps_or_detaches_the_line(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    make_lot(db, drug, "OLD", 40, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    disp = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}]).json()
    assert client.post(f"/pharmacy/prescriptions/{rx['id']}/validate", headers=ph, json={}).status_code == 200
    assert db.get(MedDose, dose_id) is not None  # validating an urgent prescription rebuilds it: same ids
    assert client.patch(f"/prescriptions/{rx['id']}", headers=login(client, DOC),
                        json={"active": False}).status_code == 200
    db.expire_all()
    line = db.scalars(select(DispensationLine).where(DispensationLine.dispensation_id == disp["id"])).one()
    assert line.dose_id is None and db.get(MedDose, dose_id) is None


def test_rebuild_keeps_ids_of_matching_future_doses(db, seeded):
    rx = Prescription(id="rx-9600", patient_id="p-0002", doctor_id="u-0001", care_plan="", active=True,
                      items=[{"med": "Z", "times": ["23:59"], "slot": None, "days": 2}])
    db.add(rx)
    db.flush()
    first = {d.id for d in schedule.rebuild_doses(db, rx)}
    assert {d.id for d in schedule.rebuild_doses(db, rx)} == first


def test_dispensing_roles(client, db):
    assert client.get("/pharmacy/dispensing", headers=login(client, DOC), params={"round": "20:00"}).status_code == 403
    assert client.post("/pharmacy/dispensations", headers=login(client, "nurse@ward.tn"),
                       json={"ward": "Cardiology", "date": "2026-10-10", "round_time": "20:00",
                             "lines": [{"dose_id": "d-000001"}]}).status_code == 403
    assert client.get("/dispensations", headers=login(client, "patient@ward.tn")).status_code == 403


def test_inactive_prescription_dose_is_not_dispensable(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    lot = make_lot(db, drug, "OLD", 40, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    db.get(Prescription, rx["id"]).active = False  # stopped; a leftover dose row is still around
    db.flush()
    r = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}])
    assert r.status_code == 409 and r.json()["code"] == "bad_status"
    assert db.get(StockLot, lot.id).quantity == 10


def test_expired_lots_are_never_used(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    dead = make_lot(db, drug, "DEAD", -1, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    r = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}])  # only an expired lot: no stock
    assert r.status_code == 409 and r.json()["code"] == "insufficient_stock"
    assert _dispense(client, ph, day, hhmm, [{"dose_id": dose_id, "lot_id": dead.id}]).status_code == 422
    assert db.get(StockLot, dead.id).quantity == 10
