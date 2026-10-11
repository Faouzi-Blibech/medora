from tests.helpers import login


def test_list_scoped_and_shaped(client):
    rows = client.get("/patients", headers=login(client, "doctor@medora.tn")).json()
    assert {r["id"] for r in rows} == {f"p-000{i}" for i in range(1, 7)}
    amira = next(r for r in rows if r["id"] == "p-0001")
    assert {"id", "first_name", "last_name", "age", "ward", "bed", "device_id", "latest_news2",
            "open_alerts"} <= set(amira)
    assert amira["bed"] == "C-12" and amira["device_id"] == "bsu-001" and amira["latest_news2"] == 0


def test_list_nurse_ward_and_filter(client):
    h = login(client, "nurse2@medora.tn")
    assert {r["ward"] for r in client.get("/patients", headers=h).json()} == {"Internal Medicine"}
    rows = client.get("/patients?q=gharb", headers=h).json()
    assert [r["id"] for r in rows] == ["p-0011"]


def test_list_admin_summary_only(client):
    rows = client.get("/patients", headers=login(client, "admin@medora.tn")).json()
    assert len(rows) == 12
    assert "latest_news2" not in rows[0] and {"first_name", "bed", "device_id"} <= set(rows[0])


def test_list_patient_forbidden(client):
    assert client.get("/patients", headers=login(client, "patient@medora.tn")).status_code == 403


def test_patient_detail_shape(client):
    p = client.get("/patients/p-0001", headers=login(client, "doctor@medora.tn")).json()
    assert p["sex"] == "F" and p["date_of_birth"] == "1972-03-14" and p["allergies"] == ["penicillin"]
    assert p["admission_id"] == "adm-0001" and p["attending_doctor_id"] == "u-0001"


def test_patch_nurse_only_allergies(client):
    h = login(client, "nurse@medora.tn")
    r = client.patch("/patients/p-0002", headers=h, json={"allergies": ["iodine"]})
    assert r.status_code == 200 and r.json()["allergies"] == ["iodine"]
    assert client.patch("/patients/p-0002", headers=h, json={"history": "x"}).status_code == 403


def test_patch_doctor(client):
    r = client.patch("/patients/p-0002", headers=login(client, "doctor@medora.tn"), json={"history": "HF"})
    assert r.status_code == 200 and r.json()["history"] == "HF"


def test_vitals_oldest_first_default_24h(client):
    rows = client.get("/patients/p-0001/vitals", headers=login(client, "nurse@medora.tn")).json()
    assert 90 <= len(rows) <= 97
    assert rows[0]["ts"] < rows[-1]["ts"] and rows[0]["ts"].endswith("Z")
    assert {"ts", "hr", "spo2", "temp", "nurse_id", "news2", "source"} <= set(rows[0])


def test_vitals_patient_self(client):
    h = login(client, "patient@medora.tn")
    assert client.get("/patients/p-0001/vitals", headers=h).status_code == 200


def test_prescriptions(client):
    rows = client.get("/patients/p-0001/prescriptions", headers=login(client, "patient@medora.tn")).json()
    assert rows[0]["id"] == "rx-0001" and rows[0]["active"] is True and rows[0]["items"]


def test_notes_roundtrip(client):
    h = login(client, "nurse@medora.tn")
    r = client.post("/patients/p-0001/notes", headers=h, json={"text": "Slept well"})
    assert r.status_code == 201
    n = r.json()
    assert n["id"].startswith("n-") and n["author_id"] == "u-0002" and n["author_role"] == "nurse"
    rows = client.get("/patients/p-0001/notes", headers=h).json()
    assert rows[0]["text"] == "Slept well"


def test_notes_patient_forbidden(client):
    assert client.get("/patients/p-0001/notes", headers=login(client, "patient@medora.tn")).status_code == 403
