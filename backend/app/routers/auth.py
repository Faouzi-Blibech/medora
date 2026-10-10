from datetime import UTC, datetime, timedelta
from functools import lru_cache

from fastapi import APIRouter, Depends, Request, Response
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import codes
from app.auth.deps import get_current_user, oauth2_scheme, user_from_token
from app.auth.passwords import check_password
from app.auth.ratelimit import CODE_LIMITS, DIRECTORY_LIMITS, LOGIN_LIMITS, check, client_ip, enforce, record
from app.auth.security import create_token, hash_password, verify_password
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.ids import new_id
from app.models import User
from app.schemas import LoginIn, LoginOut, LoginUser, Me
from app.services.audit import audit

router = APIRouter(tags=["auth"])


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


@router.get("/me", response_model=Me)
def me(user: User = Depends(get_current_user)) -> User:
    return user


RECEIVED = {"status": "received",
            "detail": "If the details are valid, your account was created or is waiting for approval."}


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # no ward, never admin: only an approver sets those
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254, pattern=r"^\s*[^@\s]+@[^@\s]+\.[^@\s]+\s*$")
    password: str = Field(min_length=1, max_length=200)
    role: Literal["patient", "nurse", "doctor", "pharmacist"]  # a request: the approver may change it
    note: str | None = Field(default=None, max_length=300)
    requested_doctor_id: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _staff_pick_no_doctor(self) -> "RegisterIn":
        if self.role in ("doctor", "pharmacist") and self.requested_doctor_id:
            raise ValueError("requested_doctor_id: doctors and pharmacists do not pick a doctor")
        return self


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
    pw_hash = hash_password(body.password)  # before any lookup: every path pays the same bcrypt cost
    if db.scalar(select(User.id).where(User.email == email)):
        audit(db, None, "register_duplicate", "user", "", ip=ip)  # same answer: emails are not enumerable
        db.commit()
        return RECEIVED
    try:
        doctor = db.get(User, body.requested_doctor_id) if body.requested_doctor_id else None
        if doctor is not None and (doctor.role != "doctor" or doctor.status != "active"):
            doctor = None
        u = User(id=new_id(db, "u"), email=email, name=name, role=None, status="pending",
                 password_hash=pw_hash, requested_note=(body.note or "").strip() or None,
                 requested_role=body.role, requested_doctor_id=doctor.id if doctor else None)
        db.add(u)
        db.flush()
        audit(db, u, "register", "user", u.id, ip=ip)
        db.commit()
    except IntegrityError:  # lost a race on the unique email: same answer
        db.rollback()
    return RECEIVED


@router.post("/auth/reset", status_code=204)
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)) -> Response:
    enforce(request, "reset", CODE_LIMITS)
    ip, email = client_ip(request), body.email.strip().lower()
    check_password(body.new_password, email=email)  # generic first: nothing below may depend on the email existing
    user = db.scalar(select(User).where(User.email == email))
    row = codes.find_valid(db, "reset", body.code, user_id=user.id) if user else None
    if row is None:
        raise _invalid_code(db, ip)
    check_password(body.new_password, email=email, name=user.name)  # the name rule: only a valid code reveals it
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
    check(request, "password_change_failed", LOGIN_LIMITS)
    if not verify_password(body.current_password, user.password_hash):
        record(request, "password_change_failed", LOGIN_LIMITS)
        raise ApiError(401, "bad_credentials", "wrong current password")
    check_password(body.new_password, email=user.email, name=user.name)
    user.password_hash = hash_password(body.new_password)
    audit(db, user, "update", "password", user.id, ip=client_ip(request))
    db.commit()
    return Response(status_code=204)


@router.get("/doctors/directory")
def doctor_directory(request: Request, token: str | None = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)) -> list[dict]:
    """Names for the sign-up "I work with" picker and the share panel: no emails, no wards. Anonymous callers share
    the per-IP bucket (a hospital may sit behind one IP); a logged-in caller has a bucket of their own."""
    caller = user_from_token(db, token)
    enforce(request, "directory", DIRECTORY_LIMITS, who=f"user:{caller.id}" if caller else None)
    rows = db.scalars(select(User).where(User.role == "doctor", User.status == "active").order_by(User.name))
    return [{"id": u.id, "name": u.name} for u in rows]


@router.get("/hospital")
def hospital(request: Request) -> dict:
    """The sign-up hospital select: one install is one hospital, named by HOSPITAL_NAME."""
    enforce(request, "hospital", DIRECTORY_LIMITS)
    return {"name": get_settings().hospital_name}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Ends this device's session: the browser drops its token and the server records it. Tokens are stateless, so a
    copied token stays valid until it expires (JWT_EXPIRE_HOURS) — the user chose device-only logout (2026-10-10)."""
    audit(db, user, "logout", "user", user.id, ip=client_ip(request))
    db.commit()
    return Response(status_code=204)
