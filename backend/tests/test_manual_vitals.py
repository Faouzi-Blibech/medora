"""POST /patients/{id}/vitals: a nurse records a reading by hand (source manual, NEWS2 scored, alert when high)."""

from app.models import Alert, Vital
from tests.helpers import login


def test_nurse_records_vitals(client, db):
    nurse_headers = login(client, "nurse@ward.tn")
    r = client.post("/patients/p-0001/vitals", headers=nurse_headers, json={"hr": 82, "spo2": 98, "temp": 36.9})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source"] == "manual" and body["news2"] == 0 and body["nurse_id"]
    rows = client.get("/patients/p-0001/vitals", headers=nurse_headers).json()
    assert rows[-1]["source"] == "manual" and rows[-1]["hr"] == 82


def test_empty_reading_rejected(client):
    nurse_headers = login(client, "nurse@ward.tn")
    r = client.post("/patients/p-0001/vitals", headers=nurse_headers, json={})
    assert r.status_code == 422


def test_out_of_range_rejected(client):
    nurse_headers = login(client, "nurse@ward.tn")
    r = client.post("/patients/p-0001/vitals", headers=nurse_headers, json={"hr": 900})
    assert r.status_code == 422


def test_patient_cannot_record(client):
    patient_headers = login(client, "patient@ward.tn")
    r = client.post("/patients/p-0001/vitals", headers=patient_headers, json={"hr": 80})
    assert r.status_code == 403


def test_high_reading_raises_alert(client, db):
    nurse_headers = login(client, "nurse@ward.tn")
    r = client.post("/patients/p-0001/vitals", headers=nurse_headers, json={"hr": 135, "spo2": 89, "temp": 39.4})
    assert r.status_code == 201, r.text
    assert r.json()["news2"] >= 7
    assert db.query(Alert).filter(Alert.patient_id == "p-0001", Alert.kind == "news2").count() >= 1
    assert db.query(Vital).filter(Vital.source == "manual", Vital.hr == 135).count() == 1
