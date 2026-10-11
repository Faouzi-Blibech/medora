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
                           interaction_groups=tuple(e["interaction_groups"]), high_alert=e["high_alert"],
                           strength=e["strength"])
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
    stems = json.loads((RULES_DIR / "allergy_synonyms.v1.json").read_text("utf-8"))["stems"]
    assert set(stems) <= classes and all(len(norm(t)) >= 5 for ts in stems.values() for t in ts)
    demo = {"amoxicillin", "azithromycin", "warfarin", "ibuprofen", "enoxaparin", "insulin glargine", "morphine",
            "potassium chloride", "metformin", "furosemide", "amlodipine", "paracetamol"}
    assert demo <= {norm(e["dci"]) for e in entries}


def test_clopidogrel_maintenance_dose_is_the_daily_max():
    checks = run_checks(ADULT, [item("d-0017", times=("08:00", "20:00"))], [], DRUGS)  # 75 mg x 2
    assert [(c.code, c.severity) for c in checks] == [("max_daily_dose", "major")]
    assert checks[0].params["max_daily_mg"] == 75


@pytest.mark.parametrize("allergy", ["aspirin", "Aspirine", "أسبرين"])
def test_aspirin_allergy_flags_ibuprofen_and_aspirin_flags_nsaid_allergy(allergy):
    checks = run_checks(PatientInfo(40, (allergy,)), [item("d-0018")], [], DRUGS)
    assert codes(checks) == [("allergy", "critical", 0)] and checks[0].params["class"] == "nsaid"
    assert ("allergy", "critical", 0) in codes(run_checks(PatientInfo(40, ("ibuprofen allergy nsaid",)),
                                                          [item("d-0016")], [], DRUGS))


@pytest.mark.parametrize("potentiator", ["d-0040", "d-0010"])  # amiodarone, metronidazole
def test_warfarin_potentiators_interact(potentiator):
    checks = run_checks(ADULT, [item("d-0012"), item(potentiator)], [], DRUGS)
    hit = [c for c in checks if c.code == "interaction" and "warfarin_potentiator" in c.params["groups"]]
    assert len(hit) == 1 and hit[0].severity == "major"


# ---- fix round: natural-language allergies, Arabic, free text, dose maths, more rules ----

def flagged(allergy, drug_id):
    return any(c.code == "allergy" for c in run_checks(PatientInfo(40, (allergy,)), [item(drug_id)], [], DRUGS))


@pytest.mark.parametrize("allergy,drug_id", [
    ("ibuprofen allergy", "d-0018"), ("ibuprofène", "d-0018"), ("allergie à l'ibuprofène", "d-0018"),
    ("allergic to Advil", "d-0018"), ("ceftriaxone allergy", "d-0008"), ("Clamoxyl 500", "d-0004"),
    ("warfarine", "d-0012"), ("allergie à la warfarine", "d-0012"), ("allergic to Coumadine", "d-0012"),
    ("sulfaméthoxazole", "d-0011"), ("allergie au paracétamol", "d-0001"), ("Doliprane", "d-0002"),
    ("héparine", "d-0014"), ("insuline", "d-0023"), ("allergie à l'amoxicilline + acide clavulanique", "d-0005"),
])
def test_allergy_named_in_a_sentence_fr_en(allergy, drug_id):
    assert flagged(allergy, drug_id), allergy


@pytest.mark.parametrize("allergy,drug_id", [
    ("ampicillin", "d-0003"), ("ampicilline", "d-0003"), ("amoxicillines", "d-0003"), ("penicilin", "d-0003"),
    ("pénicillinique", "d-0003"), ("PCN", "d-0003"), ("oracilline", "d-0003"), ("Penicillins", "d-0003"),
    ("cotrimoxazole", "d-0011"), ("co-trimoxazole", "d-0011"), ("septrin", "d-0011"), ("bactrim", "d-0011"),
    ("sulfamides", "d-0011"), ("érythromycine", "d-0006"), ("erythromycin", "d-0007"),
    ("ciprofloxacine", "d-0009"), ("quinolones", "d-0009"), ("cefalosporine", "d-0008"),
    ("céphalosporines", "d-0008"), ("AINS", "d-0016"), ("AINS", "d-0019"), ("aspirin", "d-0019"),
    ("anti-inflammatoires non stéroïdiens", "d-0020"), ("allergie aux bêta-lactamines", "d-0008"),
])
def test_allergy_synonym_and_stem_variants(allergy, drug_id):
    assert flagged(allergy, drug_id), allergy


@pytest.mark.parametrize("allergy,drug_id", [
    ("حساسية للبنسلين", "d-0003"), ("للبنسلين", "d-0003"), ("بالبنسلين", "d-0003"), ("وبالبنسلين", "d-0003"),
    ("بنسيلين", "d-0003"), ("البنسيلين", "d-0003"), ("حساسية من البنسيلين", "d-0005"),
    ("الباراسيتامول", "d-0001"), ("حساسية للباراسيتامول", "d-0002"), ("إيبوبروفين", "d-0018"),
    ("حساسيه من الايبوبروفين", "d-0018"), ("ديكلوفيناك", "d-0019"), ("وارفارين", "d-0012"),
    ("الأسبرين", "d-0016"), ("للأسبرين", "d-0018"), ("حساســـية للبنسلين", "d-0003"),  # tatweel
    ("حَسَاسِيَّة لِلْبِنِسِلِين", "d-0003"),  # harakat
    ("السلفا", "d-0011"), ("للسلفا", "d-0011"),
])
def test_arabic_allergy_phrasing(allergy, drug_id):
    assert flagged(allergy, drug_id), allergy


def test_arabic_normalisation_and_no_false_arabic_hits():
    assert norm("أإآ") == "ااا" and norm("ى") == "ي" and norm("ة") == "ه" and norm("بـنـسـلـين") == "بنسلين"
    assert not flagged("حساسية للبنسلين", "d-0006") and not flagged("الباراسيتامول", "d-0018")
    assert not flagged("latex", "d-0018") and not flagged("حساسية من الغبار", "d-0001")


def test_allergy_false_positives_stay_quiet():
    assert not flagged("paracetamol", "d-0018") and not flagged("ibuprofen", "d-0001")
    assert not flagged("peanuts", "d-0012") and not flagged("", "d-0012") and not flagged("  ", "d-0003")


def _groups(checks):
    return sorted((c.params["groups"], c.severity) for c in checks if c.code == "interaction")


@pytest.mark.parametrize("a_id,b_id", [("d-0018", "d-0012"), ("d-0033", "d-0035"), ("d-0016", "d-0018"),
                                       ("d-0040", "d-0039"), ("d-0012", "d-0010"), ("d-0012", "d-0011"),
                                       ("d-0012", "d-0009"), ("d-0012", "d-0006"), ("d-0012", "d-0040"),
                                       ("d-0021", "d-0045"), ("d-0025", "d-0036")])
def test_interactions_are_symmetric_and_present(a_id, b_id):
    ab = run_checks(ADULT, [item(a_id), item(b_id)], [], DRUGS)
    ba = run_checks(ADULT, [item(b_id), item(a_id)], [], DRUGS)
    assert _groups(ab) and _groups(ab) == _groups(ba)
    running = run_checks(ADULT, [item(a_id)], [RunningItem("rx-9", "x", b_id)], DRUGS)
    assert _groups(running) == _groups(ab)


@pytest.mark.parametrize("a_id,b_id,severity", [("d-0033", "d-0035", "major"), ("d-0016", "d-0018", "major"),
                                                ("d-0016", "d-0019", "major"), ("d-0040", "d-0039", "major"),
                                                ("d-0012", "d-0011", "major"), ("d-0012", "d-0009", "major"),
                                                ("d-0012", "d-0006", "major"), ("d-0013", "d-0010", "major")])
def test_new_interaction_rules(a_id, b_id, severity):
    hits = [c for c in run_checks(ADULT, [item(a_id), item(b_id)], [], DRUGS) if c.code == "interaction"]
    assert [c.severity for c in hits] == [severity]


def test_heparins_do_not_raise_the_inr_interaction():
    for heparin in ("d-0014", "d-0015"):
        checks = run_checks(ADULT, [item(heparin), item("d-0010")], [], DRUGS)  # + metronidazole
        assert not any(c.code == "interaction" for c in checks), heparin
    assert any(c.code == "interaction" for c in run_checks(ADULT, [item("d-0012"), item("d-0010")], [], DRUGS))


def test_nsaids_are_one_duplicate_group():
    for a_id, b_id in (("d-0018", "d-0019"), ("d-0019", "d-0020"), ("d-0018", "d-0020")):
        dup = [c for c in run_checks(ADULT, [item(a_id), item(b_id)], [], DRUGS) if c.code == "duplicate_therapy"]
        assert len(dup) == 1 and dup[0].params["reason"] == "same_atc_class", (a_id, b_id)
    ibu = run_checks(ADULT, [item("d-0018")], [RunningItem("rx-2", "Diclofenac", "d-0019")], DRUGS)
    assert ("duplicate_therapy", "major", 0) in codes(ibu)
    other = run_checks(ADULT, [item("d-0018"), item("d-0001")], [], DRUGS)
    assert not any(c.code == "duplicate_therapy" for c in other)


FOUR = ("06:00", "12:00", "18:00", "23:00")


@pytest.mark.parametrize("units,expected", [
    (1.5, [("max_daily_dose", "major", 0)]),    # d-0002: 1000 mg x 1.5 x 4 = 6000 > 4000
    ("1.5", [("max_daily_dose", "major", 0)]),
    ("1,5", [("max_daily_dose", "major", 0)]),
    (0.5, []),                                   # 2000
    (1.0, []),                                   # 4000 = max
    (2.5, [("max_daily_dose", "critical", 0)]),  # 10000 > 2 x 4000
])
def test_fractional_and_string_units(units, expected):
    assert codes(run_checks(ADULT, [item("d-0002", times=FOUR, units_per_intake=units)], [], DRUGS)) == expected


@pytest.mark.parametrize("extra", [{"dose_mg": "abc"}, {"dose_mg": ""}, {"dose_mg": []}, {"dose_mg": float("nan")},
                                   {"dose_mg": -5}, {"units_per_intake": "abc"}, {"units_per_intake": {}},
                                   {"units_per_intake": float("inf")}, {"dose_mg": True}, {"times": None},
                                   {"times": "08:00"}, {"times": []}])
def test_bad_dose_values_do_not_crash(extra):
    got = run_checks(ADULT, [{**item("d-0001"), **extra}], [], DRUGS)  # unknown dose: never a crash, never silent
    assert codes(got) == [("dose_unverified", "info", 0)]


def test_numeric_string_dose_and_levothyroxine_float_noise():
    got = run_checks(ADULT, [item("d-0001", dose_mg="2500", times=FOUR)], [], DRUGS)
    assert codes(got) == [("max_daily_dose", "critical", 0)]
    thrice = ("08:00", "14:00", "20:00")
    assert run_checks(ADULT, [item("d-0051", times=thrice)], [], DRUGS) == []  # 0.1 x 3 = 0.3, not 0.30000000000000004
    assert run_checks(ADULT, [item("d-0051", times=thrice, dose_mg=0.1)], [], DRUGS) == []
    assert codes(run_checks(ADULT, [item("d-0051", times=thrice, dose_mg=0.11)], [], DRUGS)) == [
        ("max_daily_dose", "major", 0)]


def test_malformed_input_does_not_crash():
    weird = PatientInfo(age="80", allergies=None)  # type: ignore[arg-type]
    items = ["x", None, 3, {"drug_id": ["d-0001"], "med": None}, {"drug_id": 7, "times": 5}, {}, item("d-0018")]
    running = [None, RunningItem("rx", None, ["d-0012"]), RunningItem("rx", "Warfarin", "d-0012")]
    got = run_checks(weird, items, running, DRUGS)  # type: ignore[arg-type]
    assert ("interaction", "major", 6) in codes(got)
    assert run_checks(PatientInfo("abc", None), [item("d-0045")], [], DRUGS) == []  # type: ignore[arg-type]
    old = run_checks(PatientInfo("80", ()), [item("d-0045")], [], DRUGS)  # type: ignore[arg-type]
    assert codes(old) == [("elderly", "moderate", 0)]  # a numeric string age is coerced
    bad = PatientInfo(40, ("penicillin", None, 3, ""))  # type: ignore[arg-type]
    assert codes(run_checks(bad, [item("d-0003")], [], DRUGS)) == [("allergy", "critical", 0)]
    assert run_checks(ADULT, None, None, DRUGS) == []  # type: ignore[arg-type]


def test_prn_item_without_times_is_flagged_not_dose_checked():
    prn = {"med": "Paracetamol", "drug_id": "d-0001", "units_per_intake": 99}
    got = run_checks(ADULT, [prn], [], DRUGS)
    assert codes(got) == [("dose_unverified", "info", 0)] and got[0].params == {"med": "Paracetamol"}


def test_no_dose_unverified_without_a_daily_maximum_or_with_a_computable_dose():
    got = run_checks(ADULT, [{"med": "X", "drug_id": "d-0004", "times": ["08:00"]}], [], DRUGS)
    assert not any(c.code == "dose_unverified" for c in got)
    nomax = next(k for k, v in DRUGS.items() if not v.max_daily_mg)
    got = run_checks(ADULT, [{"med": "X", "drug_id": nomax, "times": []}], [], DRUGS)
    assert not any(c.code == "dose_unverified" for c in got)


def test_penicillin_allergy_cephalosporin_is_a_moderate_cross_reactivity():
    got = run_checks(PatientInfo(40, ("penicillin",)), [item("d-0008")], [], DRUGS)
    assert codes(got) == [("allergy", "moderate", 0)]
    assert got[0].params["cross_reactivity"] is True and got[0].params["cross_class"] == "cephalosporin"
    direct = run_checks(PatientInfo(40, ("penicillin",)), [item("d-0003")], [], DRUGS)
    assert codes(direct) == [("allergy", "critical", 0)] and "cross_reactivity" not in direct[0].params
    carba = DrugInfo(id="d-x", dci="Meropenem", allergy_classes=("carbapenem",))
    assert codes(run_checks(PatientInfo(40, ("penicillin",)), [item("d-x")], [], {"d-x": carba})) == [
        ("allergy", "moderate", 0)]
    free = run_checks(PatientInfo(40, ("penicillin",)), [item(None, med="Ceftriaxone")], [], {})
    assert ("allergy", "moderate", 0) in codes(free)


def test_free_text_item_is_non_formulary_but_still_checked():
    checks = run_checks(PatientInfo(40, ("penicillin",)), [item(None, med="Amoxicillin 1g")], [], DRUGS)
    assert codes(checks) == [("allergy", "critical", 0), ("non_formulary", "moderate", 0)]
    assert checks[0].drug_id == "d-0003"
    assert checks[1].params == {"med": "Amoxicillin 1g", "matched_drug_id": "d-0003"}
    pen = PatientInfo(40, ("penicillin",))
    assert ("allergy", "critical", 0) in codes(run_checks(pen, [item("d-9999", med="Clamoxyl 500")], [], DRUGS))
    assert ("allergy", "critical", 0) in codes(run_checks(PatientInfo(40, ("warfarin",)),
                                                          [item(None, med="Warfarine 5 mg")], [], DRUGS))
    assert ("allergy", "critical", 0) in codes(run_checks(pen, [item(None, med="Tab. Amoxicillin 500 mg")], [], DRUGS))


def test_free_text_item_interacts_and_is_dose_checked():
    warfarin = [RunningItem("rx-1", "Warfarin 5mg", "d-0012")]
    checks = run_checks(ADULT, [item(None, med="Ibuprofen 400mg")], warfarin, DRUGS)
    assert ("interaction", "major", 0) in codes(checks) and ("non_formulary", "moderate", 0) in codes(checks)
    free_running = run_checks(ADULT, [item("d-0018")], [RunningItem("rx-1", "Warfarin 5mg", None)], DRUGS)
    assert codes(free_running) == [("interaction", "major", 0)]
    assert free_running[0].params["with_drug_id"] == "d-0012"
    assert free_running[0].params["with_prescription_id"] == "rx-1"
    dup = run_checks(ADULT, [item(None, med="Ibuprofen 400mg")], [RunningItem("rx-2", "Diclofenac", None)], DRUGS)
    assert ("duplicate_therapy", "major", 0) in codes(dup)
    over = run_checks(ADULT, [item(None, med="Paracetamol 1 g", times=("a", "b", "c", "d", "e"))], [], DRUGS)
    assert ("max_daily_dose", "major", 0) in codes(over)


def test_free_text_with_an_unlisted_strength_is_still_allergy_and_interaction_checked():
    # "Paracetamol 650mg" has no formulary strength: no unit maths, but the name still resolves
    got = run_checks(PatientInfo(40, ("paracetamol",)), [item(None, med="Paracetamol 650mg")], [], DRUGS)
    assert ("allergy", "critical", 0) in codes(got) and ("non_formulary", "moderate", 0) in codes(got)
    got = run_checks(ADULT, [item(None, med="Ibuprofen 650mg", times=("a",) * 9)],
                     [RunningItem("r", "Warfarin", "d-0012")], DRUGS)
    assert ("interaction", "major", 0) in codes(got) and not any(c.code == "max_daily_dose" for c in got)


def test_unresolved_free_text_allergy_fallback():
    got = run_checks(PatientInfo(40, ("aloe vera",)), [item(None, med="Aloe vera gel")], [], DRUGS)
    assert codes(got) == [("allergy", "critical", 0), ("non_formulary", "moderate", 0)] and got[0].drug_id is None
    got = run_checks(PatientInfo(40, ("ampicillin",)), [item(None, med="Penicillin V 1 MU")], [], DRUGS)
    assert ("allergy", "critical", 0) in codes(got)
    assert codes(run_checks(PatientInfo(40, ("latex",)), [item(None, med="Herbal tea")], [], DRUGS)) == [
        ("non_formulary", "moderate", 0)]
