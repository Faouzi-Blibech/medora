"""Health calendar (api.md 1.13): every active user reads events and sets category prefs; admins curate and can
push an event now. Rules live in app/services/health_calendar.py."""

from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_roles
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError, not_found
from app.ids import new_id
from app.integrations import n8n
from app.models import HealthEvent, User
from app.services import health_calendar as H
from app.services.audit import audit

router = APIRouter(tags=["health-calendar"])

Category = Literal["screening", "vaccination", "chronic_disease", "infectious_disease", "lifestyle", "mental_health",
                   "blood_donation"]
RoleName = Literal["patient", "nurse", "doctor", "admin"]


class Title(BaseModel):
    en: str = Field(min_length=1, max_length=200)
    fr: str = Field(min_length=1, max_length=200)
    ar: str = Field(min_length=1, max_length=200)


class Description(BaseModel):
    en: str = Field(default="", max_length=2000)
    fr: str = Field(default="", max_length=2000)
    ar: str = Field(default="", max_length=2000)


class Audience(BaseModel):
    roles: list[RoleName] = Field(min_length=1)
    sex: Literal["F", "M"] | None = None
    min_age: int | None = Field(default=None, ge=0, le=120)
    max_age: int | None = Field(default=None, ge=0, le=120)

    @model_validator(mode="after")
    def _ages(self):
        if self.min_age is not None and self.max_age is not None and self.min_age > self.max_age:
            raise ValueError("min_age is above max_age")
        return self


Url = Field(default=None, max_length=500, pattern=r"^https?://")


class EventIn(BaseModel):
    title: Title
    description: Description = Description()
    category: Category
    starts_on: date
    ends_on: date
    audience: Audience
    notify_days_before: int = Field(default=3, ge=0, le=30)
    organizer: str | None = Field(default=None, max_length=120)
    source_url: str | None = Url


class EventPatch(BaseModel):
    title: Title | None = None
    description: Description | None = None
    category: Category | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    audience: Audience | None = None
    notify_days_before: int | None = Field(default=None, ge=0, le=30)
    organizer: str | None = Field(default=None, max_length=120)
    source_url: str | None = Url


class PrefsIn(BaseModel):
    following: dict[str, bool]


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _bad_dates(starts: date, ends: date) -> None:
    if ends < starts:
        raise ApiError(422, "bad_dates", "ends_on is before starts_on")


def _event(db: Session, event_id: str) -> HealthEvent:
    ev = db.get(HealthEvent, event_id)
    if ev is None:
        raise not_found("health event")
    return ev


def _out(db: Session, user: User, ev: HealthEvent) -> dict:
    return H.to_out(ev, matches_me=H.matches(user, H.patient_of(db, user), ev),
                    following=H.prefs(db, user.id)[ev.category])


@router.get("/health-events")
def list_events(from_: date | None = Query(default=None, alias="from"), to: date | None = None,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    start = from_ or H._today()
    end = to or start + timedelta(days=365)
    rows = db.scalars(select(HealthEvent).where(HealthEvent.starts_on <= end, HealthEvent.ends_on >= start)
                      .order_by(HealthEvent.starts_on, HealthEvent.id)).all()
    patient, following = H.patient_of(db, user), H.prefs(db, user.id)
    return [H.to_out(e, matches_me=H.matches(user, patient, e), following=following[e.category]) for e in rows]


@router.post("/health-events", status_code=201)
def create_event(body: EventIn, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)) -> dict:
    _bad_dates(body.starts_on, body.ends_on)
    ev = HealthEvent(id=new_id(db, "he"), created_by=user.id, **body.model_dump())
    db.add(ev)
    db.commit()
    return _out(db, user, ev)


@router.patch("/health-events/{event_id}")
def update_event(event_id: str, body: EventPatch, user: User = Depends(require_roles("admin")),
                 db: Session = Depends(get_db)) -> dict:
    ev = _event(db, event_id)
    changes = body.model_dump(exclude_unset=True)
    for k in ("title", "description", "category", "starts_on", "ends_on", "audience", "notify_days_before"):
        if k in changes and changes[k] is None:
            raise ApiError(422, "invalid", f"{k} cannot be null")
    _bad_dates(changes.get("starts_on", ev.starts_on), changes.get("ends_on", ev.ends_on))
    if "starts_on" in changes and changes["starts_on"] != ev.starts_on:
        ev.announced_at = None  # a new date is a new announcement
    for k, v in changes.items():
        setattr(ev, k, v)
    db.commit()
    return _out(db, user, ev)


@router.delete("/health-events/{event_id}", status_code=204)
def delete_event(event_id: str, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    db.delete(_event(db, event_id))
    db.commit()
    return Response(status_code=204)


@router.post("/health-events/{event_id}/notify")
def notify_event(event_id: str, request: Request, user: User = Depends(require_roles("admin")),
                 db: Session = Depends(get_db)) -> dict:
    ev = _event(db, event_id)
    payload = H.upcoming_payload(db, ev, get_settings().web_url)
    ev.announced_at = datetime.now(UTC)
    audit(db, user, "notify", "health_event", ev.id, ip=_ip(request))
    n8n.emit_after_commit(db, "health_event.upcoming", payload)
    db.commit()
    return {"recipients": payload["recipient_count"]}


@router.get("/me/health-prefs")
def get_prefs(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {"following": H.prefs(db, user.id)}


@router.put("/me/health-prefs")
def put_prefs(body: PrefsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        out = H.set_prefs(db, user.id, body.following)
    except ValueError as e:
        raise ApiError(422, "invalid", str(e)) from e
    db.commit()
    return {"following": out}
