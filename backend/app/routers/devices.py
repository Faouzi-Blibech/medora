from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import check_patient_access, require_roles
from app.db import get_db
from app.errors import ApiError, forbidden, not_found
from app.ids import new_id
from app.integrations import n8n
from app.iot import publisher
from app.models import Admission, Device, MedDose, Patient, Prescription, User
from app.schemas import AssignIn, CommandIn, iso
from app.services import schedule
from app.services.audit import audit

router = APIRouter(tags=["devices"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("/devices")
def list_devices(user: User = Depends(require_roles("admin", "nurse")), db: Session = Depends(get_db)) -> list:
    out = []
    for d in db.scalars(select(Device).order_by(Device.id)):
        adm = db.scalar(select(Admission).where(Admission.device_id == d.id, Admission.discharged_at.is_(None)))
        p = db.get(Patient, adm.patient_id) if adm else None
        out.append({"id": d.id, "online": d.online, "fw_version": d.fw_version, "last_seen": iso(d.last_seen),
                    "patient_id": adm.patient_id if adm else None, "bed": adm.bed if adm else None,
                    "patient_name": f"{p.first_name} {p.last_name}" if p else None,
                    "admission_id": adm.id if adm else None,
                    "schedule_version": d.schedule_version, "schedule_acked_version": d.schedule_acked_version})
    return out


@router.post("/devices/{device_id}/assign")
def assign(device_id: str, body: AssignIn, request: Request, user: User = Depends(require_roles("admin")),
           db: Session = Depends(get_db)) -> dict:
    dev = db.get(Device, device_id)
    if dev is None:
        raise not_found("device")
    if db.get(Patient, body.patient_id) is None:
        raise not_found("patient")
    busy = db.scalar(select(Admission).where(Admission.device_id == device_id, Admission.discharged_at.is_(None),
                                             Admission.patient_id != body.patient_id))
    if busy:
        raise ApiError(409, "device_busy", f"{device_id} is assigned to {busy.patient_id}")
    adm = db.scalar(select(Admission).where(Admission.patient_id == body.patient_id,
                                            Admission.discharged_at.is_(None)))
    if adm is None:
        adm = Admission(id=new_id(db, "adm"), patient_id=body.patient_id, admitted_at=datetime.now(UTC),
                        device_id=device_id, bed=body.bed)
        db.add(adm)
    else:
        old_device = adm.device_id
        adm.device_id, adm.bed = device_id, body.bed
        db.flush()
        if old_device and old_device != device_id:  # the old unit must stop dosing this patient
            schedule.push_unassigned(db, old_device)
    db.flush()
    audit(db, user, "update", "admission", adm.id, patient_id=body.patient_id, ip=_ip(request))
    sent = schedule.push_schedule(db, body.patient_id)
    out = {"admission_id": adm.id, "patient_id": adm.patient_id, "device_id": device_id, "bed": adm.bed,
           "schedule_version": dev.schedule_version, "published_to_device": sent}
    db.commit()
    return out


@router.post("/admissions/{admission_id}/discharge")
def discharge(admission_id: str, request: Request, user: User = Depends(require_roles("admin", "doctor")),
              db: Session = Depends(get_db)) -> dict:
    adm = db.get(Admission, admission_id)
    if adm is None:
        raise not_found("admission")
    if user.role == "doctor":
        check_patient_access(db, user, adm.patient_id, write=True, resource="admission", ip=_ip(request))
    if adm.discharged_at is not None:
        raise ApiError(409, "already_discharged", "this admission is already closed")
    adm.discharged_at = datetime.now(UTC)
    db.flush()
    if user.role == "admin":  # a doctor's update was already audited by check_patient_access
        audit(db, user, "update", "admission", adm.id, patient_id=adm.patient_id, ip=_ip(request))
    if adm.device_id:
        schedule.push_unassigned(db, adm.device_id)  # the bedside unit clears its schedule
    p = db.get(Patient, adm.patient_id)
    out = {"admission_id": adm.id, "patient_id": adm.patient_id, "device_id": adm.device_id,
           "discharged_at": iso(adm.discharged_at)}
    db.commit()
    n8n.emit("patient.discharged", {"patient_id": p.id, "patient_first_name": p.first_name,
                                    "patient_email": p.email, "patient_telegram_chat_id": p.telegram_chat_id,
                                    "doctor_id": p.attending_doctor_id, "discharged_at": out["discharged_at"]})
    return out


@router.post("/devices/{device_id}/command")
def command(device_id: str, body: CommandIn, request: Request,
            user: User = Depends(require_roles("doctor", "nurse", "admin")), db: Session = Depends(get_db)) -> dict:
    if db.get(Device, device_id) is None:
        raise not_found("device")
    if user.role == "admin":
        if body.type == "dispense_now":  # releasing medication is a clinical action
            raise forbidden("admins cannot dispense medication")
        audit(db, user, "create", "device_command", device_id, ip=_ip(request))
    else:
        adm = db.scalar(select(Admission).where(Admission.device_id == device_id, Admission.discharged_at.is_(None)))
        if adm is None:
            raise forbidden("this unit is not assigned to a patient")
        check_patient_access(db, user, adm.patient_id, write=True, resource="device_command", ip=_ip(request))
        if body.dose_id:
            dose = db.get(MedDose, body.dose_id)
            if dose is None or dose.patient_id != adm.patient_id:
                raise ApiError(422, "invalid", "dose_id: not a dose of this unit's patient")
            rx = db.get(Prescription, dose.prescription_id)
            if rx is not None and not rx.active:  # a stopped, rejected or superseded prescription: no medication
                raise ApiError(409, "bad_status", f"prescription is {rx.status}: this dose must not be given")
            if dose.status == "taken":  # already given: releasing it again would double the dose
                raise ApiError(409, "bad_status", "this dose was already given")
    db.commit()
    return {"published": publisher.publish_command(device_id, body.model_dump(exclude_none=True))}
