"""Doses (api.md 1.5 proposal), built for the nurse med round and the doctor's adherence view."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import check_patient_access, require_roles
from app.db import get_db
from app.errors import ApiError, not_found
from app.iot import publisher
from app.iot.ingest import frame
from app.models import MedDose, Prescription, User
from app.schemas import DoseOut, iso
from app.services.pharmacy.dispensing import pharmacy_status
from app.services.schedule import local_to_utc, today_local

router = APIRouter(tags=["doses"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("/patients/{patient_id}/doses", response_model=list[DoseOut])
def list_doses(patient_id: str, request: Request, day: date | None = Query(None, alias="date"),
               user: User = Depends(require_roles("doctor", "nurse", "patient")), db: Session = Depends(get_db)):
    check_patient_access(db, user, patient_id, resource="dose", ip=_ip(request))
    if day:  # a local (Africa/Tunis) calendar day
        lo, hi = local_to_utc(day, "00:00"), local_to_utc(day + timedelta(days=1), "00:00")
    else:  # the last 24 h and the rest of today
        lo, hi = datetime.now(UTC) - timedelta(hours=24), local_to_utc(today_local() + timedelta(days=1), "00:00")
    rows = db.scalars(select(MedDose).where(MedDose.patient_id == patient_id, MedDose.scheduled_at >= lo,
                                            MedDose.scheduled_at < hi)
                      .order_by(MedDose.scheduled_at, MedDose.slot, MedDose.id)).all()
    st = pharmacy_status(db, [d.id for d in rows])
    db.commit()
    return [DoseOut.model_validate(d).model_copy(update={"pharmacy": st.get(d.id, "none")}) for d in rows]


@router.post("/doses/{dose_id}/given")
def given(dose_id: str, request: Request, user: User = Depends(require_roles("nurse")),
          db: Session = Depends(get_db)) -> dict:
    d = db.get(MedDose, dose_id)
    if d is None:
        raise not_found("dose")
    rx = db.get(Prescription, d.prescription_id)  # the 409 comes before check_patient_access writes its audit row
    if rx is not None and not rx.active and d.status != "taken":  # validated or urgent only (pharmacy spec §2)
        raise ApiError(409, "bad_status", f"prescription is {rx.status}: this dose must not be given")
    check_patient_access(db, user, d.patient_id, write=True, resource="dose", ip=_ip(request))
    now = datetime.now(UTC)
    if d.status != "taken":
        d.status, d.updated_at = "taken", now
        db.flush()
    st = pharmacy_status(db, [d.id]).get(d.id, "none")
    out = DoseOut.model_validate(d).model_copy(update={"pharmacy": st}).model_dump(mode="json")
    f = frame(db, "dose_event", {"patient_id": d.patient_id, "dose_id": d.id, "status": "taken", "method": None,
                                 "ts": iso(now)}, d.patient_id)
    db.commit()
    publisher.publish_ws_frame(f)
    # given_by is the confirming nurse; it is kept in audit_log (data-model 1.3 has no med_doses column for it)
    return {**out, "given_by": user.id, "given_by_name": user.name, "taken_at": iso(now)}
