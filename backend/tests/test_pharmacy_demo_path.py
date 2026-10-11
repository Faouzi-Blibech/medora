"""The spec §7 demo path through the API in-process (the same code as scripts/pharmacy_smoke.py)."""

from scripts import pharmacy_smoke


def test_demo_path(client):
    a = pharmacy_smoke.run_phase_a(client, "ward1234")
    assert a["v1"]["status"] == "pending_pharmacy" and a["v2"]["status"] == "validated"
    b = pharmacy_smoke.run_phase_b(client, "ward1234")
    assert b["dispensation"]["status"] == "sent"
    assert b["summary_after"]["low_stock"] == b["summary_before"]["low_stock"] + 1  # paracetamol 200 → 199
