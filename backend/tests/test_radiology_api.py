from datetime import UTC, datetime, timedelta

import pytest

from app.models import AuditLog, ExamResult, PatientAccess, RadiographReading
from tests.helpers import login, make_user

CHEST = {"patient_id": "p-0001", "referral_text": "douleur thoracique depuis ce matin", "symptoms": ["chest pain"]}
PNG = ("xray.png", b"\x89PNG\r\n\x1a\nfake", "image/png")
PDF = ("xray.pdf", b"%PDF-1.4 fake", "application/pdf")


@pytest.fixture()
def stored(monkeypatch):
    from app.services import storage

    files: dict[str, tuple[bytes, str]] = {}
    monkeypatch.setattr(storage, "put", lambda key, data, ct: files.__setitem__(key, (data, ct)))
    monkeypatch.setattr(storage, "get", lambda key: files[key][0])
    return files


def _ordered(client, idx):
    """Request + order exam #idx (0 ecg, 2 chest_xray). Returns (exam_id, doctor headers)."""
    a = client.post("/appointments", headers=login(client, "admin@ward.tn"), json=CHEST).json()
    doc = login(client, "doctor@ward.tn")
    exams = client.get(f"/appointments/{a['id']}/exams", headers=doc).json()
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [exams[idx]["id"]]})
    return exams[idx]["id"], doc


def _xray_result(client, file=PNG):
    ex, doc = _ordered(client, 2)
    r = client.post(f"/exams/{ex}/results", headers=login(client, "imaging@ward.tn"), files={"file": file})
    assert r.status_code == 200, r.text
    return r.json(), doc


def test_png_upload_enqueues_reading(client, db, stored):
    out, _ = _xray_result(client)
    assert out["results"][0]["reading"]["status"] == "queued"
    [row] = db.query(RadiographReading).all()
    assert row.hint == "Chest X-ray" and row.exam_result_id == out["results"][0]["id"]


def test_pdf_upload_has_no_reading(client, db, stored):
    out, _ = _xray_result(client, PDF)
    assert out["results"][0]["reading"] is None
    assert db.query(RadiographReading).count() == 0


def test_ecg_png_has_no_reading(client, db, stored):
    ex, _ = _ordered(client, 0)
    r = client.post(f"/exams/{ex}/results", headers=login(client, "nurse@ward.tn"), files={"file": PNG})
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["reading"] is None
    assert db.query(RadiographReading).count() == 0


def test_get_reading_by_role(client, db, stored):
    out, doc = _xray_result(client)
    rid = out["results"][0]["id"]
    r = client.get(f"/exam-results/{rid}/reading", headers=doc)
    assert r.status_code == 200 and "ai_suggested" in r.json()
    assert db.query(AuditLog).filter_by(action="read", resource="radiograph_reading").count() == 1
    n = client.get(f"/exam-results/{rid}/reading", headers=login(client, "imaging@ward.tn"))
    assert n.status_code == 200 and set(n.json()) == {"id", "exam_result_id", "status"}
    assert client.get(f"/exam-results/{rid}/reading", headers=login(client, "patient@ward.tn")).status_code == 403
    assert client.get(f"/exam-results/{rid}/reading", headers=login(client, "admin@ward.tn")).status_code == 403
    make_user(db, "doc2@ward.tn", role="doctor", ward="Cardiology")
    assert client.get(f"/exam-results/{rid}/reading", headers=login(client, "doc2@ward.tn")).status_code == 403


def test_get_reading_404_without_reading(client, stored):
    out, doc = _xray_result(client, PDF)
    assert client.get(f"/exam-results/{out['results'][0]['id']}/reading", headers=doc).status_code == 404


def test_confirm_reading(client, db, stored):
    out, doc = _xray_result(client)
    rid = out["results"][0]["id"]
    r = client.put(f"/exam-results/{rid}/reading", headers=doc, json={"final_text": "Conclusion : normal"})
    assert r.status_code == 200, r.text
    assert r.json()["final_text"] == "Conclusion : normal" and r.json()["confirmed_by_name"] == "Dr Trabelsi"
    db.expire_all()
    assert db.get(ExamResult, rid).report_text == "Conclusion : normal"
    assert client.put(f"/exam-results/{rid}/reading", headers=login(client, "imaging@ward.tn"),
                      json={"final_text": "x"}).status_code == 403
    assert client.put(f"/exam-results/{rid}/reading", headers=doc, json={"final_text": ""}).status_code == 422
    assert client.put(f"/exam-results/{rid}/reading", headers=doc, json={"final_text": "   "}).status_code == 422


def test_sharing_grant_reads_but_cannot_confirm(client, db, stored):
    out, doc = _xray_result(client)
    rid = out["results"][0]["id"]
    doc2 = make_user(db, "doc2.g@ward.tn", role="doctor", ward="Cardiology")
    now = datetime.now(UTC)
    db.add(PatientAccess(id="pa-8001", patient_id="p-0001", user_id=doc2.id, granted_by="u-0001",
                         created_at=now, expires_at=now + timedelta(days=7)))
    db.flush()
    h2 = login(client, "doc2.g@ward.tn")
    assert client.get(f"/exam-results/{rid}/reading", headers=h2).status_code == 200
    assert client.put(f"/exam-results/{rid}/reading", headers=h2, json={"final_text": "x"}).status_code == 403
    db.expire_all()
    assert db.query(RadiographReading).one().final_text is None
    assert client.put(f"/exam-results/{rid}/reading", headers=doc, json={"final_text": "ok"}).status_code == 200


def test_outside_radiograph_upload(client, db, stored):
    doc = login(client, "doctor@ward.tn")
    r = client.post("/patients/p-0001/radiographs", headers=doc, files={"file": PNG},
                    data={"title": "Outside X-ray — wrist"})
    assert r.status_code == 201, r.text
    o = r.json()
    assert (o["code"], o["department"], o["status"]) == ("xray_outside", "Imaging", "done")
    assert o["label"] == "Outside X-ray — wrist" and o["results"][0]["reading"]["status"] == "queued"
    assert db.query(RadiographReading).count() == 1
    bad = client.post("/patients/p-0001/radiographs", headers=doc, files={"file": PDF})
    assert bad.status_code == 422 and bad.json()["code"] == "bad_file"
    assert client.post("/patients/p-0001/radiographs", headers=login(client, "nurse@ward.tn"),
                       files={"file": PNG}).status_code == 403
    make_user(db, "doc3@ward.tn", role="doctor", ward="Cardiology")
    assert client.post("/patients/p-0001/radiographs", headers=login(client, "doc3@ward.tn"),
                       files={"file": PNG}).status_code == 403


def test_catalogue_has_xray(client):
    cat = client.get("/exams/catalogue", headers=login(client, "doctor@ward.tn")).json()
    assert any(c["code"] == "xray" and c["department"] == "Imaging" for c in cat)
