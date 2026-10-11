# Health Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A calendar of important Tunisian public-health events, visible to every Medora role, with audience-targeted, opt-out-able push (n8n W9: WhatsApp + email) and admin curation.

**Architecture:** Two new tables (`health_events`, `health_event_prefs`) behind one service module (`app/services/health_calendar.py`: matching, prefs, recipients, payloads). One router for users/admin, two new n8n callbacks. Web gets one data layer addition (types, api, mocks), one pure helper module, one shared `HealthCalendar` component reused by staff routes, the patient tab and a full-width `/calendar` page.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2 + pytest (Postgres); Next.js 16 App Router, React 19, strict TS, CSS Modules; n8n workflow JSON.

**Spec:** `docs/superpowers/specs/2026-10-10-health-calendar-design.md` (read it first).

## Global Constraints

- Git: branch `wali/health-calendar`. Conventional Commits. **No AI attribution** (no `Co-Authored-By: Claude`, no "Generated with Claude Code").
- Contracts win over code: bump `api.md` 1.9 → **1.10**, `data-model.md` 1.5 → **1.6**, `n8n-webhooks.md` 1.3 → **1.4**, each with a changelog line.
- Categories (exact strings): `screening`, `vaccination`, `chronic_disease`, `infectious_disease`, `lifestyle`, `mental_health`, `blood_donation`.
- Roles (exact strings): `patient`, `nurse`, `doctor`, `admin`.
- Event ids `he-0001`…; seed ids `he-0001`…`he-0017` fixed; `reserve_upto(db, "he", 17)`.
- n8n payloads carry **first names only**; no national IDs, no full records.
- Event push never fails the API (`n8n.emit_after_commit`).
- All UI text in en/fr/ar via `web/src/i18n/messages/*.ts` (`messages({en, fr, ar})`); Arabic is RTL, so use logical CSS (`margin-inline-start`, `inset-inline-*`, `text-align: start`).
- Honesty line on every calendar view: "Dates as announced. Check with the Ministry of Health or ONFP."
- Python: run tests from `backend/` with the venv: `.venv/Scripts/python -m pytest …`. Postgres from `docker compose` is at `localhost:5432` (db `ward`, user/pass `ward`).
- Web: from `web/`: `npm run typecheck`, `npm run build`. Mock mode is the default (`NEXT_PUBLIC_USE_MOCKS` unset = `1`); the mock clock is `2026-10-05T08:12:00Z`.

## Review Focus

1. A patient with no `sex` or no `date_of_birth` vs an age/sex-limited event → must **not** match (and must not crash). Test in Task 3.
2. Age boundary on the event's `starts_on` (birthday the day after start → still the younger age). Test in Task 3.
3. `PATCH` that moves `ends_on` before the stored `starts_on` (only one field sent) → 422 `bad_dates`. Test in Task 5.
4. `PUT /me/health-prefs` with an unknown category → 422, nothing stored. Test in Task 5.
5. Disabled users and pending users never appear in push recipients. Test in Task 3.

---

## File Structure

Backend (Wali):
- Create `backend/app/models/health.py` — `HealthEvent`, `HealthEventPref`.
- Modify `backend/app/models/__init__.py` — export them.
- Create `backend/alembic/versions/0006_health_calendar.py`.
- Create `backend/app/services/health_calendar.py` — all rules.
- Create `backend/app/health_seed.py` — the 17 events + `seed_health_events(db)`.
- Modify `backend/app/seed.py` — call it on both branches.
- Create `backend/app/routers/health_events.py` — user + admin endpoints.
- Modify `backend/app/routers/integrations.py` — `/health-events/due`, `/health-events/{id}/announced`.
- Modify `backend/app/main.py`, `backend/app/config.py` (`web_url`), `infra/docker-compose.yml` (api env `WEB_URL`).
- Tests: `backend/tests/test_health_models.py`, `test_health_service.py`, `test_health_seed.py`, `test_health_api.py`, `test_health_integrations.py`.

n8n (Faouzi's lane, tagged): `n8n/workflows/W9-health-calendar.json`, modify `W0-router.json`, `n8n/README.md`.

Web (Faouzi's lane, tagged):
- Modify `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/mocks/index.ts`.
- Create `web/src/mocks/healthEvents.ts` (generated from the backend seed).
- Create `web/src/lib/healthCalendar.ts` (pure helpers).
- Create `web/src/i18n/messages/calendar.ts`; modify `web/src/i18n/messages/index.ts`.
- Create `web/src/components/calendar/HealthCalendar.tsx` + `.module.css`, `EventForm.tsx`, `UpcomingBanner.tsx` + `.module.css`, `useHealthEvents.ts`.
- Create routes `web/src/app/{doctor,nurse,admin,patient}/calendar/page.tsx`, `web/src/app/calendar/page.tsx` + `layout.tsx`.
- Modify `web/src/components/Sidebar.tsx`, `RoleShell.tsx`, `patient/PatientScreen.tsx`, `patient/Patient.module.css`, `patient/Home.tsx`.

---

### Task 1: Contract bumps

**Files:**
- Modify: `docs/contracts/data-model.md`, `docs/contracts/api.md`, `docs/contracts/n8n-webhooks.md`

**Interfaces:**
- Produces: the written contract every later task implements (copy the tables from the spec sections "Data", "API", "n8n").

- [ ] **Step 1: data-model.md** — set header `> **Version:** 1.6 (2026-10-10)`; add a section `### health_events` and `### health_event_prefs` with exactly the column tables from the spec "Data" section (including the `audience` JSON shape and the "no row = following" rule); add changelog line:
  `- **1.6** (2026-10-10): health calendar — \`health_events\` (dated public-health events with en/fr/ar text, category, audience, \`announced_at\`) and \`health_event_prefs\` (opt-out per category). Migration 0006.`
- [ ] **Step 2: api.md** — header `1.10 (2026-10-10)`; add section `## Health calendar` with the `HealthEvent` JSON example and the endpoint table from the spec "API" section (7 user/admin endpoints), the audit note, and under the Integrations section add the two `/integrations/n8n/health-events/*` callbacks. Changelog:
  `- **1.10** (2026-10-10): health calendar — \`GET/POST /health-events\`, \`PATCH/DELETE /health-events/{id}\`, \`POST /health-events/{id}/notify\`, \`GET/PUT /me/health-prefs\`, n8n callbacks \`GET /integrations/n8n/health-events/due\` and \`POST /integrations/n8n/health-events/{id}/announced\`.`
- [ ] **Step 3: n8n-webhooks.md** — fix the stale first-line title to `# n8n contract`, header `1.4 (2026-10-10)`; add the `health_event.upcoming` row to "Events" (data = the spec payload), the two callbacks to "Callbacks", the W9 row to "Workflows" (priority "core for the calendar demo", steps from the spec). Changelog:
  `- **1.4** (2026-10-10): \`health_event.upcoming\` event, health-events due/announced callbacks, W9 health calendar (daily cron + Notify now).`
- [ ] **Step 4: Commit**

```bash
git add docs/contracts
git commit -m "docs(contracts): api 1.10, data-model 1.6, n8n 1.4 for the health calendar"
```

---

### Task 2: Models and migration 0006

**Files:**
- Create: `backend/app/models/health.py`, `backend/alembic/versions/0006_health_calendar.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_health_models.py`

**Interfaces:**
- Produces: `app.models.HealthEvent` (columns as spec), `app.models.HealthEventPref(user_id, category, following)`.

- [ ] **Step 1: Write the failing test** `backend/tests/test_health_models.py`

```python
from datetime import date

from app.models import HealthEvent, HealthEventPref


def test_event_roundtrip(db, seeded):
    ev = HealthEvent(id="he-9001", title={"en": "T", "fr": "T", "ar": "T"}, description={"en": "", "fr": "", "ar": ""},
                     category="screening", starts_on=date(2026, 10, 1), ends_on=date(2026, 10, 31),
                     audience={"roles": ["patient"], "sex": "F", "min_age": 40, "max_age": None})
    db.add(ev)
    db.flush()
    got = db.get(HealthEvent, "he-9001")
    assert got.notify_days_before == 3 and got.announced_at is None and got.audience["sex"] == "F"


def test_pref_roundtrip(db, seeded):
    db.add(HealthEventPref(user_id="u-0005", category="screening", following=False))
    db.flush()
    assert db.get(HealthEventPref, ("u-0005", "screening")).following is False
```

- [ ] **Step 2: Run** `cd backend && .venv/Scripts/python -m pytest tests/test_health_models.py -q` → FAIL (ImportError).

- [ ] **Step 3: Implement** `backend/app/models/health.py`

```python
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class HealthEvent(Base):
    """A dated public-health event (data-model 1.6). Text is {"en","fr","ar"}."""

    __tablename__ = "health_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[dict] = mapped_column(JSONB)
    description: Mapped[dict] = mapped_column(JSONB)
    category: Mapped[str] = mapped_column(String)
    starts_on: Mapped[date] = mapped_column(Date, index=True)
    ends_on: Mapped[date] = mapped_column(Date)
    audience: Mapped[dict] = mapped_column(JSONB)  # {"roles": [...], "sex": "F"|"M"|None, "min_age", "max_age"}
    notify_days_before: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    organizer: Mapped[str | None] = mapped_column(String)
    source_url: Mapped[str | None] = mapped_column(String)
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HealthEventPref(Base):
    """Opt-out per category: no row means the user follows it."""

    __tablename__ = "health_event_prefs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    category: Mapped[str] = mapped_column(String, primary_key=True)
    following: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
```

In `backend/app/models/__init__.py`: update the docstring to `(v1.6: health calendar)`, add `from app.models.health import HealthEvent, HealthEventPref`, and add `"HealthEvent", "HealthEventPref"` to `__all__` (keep it alphabetical).

`backend/alembic/versions/0006_health_calendar.py`:

```python
"""health calendar: health_events + health_event_prefs

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'health_events',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('title', postgresql.JSONB(), nullable=False),
        sa.Column('description', postgresql.JSONB(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('starts_on', sa.Date(), nullable=False),
        sa.Column('ends_on', sa.Date(), nullable=False),
        sa.Column('audience', postgresql.JSONB(), nullable=False),
        sa.Column('notify_days_before', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('organizer', sa.String(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('announced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_health_events_starts_on', 'health_events', ['starts_on'])
    op.create_table(
        'health_event_prefs',
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('category', sa.String(), primary_key=True),
        sa.Column('following', sa.Boolean(), nullable=False, server_default='true'),
    )


def downgrade() -> None:
    op.drop_table('health_event_prefs')
    op.drop_index('ix_health_events_starts_on', table_name='health_events')
    op.drop_table('health_events')
```

Check how 0004/0005 declare `created_at` and `nullable` defaults, and match them if they differ.

- [ ] **Step 4: Run** the test → PASS. Also run `.venv/Scripts/python -m pytest tests/test_seed.py -q` → PASS.
- [ ] **Step 5: Commit** `git add backend/app/models backend/alembic/versions/0006_health_calendar.py backend/tests/test_health_models.py && git commit -m "feat(backend): health_events and health_event_prefs tables (migration 0006)"`

---

### Task 3: Service — matching, prefs, recipients, payloads, due

**Files:**
- Create: `backend/app/services/health_calendar.py`
- Modify: `backend/app/config.py` (add `web_url: str = "http://localhost:3000"` next to `web_origin`), `infra/docker-compose.yml` (api service environment: `WEB_URL: ${WEB_URL:-http://localhost:3000}`; add it in the `api` service block, and in `worker` only if that block lists the same env vars as api)
- Test: `backend/tests/test_health_service.py`

**Interfaces:**
- Consumes: `HealthEvent`, `HealthEventPref` (Task 2).
- Produces (exact):
  - `CATEGORIES: tuple[str, ...]`, `ROLES: tuple[str, ...]`
  - `age_on(dob: date, on: date) -> int`
  - `matches(user: User, patient: Patient | None, ev: HealthEvent) -> bool`
  - `patient_of(db: Session, user: User) -> Patient | None`
  - `prefs(db: Session, user_id: str) -> dict[str, bool]` (all 7 keys)
  - `set_prefs(db: Session, user_id: str, changes: dict[str, bool]) -> dict[str, bool]` (raises `ValueError` on unknown category, before writing anything)
  - `recipients(db: Session, ev: HealthEvent) -> list[tuple[User, Patient | None]]`
  - `to_out(ev: HealthEvent, *, matches_me: bool, following: bool) -> dict`
  - `upcoming_payload(db: Session, ev: HealthEvent, web_url: str) -> dict`
  - `due(db: Session, today: date) -> list[HealthEvent]`

- [ ] **Step 1: Write the failing tests** `backend/tests/test_health_service.py`

```python
from datetime import date

import pytest

from app.models import HealthEvent, Patient
from app.services import health_calendar as H
from tests.helpers import make_patient, make_user

EV = dict(title={"en": "Octobre Rose", "fr": "Octobre Rose", "ar": "أكتوبر الوردي"},
          description={"en": "", "fr": "", "ar": ""}, category="screening")


def _ev(db, id_="he-9001", starts=date(2026, 10, 1), ends=date(2026, 10, 31), **aud):
    audience = {"roles": ["patient", "doctor", "nurse", "admin"], "sex": None, "min_age": None, "max_age": None}
    audience.update(aud)
    ev = HealthEvent(id=id_, starts_on=starts, ends_on=ends, audience=audience, notify_days_before=3, **EV)
    db.add(ev)
    db.flush()
    return ev


def _patient_user(db, email, sex, dob):
    p = make_patient(db, first="Salma")
    p.sex, p.date_of_birth = sex, dob
    u = make_user(db, email, role="patient", name="Salma Test")
    u.patient_id = p.id
    db.flush()
    return u, p


def test_age_on_birthday_boundary():
    assert H.age_on(date(1986, 10, 2), date(2026, 10, 1)) == 39
    assert H.age_on(date(1986, 10, 1), date(2026, 10, 1)) == 40


def test_role_must_be_in_audience(db, seeded):
    ev = _ev(db, roles=["patient"])
    doctor = make_user(db, "d9@medora.tn", role="doctor")
    assert H.matches(doctor, None, ev) is False


def test_sex_and_age_apply_to_patients(db, seeded):
    ev = _ev(db, sex="F", min_age=40)
    woman, wp = _patient_user(db, "w@x.tn", "F", date(1980, 1, 1))
    young, yp = _patient_user(db, "y@x.tn", "F", date(1995, 1, 1))
    man, mp = _patient_user(db, "m@x.tn", "M", date(1960, 1, 1))
    assert H.matches(woman, wp, ev) and not H.matches(young, yp, ev) and not H.matches(man, mp, ev)


def test_staff_ignore_sex_and_age(db, seeded):
    ev = _ev(db, sex="F", min_age=40)
    nurse = make_user(db, "n9@medora.tn", role="nurse")
    assert H.matches(nurse, None, ev) is True


def test_unknown_sex_or_birth_date_does_not_match_limited_event(db, seeded):
    u1, p1 = _patient_user(db, "a@x.tn", None, date(1970, 1, 1))
    u2, p2 = _patient_user(db, "b@x.tn", "F", None)
    assert not H.matches(u1, p1, _ev(db, "he-9002", sex="F"))
    assert not H.matches(u2, p2, _ev(db, "he-9003", min_age=40))
    assert H.matches(u2, p2, _ev(db, "he-9004"))  # no limits: everyone with the role


def test_max_age(db, seeded):
    ev = _ev(db, sex="F", min_age=11, max_age=13, starts=date(2027, 4, 5), ends=date(2027, 4, 30))
    girl, gp = _patient_user(db, "g@x.tn", "F", date(2014, 6, 1))   # 12 on 2027-04-05
    teen, tp = _patient_user(db, "t@x.tn", "F", date(2012, 1, 1))   # 15
    assert H.matches(girl, gp, ev) and not H.matches(teen, tp, ev)


def test_prefs_default_and_opt_out(db, seeded):
    assert H.prefs(db, "u-0005") == {c: True for c in H.CATEGORIES}
    out = H.set_prefs(db, "u-0005", {"screening": False})
    assert out["screening"] is False and out["vaccination"] is True
    assert H.set_prefs(db, "u-0005", {"screening": True})["screening"] is True


def test_set_prefs_rejects_unknown_category_without_writing(db, seeded):
    with pytest.raises(ValueError):
        H.set_prefs(db, "u-0005", {"vaccination": False, "astrology": False})
    assert H.prefs(db, "u-0005")["vaccination"] is True


def test_recipients_match_follow_and_active(db, seeded):
    ev = _ev(db, roles=["patient", "nurse"], sex="F", min_age=40)
    # seed: u-0005 is Amira (F, 1972) → match; nurses u-0002/3/6/7 → match
    ids = {u.id for u, _ in H.recipients(db, ev)}
    assert "u-0005" in ids and "u-0002" in ids and "u-0001" not in ids  # doctor not in roles
    H.set_prefs(db, "u-0002", {"screening": False})
    make_user(db, "off@medora.tn", role="nurse", status="disabled")
    make_user(db, "pend@medora.tn", role=None, status="pending")
    ids = {u.email for u, _ in H.recipients(db, ev)}
    assert "nurse@medora.tn" not in ids and "off@medora.tn" not in ids and "pend@medora.tn" not in ids


def test_payload_first_names_only(db, seeded):
    ev = _ev(db, roles=["patient", "doctor"])
    p = H.upcoming_payload(db, ev, "http://web")
    assert p["event_id"] == "he-9001" and p["web_url"] == "http://web/calendar"
    assert p["recipient_count"] == len(p["recipients"])
    amira = next(r for r in p["recipients"] if r["role"] == "patient")
    assert amira["first_name"] == "Amira" and set(amira) == {"first_name", "role", "email", "lang"}
    doc = next(r for r in p["recipients"] if r["role"] == "doctor")
    assert doc["first_name"] == "Trabelsi"  # "Dr Trabelsi": title dropped


def test_due_window(db, seeded):
    ev = _ev(db, starts=date(2026, 10, 10), ends=date(2026, 10, 10))
    assert ev not in H.due(db, date(2026, 10, 6))   # 4 days before, notify 3
    assert ev in H.due(db, date(2026, 10, 7))
    assert ev in H.due(db, date(2026, 10, 10))
    assert ev not in H.due(db, date(2026, 10, 11))  # over
    from datetime import UTC, datetime
    ev.announced_at = datetime.now(UTC)
    assert ev not in H.due(db, date(2026, 10, 8))


def test_to_out_shape(db, seeded):
    ev = _ev(db)
    out = H.to_out(ev, matches_me=True, following=False)
    assert out["starts_on"] == "2026-10-01" and out["matches_me"] is True and out["following"] is False
    assert out["announced_at"] is None
```

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_health_service.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement** `backend/app/services/health_calendar.py`

```python
"""Health calendar rules (spec 2026-10-10-health-calendar-design.md): audience matching, per-category opt-out,
push recipients and the `health_event.upcoming` payload (n8n-webhooks 1.4). Routers stay thin."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HealthEvent, HealthEventPref, Patient, User

CATEGORIES = ("screening", "vaccination", "chronic_disease", "infectious_disease", "lifestyle", "mental_health",
              "blood_donation")
ROLES = ("patient", "nurse", "doctor", "admin")
_TITLES = {"dr", "dr.", "nurse", "mme", "m.", "mr", "mrs", "pr", "pr."}


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
    return set(db.scalars(select(HealthEventPref.category).where(
        HealthEventPref.user_id == user_id, HealthEventPref.following.is_(False))))


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
    users = db.scalars(select(User).where(User.status == "active", User.role.in_(roles)).order_by(User.id)).all()
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
        "id": ev.id, "title": ev.title, "description": ev.description, "category": ev.category,
        "starts_on": ev.starts_on.isoformat(), "ends_on": ev.ends_on.isoformat(), "audience": ev.audience,
        "notify_days_before": ev.notify_days_before, "organizer": ev.organizer, "source_url": ev.source_url,
        "announced_at": ev.announced_at.isoformat().replace("+00:00", "Z") if ev.announced_at else None,
        "matches_me": matches_me, "following": following,
    }


def upcoming_payload(db: Session, ev: HealthEvent, web_url: str) -> dict:
    people = [{"first_name": _first_name(u, p), "role": u.role, "email": u.email, "lang": "fr"}
              for u, p in recipients(db, ev)]
    return {
        "event_id": ev.id, "title": ev.title, "category": ev.category,
        "starts_on": ev.starts_on.isoformat(), "ends_on": ev.ends_on.isoformat(),
        "organizer": ev.organizer, "source_url": ev.source_url, "web_url": f"{web_url.rstrip('/')}/calendar",
        "recipients": people, "recipient_count": len(people),
    }


def due(db: Session, today: date) -> list[HealthEvent]:
    """Not yet announced, inside [starts_on - notify_days_before, ends_on]."""
    rows = db.scalars(select(HealthEvent).where(HealthEvent.announced_at.is_(None), HealthEvent.ends_on >= today)
                      .order_by(HealthEvent.starts_on, HealthEvent.id)).all()
    return [e for e in rows if e.starts_on - timedelta(days=e.notify_days_before) <= today]
```

Config: in `backend/app/config.py` add `web_url: str = "http://localhost:3000"  # links in pushes (WEB_URL)` right after `web_origin`.

- [ ] **Step 4: Run** the tests → PASS. Run `ruff check app tests` and `ruff format app/services/health_calendar.py tests/test_health_service.py` if ruff is installed in the venv (`.venv/Scripts/python -m ruff …`); skip formatting if it would reformat unrelated files.
- [ ] **Step 5: Commit** `git add backend/app/services/health_calendar.py backend/app/config.py infra/docker-compose.yml backend/tests/test_health_service.py && git commit -m "feat(backend): health calendar rules - audience matching, opt-out prefs, recipients, push payload"`

---

### Task 4: Seed — 17 Tunisian health events

**Files:**
- Create: `backend/app/health_seed.py`
- Modify: `backend/app/seed.py`
- Test: `backend/tests/test_health_seed.py`

**Interfaces:**
- Consumes: `HealthEvent` (Task 2), `reserve_upto` (`app.ids`).
- Produces: `EVENTS: list[dict]` (keys: `id, title, description, category, starts_on, ends_on, audience, organizer, source_url`), `seed_health_events(db: Session) -> int` (number inserted). Task 8 generates the web mock from `EVENTS`.

- [ ] **Step 1: Write the failing test** `backend/tests/test_health_seed.py`

```python
from app.health_seed import EVENTS, seed_health_events
from app.models import HealthEvent
from app.services.health_calendar import CATEGORIES, ROLES


def test_seed_shape():
    assert [e["id"] for e in EVENTS] == [f"he-{n:04d}" for n in range(1, 18)]
    for e in EVENTS:
        assert e["category"] in CATEGORIES and e["ends_on"] >= e["starts_on"]
        assert set(e["audience"]["roles"]) <= set(ROLES) and e["audience"]["roles"]
        for f in ("title", "description"):
            assert set(e[f]) == {"en", "fr", "ar"} and all(e[f][k].strip() for k in ("en", "fr", "ar"))


def test_seed_is_idempotent_and_keeps_edits(db, seeded):
    assert db.query(HealthEvent).count() == 17  # seed() already ran it
    ev = db.get(HealthEvent, "he-0001")
    ev.organizer = "Edited"
    db.flush()
    assert seed_health_events(db) == 0
    assert db.get(HealthEvent, "he-0001").organizer == "Edited"
    db.delete(db.get(HealthEvent, "he-0002"))
    db.flush()
    assert seed_health_events(db) == 1
```

- [ ] **Step 2: Run** → FAIL (module missing).

- [ ] **Step 3: Implement** `backend/app/health_seed.py`

```python
"""The demo health calendar: important public-health events in Tunisia, Oct 2026 → Sep 2027 (spec table).
National campaign dates are announced yearly by the Ministry of Health / ONFP; these are the published or usual
dates, and the admin can edit them. Inserted only when the id is missing, so an admin edit is never overwritten."""

from datetime import date

from sqlalchemy.orm import Session

from app.ids import reserve_upto
from app.models import HealthEvent

ALL = ["patient", "nurse", "doctor", "admin"]
STAFF = ["nurse", "doctor", "admin"]


def _aud(roles=ALL, sex=None, min_age=None, max_age=None) -> dict:
    return {"roles": list(roles), "sex": sex, "min_age": min_age, "max_age": max_age}


def _t(en: str, fr: str, ar: str) -> dict:
    return {"en": en, "fr": fr, "ar": ar}


EVENTS: list[dict] = [
    dict(id="he-0001", category="screening", starts_on=date(2026, 9, 30), ends_on=date(2026, 10, 30),
         audience=_aud(["patient", *STAFF], sex="F", min_age=40), organizer="ONFP",
         source_url="https://www.onfp.tn",
         title=_t("Octobre Rose: free breast cancer screening", "Octobre Rose : dépistage gratuit du cancer du sein",
                  "أكتوبر الوردي: الكشف المجاني عن سرطان الثدي"),
         description=_t("Free clinical breast exams at ONFP centres and the Mamo Life mobile clinic in all 24 governorates.",
                        "Examens cliniques des seins gratuits dans les centres de l'ONFP et la clinique mobile Mamo Life, dans les 24 gouvernorats.",
                        "فحوصات سريرية مجانية للثدي في مراكز الديوان الوطني للأسرة والعمران البشري والعيادة المتنقلة Mamo Life في الولايات الـ24.")),
    dict(id="he-0002", category="mental_health", starts_on=date(2026, 10, 10), ends_on=date(2026, 10, 10),
         audience=_aud(), organizer="WHO", source_url="https://www.who.int/campaigns/world-mental-health-day",
         title=_t("World Mental Health Day", "Journée mondiale de la santé mentale", "اليوم العالمي للصحة النفسية"),
         description=_t("Talk about how you feel. Support is available at your basic health centre.",
                        "Parlez de ce que vous ressentez. Un soutien est disponible dans votre centre de santé de base.",
                        "تحدّث عمّا تشعر به. الدعم متوفر في مركز الصحة الأساسية القريب منك.")),
    dict(id="he-0003", category="vaccination", starts_on=date(2026, 10, 15), ends_on=date(2027, 2, 28),
         audience=_aud(["patient", *STAFF], min_age=65), organizer="Ministère de la Santé",
         source_url="http://www.santetunisie.rns.tn",
         title=_t("Seasonal flu vaccination", "Vaccination contre la grippe saisonnière", "التلقيح ضد النزلة الموسمية"),
         description=_t("Flu vaccine at pharmacies and basic health centres. Priority: people over 65, pregnant women, chronic illness, health workers.",
                        "Vaccin antigrippal en pharmacie et dans les centres de santé de base. Prioritaires : plus de 65 ans, femmes enceintes, maladies chroniques, soignants.",
                        "لقاح النزلة متوفر في الصيدليات ومراكز الصحة الأساسية. الأولوية: من تجاوزوا 65 سنة، الحوامل، أصحاب الأمراض المزمنة، والعاملون في الصحة.")),
    dict(id="he-0004", category="screening", starts_on=date(2026, 11, 1), ends_on=date(2026, 11, 30),
         audience=_aud(["patient", "doctor"], sex="M", min_age=50), organizer="Movember",
         source_url="https://movember.com",
         title=_t("Movember: prostate cancer awareness", "Movember : sensibilisation au cancer de la prostate",
                  "نوفمبر الأزرق: التوعية بسرطان البروستات"),
         description=_t("Men over 50: ask your doctor whether a prostate check is right for you.",
                        "Hommes de plus de 50 ans : demandez à votre médecin si un contrôle de la prostate vous concerne.",
                        "للرجال فوق 50 سنة: اسأل طبيبك إن كان فحص البروستات مناسبًا لك.")),
    dict(id="he-0005", category="chronic_disease", starts_on=date(2026, 11, 14), ends_on=date(2026, 11, 14),
         audience=_aud(), organizer="IDF / WHO", source_url="https://worlddiabetesday.org",
         title=_t("World Diabetes Day", "Journée mondiale du diabète", "اليوم العالمي للسكري"),
         description=_t("Free blood sugar checks are often offered on this day. Know your numbers.",
                        "Des contrôles gratuits de la glycémie sont souvent proposés ce jour-là. Connaissez vos chiffres.",
                        "غالبًا ما تُقدَّم فحوصات مجانية لنسبة السكر في الدم في هذا اليوم. اعرف أرقامك.")),
    dict(id="he-0006", category="infectious_disease", starts_on=date(2026, 12, 1), ends_on=date(2026, 12, 1),
         audience=_aud(["patient", *STAFF], min_age=15), organizer="UNAIDS / WHO",
         source_url="https://www.who.int/campaigns/world-aids-day",
         title=_t("World AIDS Day", "Journée mondiale de lutte contre le sida", "اليوم العالمي لمكافحة السيدا"),
         description=_t("Free and anonymous HIV testing is available. Ask at your health centre.",
                        "Le dépistage du VIH est gratuit et anonyme. Renseignez-vous dans votre centre de santé.",
                        "الكشف عن فيروس نقص المناعة مجاني وسري. استفسر في مركزك الصحي.")),
    dict(id="he-0007", category="screening", starts_on=date(2027, 2, 4), ends_on=date(2027, 2, 4),
         audience=_aud(), organizer="UICC", source_url="https://www.worldcancerday.org",
         title=_t("World Cancer Day", "Journée mondiale contre le cancer", "اليوم العالمي لمكافحة السرطان"),
         description=_t("Early detection saves lives. Ask which screening fits your age.",
                        "Le dépistage précoce sauve des vies. Demandez quel dépistage correspond à votre âge.",
                        "الكشف المبكر ينقذ الأرواح. اسأل عن الفحص المناسب لعمرك.")),
    dict(id="he-0008", category="chronic_disease", starts_on=date(2027, 2, 8), ends_on=date(2027, 3, 9),
         audience=_aud(["patient", "doctor", "nurse"], min_age=18), organizer="Ministère de la Santé",
         source_url="http://www.santetunisie.rns.tn",
         title=_t("Ramadan: fasting safely with diabetes or hypertension (approximate dates)",
                  "Ramadan : jeûner en sécurité avec un diabète ou une hypertension (dates approximatives)",
                  "رمضان: الصيام بأمان مع السكري أو ارتفاع ضغط الدم (تواريخ تقريبية)"),
         description=_t("See your doctor before Ramadan to adapt your treatment.",
                        "Consultez votre médecin avant le Ramadan pour adapter votre traitement.",
                        "راجع طبيبك قبل رمضان لتكييف علاجك.")),
    dict(id="he-0009", category="infectious_disease", starts_on=date(2027, 3, 24), ends_on=date(2027, 3, 24),
         audience=_aud(), organizer="WHO", source_url="https://www.who.int/campaigns/world-tb-day",
         title=_t("World Tuberculosis Day", "Journée mondiale de la tuberculose", "اليوم العالمي لمكافحة السل"),
         description=_t("A cough for more than two weeks needs a check. Diagnosis and treatment are free.",
                        "Une toux de plus de deux semaines doit être contrôlée. Le diagnostic et le traitement sont gratuits.",
                        "السعال لأكثر من أسبوعين يستوجب الفحص. التشخيص والعلاج مجانيان.")),
    dict(id="he-0010", category="lifestyle", starts_on=date(2027, 4, 7), ends_on=date(2027, 4, 7),
         audience=_aud(), organizer="WHO", source_url="https://www.who.int/campaigns/world-health-day",
         title=_t("World Health Day", "Journée mondiale de la santé", "اليوم العالمي للصحة"),
         description=_t("The WHO theme of the year, with events in health centres.",
                        "Le thème de l'année de l'OMS, avec des activités dans les centres de santé.",
                        "موضوع السنة لمنظمة الصحة العالمية، مع أنشطة في المراكز الصحية.")),
    dict(id="he-0011", category="vaccination", starts_on=date(2027, 4, 24), ends_on=date(2027, 4, 30),
         audience=_aud(), organizer="WHO / Ministère de la Santé",
         source_url="https://www.who.int/campaigns/world-immunization-week",
         title=_t("World Immunization Week", "Semaine mondiale de la vaccination", "الأسبوع العالمي للتلقيح"),
         description=_t("Check that your family's vaccination record is up to date.",
                        "Vérifiez que le carnet de vaccination de votre famille est à jour.",
                        "تأكد من أن دفتر تلقيح عائلتك محيَّن.")),
    dict(id="he-0012", category="vaccination", starts_on=date(2027, 4, 5), ends_on=date(2027, 4, 30),
         audience=_aud(["patient", "doctor", "nurse"], sex="F", min_age=11, max_age=13),
         organizer="Ministère de la Santé", source_url="http://www.santetunisie.rns.tn",
         title=_t("HPV vaccination for 12-year-old girls", "Vaccination HPV des filles de 12 ans",
                  "التلقيح ضد فيروس الورم الحليمي للفتيات في سن 12"),
         description=_t("Free, in schools (6th year) and at basic health centres, with parental consent.",
                        "Gratuite, à l'école (6e année) et dans les centres de santé de base, avec l'accord des parents.",
                        "مجاني، في المدارس (السنة السادسة) وفي مراكز الصحة الأساسية، بموافقة الوليّ.")),
    dict(id="he-0013", category="chronic_disease", starts_on=date(2027, 5, 17), ends_on=date(2027, 5, 17),
         audience=_aud(["patient", *STAFF], min_age=18), organizer="World Hypertension League",
         source_url="https://www.whleague.org",
         title=_t("World Hypertension Day", "Journée mondiale de l'hypertension", "اليوم العالمي لارتفاع ضغط الدم"),
         description=_t("Have your blood pressure measured. It is quick and free at health centres.",
                        "Faites mesurer votre tension. C'est rapide et gratuit dans les centres de santé.",
                        "قِس ضغط دمك. الأمر سريع ومجاني في المراكز الصحية.")),
    dict(id="he-0014", category="lifestyle", starts_on=date(2027, 5, 31), ends_on=date(2027, 5, 31),
         audience=_aud(["patient", *STAFF], min_age=15), organizer="WHO",
         source_url="https://www.who.int/campaigns/world-no-tobacco-day",
         title=_t("World No Tobacco Day", "Journée mondiale sans tabac", "اليوم العالمي للامتناع عن التدخين"),
         description=_t("Stop-smoking consultations are available. Ask your doctor.",
                        "Des consultations d'aide à l'arrêt du tabac existent. Parlez-en à votre médecin.",
                        "تتوفر استشارات للمساعدة على الإقلاع عن التدخين. تحدّث مع طبيبك.")),
    dict(id="he-0015", category="blood_donation", starts_on=date(2027, 6, 14), ends_on=date(2027, 6, 14),
         audience=_aud(["patient", *STAFF], min_age=18, max_age=65), organizer="CNTS / WHO",
         source_url="https://www.who.int/campaigns/world-blood-donor-day",
         title=_t("World Blood Donor Day", "Journée mondiale du donneur de sang", "اليوم العالمي للمتبرعين بالدم"),
         description=_t("Give blood at the national blood transfusion centre (CNTS) or a mobile unit.",
                        "Donnez votre sang au Centre national de transfusion sanguine (CNTS) ou dans une unité mobile.",
                        "تبرّع بالدم في المركز الوطني لنقل الدم أو في وحدة متنقلة.")),
    dict(id="he-0016", category="infectious_disease", starts_on=date(2027, 7, 28), ends_on=date(2027, 7, 28),
         audience=_aud(), organizer="WHO", source_url="https://www.who.int/campaigns/world-hepatitis-day",
         title=_t("World Hepatitis Day", "Journée mondiale contre l'hépatite", "اليوم العالمي لالتهاب الكبد"),
         description=_t("Hepatitis B and C can be tested and treated. Ask about a test.",
                        "Les hépatites B et C se dépistent et se traitent. Demandez un test.",
                        "يمكن الكشف عن التهاب الكبد ب و ج وعلاجهما. اسأل عن التحليل.")),
    dict(id="he-0017", category="chronic_disease", starts_on=date(2027, 9, 29), ends_on=date(2027, 9, 29),
         audience=_aud(["patient", *STAFF], min_age=18), organizer="World Heart Federation",
         source_url="https://world-heart-federation.org/world-heart-day",
         title=_t("World Heart Day", "Journée mondiale du cœur", "اليوم العالمي للقلب"),
         description=_t("Move more, eat less salt, check your blood pressure.",
                        "Bougez plus, mangez moins salé, contrôlez votre tension.",
                        "تحرّك أكثر، قلّل الملح، وراقب ضغط دمك.")),
]


def seed_health_events(db: Session) -> int:
    """Insert the seed events whose id is missing. Returns how many were inserted."""
    added = 0
    for e in EVENTS:
        if db.get(HealthEvent, e["id"]) is None:
            db.add(HealthEvent(notify_days_before=3, **e))
            added += 1
    db.flush()
    reserve_upto(db, "he", len(EVENTS))
    return added
```

In `backend/app/seed.py`: `from app.health_seed import seed_health_events`; in `seed()`, call `seed_health_events(db)` **before** `return False` in the already-seeded branch, and just before the final `for prefix, n in [...]: reserve_upto` loop in the fresh branch.

- [ ] **Step 4: Run** `.venv/Scripts/python -m pytest tests/test_health_seed.py tests/test_seed.py -q` → PASS.
- [ ] **Step 5: Commit** `git add backend/app/health_seed.py backend/app/seed.py backend/tests/test_health_seed.py && git commit -m "feat(backend): seed 17 Tunisian public-health events (Octobre Rose, flu, HPV, world days)"`

---

### Task 5: Router — `/health-events` and `/me/health-prefs`

**Files:**
- Create: `backend/app/routers/health_events.py`
- Modify: `backend/app/main.py` (import `health_events`, `app.include_router(health_events.router)`)
- Test: `backend/tests/test_health_api.py`

**Interfaces:**
- Consumes: `app.services.health_calendar as H` (Task 3), `get_current_user`, `require_roles` (`app.auth.deps`), `audit`, `n8n.emit_after_commit`, `get_settings().web_url`, `new_id`.
- Produces: HTTP endpoints exactly as api.md 1.10.

- [ ] **Step 1: Write the failing tests** `backend/tests/test_health_api.py`

```python
from app.models import AuditLog, HealthEvent
from tests.helpers import login

NEW = {"title": {"en": "Local vaccination day", "fr": "Journée de vaccination", "ar": "يوم التلقيح"},
       "category": "vaccination", "starts_on": "2026-11-20", "ends_on": "2026-11-20",
       "audience": {"roles": ["patient"], "sex": None, "min_age": None, "max_age": None}}


def test_list_needs_login(client):
    assert client.get("/health-events").status_code == 401


def test_list_window_and_flags(client):
    pat = login(client, "patient@medora.tn")
    r = client.get("/health-events?from=2026-10-01&to=2026-11-30", headers=pat)
    assert r.status_code == 200
    ids = [e["id"] for e in r.json()]
    assert ids[:2] == ["he-0001", "he-0002"] and "he-0007" not in ids
    rose = next(e for e in r.json() if e["id"] == "he-0001")
    movember = next(e for e in r.json() if e["id"] == "he-0004")
    assert rose["matches_me"] is True and rose["following"] is True and movember["matches_me"] is False


def test_prefs_get_put(client):
    pat = login(client, "patient@medora.tn")
    assert client.get("/me/health-prefs", headers=pat).json()["following"]["screening"] is True
    r = client.put("/me/health-prefs", headers=pat, json={"following": {"screening": False}})
    assert r.status_code == 200 and r.json()["following"]["screening"] is False
    ev = client.get("/health-events?from=2026-10-01&to=2026-10-31", headers=pat).json()
    assert next(e for e in ev if e["id"] == "he-0001")["following"] is False


def test_prefs_unknown_category_422(client):
    pat = login(client, "patient@medora.tn")
    r = client.put("/me/health-prefs", headers=pat, json={"following": {"vaccination": False, "astrology": False}})
    assert r.status_code == 422
    assert client.get("/me/health-prefs", headers=pat).json()["following"]["vaccination"] is True


def test_only_admin_writes(client):
    doc = login(client, "doctor@medora.tn")
    assert client.post("/health-events", headers=doc, json=NEW).status_code == 403
    assert client.delete("/health-events/he-0001", headers=doc).status_code == 403
    assert client.post("/health-events/he-0001/notify", headers=doc).status_code == 403


def test_admin_create_patch_delete(client, db):
    adm = login(client, "admin@medora.tn")
    r = client.post("/health-events", headers=adm, json=NEW)
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["id"].startswith("he-") and ev["description"] == {"en": "", "fr": "", "ar": ""}
    assert ev["notify_days_before"] == 3
    r = client.patch(f"/health-events/{ev['id']}", headers=adm, json={"organizer": "Medora"})
    assert r.status_code == 200 and r.json()["organizer"] == "Medora"
    assert client.delete(f"/health-events/{ev['id']}", headers=adm).status_code == 204
    assert client.patch(f"/health-events/{ev['id']}", headers=adm, json={"organizer": "x"}).status_code == 404


def test_bad_dates(client):
    adm = login(client, "admin@medora.tn")
    r = client.post("/health-events", headers=adm, json=dict(NEW, ends_on="2026-11-19"))
    assert r.status_code == 422 and r.json()["code"] == "bad_dates"
    r = client.patch("/health-events/he-0005", headers=adm, json={"ends_on": "2026-11-01"})  # starts 11-14
    assert r.status_code == 422 and r.json()["code"] == "bad_dates"


def test_bad_audience(client):
    adm = login(client, "admin@medora.tn")
    bad = dict(NEW, audience={"roles": [], "sex": None, "min_age": None, "max_age": None})
    assert client.post("/health-events", headers=adm, json=bad).status_code == 422
    bad = dict(NEW, audience={"roles": ["patient"], "sex": None, "min_age": 50, "max_age": 40})
    assert client.post("/health-events", headers=adm, json=bad).status_code == 422


def test_moving_start_clears_announced(client, db):
    from datetime import UTC, datetime
    db.get(HealthEvent, "he-0005").announced_at = datetime.now(UTC)
    db.flush()
    adm = login(client, "admin@medora.tn")
    r = client.patch("/health-events/he-0005", headers=adm, json={"starts_on": "2026-11-13"})
    assert r.status_code == 200 and r.json()["announced_at"] is None


def test_notify_now(client, db, emitted):
    adm = login(client, "admin@medora.tn")
    r = client.post("/health-events/he-0001/notify", headers=adm)
    assert r.status_code == 200
    (event, data), = [e for e in emitted if e[0] == "health_event.upcoming"]
    assert data["event_id"] == "he-0001" and r.json() == {"recipients": data["recipient_count"]}
    assert any(p["first_name"] == "Amira" for p in data["recipients"])
    assert db.get(HealthEvent, "he-0001").announced_at is not None
    assert db.query(AuditLog).filter_by(action="notify", resource="health_event", resource_id="he-0001").count() == 1
```

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_health_api.py -q` → FAIL (404s).

- [ ] **Step 3: Implement** `backend/app/routers/health_events.py`

```python
"""Health calendar (api.md 1.10): every active user reads events and sets category prefs; admins curate and can
push an event now. Rules live in app/services/health_calendar.py."""

from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
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
```

`from` is a Python keyword, hence the `Query(alias="from")`; a malformed date returns 422 automatically. `H._today()` is added in Task 6 — **add it now in this task** (Task 6 then only uses it):

```python
def _today() -> date:
    """Today in Africa/Tunis (UTC+1, no DST)."""
    return (datetime.now(UTC) + timedelta(hours=1)).date()
```

in `backend/app/services/health_calendar.py` (import `UTC, datetime` from `datetime`). Router imports: `from datetime import UTC, date, datetime, timedelta` and `from fastapi import APIRouter, Depends, Query, Request, Response`.

Register the router in `backend/app/main.py`: `from app.routers import ..., health_events, ...` and `app.include_router(health_events.router)` after `exams.router`.

- [ ] **Step 4: Run** `.venv/Scripts/python -m pytest tests/test_health_api.py -q` → PASS, then the whole suite `.venv/Scripts/python -m pytest -q` → all PASS (no regressions in `test_rbac.py` etc.).
- [ ] **Step 5: Commit** `git add backend/app/routers/health_events.py backend/app/main.py backend/tests/test_health_api.py && git commit -m "feat(backend): health-events API - list with my match, admin CRUD, notify now, category prefs"`

---

### Task 6: n8n callbacks — due and announced

**Files:**
- Modify: `backend/app/routers/integrations.py`
- Test: `backend/tests/test_health_integrations.py`

**Interfaces:**
- Consumes: `H.due`, `H.upcoming_payload` (Task 3), `require_n8n` router dependency (already on the router).
- Produces: `GET /integrations/n8n/health-events/due` → `list[payload]`; `POST /integrations/n8n/health-events/{id}/announced` → `{"status":"announced"}`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import UTC, date, datetime

from app.config import get_settings
from app.models import HealthEvent
from app.services import health_calendar as H


def _n8n() -> dict:
    return {"X-N8N-Secret": get_settings().n8n_callback_secret}


def test_due_needs_secret(client):
    assert client.get("/integrations/n8n/health-events/due").status_code == 401


def test_due_lists_payloads(client, monkeypatch):
    monkeypatch.setattr(H, "_today", lambda: date(2026, 10, 8))
    r = client.get("/integrations/n8n/health-events/due", headers=_n8n())
    assert r.status_code == 200
    ids = [p["event_id"] for p in r.json()]
    assert "he-0001" in ids and "he-0002" in ids and "he-0003" not in ids  # flu starts 10-15, notify 3 days
    assert all("recipients" in p and "web_url" in p for p in r.json())


def test_announced_is_idempotent(client, db):
    r = client.post("/integrations/n8n/health-events/he-0002/announced", headers=_n8n())
    assert r.status_code == 200 and r.json() == {"status": "announced"}
    first = db.get(HealthEvent, "he-0002").announced_at
    client.post("/integrations/n8n/health-events/he-0002/announced", headers=_n8n())
    assert db.get(HealthEvent, "he-0002").announced_at == first
    assert client.post("/integrations/n8n/health-events/he-9999/announced", headers=_n8n()).status_code == 404
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement.** `H._today()` already exists (Task 5); tests monkeypatch it. In `backend/app/routers/integrations.py` add imports `from app.models import HealthEvent` (extend the existing models import), `from app.services import health_calendar as H`, `from app.config import get_settings` and:

```python
@router.get("/health-events/due")
def health_events_due(db: Session = Depends(get_db)) -> list[dict]:
    web = get_settings().web_url
    return [H.upcoming_payload(db, e, web) for e in H.due(db, H._today())]


@router.post("/health-events/{event_id}/announced")
def health_event_announced(event_id: str, db: Session = Depends(get_db)) -> dict:
    ev = db.get(HealthEvent, event_id)
    if ev is None:
        raise not_found("health event")
    if ev.announced_at is None:
        ev.announced_at = datetime.now(UTC)
        db.commit()
    return {"status": "announced"}
```

Update the module docstring version mention to `n8n-webhooks.md v1.4`.

- [ ] **Step 4: Run** `.venv/Scripts/python -m pytest tests/test_health_integrations.py tests/test_integrations_api.py -q` → PASS.
- [ ] **Step 5: Commit** `git add backend/app/routers/integrations.py backend/app/services/health_calendar.py backend/tests/test_health_integrations.py && git commit -m "feat(backend): n8n callbacks for due health events and announced marker"`

---

### Task 7: n8n W9 workflow and router branch

**Files:**
- Create: `n8n/workflows/W9-health-calendar.json`
- Modify: `n8n/workflows/W0-router.json`, `n8n/README.md`

**Interfaces:**
- Consumes: event `health_event.upcoming` (payload from Task 3), callbacks from Task 6, env `WARD_API_URL`, `N8N_CALLBACK_SECRET`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WARD_WHATSAPP_STAFF`, `WARD_WHATSAPP_PATIENT`, `WARD_MAIL_FROM`, SMTP credential `ward-smtp`.

- [ ] **Step 1: Read** `n8n/workflows/W4-critical-alert.json` (WhatsApp + email node shapes, `executeWorkflowTrigger`, `onError`) and `W5-doctor-daily-digest.json` (cron + HTTP GET with `X-N8N-Secret`). Reuse their node types, typeVersions and parameter shapes exactly.
- [ ] **Step 2: Build W9** (`"id": "wardHealthCalW9x"`, name `W9 · Health calendar`):
  1. `Execute Workflow Trigger` ("From router") → Code node "Mark source" sets `json = {...$json.data, from_cron:false}`.
  2. `Schedule Trigger` ("Daily 08:00", cron `0 8 * * *`; the container TZ is Africa/Tunis) → HTTP Request GET `{{$env.WARD_API_URL}}/integrations/n8n/health-events/due` with header `X-N8N-Secret: {{$env.N8N_CALLBACK_SECRET}}` → Code node "Split" returning one item per payload with `from_cron:true`.
  3. Both → Code node "Compose": `text = "📅 " + title.fr + " · " + range + (organizer ? " · " + organizer : "") + "\n" + web_url`, where `range` = `starts_on` or `starts_on → ends_on`. Output 1 item with `text`, plus `recipients`.
  4. WhatsApp: same HTTP node shape as W4, one message per number in `WARD_WHATSAPP_PATIENT` + `WARD_WHATSAPP_STAFF` (split on commas, skip empties), `onError: continueRegularOutput`.
  5. Email: Code node "One per recipient" → Email node (`ward-smtp`, from `$env.WARD_MAIL_FROM`, to `email`, subject `Medora · {title.fr}`, body `Bonjour {first_name},\n\n{text}`), `onError: continueRegularOutput`.
  6. IF `from_cron` → HTTP POST `{{$env.WARD_API_URL}}/integrations/n8n/health-events/{{event_id}}/announced` with the secret header.
- [ ] **Step 3: W0 router**: in the Code node "Check secret + route" add `'health_event.upcoming': <next index>` to `ROUTES` (also make sure `exam.ordered`/`exam.results_ready` routes are untouched); add the matching Switch output rule and an `executeWorkflow` node "W9 health calendar" calling `wardHealthCalW9x` (same shape as the other executeWorkflow nodes), wired in `connections`.
- [ ] **Step 4: Validate JSON** `python -c "import json;[json.load(open(f'n8n/workflows/{f}.json',encoding='utf-8')) for f in ('W0-router','W9-health-calendar')];print('ok')"` → `ok`. If the local stack runs, import with the README commands (add `W9-health-calendar` before `W0-router` and `wardHealthCalW9x` before `wardRouterW00000` in both loops) and publish.
- [ ] **Step 5: README**: add W9 to the import loops and one line under the workflow list: "W9 health calendar: daily 08:00 push of due health events + admin Notify now".
- [ ] **Step 6: Commit** `git add n8n && git commit -m "feat(n8n): W9 health calendar push (daily due + notify now) and router branch"`

---

### Task 8: Web data layer — types, i18n, mocks, api, helpers

**Files:**
- Modify: `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/mocks/index.ts`, `web/src/i18n/messages/index.ts`
- Create: `web/src/mocks/healthEvents.ts`, `web/src/lib/healthCalendar.ts`, `web/src/i18n/messages/calendar.ts`

**Interfaces:**
- Consumes: backend `EVENTS` (Task 4) to generate the mock.
- Produces (exact):
  - types: `HealthCategory`, `HEALTH_CATEGORIES`, `HealthText`, `HealthAudience`, `HealthEvent`, `HealthEventInput`, `HealthPrefs`
  - api: `getHealthEvents(opts?: {from?: string; to?: string; role?: Role}): Promise<HealthEvent[]>`, `createHealthEvent(input: HealthEventInput): Promise<HealthEvent>`, `updateHealthEvent(id: string, patch: Partial<HealthEventInput>): Promise<HealthEvent>`, `deleteHealthEvent(id: string): Promise<void>`, `notifyHealthEvent(id: string): Promise<{recipients: number}>`, `getHealthPrefs(role?: Role): Promise<HealthPrefs>`, `setHealthPrefs(following: Partial<Record<HealthCategory, boolean>>, role?: Role): Promise<HealthPrefs>`
  - helpers (`lib/healthCalendar.ts`): `todayIso(): string`, `addDays(iso: string, n: number): string`, `monthGrid(year: number, month0: number): string[][]`, `eventsOn(events: HealthEvent[], iso: string): HealthEvent[]`, `upcoming(events: HealthEvent[], today: string, days: number): HealthEvent[]`, `forMe(events: HealthEvent[]): HealthEvent[]`, `badgeCount(events: HealthEvent[], today: string): number`, `fmtDay(iso: string, lang: Lang): string`, `fmtRange(ev: HealthEvent, lang: Lang): string`, `textOf(t: HealthText, lang: Lang): string`, `CATEGORY_TONE: Record<HealthCategory, {bg: string; fg: string}>`
  - i18n namespace `calendar` with the keys listed below.

- [ ] **Step 1: Types** — append to `web/src/lib/types.ts`:

```ts
// ── Health calendar (api.md 1.10) ──
export const HEALTH_CATEGORIES = ["screening", "vaccination", "chronic_disease", "infectious_disease", "lifestyle", "mental_health", "blood_donation"] as const;
export type HealthCategory = (typeof HEALTH_CATEGORIES)[number];
export interface HealthText { en: string; fr: string; ar: string; }
export interface HealthAudience { roles: Role[]; sex: "F" | "M" | null; min_age: number | null; max_age: number | null; }
export interface HealthEvent {
  id: string;
  title: HealthText;
  description: HealthText;
  category: HealthCategory;
  starts_on: string; // YYYY-MM-DD
  ends_on: string;
  audience: HealthAudience;
  notify_days_before: number;
  organizer: string | null;
  source_url: string | null;
  announced_at: string | null;
  matches_me: boolean;
  following: boolean;
}
export type HealthEventInput = Omit<HealthEvent, "id" | "announced_at" | "matches_me" | "following">;
export interface HealthPrefs { following: Record<HealthCategory, boolean>; }
```

- [ ] **Step 2: Generate the mock** from the backend seed (keeps both in sync). From the repo root:

```bash
cd backend && .venv/Scripts/python - <<'EOF'
import json
from app.health_seed import EVENTS
rows = [dict(e, starts_on=e["starts_on"].isoformat(), ends_on=e["ends_on"].isoformat(), notify_days_before=3, announced_at=None) for e in EVENTS]
body = json.dumps(rows, ensure_ascii=False, indent=2)
open("../web/src/mocks/healthEvents.ts", "w", encoding="utf-8").write(
  "// GENERATED from backend/app/health_seed.py (plan Task 8). Re-run the generator after editing the seed.\n"
  'import type { HealthEvent } from "@/lib/types";\n\n'
  "/** Seed events without the per-user flags (api.ts adds matches_me/following). */\n"
  f"export const HEALTH_EVENTS: Omit<HealthEvent, \"matches_me\" | \"following\">[] = {body};\n")
EOF
```

- [ ] **Step 3: Mock store** — in `web/src/mocks/index.ts`: `import { HEALTH_EVENTS } from "./healthEvents";`, extend `MockStore` with `healthEvents: Omit<HealthEvent, "matches_me" | "following">[]; healthPrefs: Record<string, Partial<Record<HealthCategory, boolean>>>;` (key = role), add `healthEvents: HEALTH_EVENTS, healthPrefs: {},` to `createStore()`, add `he: HEALTH_EVENTS.length` to `seq` (and to its type), and import `HealthEvent`, `HealthCategory` types.

- [ ] **Step 4: API functions** — in `web/src/lib/api.ts` add the types to the import list and a section:

```ts
// ── Health calendar (api.md 1.10) ──────────────────────────────────────────

/** The mock profile per role: Amira (F, 1972) is the patient; staff ignore sex/age limits. */
function mockMatches(s: MockStore, role: Role, ev: Omit<HealthEvent, "matches_me" | "following">): boolean {
  const a = ev.audience;
  if (!a.roles.includes(role)) return false;
  if (role !== "patient") return true; // staff ignore sex/age limits
  if (a.sex === null && a.min_age === null && a.max_age === null) return true;
  const p = s.patients.find((x) => x.id === USERS.patient.patient_id);
  if (!p) return false;
  if (a.sex !== null && p.sex !== a.sex) return false; // unknown sex never matches a sex-limited event
  return ageOk(p.date_of_birth ?? null, ev.starts_on, a);
}

function ageOk(dob: string | null, on: string, a: HealthAudience): boolean {
  if (a.min_age === null && a.max_age === null) return true;
  if (!dob) return false;
  const [y, m, d] = dob.split("-").map(Number);
  const [oy, om, od] = on.split("-").map(Number);
  const age = oy - y - (om < m || (om === m && od < d) ? 1 : 0);
  return (a.min_age === null || age >= a.min_age) && (a.max_age === null || age <= a.max_age);
}

function mockPrefs(s: MockStore, role: Role): HealthPrefs {
  const mine = s.healthPrefs[role] ?? {};
  return { following: Object.fromEntries(HEALTH_CATEGORIES.map((c) => [c, mine[c] ?? true])) as HealthPrefs["following"] };
}

function withFlags(s: MockStore, role: Role, ev: Omit<HealthEvent, "matches_me" | "following">): HealthEvent {
  return { ...ev, matches_me: mockMatches(s, role, ev), following: mockPrefs(s, role).following[ev.category] };
}

function mockEvent(s: MockStore, id: string) {
  return s.healthEvents.find((e) => e.id === id) ?? notFound(`Health event ${id}`);
}

function checkDates(starts: string, ends: string): void {
  if (ends < starts) throw new ApiError(422, "bad_dates", "ends_on is before starts_on");
}

/** GET /health-events?from&to — every role; `role` picks the mock user. */
export function getHealthEvents(opts: { from?: string; to?: string; role?: Role } = {}): Promise<HealthEvent[]> {
  if (USE_MOCKS)
    return mock((s) => {
      const from = opts.from ?? "0000-01-01";
      const to = opts.to ?? "9999-12-31";
      return s.healthEvents
        .filter((e) => e.starts_on <= to && e.ends_on >= from)
        .sort((a, b) => a.starts_on.localeCompare(b.starts_on) || a.id.localeCompare(b.id))
        .map((e) => withFlags(s, opts.role ?? "patient", e));
    });
  const q = new URLSearchParams();
  if (opts.from) q.set("from", opts.from);
  if (opts.to) q.set("to", opts.to);
  return http<HealthEvent[]>("GET", `/health-events${q.size ? `?${q}` : ""}`);
}

/** POST /health-events (admin). */
export function createHealthEvent(input: HealthEventInput): Promise<HealthEvent> {
  if (USE_MOCKS)
    return mock((s) => {
      checkDates(input.starts_on, input.ends_on);
      s.seq.he += 1;
      const ev = { ...input, id: `he-${String(s.seq.he).padStart(4, "0")}`, announced_at: null };
      s.healthEvents.push(ev);
      return withFlags(s, "admin", ev);
    });
  return http<HealthEvent>("POST", "/health-events", input);
}

/** PATCH /health-events/{id} (admin); a new start date clears announced_at. */
export function updateHealthEvent(id: string, patch: Partial<HealthEventInput>): Promise<HealthEvent> {
  if (USE_MOCKS)
    return mock((s) => {
      const ev = mockEvent(s, id);
      checkDates(patch.starts_on ?? ev.starts_on, patch.ends_on ?? ev.ends_on);
      if (patch.starts_on && patch.starts_on !== ev.starts_on) ev.announced_at = null;
      Object.assign(ev, patch);
      return withFlags(s, "admin", ev);
    });
  return http<HealthEvent>("PATCH", `/health-events/${enc(id)}`, patch);
}

/** DELETE /health-events/{id} (admin) → 204. */
export function deleteHealthEvent(id: string): Promise<void> {
  if (USE_MOCKS)
    return mock((s) => {
      mockEvent(s, id);
      s.healthEvents = s.healthEvents.filter((e) => e.id !== id);
    });
  return http<void>("DELETE", `/health-events/${enc(id)}`);
}

/** POST /health-events/{id}/notify (admin) → how many people the push targets. */
export function notifyHealthEvent(id: string): Promise<{ recipients: number }> {
  if (USE_MOCKS)
    return mock((s) => {
      const ev = mockEvent(s, id);
      ev.announced_at = now().toISOString().replace(/\.\d{3}Z$/, "Z");
      const roles: Role[] = ["patient", "nurse", "doctor", "admin"];
      const people = roles.filter((r) => mockMatches(s, r, ev) && mockPrefs(s, r).following[ev.category]);
      return { recipients: people.length };
    });
  return http<{ recipients: number }>("POST", `/health-events/${enc(id)}/notify`);
}

/** GET /me/health-prefs. */
export function getHealthPrefs(role: Role = "patient"): Promise<HealthPrefs> {
  if (USE_MOCKS) return mock((s) => mockPrefs(s, role));
  return http<HealthPrefs>("GET", "/me/health-prefs");
}

/** PUT /me/health-prefs (partial). */
export function setHealthPrefs(following: Partial<Record<HealthCategory, boolean>>, role: Role = "patient"): Promise<HealthPrefs> {
  if (USE_MOCKS)
    return mock((s) => {
      s.healthPrefs[role] = { ...(s.healthPrefs[role] ?? {}), ...following };
      return mockPrefs(s, role);
    });
  return http<HealthPrefs>("PUT", "/me/health-prefs", { following });
}
```

The behaviour must equal the backend `matches`. Check the mock `Patient` type's field names for sex and birth date (`mocks/people.ts` uses `sex` and `date_of_birth`). `enc` already exists in api.ts (used by other calls); `HEALTH_CATEGORIES` is imported from `./types` as a value.

- [ ] **Step 5: Helpers** `web/src/lib/healthCalendar.ts`

```ts
// Pure helpers for the health calendar: dates are plain "YYYY-MM-DD" strings in Africa/Tunis.
import type { Lang } from "@/i18n/config";
import { localeOf } from "@/i18n/config";
import type { HealthCategory, HealthEvent, HealthText } from "./types";
import { now } from "./time";

/** Today in Tunis (UTC+1, no DST). */
export function todayIso(): string {
  return new Date(now().getTime() + 3_600_000).toISOString().slice(0, 10);
}

export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Six Monday-first weeks covering the month (dates outside the month included). */
export function monthGrid(year: number, month0: number): string[][] {
  const first = new Date(Date.UTC(year, month0, 1));
  const back = (first.getUTCDay() + 6) % 7;
  const start = addDays(first.toISOString().slice(0, 10), -back);
  return Array.from({ length: 6 }, (_, w) => Array.from({ length: 7 }, (_, d) => addDays(start, w * 7 + d)));
}

export function eventsOn(events: HealthEvent[], iso: string): HealthEvent[] {
  return events.filter((e) => e.starts_on <= iso && e.ends_on >= iso);
}

/** Active today or starting within `days`, soonest first. */
export function upcoming(events: HealthEvent[], today: string, days: number): HealthEvent[] {
  const until = addDays(today, days);
  return events
    .filter((e) => e.ends_on >= today && e.starts_on <= until)
    .sort((a, b) => a.starts_on.localeCompare(b.starts_on) || a.id.localeCompare(b.id));
}

export function forMe(events: HealthEvent[]): HealthEvent[] {
  return events.filter((e) => e.matches_me && e.following);
}

/** Sidebar badge: events for me, active now or starting within 7 days. */
export function badgeCount(events: HealthEvent[], today: string): number {
  return forMe(upcoming(events, today, 7)).length;
}

export function textOf(t: HealthText, lang: Lang): string {
  return t[lang] || t.en;
}

export function fmtDay(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(localeOf(lang), { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));
}

export function fmtRange(ev: HealthEvent, lang: Lang): string {
  return ev.starts_on === ev.ends_on ? fmtDay(ev.starts_on, lang) : `${fmtDay(ev.starts_on, lang)} – ${fmtDay(ev.ends_on, lang)}`;
}

/** Category colours from the design tokens (globals.css). */
export const CATEGORY_TONE: Record<HealthCategory, { bg: string; fg: string }> = {
  screening: { bg: "var(--news-crit-bg)", fg: "var(--news-crit-fg)" },
  vaccination: { bg: "var(--teal-tint)", fg: "var(--teal-deep)" },
  chronic_disease: { bg: "var(--news-high-bg)", fg: "var(--news-high-fg)" },
  infectious_disease: { bg: "var(--news-low-bg)", fg: "var(--news-low-fg)" },
  lifestyle: { bg: "var(--news-normal-bg)", fg: "var(--news-normal-fg)" },
  mental_health: { bg: "var(--ai-bg)", fg: "var(--ai)" },
  blood_donation: { bg: "var(--danger-bg)", fg: "var(--danger-ink)" },
};
```

- [ ] **Step 6: i18n** `web/src/i18n/messages/calendar.ts` — `export const calendar = messages({ en: {...}, fr: {...}, ar: {...} })` with these keys and English values (write natural French and Arabic for each; every key in all three):

| key | en |
|---|---|
| nav | Health calendar |
| tab | Calendar |
| title | Health calendar |
| sub | Public-health days and campaigns in Tunisia |
| honesty | Dates as announced. Check with the Ministry of Health or ONFP. |
| today | Today |
| prev | Previous month |
| next | Next month |
| upcoming | Coming up |
| noUpcoming | Nothing in the coming weeks. |
| forYou | For you |
| following | Categories I follow |
| followHint | You get a message about these, and they show in your banner. |
| organizer | Organised by {org} |
| source | Official page |
| banner | {title} · {when} |
| bannerNow | until {date} |
| bannerSoon | starts {date} |
| bannerOpen | See the calendar |
| dismiss | Dismiss |
| openFull | Open the full calendar |
| back | Back |
| loadError | Couldn’t load the calendar. |
| more | +{n} more |
| catScreening | Screening |
| catVaccination | Vaccination |
| catChronic | Chronic disease |
| catInfectious | Infectious disease |
| catLifestyle | Healthy living |
| catMental | Mental health |
| catBlood | Blood donation |
| add | Add an event |
| edit | Edit |
| delete | Delete |
| confirmDelete | Delete this event? |
| save | Save |
| cancel | Cancel |
| notify | Notify now |
| notified | Sent to {n} people |
| announced | Announced {date} |
| fTitle | Title ({lang}) |
| fDesc | Description ({lang}) |
| fCategory | Category |
| fStarts | Starts |
| fEnds | Ends |
| fRoles | Who sees it in their banner and gets the message |
| fSex | Sex (patients) |
| sexAny | Anyone |
| sexF | Women |
| sexM | Men |
| fMinAge | Minimum age (patients) |
| fMaxAge | Maximum age (patients) |
| fNotifyDays | Message how many days before |
| fOrganizer | Organiser |
| fSource | Official link |
| badDates | The end date is before the start date. |
| saveError | Couldn’t save. Try again. |
| rolePatient | Patients |
| roleNurse | Nurses |
| roleDoctor | Doctors |
| roleAdmin | Admins |

Register it: in `web/src/i18n/messages/index.ts` import `calendar` and add it to `ALL`.

Also export from `lib/healthCalendar.ts`:
```ts
import type { Key } from "@/i18n/messages";
export const CATEGORY_LABEL: Record<HealthCategory, Key> = {
  screening: "calendar.catScreening", vaccination: "calendar.catVaccination", chronic_disease: "calendar.catChronic",
  infectious_disease: "calendar.catInfectious", lifestyle: "calendar.catLifestyle", mental_health: "calendar.catMental",
  blood_donation: "calendar.catBlood",
};
```

- [ ] **Step 7: Verify** `cd web && npm run typecheck` → no errors.
- [ ] **Step 8: Commit** `git add web/src/lib web/src/mocks web/src/i18n && git commit -m "feat(web): health calendar data layer - types, api (mock + real), helpers, en/fr/ar strings"`

---

### Task 9: Shared calendar UI + staff routes + sidebar badge + admin editing

**Files:**
- Create: `web/src/components/calendar/useHealthEvents.ts`, `HealthCalendar.tsx`, `HealthCalendar.module.css`, `EventForm.tsx`
- Create: `web/src/app/doctor/calendar/page.tsx`, `web/src/app/nurse/calendar/page.tsx`, `web/src/app/admin/calendar/page.tsx`
- Modify: `web/src/components/Sidebar.tsx`

**Interfaces:**
- Consumes: Task 8 api/helpers/i18n; `ErrorCard` (`@/components/shared/ErrorCard` — read its props first); `useT` (`{ t, lang }` — confirm the hook exposes `lang`; if not, read it from the provider the same way `LanguageSwitcher` does).
- Produces: `useHealthEvents(role: Role): { events: HealthEvent[] | null; failed: boolean; reload: () => void }`; `<HealthCalendar role={Role} editable?={boolean} compact?={boolean} />`; `<EventForm initial?={HealthEvent} onSaved={(ev) => void} onCancel={() => void} />`.

- [ ] **Step 1: Hook** `useHealthEvents.ts`: client hook; fetches `getHealthEvents({ role, from: addDays(todayIso(), -60), to: addDays(todayIso(), 400) })` on mount and on `reload()`; returns `{events, failed, reload}` with the `alive` guard pattern from `lib/useMe.ts`.

- [ ] **Step 2: `HealthCalendar.tsx`** ("use client"). Layout (non-compact): header (title `calendar.title`, sub `calendar.sub`, admin: `calendar.add` button) → two columns on ≥ 900 px (grid `minmax(0,1fr) 320px`, one column below):
  - **Left: month card.** Toolbar: prev / month name (`Intl.DateTimeFormat(localeOf(lang), {month:"long", year:"numeric", timeZone:"UTC"})`) / next / Today. Weekday header (Mon-first, `Intl` `weekday:"short"`). 6×7 grid from `monthGrid`; each cell shows the day number (muted when outside the month, ring when today) and up to 2 event chips (`textOf(title)` truncated, colours from `CATEGORY_TONE`, a dot when `matches_me && following`) plus `calendar.more` when more. Clicking a chip selects the event. Use buttons for chips (keyboard reachable).
  - **Right: side column.** (a) Selected event detail (or the first upcoming one): category chip (`CATEGORY_LABEL`), `forYou` chip when `matches_me`, title, `fmtRange`, description, `calendar.organizer`, `source` link (`target="_blank" rel="noreferrer"`), admin-only Edit / Delete (confirm with `window.confirm(t("calendar.confirmDelete"))`) / Notify now (shows `calendar.notified` toast text inline, and `calendar.announced` when `announced_at`). (b) `calendar.upcoming` list: `upcoming(events, todayIso(), 45)`, each row a button selecting the event. (c) `calendar.following` with one checkbox per `HEALTH_CATEGORIES` bound to `getHealthPrefs(role)` / `setHealthPrefs({[c]: checked}, role)`; after a change call `reload()` so flags refresh; `calendar.followHint` below.
  - Footer: `calendar.honesty` in small muted text.
  - **compact** (patient phone): no month grid toolbar columns; render a smaller month (same grid, chips replaced by coloured dots), then the upcoming list, the detail of the selected event, follow switches, honesty line. No admin controls.
  - Editing: when `editable` and add/edit is active, the side column shows `<EventForm>` instead of the detail.
  - Errors: `failed` → `ErrorCard` with `calendar.loadError` and a retry calling `reload`.
  - Month state starts at today's month; selecting an event in another month does not move the grid.

- [ ] **Step 3: `HealthCalendar.module.css`**: tokens only (no hex), logical properties for RTL, cards `background: var(--paper); border: 1px solid var(--line); border-radius: 14px`, grid cells `min-height: 92px` (compact: 36px), chip `font-size: 12px; border-radius: 6px; padding: 2px 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis`, page padding `32px 40px` (≤ 700 px: `16px`), focus-visible outlines `2px solid var(--teal)`.

- [ ] **Step 4: `EventForm.tsx`**: controlled form over `HealthEventInput`: three title inputs (`calendar.fTitle` with `{lang: "EN"|"FR"|"ع"}`), three description textareas (Arabic ones `dir="rtl"`), category select, two `type="date"` inputs, role checkboxes (`calendar.rolePatient`…), sex select (Any/F/M → null/"F"/"M"), min/max age number inputs (empty → null), notify days number (0–30, default 3), organiser, source URL. Client check: `ends_on < starts_on` → show `calendar.badDates`, don't submit. Submit → `createHealthEvent` or `updateHealthEvent(initial.id, input)`; `ApiError` with code `bad_dates` → `badDates`, other errors → `saveError`. Buttons Save / Cancel. Defaults for a new event: today for both dates, all four roles, category `screening`.

- [ ] **Step 5: Routes** — each file follows `app/admin/staff/page.tsx` (server component, `generateMetadata` with `t("calendar.title")`, `Suspense`):
  - `app/doctor/calendar/page.tsx` → `<HealthCalendar role="doctor" />`
  - `app/nurse/calendar/page.tsx` → `<HealthCalendar role="nurse" />`
  - `app/admin/calendar/page.tsx` → `<HealthCalendar role="admin" editable />`

- [ ] **Step 6: Sidebar** — in `NAV` add `{ key: "calendar", label: "calendar.nav", href: "/<role>/calendar" }` to doctor, nurse and admin, placed just before the `password` item. In `Sidebar`, compute the badge: `const [calCount, setCalCount] = useState<number | null>(null); useEffect(() => { let alive = true; getHealthEvents({ role, from: todayIso(), to: addDays(todayIso(), 7) }).then((ev) => alive && setCalCount(badgeCount(ev, todayIso())), () => undefined); return () => { alive = false; }; }, [role]);` and merge `calendar: calCount ?? ""` into the counts used for rendering (both mock and real mode — this is a real endpoint, unlike the other count pills). Mark it `hot: false`.

- [ ] **Step 7: Verify** `npm run typecheck` and `npm run build` → success. Start the dev server (`npm run dev` in `web/`, mock mode) and open `/doctor/calendar`, `/nurse/calendar`, `/admin/calendar`: October 2026 shows Octobre Rose, World Mental Health Day (10th) and the flu campaign from the 15th; the sidebar badge on doctor shows a count; admin can add an event (it appears in the grid), edit it, press Notify now (shows "Sent to N people"), delete it. Switch to العربية: layout mirrors, no overflow. Fix anything broken.
- [ ] **Step 8: Commit** `git add web/src && git commit -m "feat(web): health calendar page for doctor, nurse and admin, sidebar badge, admin event editor"`

---

### Task 10: Patient tab, full-width `/calendar` page, upcoming banner

**Files:**
- Create: `web/src/components/calendar/UpcomingBanner.tsx`, `UpcomingBanner.module.css`
- Create: `web/src/app/patient/calendar/page.tsx`, `web/src/components/patient/CalendarView.tsx`
- Create: `web/src/app/calendar/layout.tsx`, `web/src/app/calendar/page.tsx`, `web/src/components/calendar/FullCalendarPage.tsx`, `FullCalendarPage.module.css`
- Modify: `web/src/components/patient/PatientScreen.tsx`, `web/src/components/patient/Patient.module.css`, `web/src/components/patient/Home.tsx`, `web/src/components/RoleShell.tsx`

**Interfaces:**
- Consumes: `useHealthEvents`, `HealthCalendar` (Task 9), helpers (Task 8), `useMe` (`lib/useMe.ts`), `PatientScreen`.
- Produces: `<UpcomingBanner role={Role} href={string} />`.

- [ ] **Step 1: `UpcomingBanner`**: uses `useHealthEvents(role)`; picks `forMe(upcoming(events, todayIso(), 7))[0]`; renders nothing when none or when dismissed (`sessionStorage` key `ward_cal_dismissed_<id>`, wrapped in try/catch). Text: `t("calendar.banner", {title: textOf(ev.title, lang), when: ev.starts_on <= today ? t("calendar.bannerNow", {date: fmtDay(ev.ends_on, lang)}) : t("calendar.bannerSoon", {date: fmtDay(ev.starts_on, lang)})})`, a `Link` `calendar.bannerOpen` to `href`, and a dismiss button (`aria-label={t("calendar.dismiss")}`). Styling: `CATEGORY_TONE` background/foreground, 12px radius, 12px 16px padding, flex row, wraps on small widths.

- [ ] **Step 2: Patient tab** — in `PatientScreen.tsx`: `PatientTab` adds `"calendar"`; `TABS` adds `{ key: "calendar", label: "calendar.tab", shape: "tabCalendar" }` after `appts`; `hrefs` adds `calendar: "/patient/calendar"`. In `Patient.module.css`: `.tabBar` `grid-template-columns: repeat(5, 1fr)`; add `.tabCalendar { border-radius: 2px; border-top-width: 5px; }`. Check that 5 tabs still fit at 390 px (labels at 13px; if they wrap, set `.tab { font-size: 12px; }`).

- [ ] **Step 3: `CalendarView.tsx`** ("use client"): `<PatientScreen nav="calendar">` → a `styles.scroll` body with the title (`calendar.title`, class `styles.h1Small`), `<HealthCalendar role="patient" compact />`, and a `Link` to `/calendar` labelled `calendar.openFull`. `app/patient/calendar/page.tsx` follows `app/patient/vitals/page.tsx`.

- [ ] **Step 4: Full-width `/calendar`**: `app/calendar/layout.tsx` renders children on `var(--canvas)` full height. `FullCalendarPage.tsx` ("use client"): `const me = useMe();` (real mode: the signed-in role; mock mode: default to `"patient"`), header row with the Medora wordmark (reuse the brand markup/classes idea from `Sidebar`/`Brand` but in its own CSS module), `LanguageSwitcher`, and a back link (`calendar.back`) to `/patient`, `/doctor`, `/nurse` or `/admin` according to the role; then `<HealthCalendar role={role} editable={role === "admin"} />`. `app/calendar/page.tsx` is the server wrapper with metadata and `Suspense`. If the app has route protection (check how `/patient` pages redirect when signed out, e.g. a `401` handler in `api.ts`), rely on the same mechanism; do not add a new one.

- [ ] **Step 5: Banners** — patient `Home.tsx`: render `<UpcomingBanner role="patient" href="/patient/calendar" />` near the top of the home body (after the greeting block). `RoleShell.tsx`: when `pathname === "/" + role` (the role's home), render `<UpcomingBanner role={role} href={`/${role}/calendar`} />` at the top of `main` inside a wrapper with `padding: 16px 40px 0` (add a class to `RoleShell.module.css`). `RoleShell` already reads the pathname in `ShellSidebar`; read it with `usePathname()` in a small client child component so the layout stays a single client component.

- [ ] **Step 6: Verify** `npm run typecheck`, `npm run build`. Dev server, mock mode: `/patient` shows the Octobre Rose banner (mock clock 2026-10-05; Amira is F 54); the Calendar tab opens `/patient/calendar`; "Open the full calendar" opens `/calendar` full-width; unfollowing Screening on either page hides the banner after reload; doctor home `/doctor` shows a banner for the flu campaign or Mental Health Day; AR mirrors correctly; phone width (390 px) has no horizontal scroll.
- [ ] **Step 7: Commit** `git add web/src && git commit -m "feat(web): patient calendar tab, full-width /calendar page, upcoming-event banner on home screens"`

---

### Task 11: End-to-end verification and PR

**Files:** none new (fixes only if something fails).

- [ ] **Step 1: Backend suite** `cd backend && .venv/Scripts/python -m pytest -q` → all PASS.
- [ ] **Step 2: Migration on the real stack**: `docker compose -f infra/docker-compose.yml --env-file .env up -d --build api worker web` then `docker compose -f infra/docker-compose.yml exec api alembic upgrade head` (if the api container does not migrate on start) and `docker compose -f infra/docker-compose.yml exec api python -m app.seed`; `curl -s localhost:8001/health` → ok (the local API port is 8001 on this laptop).
- [ ] **Step 3: Real-mode check**: log in as `admin@medora.tn` (seed password from `.env` `SEED_PASSWORD`) at the web app, open `/admin/calendar`, press Notify now on Octobre Rose → a `health_event.upcoming` reaches n8n (check the n8n executions list; W9 present if imported). Log in as `patient@medora.tn` → banner + calendar tab.
- [ ] **Step 4: Push and PR** `git push -u origin wali/health-calendar`, then `gh pr create --title "feat: health calendar (Tunisian health events, targeted push)" --body …` with: summary, contract bumps (api 1.10, data-model 1.6, n8n 1.4), the lanes touched, **"@Faouzi-Blibech: this touches web/ and n8n/ (your lane) — please review those commits"**, and a test plan. No AI attribution in the body.
