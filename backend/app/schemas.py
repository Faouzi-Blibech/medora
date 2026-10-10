"""Pydantic shapes for docs/contracts/api.md, field-for-field. Timestamps serialize as ISO-8601 UTC with `Z`.

A few additive fields from the api.md 1.5 proposals are included where they cost nothing
(`sex`, `last_vital_at`, `device_online`, `admitted_at`, `attending_doctor_name`, `author_name`).
"""

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints, model_validator


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


Ts = Annotated[datetime, PlainSerializer(iso, return_type=str)]


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth ---
class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class LoginUser(BaseModel):
    id: str
    name: str
    role: str
    patient_id: str | None


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: LoginUser


class Me(Orm):
    id: str
    name: str
    email: str
    role: str
    patient_id: str | None


# --- patients ---
class PatientListItem(BaseModel):
    """Admin view of the list: name, bed and device only (data-model.md → role matrix)."""

    id: str
    first_name: str
    last_name: str
    ward: str | None
    bed: str | None
    device_id: str | None
    admission_id: str | None


class PatientSummary(PatientListItem):
    age: int | None
    sex: str | None
    latest_news2: int | None
    open_alerts: int
    last_vital_at: Ts | None
    device_online: bool | None


class PatientOut(PatientSummary):
    date_of_birth: date | None
    allergies: list
    history: str
    attending_doctor_id: str | None
    attending_doctor_name: str | None
    admitted_at: Ts | None


class PatientPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    phone: str | None = None
    email: str | None = None
    telegram_chat_id: str | None = None
    ward: str | None = None
    allergies: list[str] | None = None
    history: str | None = None

    @model_validator(mode="after")
    def _not_null(self):
        bad = [k for k in ("first_name", "last_name", "allergies", "history")
               if k in self.model_fields_set and getattr(self, k) is None]
        if bad:
            raise ValueError(f"{', '.join(bad)} cannot be null")
        return self


class VitalOut(Orm):
    ts: Ts
    hr: int | None
    spo2: int | None
    temp: float | None
    nurse_id: str | None
    news2: int | None
    source: str


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class NoteOut(BaseModel):
    id: str
    author_id: str
    author_role: str | None
    author_name: str | None
    text: str
    created_at: Ts


# --- prescriptions ---
class PrescriptionOut(Orm):
    id: str
    patient_id: str
    doctor_id: str
    items: list
    care_plan: str
    active: bool
    created_at: Ts


HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class RxItemIn(BaseModel):
    med: str = Field(min_length=1, max_length=80)
    times: list[Annotated[str, Field(pattern=HHMM)]] = Field(min_length=1, max_length=8)
    slot: int | None = Field(default=None, ge=1, le=4)
    days: int = Field(default=1, ge=1, le=60)


class PrescriptionIn(BaseModel):
    patient_id: str
    items: list[RxItemIn] = Field(min_length=1, max_length=8)
    care_plan: str = ""


class PrescriptionPatch(BaseModel):
    active: bool


class PrescriptionPublished(PrescriptionOut):
    schedule_version: int | None
    published_to_device: bool


class AssignIn(BaseModel):
    patient_id: str
    bed: str = Field(min_length=1, max_length=20)


class CommandIn(BaseModel):
    type: str = Field(pattern=r"^(alert|message|dispense_now|rotate_home)$")
    text: str | None = Field(default=None, max_length=120)
    dose_id: str | None = None


class DoseOut(Orm):
    id: str
    prescription_id: str
    patient_id: str
    scheduled_at: Ts
    time_of_day: str
    meds: list
    slot: int | None
    status: str
    taken_method: str | None
    updated_at: Ts


# --- pharmacy (api 1.12) ---
Comment = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
DrugForm = Literal["tablet", "capsule", "syrup", "injection", "inhaler", "patch", "drops", "other"]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"(?i)^[a-z][a-z0-9_]{0,39}$")]
Brand = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Dci = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Strength = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
Atc = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"(?i)^$|^[A-Z]\d{2}[A-Z]{2}\d{2}$")]


class DrugIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dci: Dci
    brand_names: list[Brand] = Field(default_factory=list, max_length=20)
    form: DrugForm
    strength: Strength = ""
    unit_mg: float | None = Field(default=None, gt=0, le=100000)
    max_daily_mg: float | None = Field(default=None, gt=0, le=1000000)
    atc_code: Atc = ""
    allergy_classes: list[Tag] = Field(default_factory=list, max_length=20)
    interaction_groups: list[Tag] = Field(default_factory=list, max_length=20)
    high_alert: bool = False
    min_stock: int = Field(default=0, ge=0, le=1000000)
    active: bool = True


class DrugPatch(BaseModel):
    """Only the fields sent change. `unit_mg` and `max_daily_mg` may be set to null; the others may not."""

    model_config = ConfigDict(extra="forbid")
    dci: Dci | None = None
    brand_names: list[Brand] | None = Field(default=None, max_length=20)
    form: DrugForm | None = None
    strength: Strength | None = None
    unit_mg: float | None = Field(default=None, gt=0, le=100000)
    max_daily_mg: float | None = Field(default=None, gt=0, le=1000000)
    atc_code: Atc | None = None
    allergy_classes: list[Tag] | None = Field(default=None, max_length=20)
    interaction_groups: list[Tag] | None = Field(default=None, max_length=20)
    high_alert: bool | None = None
    min_stock: int | None = Field(default=None, ge=0, le=1000000)
    active: bool | None = None
