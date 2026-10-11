"""Migration 0010 invariants through create_all: no negative lot, one lot number per drug, append-only movements,
one line per dose, a cancelled dose detaches its line."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import Dispensation, DispensationLine, MedDose, Prescription, StockLot, StockMovement


def _lot(db, lot_id="lot-t1", number="T1", qty=5):
    db.add(StockLot(id=lot_id, drug_id="d-0001", lot_number=number, expiry_date=date.today() + timedelta(days=90),
                    quantity=qty))
    db.flush()


def test_lot_quantity_cannot_go_negative(db, seeded):
    with pytest.raises(IntegrityError), db.begin_nested():
        _lot(db, qty=-1)


def test_one_lot_number_per_drug(db, seeded):
    _lot(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        _lot(db, lot_id="lot-t2")


def test_movements_are_append_only(db, seeded):
    _lot(db)
    db.add(StockMovement(id="sm-t1", drug_id="d-0001", lot_id="lot-t1", delta=5, reason="receipt",
                         by_user_id="u-0004"))
    db.flush()
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(update(StockMovement).where(StockMovement.id == "sm-t1").values(delta=6))
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(delete(StockMovement).where(StockMovement.id == "sm-t1"))


def _dose(db, dose_id="d-t00001"):
    """A prescription, one dose and an empty dispensation to hang lines on."""
    db.add(Prescription(id="rx-t1", patient_id="p-0001", doctor_id="u-0001", items=[], care_plan="", active=True))
    db.flush()
    db.add(MedDose(id=dose_id, prescription_id="rx-t1", patient_id="p-0001", scheduled_at=datetime.now(UTC),
                   time_of_day="20:00", meds=["X"], slot=None))
    db.add(Dispensation(id="disp-t1", ward="Cardiology", round_date=date.today(), round_time="20:00", status="sent",
                        prepared_by="u-0004"))
    db.flush()


def test_one_line_per_dose_and_cancel_detaches(db, seeded):
    _dose(db)
    db.add(DispensationLine(id="dl-t1", dispensation_id="disp-t1", dose_id="d-t00001", patient_id="p-0001",
                            drug_id=None, lot_id=None, quantity=1, med="X"))
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(DispensationLine(id="dl-t2", dispensation_id="disp-t1", dose_id="d-t00001", patient_id="p-0001",
                                drug_id=None, lot_id=None, quantity=1, med="X"))
        db.flush()
    db.execute(delete(MedDose).where(MedDose.id == "d-t00001"))
    db.expire_all()
    assert db.get(DispensationLine, "dl-t1").dose_id is None
