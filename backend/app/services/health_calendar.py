"""Health calendar rules (spec 2026-10-10-health-calendar-design.md): audience matching, per-category opt-out,
push recipients and the `health_event.upcoming` payload (n8n-webhooks 1.4). Routers stay thin."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HealthEvent, HealthEventPref, Patient, User

CATEGORIES = (
    "screening",
    "vaccination",
    "chronic_disease",
    "infectious_disease",
    "lifestyle",
    "mental_health",
    "blood_donation",
)
ROLES = ("patient", "nurse", "doctor", "admin")
_TITLES = {"dr", "dr.", "nurse", "mme", "m.", "mr", "mrs", "pr", "pr."}


def _today() -> date:
    """Today in Africa/Tunis (UTC+1, no DST)."""
    return (datetime.now(UTC) + timedelta(hours=1)).date()


def age_on(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def matches(user: User, patient: Patient | None, ev: HealthEvent) -> bool:
    """Role first; sex and age limits apply to patients only and never match an unknown value."""
    aud = ev.audience or {}
    if user.role not in aud.get("roles", []):
        return False
    if user.role != "patient":
        return True
    sex, lo, hi = aud.get("sex"), aud.get("min_age"), aud.get("max_age")
    if sex is None and lo is None and hi is None:
        return True
    if patient is None:
        return False
    if sex is not None and patient.sex != sex:
        return False
    if lo is not None or hi is not None:
        if patient.date_of_birth is None:
            return False
        age = age_on(patient.date_of_birth, ev.starts_on)
        if (lo is not None and age < lo) or (hi is not None and age > hi):
            return False
    return True


def patient_of(db: Session, user: User) -> Patient | None:
    return db.get(Patient, user.patient_id) if user.role == "patient" and user.patient_id else None


def _unfollowed(db: Session, user_id: str) -> set[str]:
    return set(
        db.scalars(
            select(HealthEventPref.category).where(
                HealthEventPref.user_id == user_id, HealthEventPref.following.is_(False)
            )
        )
    )


def prefs(db: Session, user_id: str) -> dict[str, bool]:
    off = _unfollowed(db, user_id)
    return {c: c not in off for c in CATEGORIES}


def set_prefs(db: Session, user_id: str, changes: dict[str, bool]) -> dict[str, bool]:
    unknown = set(changes) - set(CATEGORIES)
    if unknown:
        raise ValueError(f"unknown category: {sorted(unknown)[0]}")
    for cat, following in changes.items():
        row = db.get(HealthEventPref, (user_id, cat))
        if row is None:
            db.add(HealthEventPref(user_id=user_id, category=cat, following=bool(following)))
        else:
            row.following = bool(following)
    db.flush()
    return prefs(db, user_id)


def recipients(db: Session, ev: HealthEvent) -> list[tuple[User, Patient | None]]:
    roles = list((ev.audience or {}).get("roles", []))
    users = db.scalars(
        select(User).where(User.status == "active", User.role.in_(roles)).order_by(User.id)
    ).all()
    out = []
    for u in users:
        p = patient_of(db, u)
        if matches(u, p, ev) and ev.category not in _unfollowed(db, u.id):
            out.append((u, p))
    return out


def _first_name(user: User, patient: Patient | None) -> str:
    if patient is not None and patient.first_name:
        return patient.first_name
    words = [w for w in (user.name or "").split() if w.lower() not in _TITLES]
    return words[0] if words else ""


def to_out(ev: HealthEvent, *, matches_me: bool, following: bool) -> dict:
    return {
        "id": ev.id,
        "title": ev.title,
        "description": ev.description,
        "category": ev.category,
        "starts_on": ev.starts_on.isoformat(),
        "ends_on": ev.ends_on.isoformat(),
        "audience": ev.audience,
        "notify_days_before": ev.notify_days_before,
        "organizer": ev.organizer,
        "source_url": ev.source_url,
        "announced_at": ev.announced_at.isoformat().replace("+00:00", "Z") if ev.announced_at else None,
        "matches_me": matches_me,
        "following": following,
    }


def upcoming_payload(db: Session, ev: HealthEvent, web_url: str) -> dict:
    people = [
        {"first_name": _first_name(u, p), "role": u.role, "email": u.email, "lang": "fr"}
        for u, p in recipients(db, ev)
    ]
    return {
        "event_id": ev.id,
        "title": ev.title,
        "category": ev.category,
        "starts_on": ev.starts_on.isoformat(),
        "ends_on": ev.ends_on.isoformat(),
        "organizer": ev.organizer,
        "source_url": ev.source_url,
        "web_url": f"{web_url.rstrip('/')}/calendar",
        "recipients": people,
        "recipient_count": len(people),
    }


def due(db: Session, today: date) -> list[HealthEvent]:
    """Not yet announced, inside [starts_on - notify_days_before, ends_on]."""
    rows = db.scalars(
        select(HealthEvent)
        .where(HealthEvent.announced_at.is_(None), HealthEvent.ends_on >= today)
        .order_by(HealthEvent.starts_on, HealthEvent.id)
    ).all()
    return [e for e in rows if e.starts_on - timedelta(days=e.notify_days_before) <= today]
