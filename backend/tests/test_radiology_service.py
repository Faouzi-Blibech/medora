from app.models import ExamOrder, ExamResult, RadiographReading


def make_result(db, *, code="chest_xray", content_type="image/png", patient="p-0001", n=1):
    o = ExamOrder(id=f"ex-80{n:02d}", patient_id=patient, code=code, label="Chest X-ray", department="Imaging",
                  status="done", human_confirmed_by="u-0001")
    db.add(o)
    db.flush()
    r = ExamResult(id=f"er-80{n:02d}", exam_order_id=o.id, patient_id=patient, uploaded_by="u-0006",
                   file_key=f"exams/{o.id}/x.png", file_name="x.png", content_type=content_type, size_bytes=10)
    db.add(r)
    db.flush()
    return o, r


def test_reading_roundtrip(db, seeded):
    _, r = make_result(db)
    db.add(RadiographReading(id="rr-8001", exam_result_id=r.id, patient_id="p-0001", hint="Chest X-ray"))
    db.flush()
    got = db.get(RadiographReading, "rr-8001")
    assert got.status == "queued" and got.ai_suggested is None and got.final_text is None


from datetime import UTC, datetime  # noqa: E402

from app.iot.ingest import scope_for  # noqa: E402
from app.services import radiology as R  # noqa: E402
from tests.helpers import make_user  # noqa: E402

READY = ("ready", {"source": "llm", "model": "m", "draft_text": "Technique : thorax", "disclaimer": "d"})


def test_is_radiograph():
    assert R.is_radiograph("chest_xray", "image/png") and R.is_radiograph("xray_outside", "image/jpeg")
    assert not R.is_radiograph("chest_xray", "application/pdf") and not R.is_radiograph("ecg", "image/png")


def test_enqueue_claim_process(db, seeded, monkeypatch):
    _, res = make_result(db)
    r = R.enqueue(db, res, "Chest X-ray")
    assert r.id.startswith("rr-") and r.status == "queued"
    got = R.claim_next(db)
    assert got.id == r.id and got.status == "running" and got.started_at
    assert R.claim_next(db) is None
    monkeypatch.setattr(R.radiology, "read", lambda data, hint: READY)
    frame = R.process(db, got, get=lambda key: b"img")
    assert got.status == "ready" and got.ai_suggested["model"] == "m" and got.finished_at
    assert frame == {"type": "radiograph_reading", "reading_id": r.id, "exam_result_id": res.id,
                     "patient_id": "p-0001", "status": "ready",
                     "scope": scope_for(db, "p-0001")}
    assert frame["scope"]["doctor_id"] == "u-0001" and frame["scope"]["patient_id"] == "p-0001"


def test_missing_file_fails_softly(db, seeded):
    _, res = make_result(db)
    r = R.enqueue(db, res, "")
    R.claim_next(db)

    def gone(key):
        raise FileNotFoundError(key)

    R.process(db, r, get=gone)
    assert r.status == "failed" and r.ai_suggested["source"] == "rules" and r.ai_suggested["draft_text"]


def test_worker_never_overwrites_confirmed_text(db, seeded, monkeypatch):
    from app.models import User

    _, res = make_result(db)
    r = R.enqueue(db, res, "")
    R.claim_next(db)
    doctor = db.get(User, "u-0001")
    R.confirm(db, r, doctor, "Written by hand", datetime.now(UTC))
    monkeypatch.setattr(R.radiology, "read", lambda data, hint: READY)
    R.process(db, r, get=lambda key: b"img")
    assert r.final_text == "Written by hand" and r.status == "ready"
    assert db.get(type(res), res.id).report_text == "Written by hand"


def test_recover_requeues_running(db, seeded):
    _, res = make_result(db)
    r = R.enqueue(db, res, "")
    R.claim_next(db)
    assert R.recover(db) == 1 and r.status == "queued" and r.started_at is None


def test_tick(db, seeded, monkeypatch):
    sent = []
    assert R.tick(db, publish=sent.append, get=lambda k: b"") is False
    _, res = make_result(db)
    R.enqueue(db, res, "")
    monkeypatch.setattr(R.radiology, "read", lambda data, hint: READY)
    assert R.tick(db, publish=sent.append, get=lambda k: b"img") is True
    assert sent[0]["status"] == "ready"


def test_to_out_by_role(db, seeded):
    from app.models import User

    _, res = make_result(db)
    r = R.enqueue(db, res, "Chest X-ray")
    r.ai_suggested = READY[1]
    nurse = make_user(db, "img2@ward.tn", role="nurse", ward="Imaging")
    assert set(R.to_out(db, r, nurse)) == {"id", "exam_result_id", "status"}
    doctor = db.get(User, "u-0001")
    full = R.to_out(db, r, doctor)
    assert full["ai_suggested"]["draft_text"] and full["hint"] == "Chest X-ray" and "confirmed_by_name" in full


def test_read_raising_marks_failed(db, seeded, monkeypatch):
    _, res = make_result(db)
    r = R.enqueue(db, res, "")
    R.claim_next(db)

    def boom(data, hint):
        raise RuntimeError("poison")

    monkeypatch.setattr(R.radiology, "read", boom)
    frame = R.process(db, r, get=lambda key: b"img")
    assert r.status == "failed" and r.ai_suggested["source"] == "rules" and r.finished_at
    assert frame["status"] == "failed"


def test_missing_exam_result_marks_failed(db, seeded, monkeypatch):
    _, res = make_result(db)
    r = R.enqueue(db, res, "")
    R.claim_next(db)
    real_get = db.get
    monkeypatch.setattr(db, "get", lambda model, key: None if model is type(res) else real_get(model, key))
    frame = R.process(db, r, get=lambda key: b"img")
    assert r.status == "failed" and r.ai_suggested["draft_text"] and frame["status"] == "failed"
