"""Seed (pharmacy spec §7): pharmacist account, formulary, mapped and validated seed prescription, critical demo."""

from sqlalchemy import select

from app.models import Drug, MedDose, Prescription, PrescriptionReview, Staff, User
from app.seed import DEMO_CARE_PLAN, seed
from app.services.pharmacy.backfill import backfill_drug_ids
from app.services.pharmacy.formulary import match_drug


def test_seed_pharmacist_and_prescriptions(db):
    seed(db)
    ph = db.get(User, "u-0008")
    assert (ph.email, ph.name, ph.role, ph.status) == ("pharmacist@medora.tn", "Pharm. Salma", "pharmacist", "active")
    assert db.get(Staff, "u-0008") is None
    rx = db.get(Prescription, "rx-0001")
    assert [i["drug_id"] for i in rx.items] == ["d-0032", "d-0001"]
    assert (rx.status, rx.reviewed_by) == ("validated", "u-0008")
    assert db.query(PrescriptionReview).filter_by(prescription_id="rx-0001", decision="validated").count() == 1
    demo = db.scalars(select(Prescription).where(Prescription.care_plan == DEMO_CARE_PLAN)).one()
    assert (demo.patient_id, demo.status, demo.urgent, demo.active) == ("p-0001", "pending_pharmacy", False, False)
    assert [(c["code"], c["severity"]) for c in demo.checks] == [("allergy", "critical")] and demo.override_reason
    assert db.query(MedDose).filter_by(prescription_id=demo.id).count() == 0


def test_seed_is_idempotent_with_pharmacy(db):
    seed(db)
    seed(db)
    assert db.query(Drug).count() == 51
    assert len(db.scalars(select(Prescription).where(Prescription.care_plan == DEMO_CARE_PLAN)).all()) == 1
    assert db.query(PrescriptionReview).filter_by(prescription_id="rx-0001").count() == 1


def test_match_drug(db):
    seed(db)
    drugs = list(db.scalars(select(Drug)))

    def m(med):
        d = match_drug(med, drugs)
        return d.id if d else None

    assert m("Amlodipine 5mg") == "d-0032"
    assert m("paracetamol 1 g") == "d-0002"
    assert m("Doliprane") == "d-0001"
    assert m("Aspirin") == "d-0016"
    assert m("Zzz 5mg") is None


def test_backfill_fills_only_missing_keys(db):
    seed(db)
    db.add(Prescription(id="rx-9500", patient_id="p-0002", doctor_id="u-0001", care_plan="", active=False,
                        status="stopped", items=[{"med": "Paracetamol 500mg", "times": ["08:00"]},
                                                 {"med": "Herbal tea", "times": ["08:00"]}]))
    db.flush()
    assert backfill_drug_ids(db) == 1
    assert [i["drug_id"] for i in db.get(Prescription, "rx-9500").items] == ["d-0001", None]
    assert backfill_drug_ids(db) == 0


def test_seed_pharmacist_sees_the_critical_demo_first(client):
    from tests.helpers import login

    rows = client.get("/pharmacy/worklist", headers=login(client, "pharmacist@medora.tn")).json()
    assert rows[0]["prescription"]["care_plan"] == DEMO_CARE_PLAN and rows[0]["max_severity"] == "critical"
