import pytest

from app.models import ExamOrder, ExamResult
from tests.helpers import login

CHEST = {"patient_id": "p-0001", "referral_text": "douleur thoracique depuis ce matin", "symptoms": ["chest pain"]}
PDF = ("ecg.pdf", b"%PDF-1.4 fake", "application/pdf")


@pytest.fixture()
def stored(monkeypatch):
    """In-memory MinIO: {key: (bytes, content_type)}."""
    from app.services import storage

    files: dict[str, tuple[bytes, str]] = {}
    monkeypatch.setattr(storage, "put", lambda key, data, ct: files.__setitem__(key, (data, ct)))
    monkeypatch.setattr(storage, "get", lambda key: files[key][0])
    return files


def _request(client):
    a = client.post("/appointments", headers=login(client, "admin@medora.tn"), json=CHEST).json()
    doc = login(client, "doctor@medora.tn")
    return a, doc, client.get(f"/appointments/{a['id']}/exams", headers=doc).json()


def test_new_request_gets_suggestions(client):
    a, doc, exams = _request(client)
    assert [e["code"] for e in exams] == ["ecg", "troponin", "chest_xray"]
    assert all(e["status"] == "suggested" and e["ai_suggested"]["source"] == "rules" for e in exams)
    row = client.get("/appointments/waitlist", headers=doc).json()
    mine = next(r for r in row if r["id"] == a["id"])
    assert (mine["exams_suggested"], mine["exams_total"], mine["exams_done"]) == (3, 0, 0)


def test_order_selected_cancels_the_rest_and_emits(client, emitted):
    a, doc, exams = _request(client)
    keep = [exams[0]["id"], exams[2]["id"]]
    r = client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": keep})
    assert r.status_code == 200, r.text
    st = {e["id"]: e["status"] for e in r.json()}
    assert st == {exams[0]["id"]: "ordered", exams[1]["id"]: "cancelled", exams[2]["id"]: "ordered"}
    assert all(e["human_confirmed_by"] == "u-0001" for e in r.json() if e["status"] == "ordered")
    event, data = emitted[-1]
    assert event == "exam.ordered" and data["patient_first_name"] == "Amira"
    assert [x["label"] for x in data["exams"]] == ["ECG (12-lead)", "Chest X-ray"]


def test_order_rejects_foreign_or_stale_ids(client, db):
    a, doc, exams = _request(client)
    other = client.post("/appointments", headers=login(client, "admin@medora.tn"),
                        json=dict(CHEST, patient_id="p-0002")).json()
    foreign = client.get(f"/appointments/{other['id']}/exams", headers=doc).json()[0]["id"]
    r = client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [foreign]})
    assert r.status_code == 422
    assert db.get(ExamOrder, foreign).status == "suggested"
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [exams[0]["id"]]})
    again = client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [exams[0]["id"]]})
    assert again.status_code == 409 and again.json()["code"] == "bad_status"
    nurse = login(client, "nurse@medora.tn")
    assert client.post(f"/appointments/{a['id']}/exams/order", headers=nurse, json={"exam_ids": []}).status_code == 403


def test_doctor_adds_an_exam_by_hand(client, emitted):
    a, doc, _ = _request(client)
    r = client.post("/exams", headers=doc, json={"patient_id": "p-0001", "appointment_id": a["id"], "code": "echo"})
    assert r.status_code == 201 and r.json()["status"] == "ordered" and r.json()["ai_suggested"] is None
    assert emitted[-1][0] == "exam.ordered"
    assert client.post("/exams", headers=doc, json={"patient_id": "p-0001", "code": "mri_magic"}).status_code == 422
    assert client.get("/exams/catalogue", headers=doc).json()[0].keys() == {"code", "label", "department"}


def test_upload_rules(client, db, stored):
    a, doc, exams = _request(client)
    xray = exams[2]["id"]  # Imaging
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [xray]})
    lab = login(client, "lab@medora.tn")
    assert client.post(f"/exams/{xray}/results", headers=lab, files={"file": PDF}).status_code == 403
    img = login(client, "imaging@medora.tn")
    bad = client.post(f"/exams/{xray}/results", headers=img, files={"file": ("x.exe", b"MZ", "application/x-msdownload")})
    assert bad.status_code == 422 and bad.json()["code"] == "bad_file"
    big = client.post(f"/exams/{xray}/results", headers=img,
                      files={"file": ("big.pdf", b"0" * (15 * 1024 * 1024 + 1), "application/pdf")})
    assert big.status_code == 422 and big.json()["code"] == "bad_file"
    assert stored == {} and db.query(ExamResult).count() == 0 and db.get(ExamOrder, xray).status == "ordered"
    ok = client.post(f"/exams/{xray}/results", headers=img, files={"file": PDF}, data={"report_text": "No consolidation"})
    assert ok.status_code == 200 and ok.json()["status"] == "done"
    [res] = ok.json()["results"]
    assert res["report_text"] == "No consolidation" and res["uploaded_by_name"] == "Nurse Rania"
    assert list(stored)[0] == f"exams/{xray}/{res['id']}/ecg.pdf"
    again = client.post(f"/exams/{xray}/results", headers=img, files={"file": PDF})
    assert again.status_code == 409


def test_results_ready_fires_once_on_last_upload(client, emitted, stored):
    a, doc, exams = _request(client)
    ecg, xray = exams[0]["id"], exams[2]["id"]
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [ecg, xray]})
    client.post(f"/exams/{ecg}/results", headers=login(client, "nurse@medora.tn"), files={"file": PDF})
    assert [e for e, _ in emitted].count("exam.results_ready") == 0
    client.post(f"/exams/{xray}/results", headers=login(client, "imaging@medora.tn"), files={"file": PDF})
    ready = [d for e, d in emitted if e == "exam.results_ready"]
    assert len(ready) == 1 and ready[0]["doctor_id"] == "u-0001" and ready[0]["appointment_id"] == a["id"]


def test_file_download_is_audited_and_guarded(client, db, stored):
    from app.models import AuditLog

    a, doc, exams = _request(client)
    xray = exams[2]["id"]
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [xray]})
    res = client.post(f"/exams/{xray}/results", headers=login(client, "imaging@medora.tn"),
                      files={"file": PDF}).json()["results"][0]
    r = client.get(f"/exam-results/{res['id']}/file", headers=doc)
    assert r.status_code == 200 and r.content == PDF[1] and r.headers["content-type"] == "application/pdf"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert db.query(AuditLog).filter_by(action="read", resource="exam_result", resource_id=res["id"]).count() == 1
    assert client.get(f"/exam-results/{res['id']}/file", headers=login(client, "nurse2@medora.tn")).status_code == 403
    assert client.get(f"/exam-results/{res['id']}/file", headers=login(client, "patient@medora.tn")).status_code == 403
    assert client.get(f"/exam-results/{res['id']}/file", headers=login(client, "admin@medora.tn")).status_code == 403


def test_patient_sees_only_ordered_rows(client):
    patient = login(client, "patient@medora.tn")
    a = client.post("/appointments", headers=patient, json=CHEST).json()
    assert client.get(f"/appointments/{a['id']}/exams", headers=patient).json() == []
    assert client.get("/patients/p-0001/exams", headers=patient).json() == []
    doc = login(client, "doctor@medora.tn")
    first = client.get(f"/appointments/{a['id']}/exams", headers=doc).json()[0]["id"]
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [first]})
    [row] = client.get("/patients/p-0001/exams", headers=patient).json()
    assert row["status"] == "ordered" and "ai_suggested" not in row and "results" not in row
    assert "exams_suggested" in client.get("/appointments", headers=patient).json()[0]


def test_worklist_is_per_department(client):
    a, doc, exams = _request(client)
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [e["id"] for e in exams]})
    img = client.get("/exams?status=ordered", headers=login(client, "imaging@medora.tn")).json()
    lab = client.get("/exams?status=ordered", headers=login(client, "lab@medora.tn")).json()
    assert [e["code"] for e in img] == ["chest_xray"] and [e["code"] for e in lab] == ["troponin"]
    assert img[0]["patient_name"] == "Amira Ben Salah"
    assert client.get("/exams", headers=doc).status_code == 403


def test_admin_sees_exam_status_only(client):
    a, doc, exams = _request(client)
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [exams[0]["id"]]})
    rows = client.get("/exams?status=ordered", headers=login(client, "admin@medora.tn")).json()
    assert rows and all(set(r) == {"id", "appointment_id", "department", "status"} for r in rows)
