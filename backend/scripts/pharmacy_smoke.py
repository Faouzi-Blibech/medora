"""Demo-path smoke for the hospital pharmacy (spec 2026-10-10 §7, §9), over HTTP:

    python scripts/pharmacy_smoke.py --base http://localhost:8000

Needs the seed (`python -m app.seed`); the password comes from SEED_PASSWORD (default ward1234).
tests/test_pharmacy_demo_path.py runs the same functions through the in-process TestClient.
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta

import httpx

AMOX = {"med": "Amoxicillin 1 g", "drug_id": "d-0003", "dose_mg": 1000, "times": ["08:00", "14:00", "20:00"],
        "days": 7}
AZI = {"med": "Azithromycin 250 mg", "drug_id": "d-0006", "units_per_intake": 2, "times": ["08:00"], "days": 3}


def _check(cond: bool, what: str) -> None:
    if not cond:
        raise SystemExit(f"smoke failed: {what}")


def _ok(r, status: int = 200) -> dict | list:
    _check(r.status_code == status, f"{r.request.method} {r.request.url} -> {r.status_code} {r.text}")
    return r.json()


def _login(c, email: str, password: str) -> dict:
    token = _ok(c.post("/auth/login", json={"email": email, "password": password}))["access_token"]
    return {"Authorization": f"Bearer {token}"}


def tunis_day(offset_days: int = 0) -> str:
    return (datetime.now(UTC) + timedelta(hours=1, days=offset_days)).date().isoformat()


def run_phase_a(c, password: str, patient_id: str = "p-0001") -> dict:
    """Steps 1-5: live allergy warning, send with a reason, red on the worklist, change requested, resubmit with
    azithromycin, validate, doses on the nurse round."""
    doc, ph = _login(c, "doctor@ward.tn", password), _login(c, "pharmacist@ward.tn", password)
    nurse = _login(c, "nurse@ward.tn", password)
    checks = _ok(c.post("/prescriptions/check", headers=doc, json={"patient_id": patient_id, "items": [AMOX]}))
    _check(any(x["code"] == "allergy" and x["severity"] == "critical" for x in checks["checks"]), "allergy warning")
    body = {"patient_id": patient_id, "items": [AMOX], "care_plan": ""}
    r = c.post("/prescriptions", headers=doc, json=body)
    _check(r.status_code == 422 and r.json()["code"] == "override_required", "override required")
    v1 = _ok(c.post("/prescriptions", headers=doc, json={**body, "override_reason": "Smoke: allergy unclear"}), 201)
    row = next((w for w in _ok(c.get("/pharmacy/worklist", headers=ph)) if w["prescription"]["id"] == v1["id"]), None)
    _check(row is not None and row["max_severity"] == "critical", "critical row on the worklist")
    _ok(c.post(f"/pharmacy/prescriptions/{v1['id']}/request-changes", headers=ph,
               json={"comment": "allergie pénicilline → azithromycine"}))
    v2 = _ok(c.post("/prescriptions", headers=doc, json={"patient_id": patient_id, "items": [AZI], "care_plan": "",
                                                         "replaces_id": v1["id"]}), 201)
    done = _ok(c.post(f"/pharmacy/prescriptions/{v2['id']}/validate", headers=ph,
                      json={"acknowledged": bool(v2["checks"])}))
    _check(done["status"] == "validated", "v2 validated")
    doses = [d for day in (tunis_day(0), tunis_day(1))
             for d in _ok(c.get(f"/patients/{patient_id}/doses", headers=nurse, params={"date": day}))]
    _check(any(d["prescription_id"] == v2["id"] for d in doses), "azithromycin doses on the nurse round")
    return {"v1": v1, "v2": done}  # v1 as saved (pending_pharmacy); it is superseded by now


def run_phase_b(c, password: str, ward: str = "Cardiology", round_time: str = "20:00") -> dict:
    """Step 6: the pharmacist prepares the round, the nurse confirms receipt, the stock goes down, and a
    low-stock alert shows on the pharmacy dashboard."""
    ph, nurse = _login(c, "pharmacist@ward.tn", password), _login(c, "nurse@ward.tn", password)
    day = tunis_day()
    before = _ok(c.get("/pharmacy/summary", headers=ph))
    view = _ok(c.get("/pharmacy/dispensing", headers=ph, params={"date": day, "round": round_time, "ward": ward}))
    lines = [{"dose_id": d["dose_id"]} for w in view for p in w["patients"] for d in p["doses"] if not d["dispensed"]]
    if not lines:
        print(f"pharmacy smoke: the {ward} {round_time} round of {day} is already dispensed")
        return {"dispensation": None, "summary_before": before, "summary_after": before}
    disp = _ok(c.post("/pharmacy/dispensations", headers=ph,
                      json={"ward": ward, "date": day, "round_time": round_time, "lines": lines}), 201)
    listed = _ok(c.get("/dispensations", headers=nurse, params={"date": day}))
    _check(any(d["id"] == disp["id"] for d in listed), "the nurse sees the delivery")
    _check(_ok(c.post(f"/dispensations/{disp['id']}/receive", headers=nurse))["status"] == "received", "received")
    after = _ok(c.get("/pharmacy/summary", headers=ph))
    _check(after["low_stock"] >= 1, "a low-stock alert after the round")
    return {"dispensation": disp, "summary_before": before, "summary_after": after}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pharmacy demo-path smoke test")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--phase", choices=["a", "b", "all"], default="all")
    args = ap.parse_args(argv)
    password = os.environ.get("SEED_PASSWORD", "ward1234")
    with httpx.Client(base_url=args.base, timeout=10) as c:
        if args.phase in ("a", "all"):
            run_phase_a(c, password)
            print("pharmacy smoke: phase A ok")
        if args.phase in ("b", "all"):
            run_phase_b(c, password)
            print("pharmacy smoke: phase B ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
