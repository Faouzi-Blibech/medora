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


def test_name_matcher_normalises_spacing_accents_and_breaks_ties_by_strength():
    from types import SimpleNamespace as D

    from app.services.pharmacy.formulary import match_drug

    drugs = [D(**{k: e[k] for k in ("id", "dci", "brand_names", "strength")}) for e in formulary_entries()]
    for med in ("Paracetamol 500mg", "paracetamol 500 mg", "PARACÉTAMOL  500 MG", "Doliprane 500mg"):
        assert match_drug(med, drugs).id == "d-0001", med
    assert match_drug("Paracetamol 1 g", drugs).id == "d-0002"
    assert match_drug("Amoxicillin 500mg", drugs).id == "d-0004"
    assert match_drug("Amoxicillin 1g", drugs).id == "d-0003"
    assert match_drug("Amoxicillin + clavulanic acid 1 g/125 mg", drugs).id == "d-0005"
    assert match_drug("Héparine Choay 5 mL", drugs).id == "d-0015"
    assert match_drug("Unobtainium 5mg", drugs) is None


def test_formulary_file_shape_and_covers_the_seed():
    import json
    import re

    from app.services.pharmacy.formulary import FORMULARY, match_drug

    doc = json.loads(FORMULARY.read_text(encoding="utf-8"))
    assert "not a clinical reference" in doc["note"]
    required = {"id", "dci", "brand_names", "form", "strength", "unit_mg", "max_daily_mg", "atc_code",
                "allergy_classes", "interaction_groups", "high_alert", "min_stock"}
    for e in doc["drugs"]:
        assert re.fullmatch(r"d-\d{4}", e["id"]) and required <= set(e), e["id"]
    from types import SimpleNamespace as D

    drugs = [D(**{k: e[k] for k in ("id", "dci", "brand_names", "strength")}) for e in doc["drugs"]]
    seed = open("app/seed.py", encoding="utf-8").read()
    meds = re.findall(r'"med": "([^"]+)"', seed)
    assert meds and all(match_drug(m, drugs) for m in meds), meds


def test_name_matcher_respects_the_strength_in_the_text():
    from types import SimpleNamespace as D

    from app.services.pharmacy.formulary import match_drug

    drugs = [D(**{k: e[k] for k in ("id", "dci", "brand_names", "strength")}) for e in formulary_entries()]
    assert match_drug("Paracetamol 1000mg", drugs).id == "d-0002"
    assert match_drug("Paracetamol 1000 mg", drugs).id == "d-0002"
    assert match_drug("Paracetamol 0.5 g", drugs).id == "d-0001"
    assert match_drug("Paracetamol 650mg", drugs) is None  # no such strength: not the 500 mg tablet
    assert match_drug("Paracetamol 650 mg", drugs) is None
    assert match_drug("Doliprane 500mg", drugs).id == "d-0001"
    assert match_drug("Amoxicillin 750mg", drugs) is None
    assert match_drug("Levothyroxine 100 mcg", drugs).id == "d-0051"
    assert match_drug("Levothyroxine 0.1 mg", drugs).id == "d-0051"
    assert match_drug("Levothyroxine 50 µg", drugs) is None
    assert match_drug("Paracetamol", drugs) is not None  # no strength in the text: any strength will do


def test_name_matcher_treats_slash_and_plus_alike():
    from types import SimpleNamespace as D

    from app.services.pharmacy.formulary import match_drug

    drugs = [D(**{k: e[k] for k in ("id", "dci", "brand_names", "strength")}) for e in formulary_entries()]
    for med in ("Amoxicillin/clavulanic acid", "amoxicillin + clavulanic acid 1 g/125 mg",
                "Amoxicillin/Clavulanic acid 1g/125mg", "Augmentin"):
        assert match_drug(med, drugs).id == "d-0005", med
    assert match_drug("Amoxicillin 500mg", drugs).id == "d-0004"


def test_loader_updates_rule_fields_of_seeded_drugs_only(db):
    load_formulary(db)
    seeded = db.get(Drug, "d-0003")
    seeded.interaction_groups, seeded.max_daily_mg, seeded.high_alert = ["stale"], 1, True
    seeded.min_stock, seeded.active = 9, False
    own = Drug(id=new_id(db, "d"), dci="Amoxicillin", form="tablet", strength="1 g", brand_names=[], active=True,
               allergy_classes=[], interaction_groups=["mine"], high_alert=False, min_stock=1)
    db.add(own)
    db.flush()
    assert load_formulary(db) == 0
    entry = next(e for e in formulary_entries() if e["id"] == "d-0003")
    got = db.get(Drug, "d-0003")
    assert (got.interaction_groups, float(got.max_daily_mg), got.high_alert) == (
        entry["interaction_groups"], float(entry["max_daily_mg"]), entry["high_alert"])
    assert (got.min_stock, got.active) == (9, False)  # stock and the active flag stay the pharmacist's
    assert db.get(Drug, own.id).interaction_groups == ["mine"]  # a drug made through the API is never touched
