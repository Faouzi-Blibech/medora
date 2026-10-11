# Accounts and access: Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Self sign-up, approval at three levels (company → hospital admin → doctor's team), enrollment and reset
codes, doctor-to-doctor sharing, and internet-grade login protection, in the FastAPI backend.

**Architecture:**
- Every request keeps the path token → `get_current_user` → `require_roles` → ownership check (`app/auth/deps.py`).
- This plan adds account status to that path, adds two access rules to `can_access` (team nurse, shared doctor),
  and adds new auth/admin routes on top.
- Business rules live in `app/services/accounts.py` and the small `app/auth/*` modules; routers only load rows,
  call them, audit and commit.

**Tech Stack:** FastAPI, SQLAlchemy 2 (`Mapped[...]`), Alembic, Pydantic v2, bcrypt, PyJWT, pytest (Postgres).

**Spec:** `docs/superpowers/specs/2026-10-10-accounts-and-access-design.md` (read it first; this plan argues from it).
Sibling plans: `2026-10-10-accounts-infra.md` (HTTPS proxy) and `2026-10-10-accounts-web.md` (screens).

## Global Constraints

- **Test command** (all tasks; Git Bash on Windows, Postgres from the running compose stack on network `ward_default`):
  `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none -e LAYA_ENABLED=false ward-test pytest -q -p no:cacheprovider <paths>`.
  On Linux/macOS, use `$(pwd)` instead of `$(pwd -W)`. Lint: the same command with `ruff check app tests`.
- **Baseline:** 354 passed, 2 skipped, 1 xfailed. Every task ends with the full suite green.
- **Errors** use `app/errors.py`: `ApiError(status, code, detail)`, `forbidden()`, `not_found()`. Envelope `{"detail","code"}`.
- **New error codes:** `weak_password` 422, `invalid_code` 400, `already_enrolled` 409, `rate_limited` 429,
  `account_pending` 403, `account_disabled` 403, `account_rejected` 403, `account_locked` 423, `bad_status` 409.
- **Account status** values: `pending | active | disabled | rejected`. Only `active` users pass `get_current_user`.
- **Codes:** 10 characters from `ABCDEFGHJKMNPQRSTUVWXYZ23456789` (31 symbols), shown as `XXXXX-XXXXX`, sha256 stored,
  48 h lifetime, single use. Issuing a new code revokes the previous unused one for the same target.
- **Limits:**
  - per-account lock after 5 failed logins, for 15 min;
  - 10 **failed** logins/min per IP. Successful logins don't count, because a whole hospital may share one public
    IP. The limit is checked before the password is verified.
  - `/auth/register` and `/auth/reset` 5/min and 30/day per IP;
  - `/doctors/directory` 30/min per IP.
- **Passwords:** at least 10 characters, at most 72 UTF-8 bytes (bcrypt limit), not in the common list, not equal to
  the email, its local part, or the name.
- **Sharing grants:** default 30 days, at most 365 days, expiry required.
- **JWT lifetime** default becomes 8 h.
- **Audit everything** (spec §7): register, register_duplicate, code_failed, code_used, login, login_failed, lockout,
  approve/reject/disable/enable (action `update`, resource `user`), code issue (action `create`, resource
  `access_code`), share/revoke (resource `patient_access`).
- **Repo rules:**
  - Only commit when the user has asked for commits.
  - Conventional Commits; no AI attribution lines.
  - Contracts change only with a version bump (Task 9).
  - The backend is Wali's lane: coordinate.

## Review Focus

1. **Email typed with capitals or spaces at sign-up, then lowercase at login** → it must log in. Pinned in Task 4
   (`test_email_is_normalised`).
2. **Code typed in lowercase, with spaces, or without the dash** → it must still be accepted. Pinned in Task 2
   (`test_code_normalisation`).
3. **Password longer than 72 bytes** (bcrypt) → it must be a clean 422 `weak_password`, never a 500. Pinned in Task 2
   and Task 4.
4. **A team nurse with no ward opens ward-based screens** (exam worklist, patient list with a `ward` filter) → empty
   lists, never a 500 and never other wards' data. Pinned in Task 7 (`test_team_nurse_ward_screens_are_empty_not_errors`).
5. **A locked-out user resets the password with a code** → the lock is cleared and they can log in at once. Pinned in
   Task 5 (`test_reset_code_clears_lock`).

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `backend/app/models/user.py` | modify | `User` status/lock/approval columns; `Staff.supervisor_id` |
| `backend/app/models/access.py` | create | `AccessCode`, `PatientAccess` tables |
| `backend/app/models/__init__.py` | modify | export the new models |
| `backend/alembic/versions/0004_accounts.py` | create | migration for all of the above |
| `backend/app/auth/ratelimit.py` | create | in-process sliding-window limiter + `enforce()` |
| `backend/app/auth/passwords.py` | create | password policy |
| `backend/app/auth/common_passwords.txt` | create | top-1000 common passwords (downloaded) |
| `backend/app/auth/codes.py` | create | issue / find / mark one-time codes |
| `backend/app/auth/deps.py` | modify | active-only users; team-nurse and shared-doctor rules; list filters |
| `backend/app/routers/auth.py` | modify | login hardening, register, reset, change-password, doctor directory |
| `backend/app/services/accounts.py` | create | approve / reject / disable / enable rules and output shapes |
| `backend/app/routers/users.py` | create | `/users*`, `/doctors/me/team` |
| `backend/app/routers/access.py` | create | `/patients/{id}/enrollment-code`, `/patients/{id}/access*` |
| `backend/app/routers/staff.py` | modify | `status` in `GET /staff` |
| `backend/app/routers/patients.py`, `routers/alerts.py`, `services/patients.py`, `ws/hub.py`, `ws/router.py` | modify | use the new nurse and doctor filters |
| `backend/app/bootstrap.py` | create | `python -m app.bootstrap` first admin |
| `backend/app/config.py`, `backend/app/main.py`, `.env.example` | modify | 8 h JWT, `WEB_ORIGIN` CORS, new routers |
| `docs/contracts/api.md`, `docs/contracts/data-model.md` | modify | 1.9 / 1.5 |
| `backend/tests/helpers.py`, `backend/tests/conftest.py` | modify | `make_user`, `make_patient`, limiter reset |
| `backend/tests/test_account_models.py`, `test_auth_primitives.py`, `test_login_hardening.py`, `test_register.py`, `test_user_admin.py`, `test_enrollment.py`, `test_team_and_sharing.py`, `test_bootstrap.py` | create | tests per task |

---

### Task 1: Data model and migration 0004

**Files:**
- Modify: `backend/app/models/user.py`, `backend/app/models/__init__.py`, `backend/tests/helpers.py`
- Create: `backend/app/models/access.py`, `backend/alembic/versions/0004_accounts.py`, `backend/tests/test_account_models.py`

**Interfaces:**
- Produces:
  - `User.status: str` (default `"active"`), `User.role: str | None`, `User.failed_logins: int`,
    `User.locked_until`, `User.approved_by`, `User.approved_at`, `User.requested_note`, `User.requested_doctor_id`;
  - `Staff.supervisor_id: str | None`;
  - `AccessCode(id, purpose, code_hash, patient_id, user_id, issued_by, created_at, expires_at, used_at, used_by)`;
  - `PatientAccess(id, patient_id, user_id, granted_by, created_at, expires_at, revoked_at)`;
  - test helpers `make_user(db, email, *, role="nurse", status="active", name="Test User", ward=None, supervisor_id=None, requested_doctor_id=None, password="ward1234") -> User`
    and `make_patient(db, *, attending=None, ward="Cardiology", first="Test", last="Patient") -> Patient`.

- [ ] **Step 1: Add test helpers** to `backend/tests/helpers.py` (append):

```python
def make_user(db, email: str, *, role: str | None = "nurse", status: str = "active", name: str = "Test User",
              ward: str | None = None, supervisor_id: str | None = None, requested_doctor_id: str | None = None,
              password: str = "ward1234"):
    from app.auth.security import hash_password
    from app.ids import new_id
    from app.models import Staff, User

    u = User(id=new_id(db, "u"), email=email, name=name, role=role, status=status,
             password_hash=hash_password(password), requested_doctor_id=requested_doctor_id)
    db.add(u)
    db.flush()
    if role in ("doctor", "nurse") or ward or supervisor_id:
        db.add(Staff(user_id=u.id, ward=ward, supervisor_id=supervisor_id))
        db.flush()
    return u


def make_patient(db, *, attending: str | None = None, ward: str = "Cardiology", first: str = "Test",
                 last: str = "Patient"):
    from app.ids import new_id
    from app.models import Patient

    p = Patient(id=new_id(db, "p"), first_name=first, last_name=last, ward=ward, attending_doctor_id=attending,
                allergies=[], history="")
    db.add(p)
    db.flush()
    return p
```

- [ ] **Step 2: Write the failing test** `backend/tests/test_account_models.py`:

```python
from datetime import UTC, datetime, timedelta

from app.models import AccessCode, PatientAccess, Staff, User
from tests.helpers import make_patient, make_user


def test_existing_style_user_defaults_to_active(seeded):
    u = seeded.get(User, "u-0001")
    assert u.status == "active" and u.failed_logins == 0 and u.locked_until is None


def test_pending_user_has_no_role_and_remembers_the_request(seeded):
    u = make_user(seeded, "new@medora.tn", role=None, status="pending", requested_doctor_id="u-0001")
    assert u.role is None and u.status == "pending" and u.requested_doctor_id == "u-0001"


def test_staff_supervisor(seeded):
    u = make_user(seeded, "team@medora.tn", role="nurse", supervisor_id="u-0001")
    assert seeded.get(Staff, u.id).supervisor_id == "u-0001"


def test_access_code_and_grant_rows(seeded):
    now = datetime.now(UTC)
    p = make_patient(seeded, attending="u-0001")
    seeded.add(AccessCode(id="ac-9001", purpose="enrollment", code_hash="x" * 64, patient_id=p.id,
                          issued_by="u-0004", expires_at=now + timedelta(hours=48)))
    seeded.add(PatientAccess(id="pa-9001", patient_id=p.id, user_id="u-0001", granted_by="u-0004",
                             expires_at=now + timedelta(days=30)))
    seeded.flush()
    assert seeded.get(AccessCode, "ac-9001").used_at is None
    assert seeded.get(PatientAccess, "pa-9001").revoked_at is None
```

- [ ] **Step 3: Run it to see it fail.** Run: test command with `tests/test_account_models.py`.
  Expected: `ImportError: cannot import name 'AccessCode'`.

- [ ] **Step 4: Implement the models.** In `backend/app/models/user.py`, add `Integer` to the sqlalchemy import, then
  replace the `role` line and add the new columns:

```python
    role: Mapped[str | None] = mapped_column(String)  # doctor | nurse | admin | patient; NULL while pending
    status: Mapped[str] = mapped_column(String, default="active", server_default="active")
    # status: pending | active | disabled | rejected (only active users pass get_current_user)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_note: Mapped[str | None] = mapped_column(String)
    requested_doctor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
```

In `Staff`, add:

```python
    supervisor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))  # the doctor whose team this nurse is in
```

Create `backend/app/models/access.py`:

```python
"""One-time codes and doctor-to-doctor patient sharing (data-model 1.5)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AccessCode(Base):
    """`enrollment` links a patient account to a record; `reset` sets a password. Only the sha256 is stored."""

    __tablename__ = "access_codes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    purpose: Mapped[str] = mapped_column(String)
    code_hash: Mapped[str] = mapped_column(String, index=True)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    issued_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class PatientAccess(Base):
    """The attending doctor (or an admin) shares a patient with another doctor until `expires_at`."""

    __tablename__ = "patient_access"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    granted_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

In `backend/app/models/__init__.py`, add `from app.models.access import AccessCode, PatientAccess`, and add both names
to `__all__`. Update the docstring to "(v1.5: accounts)".

- [ ] **Step 5: Write the migration** `backend/alembic/versions/0004_accounts.py`:

```python
"""accounts: user status/lockout/approval, staff supervisor, access_codes, patient_access (data-model 1.5)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('users', 'role', existing_type=sa.String(), nullable=True)
    op.add_column('users', sa.Column('status', sa.String(), server_default='active', nullable=False))
    op.add_column('users', sa.Column('failed_logins', sa.Integer(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('approved_by', sa.String(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column('users', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('requested_note', sa.String(), nullable=True))
    op.add_column('users', sa.Column('requested_doctor_id', sa.String(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column('staff', sa.Column('supervisor_id', sa.String(), sa.ForeignKey('users.id'), nullable=True))
    op.create_table('access_codes',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('purpose', sa.String(), nullable=False),
    sa.Column('code_hash', sa.String(), nullable=False),
    sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=True),
    sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True),
    sa.Column('issued_by', sa.String(), sa.ForeignKey('users.id'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('used_by', sa.String(), sa.ForeignKey('users.id'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_access_codes_code_hash', 'access_codes', ['code_hash'])
    op.create_table('patient_access',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
    sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
    sa.Column('granted_by', sa.String(), sa.ForeignKey('users.id'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_patient_access_patient_id', 'patient_access', ['patient_id'])
    op.create_index('ix_patient_access_user_id', 'patient_access', ['user_id'])


def downgrade() -> None:
    op.drop_table('patient_access')
    op.drop_table('access_codes')
    op.drop_column('staff', 'supervisor_id')
    for col in ('requested_doctor_id', 'requested_note', 'approved_at', 'approved_by', 'locked_until',
                'failed_logins', 'status'):
        op.drop_column('users', col)
    op.alter_column('users', 'role', existing_type=sa.String(), nullable=False)
```

- [ ] **Step 6: Run the tests.** Run: test command with `tests/test_account_models.py`, then the full suite.
  Expected: 4 passed; full suite green.

- [ ] **Step 7: Check the migration on the real database.** From the repo root:
  `docker compose -f infra/docker-compose.yml --env-file .env up -d --build api && docker exec ward-api-1 alembic current && docker exec ward-db-1 psql -U ward -d ward -c "\d users" | grep -E "status|supervisor|locked_until"`.
  Expected: `0004 (head)`; the `status` column shows `default 'active'`. Then run
  `docker exec ward-api-1 alembic downgrade 0003 && docker exec ward-api-1 alembic upgrade head`. Expected: both
  succeed with no error.

- [ ] **Step 8: Commit** (only if the user asked):
  `git add backend/app/models backend/alembic/versions/0004_accounts.py backend/tests/helpers.py backend/tests/test_account_models.py && git commit -m "feat(backend): account status, staff supervisor, access codes and patient sharing tables"`

---

### Task 2: Auth primitives: rate limiter, password policy, one-time codes

**Files:**
- Create: `backend/app/auth/ratelimit.py`, `backend/app/auth/passwords.py`, `backend/app/auth/common_passwords.txt`,
  `backend/app/auth/codes.py`, `backend/tests/test_auth_primitives.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: `AccessCode` (Task 1), `new_id`.
- Produces:
  - `ratelimit.limiter: SlidingWindow` with `.allow(key, limit, window_s, now=None) -> bool` and `.reset()`;
  - `ratelimit.client_ip(request) -> str`;
  - `ratelimit.enforce(request, route: str, limits: tuple[tuple[int, float], ...]) -> None`, which counts this hit
    and raises 429;
  - `ratelimit.check(request, route, limits) -> None`, which raises 429 if any window is full without counting;
  - `ratelimit.record(request, route, limits) -> None`, which counts a hit without raising (login failures);
  - `SlidingWindow.full(key, limit, window_s, now=None) -> bool`;
  - the constants `LOGIN_LIMITS`, `CODE_LIMITS`, `DIRECTORY_LIMITS`;
  - `passwords.password_problem(pw, *, email="", name="") -> str | None` and `passwords.check_password(...)`, which
    raises 422 `weak_password`;
  - `codes.new_code() -> str`, `codes.normalize(code) -> str`, `codes.code_hash(code) -> str`;
  - `codes.issue(db, purpose, *, issued_by, patient_id=None, user_id=None, now=None) -> tuple[str, AccessCode]`;
  - `codes.find_valid(db, purpose, code, *, user_id=None, now=None) -> AccessCode | None`;
  - `codes.mark_used(row, *, used_by, now=None) -> None`.

- [ ] **Step 1: Download the common-password list.** From the repo root:
  `curl -fsSL https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Common-Credentials/10-million-password-list-top-1000.txt -o backend/app/auth/common_passwords.txt && wc -l backend/app/auth/common_passwords.txt`.
  Expected: about 1000 lines. Add a first line `# SecLists 10-million-password-list-top-1000 (MIT); one password per line`.
  The loader skips `#` lines.

- [ ] **Step 2: Reset the limiter between tests.** Append to `backend/tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Rate-limit counters are process-wide; every test starts from zero."""
    from app.auth.ratelimit import limiter

    limiter.reset()
    yield
    limiter.reset()
```

- [ ] **Step 3: Write the failing tests** `backend/tests/test_auth_primitives.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from app.auth import codes, passwords
from app.auth.ratelimit import SlidingWindow
from app.errors import ApiError
from tests.helpers import make_patient


def test_sliding_window_allows_up_to_limit_then_blocks_then_recovers():
    w = SlidingWindow()
    assert all(w.allow("k", 3, 60, now=t) for t in (0, 1, 2))
    assert not w.allow("k", 3, 60, now=3)
    assert w.allow("k", 3, 60, now=61)  # the first hit left the window


def test_keys_are_independent():
    w = SlidingWindow()
    assert w.allow("a", 1, 60, now=0) and w.allow("b", 1, 60, now=0)
    assert not w.allow("a", 1, 60, now=1)


def test_full_peeks_without_counting():
    w = SlidingWindow()
    assert not w.full("k", 2, 60, now=0)
    w.allow("k", 2, 60, now=0)
    assert not w.full("k", 2, 60, now=1)  # peeking did not add a hit
    w.allow("k", 2, 60, now=1)
    assert w.full("k", 2, 60, now=2) and not w.full("k", 2, 60, now=61)


@pytest.mark.parametrize("pw", ["short", "x" * 9])
def test_too_short(pw):
    assert "at least 10" in passwords.password_problem(pw)


def test_over_72_bytes_is_rejected_not_a_crash():
    assert "72" in passwords.password_problem("é" * 40)  # 80 bytes in UTF-8
    with pytest.raises(ApiError) as e:
        passwords.check_password("é" * 40)
    assert e.value.status_code == 422 and e.value.code == "weak_password"


def test_common_password(monkeypatch):
    monkeypatch.setattr(passwords, "_common", lambda: frozenset({"letmein12345"}))
    assert "common" in passwords.password_problem("LetMeIn12345")


def test_email_and_name_are_not_passwords():
    assert passwords.password_problem("amira.bensalah", email="amira.bensalah@medora.tn")
    assert passwords.password_problem("amira.bensalah@medora.tn", email="amira.bensalah@medora.tn")
    assert passwords.password_problem("Amira Ben Salah", name="Amira Ben Salah")
    assert passwords.password_problem("correct-horse-battery", email="a@b.tn", name="A") is None


def test_shipped_list_is_loaded():
    assert len(passwords._common()) >= 900 and "123456" in passwords._common()


def test_code_shape():
    c = codes.new_code()
    assert len(c) == 11 and c[5] == "-" and all(ch in codes.ALPHABET for ch in c.replace("-", ""))


def test_code_normalisation():
    assert codes.code_hash("abcde-fghjk") == codes.code_hash(" ABCDE FGHJK ") == codes.code_hash("ABCDEFGHJK")


def test_issue_find_and_use_once(seeded):
    p = make_patient(seeded, attending="u-0001")
    code, row = codes.issue(seeded, "enrollment", issued_by="u-0004", patient_id=p.id)
    assert row.code_hash != code and row.expires_at > datetime.now(UTC)
    found = codes.find_valid(seeded, "enrollment", code.lower())
    assert found.id == row.id
    codes.mark_used(found, used_by="u-0004")
    seeded.flush()
    assert codes.find_valid(seeded, "enrollment", code) is None


def test_new_code_revokes_previous(seeded):
    p = make_patient(seeded, attending="u-0001")
    first, _ = codes.issue(seeded, "enrollment", issued_by="u-0004", patient_id=p.id)
    second, _ = codes.issue(seeded, "enrollment", issued_by="u-0004", patient_id=p.id)
    assert codes.find_valid(seeded, "enrollment", first) is None
    assert codes.find_valid(seeded, "enrollment", second) is not None


def test_expired_and_wrong_purpose(seeded):
    p = make_patient(seeded, attending="u-0001")
    old, _ = codes.issue(seeded, "enrollment", issued_by="u-0004", patient_id=p.id,
                         now=datetime.now(UTC) - timedelta(hours=49))
    assert codes.find_valid(seeded, "enrollment", old) is None
    fresh, _ = codes.issue(seeded, "enrollment", issued_by="u-0004", patient_id=p.id)
    assert codes.find_valid(seeded, "reset", fresh) is None


def test_reset_code_is_bound_to_its_user(seeded):
    code, _ = codes.issue(seeded, "reset", issued_by="u-0004", user_id="u-0002")
    assert codes.find_valid(seeded, "reset", code, user_id="u-0003") is None
    assert codes.find_valid(seeded, "reset", code, user_id="u-0002") is not None
```

- [ ] **Step 4: Run it to see it fail.** Expected: `ModuleNotFoundError: No module named 'app.auth.codes'` (or ratelimit).

- [ ] **Step 5: Implement** `backend/app/auth/ratelimit.py`:

```python
"""In-process sliding-window rate limits for the public auth routes (spec §7).

Correct because the API runs as ONE uvicorn process. If it is ever scaled out, move these limits to the proxy or
Redis. Behind the proxy, uvicorn's --proxy-headers makes request.client the real client IP.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.errors import ApiError

LOGIN_LIMITS = ((10, 60.0),)
CODE_LIMITS = ((5, 60.0), (30, 86400.0))  # /auth/register and /auth/reset
DIRECTORY_LIMITS = ((30, 60.0),)


class SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: float, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def full(self, key: str, limit: int, window_s: float, now: float | None = None) -> bool:
        """True if `key` already has `limit` hits in the window; does not add a hit."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return False
            while q and q[0] <= now - window_s:
                q.popleft()
            return len(q) >= limit

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindow()
_TOO_MANY = ("rate_limited", "too many attempts, try again later")


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _keys(request: Request, route: str, limits: tuple[tuple[int, float], ...]):
    ip = client_ip(request)
    return [(f"{route}:{ip}:{window}", limit, window) for limit, window in limits]


def enforce(request: Request, route: str, limits: tuple[tuple[int, float], ...]) -> None:
    """Count this request; 429 once a window is full (register, reset, directory)."""
    for key, limit, window in _keys(request, route, limits):
        if not limiter.allow(key, limit, window):
            raise ApiError(429, *_TOO_MANY)


def check(request: Request, route: str, limits: tuple[tuple[int, float], ...]) -> None:
    """429 if a window is already full, without counting (login checks this BEFORE verifying the password)."""
    for key, limit, window in _keys(request, route, limits):
        if limiter.full(key, limit, window):
            raise ApiError(429, *_TOO_MANY)


def record(request: Request, route: str, limits: tuple[tuple[int, float], ...]) -> None:
    """Count a hit without raising (a failed login)."""
    for key, limit, window in _keys(request, route, limits):
        limiter.allow(key, limit, window)
```

`backend/app/auth/passwords.py`:

```python
"""Password policy for sign-up, reset and change (spec §7)."""

from functools import lru_cache
from pathlib import Path

from app.errors import ApiError

MIN_LENGTH = 10
MAX_BYTES = 72  # bcrypt ignores or rejects anything longer
COMMON = Path(__file__).parent / "common_passwords.txt"


@lru_cache
def _common() -> frozenset[str]:
    lines = COMMON.read_text(encoding="utf-8").splitlines()
    return frozenset(s.strip().lower() for s in lines if s.strip() and not s.startswith("#"))


def password_problem(password: str, *, email: str = "", name: str = "") -> str | None:
    if len(password) < MIN_LENGTH:
        return f"use at least {MIN_LENGTH} characters"
    if len(password.encode("utf-8")) > MAX_BYTES:
        return f"use at most {MAX_BYTES} bytes (about {MAX_BYTES} letters without accents)"
    low = password.lower()
    if low in _common():
        return "this password is too common"
    email = email.strip().lower()
    if email and low in (email, email.split("@")[0]):
        return "do not use your email as a password"
    if name and low.replace(" ", "") == name.lower().replace(" ", ""):
        return "do not use your name as a password"
    return None


def check_password(password: str, *, email: str = "", name: str = "") -> None:
    problem = password_problem(password, email=email, name=name)
    if problem:
        raise ApiError(422, "weak_password", problem)
```

`backend/app/auth/codes.py`:

```python
"""One-time codes (spec §5 access_codes). `enrollment` links a patient account to a record; `reset` sets a password.
Only the sha256 is stored; the plain code is returned once to the issuer."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ids import new_id
from app.models import AccessCode

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 31 symbols: no 0/O/1/I/L
LENGTH = 10
LIFETIME = timedelta(hours=48)


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    return f"{raw[:5]}-{raw[5:]}"


def normalize(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def code_hash(code: str) -> str:
    return hashlib.sha256(normalize(code).encode()).hexdigest()


def _target(purpose: str, patient_id: str | None, user_id: str | None):
    return AccessCode.patient_id == patient_id if purpose == "enrollment" else AccessCode.user_id == user_id


def issue(db: Session, purpose: str, *, issued_by: str, patient_id: str | None = None, user_id: str | None = None,
          now: datetime | None = None) -> tuple[str, AccessCode]:
    """New code for one patient (enrollment) or one user (reset); the previous unused one stops working."""
    now = now or datetime.now(UTC)
    db.execute(update(AccessCode).where(AccessCode.purpose == purpose, _target(purpose, patient_id, user_id),
                                        AccessCode.used_at.is_(None), AccessCode.expires_at > now)
               .values(expires_at=now))
    code = new_code()
    row = AccessCode(id=new_id(db, "ac"), purpose=purpose, code_hash=code_hash(code), patient_id=patient_id,
                     user_id=user_id, issued_by=issued_by, expires_at=now + LIFETIME)
    db.add(row)
    db.flush()
    return code, row


def find_valid(db: Session, purpose: str, code: str, *, user_id: str | None = None,
               now: datetime | None = None) -> AccessCode | None:
    """The unused, unexpired code row (locked until commit), or None. A reset code must belong to `user_id`."""
    now = now or datetime.now(UTC)
    stmt = select(AccessCode).where(AccessCode.purpose == purpose, AccessCode.code_hash == code_hash(code),
                                    AccessCode.used_at.is_(None), AccessCode.expires_at > now)
    if purpose == "reset":
        stmt = stmt.where(AccessCode.user_id == user_id)
    return db.scalar(stmt.with_for_update())


def mark_used(row: AccessCode, *, used_by: str, now: datetime | None = None) -> None:
    row.used_at, row.used_by = now or datetime.now(UTC), used_by
```

- [ ] **Step 6: Run the tests.** Run: test command with `tests/test_auth_primitives.py`, then the full suite.
  Expected: all pass. Lint is clean.

- [ ] **Step 7: Commit** (only if asked):
  `git add backend/app/auth backend/tests/conftest.py backend/tests/test_auth_primitives.py && git commit -m "feat(backend): rate limiter, password policy and one-time codes"`

---

### Task 3: Login hardening and active-only sessions

**Files:**
- Modify: `backend/app/routers/auth.py` (`login`), `backend/app/auth/deps.py` (`user_from_token`)
- Create: `backend/tests/test_login_hardening.py`

**Interfaces:**
- Consumes: `enforce`, `client_ip`, `LOGIN_LIMITS` (Task 2); `User.status`, `failed_logins`, `locked_until` (Task 1).
- Produces:
  - `user_from_token` returns `None` for any user whose status is not `active`, so REST and WebSocket both reject it;
  - login error codes as in Global Constraints.

- [ ] **Step 1: Write the failing tests** `backend/tests/test_login_hardening.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, User
from tests.helpers import login, make_user

WRONG = "wrong-password-123"


def _post(client, email, pw):
    return client.post("/auth/login", json={"email": email, "password": pw})


def test_unknown_email_and_wrong_password_look_the_same(client):
    a, b = _post(client, "nobody@medora.tn", WRONG), _post(client, "doctor@medora.tn", WRONG)
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_pending_message_only_with_the_right_password(client, db):
    make_user(db, "pending@medora.tn", role=None, status="pending")
    assert _post(client, "pending@medora.tn", WRONG).status_code == 401
    r = _post(client, "pending@medora.tn", "ward1234")
    assert r.status_code == 403 and r.json()["code"] == "account_pending"


@pytest.mark.parametrize("status,code", [("disabled", "account_disabled"), ("rejected", "account_rejected")])
def test_inactive_accounts(client, db, status, code):
    make_user(db, f"{status}@medora.tn", status=status)
    r = _post(client, f"{status}@medora.tn", "ward1234")
    assert r.status_code == 403 and r.json()["code"] == code


def test_five_failures_lock_then_unlock(client, db):
    for _ in range(5):
        assert _post(client, "nurse@medora.tn", WRONG).status_code == 401
    r = _post(client, "nurse@medora.tn", "ward1234")
    assert r.status_code == 423 and r.json()["code"] == "account_locked"
    db.get(User, "u-0002").locked_until = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert _post(client, "nurse@medora.tn", "ward1234").status_code == 200
    assert db.get(User, "u-0002").failed_logins == 0


def test_failures_and_lockout_are_audited(client, db):
    for _ in range(5):
        _post(client, "nurse@medora.tn", WRONG)
    actions = db.scalars(select(AuditLog.action).where(AuditLog.resource_id == "u-0002")).all()
    assert actions.count("login_failed") == 5 and "lockout" in actions


def test_disabled_user_token_dies_on_next_request(client, db):
    h = login(client, "nurse@medora.tn")
    assert client.get("/me", headers=h).status_code == 200
    db.get(User, "u-0002").status = "disabled"
    db.flush()
    assert client.get("/me", headers=h).status_code == 401


def test_failed_login_rate_limit_per_ip(client):
    codes = [_post(client, f"ghost{i}@medora.tn", WRONG).status_code for i in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    # once blocked, even the right password is not checked (no oracle for a guesser)
    assert _post(client, "doctor@medora.tn", "ward1234").status_code == 429


def test_successful_logins_do_not_count(client):
    for _ in range(15):  # a hospital behind one public IP
        assert _post(client, "doctor@medora.tn", "ward1234").status_code == 200
```

- [ ] **Step 2: Run it to see it fail.** Expected: several failures (no 403/423/429; the disabled token still works).

- [ ] **Step 3: Implement.** In `backend/app/auth/deps.py`, change `user_from_token`:

```python
def user_from_token(db: Session, token: str | None) -> User | None:
    """The token's user, or None if the token is bad or the account is not active (disable works immediately)."""
    claims = decode_token(token) if token else None
    user = db.get(User, claims["sub"]) if claims and claims.get("sub") else None
    return user if user is not None and user.status == "active" else None
```

Replace `login` in `backend/app/routers/auth.py`, adding the imports
`from datetime import UTC, datetime, timedelta`, `from functools import lru_cache`,
`from app.auth.ratelimit import LOGIN_LIMITS, check, client_ip, record` and `from app.auth.security import hash_password`:

```python
MAX_FAILED = 5
LOCK_FOR = timedelta(minutes=15)
_INACTIVE = {"pending": ("account_pending", "your account is waiting for approval"),
             "disabled": ("account_disabled", "this account is disabled; contact the hospital"),
             "rejected": ("account_rejected", "this sign-up request was not approved; contact the hospital")}


@lru_cache
def _dummy_hash() -> str:
    """Checked against when the email is unknown, so both paths take the same time."""
    return hash_password("not-a-real-password")


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> LoginOut:
    check(request, "login_failed", LOGIN_LIMITS)  # only failures count; checked before the password
    ip, now = client_ip(request), datetime.now(UTC)
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    ok = verify_password(body.password, user.password_hash if user else _dummy_hash())
    if user is None or not ok:
        record(request, "login_failed", LOGIN_LIMITS)
        if user is not None:
            user.failed_logins = (user.failed_logins or 0) + 1
            if user.failed_logins >= MAX_FAILED:
                user.locked_until, user.failed_logins = now + LOCK_FOR, 0
                audit(db, user, "lockout", "user", user.id, ip=ip)
        audit(db, user, "login_failed", "user", user.id if user else "", ip=ip)
        db.commit()
        raise ApiError(401, "bad_credentials", "wrong email or password")
    # the specific reasons below are only revealed to someone who knows the password
    if user.locked_until and user.locked_until > now:
        raise ApiError(423, "account_locked", "too many failed attempts; try again in 15 minutes")
    if user.status != "active":
        code, detail = _INACTIVE.get(user.status, ("account_disabled", "this account is not active"))
        raise ApiError(403, code, detail)
    user.failed_logins, user.locked_until = 0, None
    audit(db, user, "login", "user", user.id, ip=ip)
    db.commit()
    return LoginOut(access_token=create_token(user),
                    user=LoginUser(id=user.id, name=user.name, role=user.role, patient_id=user.patient_id))
```

- [ ] **Step 4: Run the tests.** Run: test command with `tests/test_login_hardening.py tests/test_auth.py tests/test_ws.py`,
  then the full suite. Expected: all pass.

- [ ] **Step 5: Commit** (only if asked):
  `git add backend/app/routers/auth.py backend/app/auth/deps.py backend/tests/test_login_hardening.py && git commit -m "feat(backend): login lockout, rate limit, status-aware sessions"`

---

### Task 4: Sign-up, password reset, password change, doctor directory

**Files:**
- Modify: `backend/app/routers/auth.py`
- Create: `backend/tests/test_register.py`

**Interfaces:**
- Consumes: `check_password`, `codes.find_valid` / `mark_used` / `issue`, `enforce`, `CODE_LIMITS`, `DIRECTORY_LIMITS`.
- Produces:
  - `POST /auth/register` → 202 `RECEIVED`;
  - `POST /auth/reset` → 204;
  - `POST /auth/change-password` → 204;
  - `GET /doctors/directory` → `[{id, name}]`;
  - module constant `RECEIVED` (dict) in `app/routers/auth.py`.

- [ ] **Step 1: Write the failing tests** `backend/tests/test_register.py`:

```python
from sqlalchemy import func, select

from app.auth import codes
from app.models import AccessCode, User
from tests.helpers import login, make_patient

GOOD = "correct-horse-battery"


def _reg(client, **body):
    base = {"name": "Amira Test", "email": "amira.t@medora.tn", "password": GOOD}
    return client.post("/auth/register", json={**base, **body})


def _user(db, email):
    return db.scalar(select(User).where(User.email == email))


def test_register_creates_pending_account_without_role(client, db):
    r = _reg(client, note="nurse, Cardiology")
    assert r.status_code == 202 and r.json()["status"] == "received"
    u = _user(db, "amira.t@medora.tn")
    assert u.status == "pending" and u.role is None and u.requested_note == "nurse, Cardiology"
    assert client.post("/auth/login", json={"email": "amira.t@medora.tn", "password": GOOD}).json()["code"] == \
        "account_pending"


def test_email_is_normalised(client, db):
    assert _reg(client, email="  Amira.T@Medora.TN ").status_code == 202
    assert _user(db, "amira.t@medora.tn") is not None


def test_role_or_ward_in_body_is_refused(client):
    assert _reg(client, role="admin").status_code == 422
    assert _reg(client, ward="Cardiology").status_code == 422


def test_existing_email_same_answer_no_duplicate(client, db):
    r = _reg(client, email="doctor@medora.tn")
    assert r.status_code == 202 and r.json() == _reg(client, email="other.t@medora.tn").json()
    assert db.scalar(select(func.count()).select_from(User).where(User.email == "doctor@medora.tn")) == 1


def test_weak_and_too_long_passwords(client):
    for pw in ("short", "é" * 40):
        r = _reg(client, password=pw)
        assert r.status_code == 422 and r.json()["code"] == "weak_password"


def test_requested_doctor_recorded_only_if_active_doctor(client, db):
    _reg(client, email="a1@medora.tn", requested_doctor_id="u-0001")
    _reg(client, email="a2@medora.tn", requested_doctor_id="u-0002")  # a nurse, ignored
    assert _user(db, "a1@medora.tn").requested_doctor_id == "u-0001"
    assert _user(db, "a2@medora.tn").requested_doctor_id is None


def test_enrollment_code_creates_active_linked_patient(client, db):
    p, other = make_patient(db, attending="u-0001"), make_patient(db, attending="u-0001")
    code, row = codes.issue(db, "enrollment", issued_by="u-0004", patient_id=p.id)
    assert _reg(client, email="pat.t@medora.tn", enrollment_code=code.lower()).status_code == 202
    u = _user(db, "pat.t@medora.tn")
    assert (u.status, u.role, u.patient_id) == ("active", "patient", p.id)
    assert db.get(AccessCode, row.id).used_by == u.id
    h = {"Authorization": f"Bearer {client.post('/auth/login', json={'email': 'pat.t@medora.tn', 'password': GOOD}).json()['access_token']}"}
    assert client.get(f"/patients/{p.id}", headers=h).status_code == 200
    assert client.get(f"/patients/{other.id}", headers=h).status_code == 403


def test_code_single_use_wrong_and_expired(client, db):
    p = make_patient(db, attending="u-0001")
    code, _ = codes.issue(db, "enrollment", issued_by="u-0004", patient_id=p.id)
    assert _reg(client, email="first.t@medora.tn", enrollment_code=code).status_code == 202
    r = _reg(client, email="second.t@medora.tn", enrollment_code=code)
    assert r.status_code == 400 and r.json()["code"] == "invalid_code"
    assert _reg(client, email="third.t@medora.tn", enrollment_code="AAAAA-BBBBB").json()["code"] == "invalid_code"
    assert _user(db, "second.t@medora.tn") is None and _user(db, "third.t@medora.tn") is None


def test_already_enrolled_keeps_the_code_unused(client, db):
    code, row = codes.issue(db, "enrollment", issued_by="u-0004", patient_id="p-0001")  # patient@medora.tn owns p-0001
    r = _reg(client, email="dup.t@medora.tn", enrollment_code=code)
    assert r.status_code == 409 and r.json()["code"] == "already_enrolled"
    assert db.get(AccessCode, row.id).used_at is None


def test_register_rate_limit(client):
    statuses = [_reg(client, email=f"rl{i}@medora.tn", password="short").status_code for i in range(6)]
    assert statuses[:5] == [422] * 5 and statuses[5] == 429


def test_reset_with_code(client, db):
    code, _ = codes.issue(db, "reset", issued_by="u-0004", user_id="u-0002")
    r = client.post("/auth/reset", json={"email": "nurse@medora.tn", "code": code, "new_password": GOOD})
    assert r.status_code == 204
    assert client.post("/auth/login", json={"email": "nurse@medora.tn", "password": GOOD}).status_code == 200
    again = client.post("/auth/reset", json={"email": "nurse@medora.tn", "code": code, "new_password": GOOD + "x"})
    assert again.status_code == 400 and again.json()["code"] == "invalid_code"


def test_reset_weak_password_does_not_burn_the_code(client, db):
    code, row = codes.issue(db, "reset", issued_by="u-0004", user_id="u-0002")
    r = client.post("/auth/reset", json={"email": "nurse@medora.tn", "code": code, "new_password": "short"})
    assert r.status_code == 422 and db.get(AccessCode, row.id).used_at is None


def test_change_password(client):
    h = login(client, "nurse@medora.tn")
    bad = client.post("/auth/change-password", headers=h, json={"current_password": "nope-nope-1", "new_password": GOOD})
    assert bad.status_code == 401
    ok = client.post("/auth/change-password", headers=h, json={"current_password": "ward1234", "new_password": GOOD})
    assert ok.status_code == 204
    assert client.post("/auth/login", json={"email": "nurse@medora.tn", "password": GOOD}).status_code == 200


def test_doctor_directory_lists_active_doctors_names_only(client):
    rows = client.get("/doctors/directory").json()
    assert {"id": "u-0001", "name": "Dr Trabelsi"} in rows
    assert all(set(r) == {"id", "name"} for r in rows)
```

- [ ] **Step 2: Run it to see it fail.** Expected: 404s for the new routes.

- [ ] **Step 3: Implement** (append to `backend/app/routers/auth.py`, merging imports:
  `from fastapi import Response`, `from pydantic import BaseModel, ConfigDict, Field`, `from app.auth import codes`,
  `from app.auth.passwords import check_password`, `from app.auth.ratelimit import CODE_LIMITS, DIRECTORY_LIMITS`,
  `from app.auth.deps import get_current_user` (already imported), `from app.ids import new_id`):

```python
RECEIVED = {"status": "received",
            "detail": "If the details are valid, your account was created or is waiting for approval."}


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # no role, no ward: only an approver sets those
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254, pattern=r"^\s*[^@\s]+@[^@\s]+\.[^@\s]+\s*$")
    password: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=300)
    requested_doctor_id: str | None = Field(default=None, max_length=20)
    enrollment_code: str | None = Field(default=None, max_length=20)


class ResetIn(BaseModel):
    email: str = Field(max_length=254)
    code: str = Field(max_length=20)
    new_password: str = Field(min_length=1, max_length=200)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


def _invalid_code(db: Session, ip: str) -> ApiError:
    audit(db, None, "code_failed", "access_code", "", ip=ip)
    db.commit()
    return ApiError(400, "invalid_code", "this code is not valid or has expired")


@router.post("/auth/register", status_code=202)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)) -> dict:
    enforce(request, "register", CODE_LIMITS)
    ip, email, name = client_ip(request), body.email.strip().lower(), body.name.strip()
    check_password(body.password, email=email, name=name)
    if db.scalar(select(User.id).where(User.email == email)):
        audit(db, None, "register_duplicate", "user", "", ip=ip)  # same answer: emails are not enumerable
        db.commit()
        return RECEIVED
    if body.enrollment_code:
        row = codes.find_valid(db, "enrollment", body.enrollment_code)
        if row is None:
            raise _invalid_code(db, ip)
        if db.scalar(select(User.id).where(User.patient_id == row.patient_id, User.status != "disabled")):
            raise ApiError(409, "already_enrolled", "this patient already has an account")
        u = User(id=new_id(db, "u"), email=email, name=name, role="patient", status="active",
                 patient_id=row.patient_id, password_hash=hash_password(body.password))
        db.add(u)
        db.flush()
        codes.mark_used(row, used_by=u.id)
        audit(db, u, "register", "user", u.id, patient_id=row.patient_id, ip=ip)
        audit(db, u, "code_used", "access_code", row.id, patient_id=row.patient_id, ip=ip)
        db.commit()
        return RECEIVED
    doctor = db.get(User, body.requested_doctor_id) if body.requested_doctor_id else None
    if doctor is not None and (doctor.role != "doctor" or doctor.status != "active"):
        doctor = None
    u = User(id=new_id(db, "u"), email=email, name=name, role=None, status="pending",
             password_hash=hash_password(body.password), requested_note=(body.note or "").strip() or None,
             requested_doctor_id=doctor.id if doctor else None)
    db.add(u)
    db.flush()
    audit(db, u, "register", "user", u.id, ip=ip)
    db.commit()
    return RECEIVED


@router.post("/auth/reset", status_code=204)
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)) -> Response:
    enforce(request, "reset", CODE_LIMITS)
    ip, email = client_ip(request), body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    check_password(body.new_password, email=email, name=user.name if user else "")  # before the code is spent
    row = codes.find_valid(db, "reset", body.code, user_id=user.id) if user else None
    if row is None:
        raise _invalid_code(db, ip)
    codes.mark_used(row, used_by=user.id)
    user.password_hash = hash_password(body.new_password)
    user.failed_logins, user.locked_until = 0, None
    audit(db, user, "code_used", "access_code", row.id, ip=ip)
    audit(db, user, "update", "password", user.id, ip=ip)
    db.commit()
    return Response(status_code=204)


@router.post("/auth/change-password", status_code=204)
def change_password(body: ChangePasswordIn, request: Request, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> Response:
    if not verify_password(body.current_password, user.password_hash):
        raise ApiError(401, "bad_credentials", "wrong current password")
    check_password(body.new_password, email=user.email, name=user.name)
    user.password_hash = hash_password(body.new_password)
    audit(db, user, "update", "password", user.id, ip=client_ip(request))
    db.commit()
    return Response(status_code=204)


@router.get("/doctors/directory")
def doctor_directory(request: Request, db: Session = Depends(get_db)) -> list[dict]:
    """Names for the sign-up "I work with" picker: no emails, no wards."""
    enforce(request, "directory", DIRECTORY_LIMITS)
    rows = db.scalars(select(User).where(User.role == "doctor", User.status == "active").order_by(User.name))
    return [{"id": u.id, "name": u.name} for u in rows]
```

- [ ] **Step 4: Run the tests.** Run: test command with `tests/test_register.py`, then the full suite. Expected: all pass.

- [ ] **Step 5: Commit** (only if asked):
  `git add backend/app/routers/auth.py backend/tests/test_register.py && git commit -m "feat(backend): self sign-up with enrollment codes, password reset and change"`

---

### Task 5: Approval and account administration (hospital admin and doctor's team)

**Files:**
- Create: `backend/app/services/accounts.py`, `backend/app/routers/users.py`, `backend/tests/test_user_admin.py`
- Modify: `backend/app/main.py` (include the router), `backend/app/routers/staff.py` (`status`)

**Interfaces:**
- Consumes: `codes.issue`, `User`/`Staff` columns (Task 1), `require_roles`, `audit`.
- Produces:
  - `accounts.can_review(approver, target) -> bool`;
  - `accounts.approve(db, approver, target, role, ward, *, now) -> None`;
  - `accounts.reject(approver, target) -> None`;
  - `accounts.can_manage(db, actor, target) -> bool`;
  - `accounts.set_active(db, actor, target, active: bool) -> None`;
  - `accounts.admin_out(db, u) -> dict` with keys `{id, name, email, role, status, ward, supervisor_id}`;
  - `accounts.pending_out(db, u) -> dict` with keys `{id, name, email, note, requested_doctor_id, requested_doctor_name, status, created_at}`.
  - Routes:
    - `GET /users?status=pending|rejected`;
    - `POST /users/{id}/approve` with `{role, ward?}`;
    - `POST /users/{id}/reject`, `/disable`, `/enable`;
    - `POST /users/{id}/reset-code` → `{code, expires_at}`;
    - `PATCH /users/{id}` with `{ward}` (admin; doctors and nurses only) → `admin_out`;
    - `GET /doctors/me/team`.

- [ ] **Step 1: Write the failing tests** `backend/tests/test_user_admin.py`:

```python
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import AuditLog, Staff, User
from tests.helpers import login, make_user


def _ids(r):
    assert r.status_code == 200, r.text
    return {row["id"] for row in r.json()}


def test_admin_sees_all_pending_doctor_only_his(client, db):
    a = make_user(db, "a.t@medora.tn", role=None, status="pending", requested_doctor_id="u-0001")
    b = make_user(db, "b.t@medora.tn", role=None, status="pending")
    admin, doc = login(client, "admin@medora.tn"), login(client, "doctor@medora.tn")
    assert {a.id, b.id} <= _ids(client.get("/users", headers=admin))
    assert _ids(client.get("/users", headers=doc)) == {a.id}
    assert client.get("/users", headers=login(client, "nurse@medora.tn")).status_code == 403


def test_admin_approves_with_role_and_ward(client, db):
    b = make_user(db, "b.t@medora.tn", role=None, status="pending")
    r = client.post(f"/users/{b.id}/approve", headers=login(client, "admin@medora.tn"),
                    json={"role": "nurse", "ward": "Internal Medicine"})
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["ward"] == "Internal Medicine"
    h = login(client, "b.t@medora.tn")
    assert {p["ward"] for p in client.get("/patients", headers=h).json()} <= {"Internal Medicine"}


def test_admin_approving_a_team_request_as_nurse_keeps_the_doctor(client, db):
    a = make_user(db, "a.t@medora.tn", role=None, status="pending", requested_doctor_id="u-0001")
    client.post(f"/users/{a.id}/approve", headers=login(client, "admin@medora.tn"), json={"role": "nurse"})
    assert db.get(Staff, a.id).supervisor_id == "u-0001"


def test_doctor_approves_his_request_into_his_team(client, db):
    a = make_user(db, "a.t@medora.tn", role=None, status="pending", requested_doctor_id="u-0001")
    r = client.post(f"/users/{a.id}/approve", headers=login(client, "doctor@medora.tn"),
                    json={"role": "nurse", "ward": "Imaging"})
    assert r.status_code == 200
    out = r.json()
    assert (out["role"], out["supervisor_id"], out["ward"]) == ("nurse", "u-0001", None)  # ward ignored for doctors


def test_doctor_limits(client, db):
    a = make_user(db, "a.t@medora.tn", role=None, status="pending", requested_doctor_id="u-0001")
    b = make_user(db, "b.t@medora.tn", role=None, status="pending")
    doc = login(client, "doctor@medora.tn")
    assert client.post(f"/users/{b.id}/approve", headers=doc, json={"role": "nurse"}).status_code == 403
    for role in ("doctor", "admin"):
        assert client.post(f"/users/{a.id}/approve", headers=doc, json={"role": role}).status_code == 403


def test_approve_twice_is_409_and_bad_role_is_422(client, db):
    b = make_user(db, "b.t@medora.tn", role=None, status="pending")
    admin = login(client, "admin@medora.tn")
    assert client.post(f"/users/{b.id}/approve", headers=admin, json={"role": "patient"}).status_code == 422
    assert client.post(f"/users/{b.id}/approve", headers=admin, json={"role": "nurse"}).status_code == 200
    assert client.post(f"/users/{b.id}/approve", headers=admin, json={"role": "nurse"}).status_code == 409


def test_reject_then_approve_later(client, db):
    b = make_user(db, "b.t@medora.tn", role=None, status="pending")
    admin = login(client, "admin@medora.tn")
    assert client.post(f"/users/{b.id}/reject", headers=admin).json()["status"] == "rejected"
    assert client.post("/auth/login", json={"email": "b.t@medora.tn", "password": "ward1234"}).json()["code"] == \
        "account_rejected"
    assert client.post(f"/users/{b.id}/approve", headers=admin, json={"role": "nurse"}).status_code == 200


def test_doctor_disables_only_his_team(client, db):
    team = make_user(db, "team.t@medora.tn", role="nurse", supervisor_id="u-0001")
    doc, admin = login(client, "doctor@medora.tn"), login(client, "admin@medora.tn")
    assert client.post(f"/users/{team.id}/disable", headers=doc).json()["status"] == "disabled"
    assert client.post("/users/u-0002/disable", headers=doc).status_code == 403
    assert client.post(f"/users/{team.id}/enable", headers=doc).json()["status"] == "active"
    assert client.post("/users/u-0002/disable", headers=admin).json()["status"] == "disabled"
    assert client.post("/users/u-0004/disable", headers=admin).status_code == 403  # not yourself


def test_team_endpoint(client, db):
    team = make_user(db, "team.t@medora.tn", role="nurse", supervisor_id="u-0001")
    assert _ids(client.get("/doctors/me/team", headers=login(client, "doctor@medora.tn"))) == {team.id}


def test_reset_code_flow(client, db):
    r = client.post("/users/u-0002/reset-code", headers=login(client, "admin@medora.tn"))
    assert r.status_code == 200 and len(r.json()["code"]) == 11
    assert client.post("/users/u-0002/reset-code", headers=login(client, "doctor@medora.tn")).status_code == 403


def test_reset_code_clears_lock(client, db):
    db.get(User, "u-0002").locked_until = datetime.now(UTC) + timedelta(minutes=10)
    db.flush()
    code = client.post("/users/u-0002/reset-code", headers=login(client, "admin@medora.tn")).json()["code"]
    assert client.post("/auth/reset", json={"email": "nurse@medora.tn", "code": code,
                                            "new_password": "correct-horse-battery"}).status_code == 204
    assert client.post("/auth/login", json={"email": "nurse@medora.tn",
                                            "password": "correct-horse-battery"}).status_code == 200


def test_admin_actions_are_audited(client, db):
    b = make_user(db, "b.t@medora.tn", role=None, status="pending")
    admin = login(client, "admin@medora.tn")
    client.post(f"/users/{b.id}/approve", headers=admin, json={"role": "nurse"})
    client.post(f"/users/{b.id}/disable", headers=admin)
    rows = db.scalars(select(AuditLog).where(AuditLog.resource == "user", AuditLog.resource_id == b.id)).all()
    assert len([r for r in rows if r.action == "update"]) >= 2


def test_staff_list_has_status(client):
    rows = client.get("/staff", headers=login(client, "admin@medora.tn")).json()
    assert all("status" in r for r in rows)


def test_admin_sets_ward_on_an_active_team_nurse(client, db):
    team = make_user(db, "team.t@medora.tn", role="nurse", supervisor_id="u-0001")
    r = client.patch(f"/users/{team.id}", headers=login(client, "admin@medora.tn"), json={"ward": "Cardiology"})
    assert r.status_code == 200 and (r.json()["ward"], r.json()["supervisor_id"]) == ("Cardiology", "u-0001")
    assert client.patch(f"/users/{team.id}", headers=login(client, "doctor@medora.tn"),
                        json={"ward": None}).status_code == 403
    assert client.patch("/users/u-0004", headers=login(client, "admin@medora.tn"),
                        json={"ward": "Cardiology"}).status_code == 409  # admins have no ward
```

- [ ] **Step 2: Run it to see it fail.** Expected: 404 on `/users`.

- [ ] **Step 3: Implement** `backend/app/services/accounts.py`:

```python
"""Who may approve, reject, disable and enable whom (spec §6.2–6.5).

Hospital admin: any account. Doctor: only requests that name him (approve as nurse only, into his team) and only his
team members afterwards. Routers call these and then audit + commit."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.errors import ApiError, forbidden
from app.models import Staff, User
from app.schemas import iso

STAFF_ROLES = ("doctor", "nurse", "admin")


def can_review(approver: User, target: User) -> bool:
    if approver.role == "admin":
        return True
    return approver.role == "doctor" and target.requested_doctor_id == approver.id


def approve(db: Session, approver: User, target: User, role: str, ward: str | None, *, now: datetime) -> None:
    if not can_review(approver, target):
        raise forbidden("this request is not addressed to you")
    if role not in STAFF_ROLES:
        raise ApiError(422, "invalid", "role: doctor, nurse or admin")
    if target.status not in ("pending", "rejected"):
        raise ApiError(409, "bad_status", f"account is {target.status}")
    if approver.role == "doctor":
        if role != "nurse":
            raise forbidden("a doctor can only add nurses to his team")
        ward, supervisor = None, approver.id
    else:
        supervisor = target.requested_doctor_id if role == "nurse" else None
    target.role, target.status, target.approved_by, target.approved_at = role, "active", approver.id, now
    if role != "admin":
        st = db.get(Staff, target.id)
        if st is None:
            st = Staff(user_id=target.id)
            db.add(st)
        st.ward, st.supervisor_id = ward, supervisor
    db.flush()


def reject(approver: User, target: User) -> None:
    if not can_review(approver, target):
        raise forbidden("this request is not addressed to you")
    if target.status != "pending":
        raise ApiError(409, "bad_status", f"account is {target.status}")
    target.status = "rejected"


def can_manage(db: Session, actor: User, target: User) -> bool:
    if actor.id == target.id:
        return False
    if actor.role == "admin":
        return True
    st = db.get(Staff, target.id)
    return actor.role == "doctor" and st is not None and st.supervisor_id == actor.id


def set_active(db: Session, actor: User, target: User, active: bool) -> None:
    if not can_manage(db, actor, target):
        raise forbidden("you cannot manage this account")
    if active:
        if target.status != "disabled" or target.role is None:
            raise ApiError(409, "bad_status", f"account is {target.status}")
        target.status = "active"
    else:
        if target.status == "disabled":
            raise ApiError(409, "bad_status", "account is already disabled")
        target.status = "disabled"


def admin_out(db: Session, u: User) -> dict:
    st = db.get(Staff, u.id)
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "status": u.status,
            "ward": st.ward if st else None, "supervisor_id": st.supervisor_id if st else None}


def pending_out(db: Session, u: User) -> dict:
    doc = db.get(User, u.requested_doctor_id) if u.requested_doctor_id else None
    return {"id": u.id, "name": u.name, "email": u.email, "note": u.requested_note,
            "requested_doctor_id": u.requested_doctor_id, "requested_doctor_name": doc.name if doc else None,
            "status": u.status, "created_at": iso(u.created_at)}
```

`backend/app/routers/users.py`:

```python
"""Account administration (spec §6.2–6.5, api.md 1.9). Rules: app/services/accounts.py."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import codes
from app.auth.deps import require_roles
from app.auth.ratelimit import client_ip
from app.db import get_db
from app.errors import ApiError, not_found
from app.models import Staff, User
from app.schemas import iso
from app.services import accounts as A
from app.services.audit import audit

router = APIRouter(tags=["users"])


class ApproveIn(BaseModel):
    role: str
    ward: str | None = None


def _target(db: Session, user_id: str) -> User:
    u = db.get(User, user_id)
    if u is None:
        raise not_found("user")
    return u


def _done(db: Session, actor: User, target: User, request: Request) -> dict:
    audit(db, actor, "update", "user", target.id, ip=client_ip(request))
    db.flush()
    out = A.admin_out(db, target)
    db.commit()
    return out


@router.get("/users")
def list_requests(request: Request, status: Literal["pending", "rejected"] = "pending",
                  user: User = Depends(require_roles("admin", "doctor")), db: Session = Depends(get_db)) -> list:
    stmt = select(User).where(User.status == status).order_by(User.created_at, User.id)
    if user.role == "doctor":
        stmt = stmt.where(User.requested_doctor_id == user.id)
    out = [A.pending_out(db, u) for u in db.scalars(stmt)]
    audit(db, user, "read", "account_requests", status, ip=client_ip(request))
    db.commit()
    return out


@router.post("/users/{user_id}/approve")
def approve(user_id: str, body: ApproveIn, request: Request, user: User = Depends(require_roles("admin", "doctor")),
            db: Session = Depends(get_db)) -> dict:
    target = _target(db, user_id)
    A.approve(db, user, target, body.role, body.ward, now=datetime.now(UTC))
    return _done(db, user, target, request)


@router.post("/users/{user_id}/reject")
def reject(user_id: str, request: Request, user: User = Depends(require_roles("admin", "doctor")),
           db: Session = Depends(get_db)) -> dict:
    target = _target(db, user_id)
    A.reject(user, target)
    return _done(db, user, target, request)


@router.post("/users/{user_id}/disable")
def disable(user_id: str, request: Request, user: User = Depends(require_roles("admin", "doctor")),
            db: Session = Depends(get_db)) -> dict:
    target = _target(db, user_id)
    A.set_active(db, user, target, False)
    return _done(db, user, target, request)


@router.post("/users/{user_id}/enable")
def enable(user_id: str, request: Request, user: User = Depends(require_roles("admin", "doctor")),
           db: Session = Depends(get_db)) -> dict:
    target = _target(db, user_id)
    A.set_active(db, user, target, True)
    return _done(db, user, target, request)


@router.post("/users/{user_id}/reset-code")
def reset_code(user_id: str, request: Request, user: User = Depends(require_roles("admin")),
               db: Session = Depends(get_db)) -> dict:
    target = _target(db, user_id)
    code, row = codes.issue(db, "reset", issued_by=user.id, user_id=target.id)
    audit(db, user, "create", "access_code", row.id, ip=client_ip(request))
    db.commit()
    return {"code": code, "expires_at": iso(row.expires_at)}


class WardIn(BaseModel):
    ward: str | None


@router.patch("/users/{user_id}")
def set_ward(user_id: str, body: WardIn, request: Request, user: User = Depends(require_roles("admin")),
             db: Session = Depends(get_db)) -> dict:
    """The hospital admin adds (or clears) a ward on an active doctor or nurse, e.g. a doctor's team nurse."""
    target = _target(db, user_id)
    st = db.get(Staff, target.id)
    if target.role not in ("doctor", "nurse") or st is None:
        raise ApiError(409, "bad_status", "only doctors and nurses have a ward")
    st.ward = (body.ward or "").strip() or None
    return _done(db, user, target, request)


@router.get("/doctors/me/team")
def my_team(user: User = Depends(require_roles("doctor")), db: Session = Depends(get_db)) -> list[dict]:
    members = db.scalars(select(User).join(Staff, Staff.user_id == User.id)
                         .where(Staff.supervisor_id == user.id).order_by(User.name)).all()
    return [A.admin_out(db, u) for u in members]
```

In `backend/app/main.py`: change the import to `from app.routers import ai, alerts, appointments, auth, devices, doses, exams, integrations, patients, prescriptions, staff, users`
and add `app.include_router(users.router)` after `staff.router`. In `backend/app/routers/staff.py`, add
`"status": u.status,` to the dict in `list_staff`.

- [ ] **Step 4: Run the tests.** Run: test command with `tests/test_user_admin.py`, then the full suite. Expected: all pass.

- [ ] **Step 5: Commit** (only if asked):
  `git add backend/app/services/accounts.py backend/app/routers/users.py backend/app/routers/staff.py backend/app/main.py backend/tests/test_user_admin.py && git commit -m "feat(backend): account approval by hospital admin and by doctor for his team"`

---

### Task 6: Enrollment codes for patients

**Files:**
- Create: `backend/app/routers/access.py` (the enrollment part; Task 7 adds sharing to the same file),
  `backend/tests/test_enrollment.py`
- Modify: `backend/app/main.py` (include `access.router`)

**Interfaces:**
- Consumes: `codes.issue`.
- Produces:
  - `POST /patients/{patient_id}/enrollment-code` → `{code, expires_at}`;
  - `POST /patients/{patient_id}/reset-code` → `{code, expires_at}` (admin or attending doctor; 404 if the
    patient has no active account);
  - helper `owner_or_admin(db, user, patient_id) -> Patient` in `app/routers/access.py`, reused by Task 7.

- [ ] **Step 1: Write the failing tests** `backend/tests/test_enrollment.py`:

```python
from tests.helpers import login, make_patient, make_user

GOOD = "correct-horse-battery"


def _issue(client, h, pid):
    return client.post(f"/patients/{pid}/enrollment-code", headers=h)


def _register(client, email, code):
    return client.post("/auth/register", json={"name": "Pat", "email": email, "password": GOOD,
                                               "enrollment_code": code})


def test_attending_doctor_issues_and_patient_enrolls(client, db):
    p = make_patient(db, attending="u-0001")
    r = _issue(client, login(client, "doctor@medora.tn"), p.id)
    assert r.status_code == 200 and "expires_at" in r.json()
    assert _register(client, "pat1.t@medora.tn", r.json()["code"]).status_code == 202


def test_other_doctor_nurse_and_patient_cannot_issue(client, db):
    p = make_patient(db, attending="u-0001")
    make_user(db, "doc2.t@medora.tn", role="doctor", ward="Cardiology")
    for email in ("doc2.t@medora.tn", "nurse@medora.tn", "patient@medora.tn"):
        assert _issue(client, login(client, email), p.id).status_code == 403


def test_admin_new_code_revokes_old(client, db):
    p = make_patient(db, attending="u-0001")
    admin = login(client, "admin@medora.tn")
    first, second = _issue(client, admin, p.id).json()["code"], _issue(client, admin, p.id).json()["code"]
    assert _register(client, "pat2.t@medora.tn", first).json()["code"] == "invalid_code"
    assert _register(client, "pat3.t@medora.tn", second).status_code == 202


def test_enrolled_patient_gets_409(client):
    r = _issue(client, login(client, "admin@medora.tn"), "p-0001")
    assert r.status_code == 409 and r.json()["code"] == "already_enrolled"


def test_unknown_patient_404(client):
    assert _issue(client, login(client, "admin@medora.tn"), "p-9999").status_code == 404


def test_patient_password_reset_code_from_attending_or_admin(client, db):
    # patient@medora.tn owns p-0001, whose attending doctor is u-0001
    r = client.post("/patients/p-0001/reset-code", headers=login(client, "doctor@medora.tn"))
    assert r.status_code == 200
    assert client.post("/auth/reset", json={"email": "patient@medora.tn", "code": r.json()["code"],
                                            "new_password": GOOD}).status_code == 204
    assert client.post("/patients/p-0001/reset-code", headers=login(client, "nurse@medora.tn")).status_code == 403
    p = make_patient(db, attending="u-0001")  # no account yet
    assert client.post(f"/patients/{p.id}/reset-code", headers=login(client, "admin@medora.tn")).status_code == 404
```

- [ ] **Step 2: Run it to see it fail.** Expected: 404/405 on the route.

- [ ] **Step 3: Implement** `backend/app/routers/access.py`:

```python
"""Who may reach a patient beyond the defaults (spec §6.3, §6.6): enrollment codes and doctor-to-doctor sharing."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import codes
from app.auth.deps import require_roles
from app.auth.ratelimit import client_ip
from app.db import get_db
from app.errors import ApiError, forbidden, not_found
from app.models import Patient, User
from app.schemas import iso
from app.services.audit import audit

router = APIRouter(prefix="/patients", tags=["access"])


def owner_or_admin(db: Session, user: User, patient_id: str) -> Patient:
    p = db.get(Patient, patient_id)
    if p is None:
        raise not_found("patient")
    if user.role == "admin" or (user.role == "doctor" and p.attending_doctor_id == user.id):
        return p
    raise forbidden("only the hospital admin or the attending doctor")


@router.post("/{patient_id}/enrollment-code")
def enrollment_code(patient_id: str, request: Request, user: User = Depends(require_roles("admin", "doctor")),
                    db: Session = Depends(get_db)) -> dict:
    p = owner_or_admin(db, user, patient_id)
    if db.scalar(select(User.id).where(User.patient_id == p.id, User.status != "disabled")):
        raise ApiError(409, "already_enrolled", "this patient already has an account")
    code, row = codes.issue(db, "enrollment", issued_by=user.id, patient_id=p.id)
    audit(db, user, "create", "access_code", row.id, patient_id=p.id, ip=client_ip(request))
    db.commit()
    return {"code": code, "expires_at": iso(row.expires_at)}


@router.post("/{patient_id}/reset-code")
def patient_reset_code(patient_id: str, request: Request, user: User = Depends(require_roles("admin", "doctor")),
                       db: Session = Depends(get_db)) -> dict:
    """A patient forgot their password: the admin or attending doctor issues a reset code for the patient's account."""
    p = owner_or_admin(db, user, patient_id)
    account = db.scalar(select(User).where(User.patient_id == p.id, User.status != "disabled"))
    if account is None:
        raise not_found("patient account")
    code, row = codes.issue(db, "reset", issued_by=user.id, user_id=account.id)
    audit(db, user, "create", "access_code", row.id, patient_id=p.id, ip=client_ip(request))
    db.commit()
    return {"code": code, "expires_at": iso(row.expires_at)}
```

In `backend/app/main.py`: add `access` to the routers import and `app.include_router(access.router)` **before**
`patients.router` (both use the `/patients` prefix; the paths don't collide, but keep the order explicit).

- [ ] **Step 4: Run the tests.** Run: test command with `tests/test_enrollment.py tests/test_register.py`, then the full
  suite. Expected: all pass.

- [ ] **Step 5: Commit** (only if asked):
  `git add backend/app/routers/access.py backend/app/main.py backend/tests/test_enrollment.py && git commit -m "feat(backend): enrollment codes issued by admin or attending doctor"`

---

### Task 7: Team-nurse and shared-doctor access everywhere, sharing routes

**Files:**
- Modify: `backend/app/auth/deps.py`, `backend/app/services/patients.py` (`search`), `backend/app/routers/patients.py`
  (`list_patients`), `backend/app/routers/alerts.py` (`list_alerts`), `backend/app/ws/hub.py`, `backend/app/ws/router.py`,
  `backend/app/routers/access.py`
- Create: `backend/tests/test_team_and_sharing.py`

**Interfaces:**
- Consumes: `PatientAccess`, `Staff.supervisor_id` (Task 1); `owner_or_admin` (Task 6).
- Produces:
  - in `deps.py`: `has_grant(db, user_id, patient_id, now=None) -> bool`,
    `nurse_scope(db, user) -> tuple[str | None, str | None]` (ward, supervisor_id),
    `nurse_patient_filter(db, user)` and `doctor_patient_filter(db, user)` (SQLAlchemy boolean clauses on `Patient`);
  - `search(db, *, where=None, doctor_id=None, ward=None, q=None)`;
  - `Client.supervisor_id`;
  - routes `GET`/`POST /patients/{id}/access` and `DELETE /patients/{id}/access/{doctor_id}`.

- [ ] **Step 1: Write the failing tests** `backend/tests/test_team_and_sharing.py`:

```python
from datetime import UTC, datetime, timedelta

from app.models import PatientAccess
from app.services import alerts as AL
from app.ws.hub import Client, wants
from tests.helpers import login, make_patient, make_user


def _setup(db):
    team = make_user(db, "team.t@medora.tn", role="nurse", supervisor_id="u-0001")
    doc2 = make_user(db, "doc2.t@medora.tn", role="doctor", ward="Cardiology")
    mine = make_patient(db, attending="u-0001", ward="Cardiology")
    theirs = make_patient(db, attending=doc2.id, ward="Cardiology")
    return team, doc2, mine, theirs


def test_team_nurse_sees_only_her_doctors_patients(client, db):
    _, _, mine, theirs = _setup(db)
    h = login(client, "team.t@medora.tn")
    assert client.get(f"/patients/{mine.id}", headers=h).status_code == 200
    assert client.get(f"/patients/{theirs.id}", headers=h).status_code == 403
    ids = {r["id"] for r in client.get("/patients", headers=h).json()}
    assert mine.id in ids and theirs.id not in ids


def test_team_nurse_gets_her_doctors_alerts_only(client, db):
    _, _, mine, theirs = _setup(db)
    a1 = AL.create_alert(db, mine.id, None, "trend", "medium", None, "test mine", None)
    a2 = AL.create_alert(db, theirs.id, None, "trend", "medium", None, "test theirs", None)
    ids = {a["id"] for a in client.get("/alerts", headers=login(client, "team.t@medora.tn")).json()}
    assert a1.id in ids and a2.id not in ids


def test_team_nurse_ward_screens_are_empty_not_errors(client, db):
    _setup(db)
    h = login(client, "team.t@medora.tn")
    assert client.get("/exams", headers=h).json() == []
    r = client.get("/patients?ward=Nowhere", headers=h)
    assert r.status_code == 200 and r.json() == []


def test_ward_nurse_unchanged(client):
    rows = client.get("/patients", headers=login(client, "nurse@medora.tn")).json()
    assert rows and {r["ward"] for r in rows} == {"Cardiology"}


def test_ws_routes_doctor_frames_to_his_team_nurse():
    team = Client(ws=None, user_id="u-x", role="nurse", ward=None, supervisor_id="u-0001")
    assert wants(team, {"type": "alert", "scope": {"ward": "Cardiology", "doctor_id": "u-0001"}})
    assert not wants(team, {"type": "alert", "scope": {"ward": "Cardiology", "doctor_id": "u-0999"}})
    ward_nurse = Client(ws=None, user_id="u-y", role="nurse", ward="Cardiology")
    assert wants(ward_nurse, {"type": "alert", "scope": {"ward": "Cardiology", "doctor_id": "u-0999"}})


def test_share_gives_access_until_revoked(client, db):
    _, doc2, _, _ = _setup(db)
    h2, h1 = login(client, "doc2.t@medora.tn"), login(client, "doctor@medora.tn")
    assert client.get("/patients/p-0001", headers=h2).status_code == 403
    r = client.post("/patients/p-0001/access", headers=h1, json={"doctor_id": doc2.id})
    assert r.status_code == 200 and r.json()["doctor_id"] == doc2.id
    assert client.get("/patients/p-0001", headers=h2).status_code == 200
    assert "p-0001" in {p["id"] for p in client.get("/patients", headers=h2).json()}
    assert [g["doctor_id"] for g in client.get("/patients/p-0001/access", headers=h1).json()] == [doc2.id]
    assert client.delete(f"/patients/p-0001/access/{doc2.id}", headers=h1).status_code == 204
    assert client.get("/patients/p-0001", headers=h2).status_code == 403


def test_expired_grant_gives_nothing(client, db):
    _, doc2, _, _ = _setup(db)
    now = datetime.now(UTC)
    db.add(PatientAccess(id="pa-9001", patient_id="p-0001", user_id=doc2.id, granted_by="u-0001",
                         created_at=now - timedelta(days=31), expires_at=now - timedelta(days=1)))
    db.flush()
    assert client.get("/patients/p-0001", headers=login(client, "doc2.t@medora.tn")).status_code == 403


def test_only_attending_or_admin_can_share(client, db):
    _, doc2, _, _ = _setup(db)
    body = {"doctor_id": doc2.id}
    assert client.post("/patients/p-0001/access", headers=login(client, "doc2.t@medora.tn"), json=body).status_code == 403
    assert client.post("/patients/p-0001/access", headers=login(client, "nurse@medora.tn"), json=body).status_code == 403
    assert client.post("/patients/p-0001/access", headers=login(client, "admin@medora.tn"), json=body).status_code == 200


def test_share_validation(client, db):
    _, doc2, _, _ = _setup(db)
    h1 = login(client, "doctor@medora.tn")
    far = (datetime.now(UTC) + timedelta(days=400)).isoformat()
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    for body in ({"doctor_id": doc2.id, "expires_at": far}, {"doctor_id": doc2.id, "expires_at": past},
                 {"doctor_id": "u-0002"}, {"doctor_id": "u-0001"}):
        assert client.post("/patients/p-0001/access", headers=h1, json=body).status_code == 422, body
```

- [ ] **Step 2: Run it to see it fail.** Expected: a `TypeError` on `Client(..., supervisor_id=…)` and 403s/404s.

- [ ] **Step 3: Implement the access rules** in `backend/app/auth/deps.py` (add the imports `from datetime import UTC, datetime`,
  `from sqlalchemy import false, or_, select` and `PatientAccess` to the models import):

```python
def has_grant(db: Session, user_id: str, patient_id: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return db.scalar(select(PatientAccess.id).where(
        PatientAccess.patient_id == patient_id, PatientAccess.user_id == user_id,
        PatientAccess.revoked_at.is_(None), PatientAccess.expires_at > now).limit(1)) is not None


def nurse_scope(db: Session, user: User) -> tuple[str | None, str | None]:
    """(ward, supervisor doctor id) of a nurse; a doctor's team nurse may have no ward."""
    st = db.get(Staff, user.id)
    return (st.ward, st.supervisor_id) if st else (None, None)


def nurse_patient_filter(db: Session, user: User):
    ward, sup = nurse_scope(db, user)
    conds = ([Patient.ward == ward] if ward else []) + ([Patient.attending_doctor_id == sup] if sup else [])
    return or_(*conds) if conds else false()


def doctor_patient_filter(db: Session, user: User):
    granted = select(PatientAccess.patient_id).where(
        PatientAccess.user_id == user.id, PatientAccess.revoked_at.is_(None),
        PatientAccess.expires_at > datetime.now(UTC))
    return or_(Patient.attending_doctor_id == user.id, Patient.id.in_(granted))
```

Replace the doctor and nurse branches of `can_access`:

```python
    if user.role == "doctor":
        return patient.attending_doctor_id == user.id or has_grant(db, user.id, patient.id)
    if user.role == "nurse":
        ward, sup = nurse_scope(db, user)
        return (ward is not None and patient.ward == ward) or (
            sup is not None and patient.attending_doctor_id == sup)
```

In `backend/app/services/patients.py`, change `search`:

```python
def search(db: Session, *, where=None, doctor_id: str | None = None, ward: str | None = None,
           q: str | None = None) -> list[Patient]:
    stmt = select(Patient)
    if where is not None:
        stmt = stmt.where(where)
    if doctor_id is not None:
        stmt = stmt.where(Patient.attending_doctor_id == doctor_id)
    # (rest unchanged: ward filter, q filter, order_by)
```

In `backend/app/routers/patients.py` `list_patients`, replace the non-admin branch (import `nurse_patient_filter`,
`doctor_patient_filter` and `nurse_scope` from `app.auth.deps`):

```python
        if user.role == "nurse":
            own, sup = nurse_scope(db, user)
            if ward and own and ward != own and not sup:
                raise forbidden("another ward")
            found = P.search(db, where=nurse_patient_filter(db, user), ward=ward, q=q)
        else:
            found = P.search(db, where=doctor_patient_filter(db, user), ward=ward, q=q)
```

In `backend/app/routers/alerts.py` `list_alerts`, replace the scope block (import both filters from `app.auth.deps`):

```python
    if user.role == "nurse":
        mine = select(Patient.id).where(nurse_patient_filter(db, user))
    else:
        mine = select(Patient.id).where(doctor_patient_filter(db, user))
```

Remove the now-unused `staff_ward` import there if ruff flags it.

In `backend/app/ws/hub.py`, add `supervisor_id: str | None = None` as the last field of `Client`, and change the
nurse rule in `wants`:

```python
    if c.role == "nurse":
        return (c.ward is not None and scope.get("ward") == c.ward) or (
            c.supervisor_id is not None and scope.get("doctor_id") == c.supervisor_id)
```

In `backend/app/ws/router.py`, import `nurse_scope` instead of `staff_ward` and build the client:

```python
    ward, supervisor = nurse_scope(db, user) if user.role in ("nurse", "doctor") else (None, None)
    client = Client(ws=websocket, user_id=user.id, role=user.role, ward=ward, supervisor_id=supervisor)
```

- [ ] **Step 4: Implement the sharing routes** (append to `backend/app/routers/access.py`; add the imports
  `from datetime import UTC, datetime, timedelta`, `from fastapi import Response`, `from pydantic import BaseModel`,
  `from app.ids import new_id` and `PatientAccess` to the models import):

```python
DEFAULT_SHARE = timedelta(days=30)
MAX_SHARE = timedelta(days=365)


class ShareIn(BaseModel):
    doctor_id: str
    expires_at: datetime | None = None


def _active_grants(db: Session, patient_id: str, now: datetime, doctor_id: str | None = None):
    stmt = select(PatientAccess).where(PatientAccess.patient_id == patient_id, PatientAccess.revoked_at.is_(None),
                                       PatientAccess.expires_at > now)
    if doctor_id:
        stmt = stmt.where(PatientAccess.user_id == doctor_id)
    return db.scalars(stmt.order_by(PatientAccess.created_at)).all()


def _grant_out(db: Session, g: PatientAccess) -> dict:
    doc = db.get(User, g.user_id)
    return {"patient_id": g.patient_id, "doctor_id": g.user_id, "doctor_name": doc.name if doc else None,
            "expires_at": iso(g.expires_at)}


@router.get("/{patient_id}/access")
def list_access(patient_id: str, request: Request, user: User = Depends(require_roles("admin", "doctor")),
                db: Session = Depends(get_db)) -> list[dict]:
    p = owner_or_admin(db, user, patient_id)
    out = [_grant_out(db, g) for g in _active_grants(db, p.id, datetime.now(UTC))]
    audit(db, user, "read", "patient_access", p.id, patient_id=p.id, ip=client_ip(request))
    db.commit()
    return out


@router.post("/{patient_id}/access")
def share(patient_id: str, body: ShareIn, request: Request, user: User = Depends(require_roles("admin", "doctor")),
          db: Session = Depends(get_db)) -> dict:
    p = owner_or_admin(db, user, patient_id)
    now = datetime.now(UTC)
    doc = db.get(User, body.doctor_id)
    if doc is None or doc.role != "doctor" or doc.status != "active" or doc.id == p.attending_doctor_id:
        raise ApiError(422, "invalid", "doctor_id: an active doctor other than the attending doctor")
    exp = body.expires_at or now + DEFAULT_SHARE
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if exp <= now or exp > now + MAX_SHARE:
        raise ApiError(422, "invalid", "expires_at: in the future and within one year")
    for old in _active_grants(db, p.id, now, doc.id):  # one live grant per doctor: the new one replaces it
        old.revoked_at = now
    g = PatientAccess(id=new_id(db, "pa"), patient_id=p.id, user_id=doc.id, granted_by=user.id, expires_at=exp)
    db.add(g)
    db.flush()
    audit(db, user, "create", "patient_access", g.id, patient_id=p.id, ip=client_ip(request))
    out = _grant_out(db, g)
    db.commit()
    return out


@router.delete("/{patient_id}/access/{doctor_id}", status_code=204)
def revoke(patient_id: str, doctor_id: str, request: Request, user: User = Depends(require_roles("admin", "doctor")),
           db: Session = Depends(get_db)) -> Response:
    p = owner_or_admin(db, user, patient_id)
    now = datetime.now(UTC)
    grants = _active_grants(db, p.id, now, doctor_id)
    if not grants:
        raise not_found("grant")
    for g in grants:
        g.revoked_at = now
        audit(db, user, "delete", "patient_access", g.id, patient_id=p.id, ip=client_ip(request))
    db.commit()
    return Response(status_code=204)
```

- [ ] **Step 5: Run the tests.** Run: test command with
  `tests/test_team_and_sharing.py tests/test_rbac.py tests/test_access_control.py tests/test_ws.py tests/test_alerts.py tests/test_patients.py`,
  then the full suite. Expected: all pass.

- [ ] **Step 6: Commit** (only if asked):
  `git add backend/app backend/tests/test_team_and_sharing.py && git commit -m "feat(backend): doctor's team nurses and time-limited patient sharing"`

---

### Task 8: First-admin bootstrap command

**Files:**
- Create: `backend/app/bootstrap.py`, `backend/tests/test_bootstrap.py`

**Interfaces:**
- Consumes: `codes.issue`, `check_secrets`.
- Produces:
  - `bootstrap(db, email, name) -> str` (the one-time reset code), which raises `RuntimeError` if an admin or that
    email exists;
  - CLI `python -m app.bootstrap --email … --name …` (exit 0 / 2).

- [ ] **Step 1: Write the failing tests** `backend/tests/test_bootstrap.py`:

```python
import pytest
from sqlalchemy import select

from app.auth import codes
from app.bootstrap import bootstrap
from app.models import User


def test_bootstrap_creates_admin_with_a_working_one_time_code(db):
    code = bootstrap(db, " Boss@Site.TN ", "Hospital Admin")
    u = db.scalar(select(User).where(User.email == "boss@site.tn"))
    assert (u.role, u.status) == ("admin", "active")
    assert codes.find_valid(db, "reset", code, user_id=u.id) is not None


def test_bootstrap_refuses_when_an_admin_exists(seeded):
    with pytest.raises(RuntimeError, match="already"):
        bootstrap(seeded, "other@site.tn", "Other")
```

- [ ] **Step 2: Run it to see it fail.** Expected: `ModuleNotFoundError: No module named 'app.bootstrap'`.

- [ ] **Step 3: Implement** `backend/app/bootstrap.py`:

```python
"""Company → hospital (spec §6.1): create the site's first admin, once, at installation.

    python -m app.bootstrap --email admin@hospital.tn --name "Hospital Admin"

Prints a one-time code (48 h). The admin opens the web app → "I have a code" and sets their own password. The
company keeps no login: the random initial password is never shown and the code dies after use.
"""

import argparse
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import codes
from app.auth.security import hash_password
from app.config import check_secrets, get_settings
from app.db import SessionLocal
from app.ids import new_id
from app.models import User
from app.services.audit import audit


def bootstrap(db: Session, email: str, name: str) -> str:
    email = email.strip().lower()
    if db.scalar(select(User.id).where(User.role == "admin")):
        raise RuntimeError("an admin already exists: approve new accounts from the web app")
    if db.scalar(select(User.id).where(User.email == email)):
        raise RuntimeError(f"{email} is already used")
    u = User(id=new_id(db, "u"), email=email, name=name.strip(), role="admin", status="active",
             password_hash=hash_password(secrets.token_urlsafe(32)))
    db.add(u)
    db.flush()
    code, _ = codes.issue(db, "reset", issued_by=u.id, user_id=u.id)
    audit(db, None, "create", "user", u.id)
    return code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create the first hospital admin")
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", required=True)
    args = ap.parse_args(argv)
    check_secrets(get_settings())
    with SessionLocal() as db:
        try:
            code = bootstrap(db, args.email, args.name)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        db.commit()
    print(f"Admin created: {args.email.strip().lower()}")
    print(f"One-time code (valid 48 h): {code}")
    print("Open the web app, choose 'I have a code', and set your password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests.** Run: test command with `tests/test_bootstrap.py`, then the full suite. Expected: all pass.
  Manual check on the running stack: `docker exec ward-api-1 python -m app.bootstrap --email x@y.tn --name X`.
  Expected: exit code 2 with "an admin already exists" (the seed has an admin).

- [ ] **Step 5: Commit** (only if asked):
  `git add backend/app/bootstrap.py backend/tests/test_bootstrap.py && git commit -m "feat(backend): first-admin bootstrap command"`

---

### Task 9: Settings, CORS and contracts

**Files:**
- Modify: `backend/app/config.py`, `backend/app/main.py`, `.env.example`, `docs/contracts/api.md`,
  `docs/contracts/data-model.md`, `backend/tests/test_config_hardening.py`

**Interfaces:**
- Produces: `Settings.jwt_expire_hours` default 8, and `Settings.web_origin: str` (comma-separated origins, default
  `"http://localhost:3000"`).

- [ ] **Step 1: Write the failing test** (append to `backend/tests/test_config_hardening.py`):

```python
def test_session_and_cors_defaults():
    from app.config import Settings

    s = Settings(_env_file=None)
    assert s.jwt_expire_hours == 8 and s.web_origin == "http://localhost:3000"
```

- [ ] **Step 2: Run it to see it fail.** Expected: the `12 == 8` assertion or a missing `web_origin`.

- [ ] **Step 3: Implement.**
  - In `config.py`, set `jwt_expire_hours: int = 8` and add `web_origin: str = "http://localhost:3000"` after it,
    with the comment `# comma-separated; the proxy domain in the internet profile`.
  - In `main.py`, replace `allow_origins=["http://localhost:3000"]` with
    `allow_origins=[o.strip() for o in get_settings().web_origin.split(",") if o.strip()]`.
  - In `.env.example`, set `JWT_EXPIRE_HOURS=8` and add `WEB_ORIGIN=http://localhost:3000` with the comment
    `# browser origin(s) allowed by CORS; https://<your domain> with the internet profile`.

- [ ] **Step 4: Update the contracts.**
  - `docs/contracts/data-model.md`:
    - bump the header to `**Version:** 1.5 (2026-10-10)`;
    - add the changelog line `1.5 (2026-10-10): accounts — users.status/failed_logins/locked_until/approved_by/approved_at/requested_note/requested_doctor_id, users.role nullable while pending, staff.supervisor_id, new access_codes and patient_access tables`;
    - add the two new tables and the changed columns, copying the tables in spec §5 verbatim;
    - add a role-matrix note: "nurse: own ward OR patients of her supervisor doctor; doctor: attending OR an unexpired, unrevoked patient_access grant".
  - `docs/contracts/api.md`:
    - bump the header to `**Version:** 1.9 (2026-10-10)`;
    - add the changelog line `1.9 (2026-10-10): accounts — register/reset/change-password, doctor directory, account approval (/users*), doctor team, enrollment codes, patient sharing; login error codes; JWT exp 8 h`;
    - change the JWT line in Conventions to `exp (8 h)`;
    - add a new `## Accounts and access` section containing the spec §9 table verbatim, the error codes listed under
      Global Constraints above, and the exact response shapes from Tasks 4–7: `RECEIVED`, `admin_out`,
      `pending_out`, `{code, expires_at}`, `_grant_out`.

- [ ] **Step 5: Run the full suite and lint.** Expected: all pass and `ruff` is clean. Then rebuild and smoke-test the
  live stack:
  `docker compose -f infra/docker-compose.yml --env-file .env up -d --build api && curl -s localhost:8000/health && curl -s localhost:8000/doctors/directory`.
  Expected: health ok and a JSON list of doctor names.

- [ ] **Step 6: Commit** (only if asked):
  `git add backend/app/config.py backend/app/main.py .env.example docs/contracts backend/tests/test_config_hardening.py && git commit -m "docs(contracts): api 1.9 and data-model 1.5 for accounts; 8 h sessions; CORS origin setting"`
  Then announce the contract bump in the team chat and get a 👍 from Faouzi (web) and Wali (backend).
