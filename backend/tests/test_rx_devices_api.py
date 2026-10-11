from app.models import Admission, MedDose, Patient
from tests.helpers import login

RX = {"patient_id": "p-0001", "care_plan": "Monitor temperature every 4h",
      "items": [{"med": "Paracetamol 500mg", "times": ["08:00", "20:00"], "slot": 1, "days": 5}]}


def _schedules(published):
    return [p for p in published if p[0].endswith("/schedule")]


def test_prescribe_publishes_schedule(client, published):
    r = client.post("/prescriptions", headers=login(client, "doctor@ward.tn"), json=dict(RX, urgent=True))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"].startswith("rx-") and body["doctor_id"] == "u-0001" and body["active"] is True
    assert (body["status"], body["urgent"]) == ("pending_pharmacy", True)
    assert body["published_to_device"] is True and body["schedule_version"] == 1
    topic, payload, _, retain = _schedules(published)[-1]
    assert topic == "hospital/device/bsu-001/schedule" and retain
    assert payload["schedule_version"] == 1 and any(d["time"] == "20:00" for d in payload["doses"])


def test_prescribe_patient_without_device(client, published):
    r = client.post("/prescriptions", headers=login(client, "doctor@ward.tn"),
                    json=dict(RX, patient_id="p-0002", urgent=True))
    assert r.status_code == 201 and r.json()["published_to_device"] is False
    assert _schedules(published) == []


def test_prescribe_rules(client):
    h = login(client, "doctor@ward.tn")
    assert client.post("/prescriptions", headers=h, json=dict(RX, patient_id="p-0007")).status_code == 403
    assert client.post("/prescriptions", headers=login(client, "nurse@ward.tn"), json=RX).status_code == 403
    bad = dict(RX, items=[{"med": "X", "times": ["25:00"], "slot": 1, "days": 1}])
    assert client.post("/prescriptions", headers=h, json=bad).status_code == 422


def test_stop_prescription(client, db, published):
    h = login(client, "doctor@ward.tn")
    rx = client.post("/prescriptions", headers=h, json=dict(RX, urgent=True)).json()
    r = client.patch(f"/prescriptions/{rx['id']}", headers=h, json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False and r.json()["schedule_version"] == 2
    payload = _schedules(published)[-1][1]
    assert all("Paracetamol 500mg" not in d["meds"] or d["slot"] != 1 for d in payload["doses"])


def test_devices_list(client):
    rows = client.get("/devices", headers=login(client, "nurse@ward.tn")).json()
    d = next(r for r in rows if r["id"] == "bsu-001")
    assert d["patient_id"] == "p-0001" and d["bed"] == "C-12" and d["admission_id"] == "adm-0001"
    assert {"online", "fw_version", "last_seen"} <= set(d)
    assert client.get("/devices", headers=login(client, "doctor@ward.tn")).status_code == 403


def test_assign_and_discharge(client, db, published, emitted):
    admin = login(client, "admin@ward.tn")
    r = client.post("/admissions/adm-0001/discharge", headers=admin)
    assert r.status_code == 200 and r.json()["discharged_at"]
    topic, payload, _, _ = published[-1]
    assert topic == "hospital/device/bsu-001/schedule" and payload["patient_id"] is None and payload["doses"] == []
    event, data = emitted[-1]
    assert event == "patient.discharged" and data["patient_id"] == "p-0001" and data["patient_first_name"] == "Amira"
    assert client.post("/admissions/adm-0001/discharge", headers=admin).status_code == 409

    r = client.post("/devices/bsu-001/assign", headers=admin, json={"patient_id": "p-0002", "bed": "C-14"})
    assert r.status_code == 200, r.text
    adm = db.query(Admission).filter_by(patient_id="p-0002", discharged_at=None).one()
    assert adm.device_id == "bsu-001" and adm.bed == "C-14"
    assert published[-1][1]["patient_id"] == "p-0002"


def test_assign_busy_device(client):
    r = client.post("/devices/bsu-001/assign", headers=login(client, "admin@ward.tn"),
                    json={"patient_id": "p-0002", "bed": "C-14"})
    assert r.status_code == 409 and r.json()["code"] == "device_busy"


def test_assign_requires_admin(client):
    r = client.post("/devices/bsu-001/assign", headers=login(client, "nurse@ward.tn"),
                    json={"patient_id": "p-0002", "bed": "C-14"})
    assert r.status_code == 403


def test_command(client, published):
    h = login(client, "nurse@ward.tn")
    r = client.post("/devices/bsu-001/command", headers=h, json={"type": "alert", "text": "Nurse is on the way"})
    assert r.status_code == 200
    assert published[-1][:2] == ("hospital/device/bsu-001/command", {"type": "alert", "text": "Nurse is on the way"})
    assert client.post("/devices/bsu-001/command", headers=h, json={"type": "selfdestruct"}).status_code == 422
    assert client.post("/devices/bsu-404/command", headers=h, json={"type": "rotate_home"}).status_code == 404


def test_doses_today_and_given(client, db, published):
    h = login(client, "nurse@ward.tn")
    rows = client.get("/patients/p-0001/doses", headers=h).json()
    assert rows and rows[0]["scheduled_at"] <= rows[-1]["scheduled_at"]
    assert {"id", "prescription_id", "patient_id", "scheduled_at", "time_of_day", "meds", "slot", "status",
            "taken_method", "updated_at"} <= set(rows[0])
    r = client.post(f"/doses/{rows[0]['id']}/given", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "taken" and r.json()["given_by"] == "u-0002"
    assert db.get(MedDose, rows[0]["id"]).status == "taken"
    assert published[-1][1]["type"] == "dose_event"
    assert client.post(f"/doses/{rows[1]['id']}/given", headers=login(client, "nurse2@ward.tn")).status_code == 403


def test_doses_by_date_patient_self(client):
    rows = client.get("/patients/p-0001/doses?date=2020-01-01", headers=login(client, "patient@ward.tn")).json()
    assert rows == []


def test_patient_record_untouched_by_discharge(client, db):
    client.post("/admissions/adm-0001/discharge", headers=login(client, "doctor@ward.tn"))
    assert db.get(Patient, "p-0001") is not None
