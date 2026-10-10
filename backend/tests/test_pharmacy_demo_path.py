"""The spec §7 demo path, steps 1-5, through the API in-process (the same code as scripts/pharmacy_smoke.py)."""

from scripts import pharmacy_smoke


def test_demo_path_phase_a(client):
    out = pharmacy_smoke.run_phase_a(client, "ward1234")
    assert out["v1"]["status"] == "pending_pharmacy" and out["v2"]["status"] == "validated"
