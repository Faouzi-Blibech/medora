"""Radiograph reading jobs (spec 2026-10-10-radiograph-reading-design.md): uploads enqueue, the worker thread
drafts, a doctor confirms. The model call lives in app/ai/radiology.py; this module owns states and storage."""

import logging
import threading
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import radiology
from app.config import get_settings
from app.db import SessionLocal
from app.ids import new_id
from app.iot import publisher
from app.iot.ingest import scope_for
from app.models import ExamResult, RadiographReading, User
from app.schemas import iso
from app.services import storage

log = logging.getLogger("ward.radiology")


def is_radiograph(code: str, content_type: str) -> bool:
    return code in radiology.RULES["codes"] and content_type in radiology.RULES["image_types"]


def enqueue(db: Session, result: ExamResult, hint: str) -> RadiographReading:
    r = RadiographReading(id=new_id(db, "rr"), exam_result_id=result.id, patient_id=result.patient_id,
                          status="queued", hint=(hint or "")[:120])
    db.add(r)
    db.flush()
    return r


def claim_next(db: Session) -> RadiographReading | None:
    r = db.scalars(select(RadiographReading).where(RadiographReading.status == "queued")
                   .order_by(RadiographReading.created_at, RadiographReading.id)
                   .limit(1).with_for_update(skip_locked=True)).first()
    if r is not None:
        r.status, r.started_at = "running", datetime.now(UTC)
        db.commit()
    return r


def process(db: Session, r: RadiographReading, get=None) -> dict:
    get = get or storage.get
    lang = get_settings().radiology_report_lang
    try:
        result = db.get(ExamResult, r.exam_result_id)
        try:
            data = get(result.file_key)
        except Exception as e:
            log.warning("reading %s: file unavailable: %s", r.id, e)
            status, ai = "failed", radiology.template(lang, "file unavailable")
        else:
            hint = r.hint
            db.commit()  # do not hold a transaction open during the slow model call
            status, ai = radiology.read(data, hint)
    except Exception:
        log.exception("reading %s: processing error", r.id)
        db.rollback()
        status, ai = "failed", radiology.template(lang, "processing error")
    r.status, r.ai_suggested, r.finished_at = status, ai, datetime.now(UTC)
    db.commit()
    return {"type": "radiograph_reading", "reading_id": r.id, "exam_result_id": r.exam_result_id,
            "patient_id": r.patient_id, "status": r.status, "scope": scope_for(db, r.patient_id)}


def recover(db: Session) -> int:
    rows = db.scalars(select(RadiographReading).where(RadiographReading.status == "running")).all()
    for r in rows:
        r.status, r.started_at = "queued", None
    db.commit()
    return len(rows)


def tick(db: Session, publish=None, get=None) -> bool:
    r = claim_next(db)
    if r is None:
        return False
    (publish or publisher.publish_ws_frame)(process(db, r, get=get))
    return True


def run_forever(stop: threading.Event, poll_s: float = 3.0) -> None:
    """Worker thread: one job at a time (one GPU). Never dies on a bad job."""
    with SessionLocal() as db:
        n = recover(db)
        if n:
            log.info("re-queued %d interrupted radiograph readings", n)
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                busy = tick(db)
        except Exception:
            log.exception("radiograph job loop error")
            busy = False
        if not busy:
            stop.wait(poll_s)


def _name(db: Session, user_id: str | None) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return u.name if u else None


def to_out(db: Session, r: RadiographReading, viewer: User) -> dict:
    if viewer.role != "doctor":
        return {"id": r.id, "exam_result_id": r.exam_result_id, "status": r.status}
    return {"id": r.id, "exam_result_id": r.exam_result_id, "patient_id": r.patient_id, "status": r.status,
            "hint": r.hint, "ai_suggested": r.ai_suggested, "final_text": r.final_text,
            "human_confirmed_by": r.human_confirmed_by, "confirmed_by_name": _name(db, r.human_confirmed_by),
            "confirmed_at": iso(r.confirmed_at), "created_at": iso(r.created_at), "finished_at": iso(r.finished_at)}


def confirm(db: Session, r: RadiographReading, user: User, text: str, now: datetime) -> None:
    r.final_text, r.human_confirmed_by, r.confirmed_at = text, user.id, now
    db.get(ExamResult, r.exam_result_id).report_text = text
    db.flush()
