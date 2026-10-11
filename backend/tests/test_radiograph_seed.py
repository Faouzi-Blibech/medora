from app.models import ExamOrder, ExamResult, RadiographReading
from app.radiograph_seed import ASSETS, DEMO, requeue, seed_radiographs


def test_assets_exist_and_are_credited():
    credits = (ASSETS / "CREDITS.md").read_text(encoding="utf-8")
    for row in DEMO:
        assert (ASSETS / row["file"]).stat().st_size < 1_500_000
        assert row["file"] in credits
    assert "CC0" in credits


def test_seed_radiographs_idempotent(db, seeded):
    put = []
    assert seed_radiographs(db, put=lambda key, data, ct: put.append((key, ct))) == len(DEMO)
    assert len(put) == len(DEMO) and all(ct == "image/jpeg" for _, ct in put)
    assert db.query(RadiographReading).filter(RadiographReading.status == "queued").count() == len(DEMO)
    assert seed_radiographs(db, put=lambda *a: put.append(a)) == 0 and len(put) == len(DEMO)
    o = db.get(ExamOrder, "ex-0901")
    assert o.department == "Imaging" and o.status == "done" and db.get(ExamResult, "er-0901").content_type == "image/jpeg"


def test_requeue_resets_unavailable_and_failed_only(db, seeded):
    from datetime import UTC, datetime

    seed_radiographs(db, put=lambda *a: None)
    now = datetime.now(UTC)
    rows = {r.id: r for r in db.query(RadiographReading).order_by(RadiographReading.id)}
    rows["rr-0901"].status, rows["rr-0901"].started_at, rows["rr-0901"].finished_at = "unavailable", now, now
    rows["rr-0902"].status, rows["rr-0902"].finished_at = "failed", now
    rows["rr-0903"].status, rows["rr-0903"].final_text = "unavailable", "Doctor wrote this"  # confirmed: keep
    rows["rr-0904"].status = "ready"
    db.flush()
    assert requeue(db) == 2
    db.expire_all()
    for rid in ("rr-0901", "rr-0902"):
        r = db.get(RadiographReading, rid)
        assert (r.status, r.started_at, r.finished_at) == ("queued", None, None)
    assert db.get(RadiographReading, "rr-0903").status == "unavailable"
    assert db.get(RadiographReading, "rr-0904").status == "ready"
    assert requeue(db) == 0
