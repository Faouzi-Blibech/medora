"""Stock (api 1.12 → Dispensing and stock): receipts, adjustments, the stock view, reorder, FEFO, alerts."""

from datetime import timedelta

from sqlalchemy import select

from app.models import AuditLog, StockLot, StockMovement
from app.services.pharmacy.stock import pick_lot
from app.services.schedule import today_local
from tests.helpers import login, make_drug, make_lot, pharmacist


def _day(n: int) -> str:
    return (today_local() + timedelta(days=n)).isoformat()


def test_receipt_creates_then_tops_up_a_lot(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    body = {"drug_id": drug.id, "lot_number": " T-1 ", "expiry_date": _day(200), "quantity": 40}
    r = client.post("/pharmacy/stock/receipts", headers=ph, json=body)
    assert r.status_code == 201, r.text
    lot = r.json()
    assert (lot["lot_number"], lot["quantity"], lot["expired"], lot["expiring"]) == ("T-1", 40, False, False)
    again = client.post("/pharmacy/stock/receipts", headers=ph, json={**body, "quantity": 10}).json()
    assert (again["id"], again["quantity"]) == (lot["id"], 50)
    moves = db.scalars(select(StockMovement).where(StockMovement.lot_id == lot["id"])).all()
    assert sorted((m.reason, m.delta) for m in moves) == [("receipt", 10), ("receipt", 40)]
    assert db.query(AuditLog).filter(AuditLog.resource == "stock_movement",
                                     AuditLog.resource_id.in_([m.id for m in moves])).count() == 2


def test_receipt_errors(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    base = {"drug_id": drug.id, "lot_number": "T-2", "expiry_date": _day(100), "quantity": 5}
    assert client.post("/pharmacy/stock/receipts", headers=ph, json=base).status_code == 201
    r = client.post("/pharmacy/stock/receipts", headers=ph, json={**base, "expiry_date": _day(101)})
    assert r.status_code == 409 and r.json()["code"] == "conflict"
    assert client.post("/pharmacy/stock/receipts", headers=ph,
                       json={**base, "lot_number": "T-3", "expiry_date": _day(-1)}).status_code == 422
    assert client.post("/pharmacy/stock/receipts", headers=ph, json={**base, "quantity": 0}).status_code == 422
    assert client.post("/pharmacy/stock/receipts", headers=ph, json={**base, "drug_id": "d-9999"}).status_code == 404


def test_adjustment_never_goes_negative(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    lot = make_lot(db, drug, "A", 100, 50)
    r = client.post("/pharmacy/stock/adjustments", headers=ph,
                    json={"lot_id": lot.id, "delta": -20, "reason": "adjustment", "comment": "inventory count"})
    assert r.status_code == 200 and r.json()["quantity"] == 30
    before = db.query(StockMovement).count()
    r = client.post("/pharmacy/stock/adjustments", headers=ph,
                    json={"lot_id": lot.id, "delta": -31, "reason": "adjustment", "comment": "x"})
    assert r.status_code == 409 and r.json()["code"] == "insufficient_stock" and r.json()["drug_id"] == drug.id
    assert db.get(StockLot, lot.id).quantity == 30 and db.query(StockMovement).count() == before
    for bad in ({"delta": 5, "reason": "expired", "comment": "x"}, {"delta": 0, "reason": "adjustment", "comment": "x"},
                {"delta": -1, "reason": "adjustment"}, {"delta": -1, "reason": "lost", "comment": "x"}):
        assert client.post("/pharmacy/stock/adjustments", headers=ph,
                           json={"lot_id": lot.id, **bad}).status_code == 422, bad
    assert client.post("/pharmacy/stock/adjustments", headers=ph,
                       json={"lot_id": "lot-9999", "delta": -1, "reason": "return", "comment": "x"}).status_code == 404


def test_stock_view_flags_and_reorder(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db, min_stock=10)
    make_lot(db, drug, "OK", 100, 5)
    make_lot(db, drug, "SOON", 10, 3)
    make_lot(db, drug, "DEAD", -1, 7)
    make_lot(db, drug, "EMPTY", 200, 0)
    row = next(r for r in client.get("/pharmacy/stock", headers=ph).json() if r["drug_id"] == drug.id)
    assert (row["on_hand"], row["min_stock"], row["low"], row["expiring"], row["expired"]) == (8, 10, True, True, True)
    assert sorted(lot["lot_number"] for lot in row["lots"]) == ["DEAD", "OK", "SOON"]
    re = next(r for r in client.get("/pharmacy/stock/reorder", headers=ph).json() if r["drug_id"] == drug.id)
    assert (re["on_hand"], re["suggested_quantity"]) == (8, 12)
    full = make_drug(db, dci="Fullamycin", min_stock=1)
    make_lot(db, full, "F", 100, 5)
    assert full.id not in {r["drug_id"] for r in client.get("/pharmacy/stock/reorder", headers=ph).json()}


def test_summary_has_stock_alerts(client, db):
    ph = pharmacist(client, db)
    before = client.get("/pharmacy/summary", headers=ph).json()
    drug = make_drug(db, min_stock=10)
    make_lot(db, drug, "SOON", 5, 2)
    after = client.get("/pharmacy/summary", headers=ph).json()
    assert (after["low_stock"] - before["low_stock"], after["expiring"] - before["expiring"]) == (1, 1)


def test_stock_roles(client, db):
    for email in ("doctor@medora.tn", "nurse@medora.tn", "patient@medora.tn"):
        assert client.get("/pharmacy/stock", headers=login(client, email)).status_code == 403
    admin = login(client, "admin@medora.tn")
    assert client.get("/pharmacy/stock", headers=admin).status_code == 200
    assert client.get("/pharmacy/stock/reorder", headers=admin).status_code == 200
    body = {"drug_id": "d-0001", "lot_number": "X", "expiry_date": _day(10), "quantity": 1}
    assert client.post("/pharmacy/stock/receipts", headers=admin, json=body).status_code == 403
    assert client.post("/pharmacy/stock/adjustments", headers=admin,
                       json={"lot_id": "lot-x", "delta": 1, "reason": "return", "comment": "x"}).status_code == 403


def test_fefo_pick(db, seeded):
    drug = make_drug(db)
    late = make_lot(db, drug, "LATE", 300, 10)
    early = make_lot(db, drug, "EARLY", 30, 10)
    small = make_lot(db, drug, "SMALL", 20, 1)
    dead = make_lot(db, drug, "DEAD", -1, 10)
    lots = [late, early, small, dead]
    on = today_local()
    assert pick_lot(lots, 1, on) is small  # earliest expiry that holds the line
    assert pick_lot(lots, 2, on) is early  # SMALL cannot hold 2; DEAD is expired
    assert pick_lot(lots, 2, on, {late.id: 10, early.id: 1, small.id: 1, dead.id: 10}) is late  # what's left counts
    assert pick_lot(lots, 11, on) is None
