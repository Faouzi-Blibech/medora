"""One patient's record as retrieval sources for the chat assistants (app/ai/chat.py), filtered by role.

Doctors and nurses get the whole record: facts, referrals and triage, notes, prescriptions, today's doses, vitals,
exam reports and the text of uploaded PDF reports, and the latest AI summary. Patients get only what their own app
already shows: today's doses, their appointments, the exams to do and their latest readings. Images are never read.
"""

import io
import logging
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import copilot
from app.ai.rag import Source
from app.models import Admission, AiSummary, Appointment, ExamOrder, ExamResult, MedDose, Note, Patient, Prescription, User, Vital
from app.services import storage
from app.services.schedule import local_to_utc, today_local

log = logging.getLogger(__name__)
NOTES_LIMIT = 40
PDF_CHARS = 20_000


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _day(dt: datetime | None) -> str:
    return dt.astimezone(UTC).strftime("%d %b %Y %H:%M UTC") if dt else ""


def _age(dob: date | None) -> str:
    if dob is None:
        return "age unknown"
    t = date.today()
    return f"{t.year - dob.year - ((t.month, t.day) < (dob.month, dob.day))} years old"


@lru_cache(maxsize=256)
def _pdf_text(file_key: str) -> str:
    """Text layer of an uploaded PDF report (cached per file). Scanned PDFs without text give ""."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(storage.get(file_key)))
        return "\n".join(page.extract_text() or "" for page in reader.pages)[:PDF_CHARS]
    except Exception as e:  # missing pypdf, MinIO down, broken file: the report text still counts
        log.warning("could not read PDF %s: %s", file_key, e)
        return ""


def _name(db: Session, user_id: str | None) -> str:
    u = db.get(User, user_id) if user_id else None
    return u.name if u else "staff"


def build(db: Session, p: Patient, role: str) -> list[Source]:
    staff = role in ("doctor", "nurse")
    now = datetime.now(UTC)
    out: list[Source] = []

    adm = db.scalar(select(Admission).where(Admission.patient_id == p.id).order_by(Admission.admitted_at.desc())
                    .limit(1))
    facts = [f"Sex {p.sex or 'unknown'}, {_age(p.date_of_birth)}.", f"Ward: {p.ward or 'none'}."]
    if adm is not None:
        facts.append(f"Bed {adm.bed}, admitted {_day(adm.admitted_at)}"
                     + (f", discharged {_day(adm.discharged_at)}." if adm.discharged_at else ", still admitted."))
    facts.append(f"Allergies: {', '.join(map(str, p.allergies)) if p.allergies else 'none recorded'}.")
    if staff and p.history:
        facts.append(f"Medical history: {p.history}")
    out.append(Source("patient:facts", "facts", "Patient facts", None, " ".join(facts)))

    for a in db.scalars(select(Appointment).where(Appointment.patient_id == p.id)
                        .order_by(Appointment.created_at.desc()).limit(10)):
        text = f"Status {a.status}." + (f" Slot {_day(a.slot_at)}." if a.slot_at else "")
        if staff:
            text += f" Referral: {a.referral_text}" + (f" Symptoms: {', '.join(a.symptoms)}." if a.symptoms else "")
            reasons = (a.ai_suggested or {}).get("reasons") or []
            if reasons:
                text += f" AI triage (suggestion) urgency {a.urgency_ai}: {'; '.join(reasons)}."
        out.append(Source(f"appointment:{a.id}", "appointment", f"Appointment request {_day(a.created_at)}",
                          _iso(a.created_at), text))

    if staff:
        for n in db.scalars(select(Note).where(Note.patient_id == p.id).order_by(Note.created_at.desc())
                            .limit(NOTES_LIMIT)):
            out.append(Source(f"note:{n.id}", "note", f"Note by {_name(db, n.author_id)} · {_day(n.created_at)}",
                              _iso(n.created_at), n.text))

    for rx in db.scalars(select(Prescription).where(Prescription.patient_id == p.id)
                         .order_by(Prescription.created_at.desc()).limit(10)):
        items = "; ".join(f"{i.get('med')} at {', '.join(i.get('times') or [])} for {i.get('days')} days"
                          for i in rx.items)
        text = f"{'Active' if rx.active else 'Stopped'} prescription: {items}."
        if rx.care_plan:
            text += f" Care plan: {rx.care_plan}"
        out.append(Source(f"rx:{rx.id}", "prescription", f"Prescription {_day(rx.created_at)}",
                          _iso(rx.created_at), text))

    day = today_local()
    doses = db.scalars(select(MedDose).where(MedDose.patient_id == p.id,
                                             MedDose.scheduled_at >= local_to_utc(day, "00:00"),
                                             MedDose.scheduled_at < local_to_utc(day + timedelta(days=1), "00:00"))
                       .order_by(MedDose.scheduled_at)).all()
    if doses:
        text = " ".join(f"{d.time_of_day} {', '.join(d.meds)}: {d.status}"
                        + (" (time already passed)" if d.status == "scheduled" and d.scheduled_at <= now else "") + "."
                        for d in doses)
        out.append(Source("doses:today", "doses", "Today's doses (Tunis time)", _iso(now), text))

    since = now - timedelta(hours=24)
    vitals = db.scalars(select(Vital).where(Vital.patient_id == p.id, Vital.ts >= since).order_by(Vital.ts)).all()
    if vitals:
        v = vitals[-1]
        text = copilot._stats_text([{"hr": x.hr, "spo2": x.spo2, "temp": x.temp, "news2": x.news2} for x in vitals])
        text += f" Latest reading {_day(v.ts)}: HR {v.hr}, SpO2 {v.spo2}%, temperature {v.temp} °C, NEWS2 {v.news2}."
        out.append(Source("vitals:24h", "vitals", "Vital signs, last 24 h", _iso(v.ts), text))

    for o in db.scalars(select(ExamOrder).where(ExamOrder.patient_id == p.id).order_by(ExamOrder.created_at.desc())):
        if role == "patient" and o.status not in ("ordered", "done"):
            continue
        out.append(Source(f"exam:{o.id}", "exam", f"Exam: {o.label} ({o.department})", _iso(o.created_at),
                          f"{o.label}, {o.department}: {o.status}." + (f" Done {_day(o.done_at)}." if o.done_at else "")))
        if not staff:
            continue
        for r in db.scalars(select(ExamResult).where(ExamResult.exam_order_id == o.id)):
            text = r.report_text or ""
            if r.content_type == "application/pdf":
                text = f"{text}\n{_pdf_text(r.file_key)}".strip()
            if text:
                out.append(Source(f"result:{r.id}", "report", f"Report: {o.label} · {_day(r.created_at)}",
                                  _iso(r.created_at), text))

    if staff:
        s = db.scalar(select(AiSummary).where(AiSummary.patient_id == p.id).order_by(AiSummary.created_at.desc())
                      .limit(1))
        if s is not None:
            state = "reviewed by a doctor" if s.human_confirmed_by else "not reviewed yet"
            out.append(Source(f"summary:{s.id}", "ai_summary", f"AI daily summary ({state})", _iso(s.created_at),
                              s.ai_suggested.get("summary", "")))
    return out
