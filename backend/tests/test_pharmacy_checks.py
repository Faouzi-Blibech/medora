"""The pure check engine (pharmacy spec §4): one test per rule, the fr/ar synonyms, the ×2 dose threshold."""

import json
import time

import pytest

from app.services.pharmacy.checks import (RULES_DIR, DrugInfo, PatientInfo, RunningItem, load_rules, norm,
                                          run_checks)
from app.services.pharmacy.formulary import FORMULARY, formulary_entries

DRUGS = {e["id"]: DrugInfo(id=e["id"], dci=e["dci"], brand_names=tuple(e["brand_names"]), atc_code=e["atc_code"],
                           unit_mg=e["unit_mg"], max_daily_mg=e["max_daily_mg"],
                           allergy_classes=tuple(e["allergy_classes"]),
                           interaction_groups=tuple(e["interaction_groups"]), high_alert=e["high_alert"])
         for e in formulary_entries()}
ADULT = PatientInfo(age=40)


def item(drug_id=None, med="X", times=("08:00",), **kw):
    return {"med": med, "drug_id": drug_id, "times": list(times), "units_per_intake": 1, **kw}


def codes(checks):
    return [(c.code, c.severity, c.item_index) for c in checks]


def test_allergy_english():
    checks = run_checks(PatientInfo(40, ("penicillin",)), [item("d-0003")], [], DRUGS)
    assert codes(checks) == [("allergy", "critical", 0)]
    assert checks[0].params == {"med": "X", "allergy": "penicillin", "class": "penicillin"}
    assert checks[0].drug_id == "d-0003"


@pytest.mark.parametrize("allergy", ["Pénicilline", "PENICILLINES", "بنسلين", "البنسلين", "حساسية من البنسلين",
                                     "allergie à la pénicilline", "beta-lactam"])
def test_allergy_french_arabic_and_free_text(allergy):
    assert codes(run_checks(PatientInfo(40, (allergy,)), [item("d-0003")], [], DRUGS)) == [("allergy", "critical", 0)]


def test_sulfa_allergy_flags_cotrimoxazole():
    checks = run_checks(PatientInfo(79, ("sulfa",)), [item("d-0011")], [], DRUGS)
    assert codes(checks) == [("allergy", "critical", 0)] and checks[0].params["class"] == "sulfonamide"


def test_no_false_allergy():
    assert run_checks(PatientInfo(40, ("latex",)), [item("d-0003")], [], DRUGS) == []
    assert run_checks(PatientInfo(40, ("penicillin",)), [item("d-0006")], [], DRUGS) == []


@pytest.mark.parametrize("allergy", ["Ibuprofen", "advil"])
def test_allergy_named_by_drug_or_brand(allergy):
    checks = run_checks(PatientInfo(40, (allergy,)), [item("d-0018")], [], DRUGS)
    assert codes(checks) == [("allergy", "critical", 0)] and checks[0].params["class"] == "ibuprofen"


def test_max_daily_dose_thresholds():
    four = ("06:00", "12:00", "18:00", "23:00")
    assert run_checks(ADULT, [item("d-0001", times=four, units_per_intake=2)], [], DRUGS) == []  # 4000 = max
    major = run_checks(ADULT, [item("d-0001", times=four, units_per_intake=3)], [], DRUGS)  # 6000
    assert codes(major) == [("max_daily_dose", "major", 0)]
    assert major[0].params == {"med": "X", "daily_mg": 6000.0, "max_daily_mg": 4000}
    assert codes(run_checks(ADULT, [item("d-0001", times=four, dose_mg=2000)], [], DRUGS)) == [
        ("max_daily_dose", "major", 0)]  # exactly 2x is still major
    assert codes(run_checks(ADULT, [item("d-0001", times=four, dose_mg=2500)], [], DRUGS)) == [
        ("max_daily_dose", "critical", 0)]  # 10000 > 2 x 4000
    assert run_checks(ADULT, [item("d-0001", times=four, dose_mg=1000, units_per_intake=3)], [], DRUGS) == []


def test_no_dose_check_without_mg_data():
    assert codes(run_checks(ADULT, [item("d-0014", times=("08:00", "20:00"))], [], DRUGS)) == [
        ("high_alert", "info", 0)]


def test_interaction_with_a_running_prescription():
    checks = run_checks(ADULT, [item("d-0018", med="Ibuprofen")], [RunningItem("rx-1", "Warfarin 5 mg", "d-0012")],
                        DRUGS)
    assert codes(checks) == [("interaction", "major", 0)]
    assert checks[0].params == {"med": "Ibuprofen", "groups": ["anticoagulant", "nsaid"], "note": "bleeding risk",
                                "with_med": "Warfarin 5 mg", "with_drug_id": "d-0012", "with_item_index": None,
                                "with_prescription_id": "rx-1"}


def test_interactions_inside_one_prescription():
    checks = run_checks(ADULT, [item("d-0021"), item("d-0045")], [], DRUGS)  # morphine + diazepam
    assert codes(checks) == [("interaction", "critical", 0), ("high_alert", "info", 0)]
    assert checks[0].params["with_item_index"] == 1
    assert codes(run_checks(ADULT, [item("d-0027"), item("d-0030")], [], DRUGS)) == [
        ("interaction", "critical", 0), ("high_alert", "info", 0)]  # KCl IV + spironolactone
    assert codes(run_checks(ADULT, [item("d-0047"), item("d-0022")], [], DRUGS)) == [("interaction", "major", 0)]
    assert run_checks(ADULT, [item("d-0022")], [], DRUGS) == []  # one serotonergic drug alone


def test_duplicate_therapy():
    same = run_checks(ADULT, [item("d-0001"), item("d-0002")], [], DRUGS)
    assert codes(same) == [("duplicate_therapy", "major", 0)] and same[0].params["reason"] == "same_dci"
    cls = run_checks(ADULT, [item("d-0018")], [RunningItem("rx-2", "Ketoprofen", "d-0020")], DRUGS)
    assert codes(cls) == [("duplicate_therapy", "major", 0)]
    assert (cls[0].params["reason"], cls[0].params["with_prescription_id"]) == ("same_atc_class", "rx-2")


def test_non_formulary_item():
    checks = run_checks(PatientInfo(40, ("penicillin",)), [item(None, med="Herbal tea")],
                        [RunningItem("rx-3", "Unknown", None)], DRUGS)
    assert codes(checks) == [("non_formulary", "moderate", 0)]
    assert (checks[0].drug_id, checks[0].params) == (None, {"med": "Herbal tea"})


def test_high_alert_and_elderly():
    assert codes(run_checks(ADULT, [item("d-0012")], [], DRUGS)) == [("high_alert", "info", 0)]
    assert codes(run_checks(PatientInfo(75), [item("d-0045")], [], DRUGS)) == [("elderly", "moderate", 0)]
    assert run_checks(PatientInfo(74), [item("d-0045")], [], DRUGS) == []
    assert run_checks(PatientInfo(None), [item("d-0045")], [], DRUGS) == []


def test_sorted_by_severity_then_item():
    checks = run_checks(PatientInfo(80, ("penicillin",)), [item("d-0045"), item("d-0003"), item("d-0021")], [],
                        DRUGS)
    assert codes(checks) == [("interaction", "critical", 0), ("allergy", "critical", 1), ("elderly", "moderate", 0),
                             ("high_alert", "info", 2)]
    assert set(checks[0].as_dict()) == {"code", "severity", "item_index", "drug_id", "params", "message"}
    assert checks == run_checks(PatientInfo(80, ("penicillin",)),
                                [item("d-0045"), item("d-0003"), item("d-0021")], [], DRUGS)  # deterministic


def test_under_20_ms():
    items = [item(d) for d in ("d-0001", "d-0003", "d-0006", "d-0012", "d-0018", "d-0021", "d-0045", "d-0047")]
    ids = list(DRUGS)
    running = [RunningItem(f"rx-{n}", "x", ids[n % len(ids)]) for n in range(30)]
    patient = PatientInfo(80, ("penicillin", "sulfa", "بنسلين"))
    run_checks(patient, items, running, DRUGS)  # warm the rule cache
    best = min(_timed(lambda: run_checks(patient, items, running, DRUGS)) for _ in range(5))
    assert best < 0.020


def _timed(fn) -> float:
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


def test_rule_files_are_consistent_and_labelled():
    rules = load_rules()
    classes = set(json.loads((RULES_DIR / "allergy_synonyms.v1.json").read_text("utf-8"))["classes"])
    entries = formulary_entries()
    assert all(set(e["allergy_classes"]) <= classes for e in entries)
    groups = {g for e in entries for g in e["interaction_groups"]}
    assert all(r.a in groups and r.b in groups and r.severity in ("critical", "major", "moderate")
               for r in rules.interactions)
    assert rules.elderly_dci <= {norm(e["dci"]) for e in entries} and rules.elderly_min_age == 75
    for name in ("allergy_synonyms.v1.json", "interactions.v1.json", "elderly_caution.v1.json"):
        assert "not a clinical reference" in json.loads((RULES_DIR / name).read_text("utf-8"))["note"]
    assert "not a clinical reference" in json.loads(FORMULARY.read_text("utf-8"))["note"]
    demo = {"amoxicillin", "azithromycin", "warfarin", "ibuprofen", "enoxaparin", "insulin glargine", "morphine",
            "potassium chloride", "metformin", "furosemide", "amlodipine", "paracetamol"}
    assert demo <= {norm(e["dci"]) for e in entries}
