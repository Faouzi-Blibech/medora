"""Migration 0007 shapes (through create_all) and the formulary loader (pharmacy spec §3)."""

from app.ids import new_id
from app.models import Drug, Prescription, PrescriptionReview
from app.seed import seed
from app.services.pharmacy.formulary import formulary_entries, load_formulary


def test_formulary_file_has_about_fifty_unique_drugs():
    entries = formulary_entries()
    assert len(entries) == 51 and len({e["id"] for e in entries}) == 51


def test_formulary_loads_once_and_keeps_edits(db):
    assert load_formulary(db) == 51 and db.query(Drug).count() == 51
    amox = db.get(Drug, "d-0003")
    assert (amox.dci, amox.allergy_classes, float(amox.unit_mg), amox.active) == (
        "Amoxicillin", ["penicillin", "beta_lactam"], 1000.0, True)
    amox.min_stock = 7
    db.flush()
    assert load_formulary(db) == 0 and db.get(Drug, "d-0003").min_stock == 7  # a pharmacist's edit wins
    assert int(new_id(db, "d")[2:]) > 51  # the shared `d` sequence is past the file's ids


def test_prescription_defaults(db, seeded):
    rx = Prescription(id="rx-9400", patient_id="p-0002", doctor_id="u-0001", items=[], care_plan="", active=True)
    db.add(rx)
    db.flush()
    db.refresh(rx)
    assert (rx.status, rx.urgent, rx.version, rx.checks, rx.replaces_id, rx.reviewed_by) == (
        "validated", False, 1, [], None, None)


def test_review_row(db, seeded):
    db.add(Prescription(id="rx-9401", patient_id="p-0002", doctor_id="u-0001", items=[], care_plan="",
                        active=False, status="pending_pharmacy"))
    db.flush()
    db.add(PrescriptionReview(id="pr-9401", prescription_id="rx-9401", pharmacist_id="u-0004",
                              decision="rejected", comment="no", checks_snapshot=[{"code": "allergy"}]))
    db.flush()
    r = db.get(PrescriptionReview, "pr-9401")
    assert (r.decision, r.checks_snapshot, r.created_at is not None) == ("rejected", [{"code": "allergy"}], True)


def test_seed_loads_the_formulary(db):
    seed(db)
    assert db.query(Drug).count() == 51
    seed(db)  # second run: the "already seeded" path loads nothing twice
    assert db.query(Drug).count() == 51
