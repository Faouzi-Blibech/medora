"""Dispensing to wards (api.md 1.12 → Dispensing and stock). Pharmacist prepares; the ward nurse receives."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.db import get_db
from app.models import User
from app.schemas import HHMM, DispenseIn
from app.services.audit import audit
from app.services.pharmacy import dispensing as D
from app.services.schedule import today_local

router = APIRouter(tags=["dispensing"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("/pharmacy/dispensing")
def round_view(request: Request, round_time: str = Query(alias="round", pattern=HHMM),
               day: date | None = Query(None, alias="date"), ward: str | None = Query(None, max_length=60),
               user: User = Depends(require_roles("pharmacist")), db: Session = Depends(get_db)) -> list[dict]:
    day = day or today_local()
    rows = D.round_view(db, day, round_time, ward)
    for w in rows:
        for p in w["patients"]:
            audit(db, user, "read", "dose", f"{day.isoformat()} {round_time}", patient_id=p["id"], ip=_ip(request))
    db.commit()
    return rows


@router.post("/pharmacy/dispensations", status_code=201)
def dispense(body: DispenseIn, request: Request, user: User = Depends(require_roles("pharmacist")),
             db: Session = Depends(get_db)) -> dict:
    disp = D.dispense(db, user, body.ward, body.day, body.round_time,
                      [(ln.dose_id, ln.lot_id) for ln in body.lines], ip=_ip(request))
    out = D.dispensation_out(db, disp)
    db.commit()
    return out


@router.get("/dispensations")
def list_dispensations(request: Request, ward: str | None = Query(None, max_length=60),
                       day: date | None = Query(None, alias="date"),
                       user: User = Depends(require_roles("nurse", "pharmacist")),
                       db: Session = Depends(get_db)) -> list[dict]:
    out = [D.dispensation_out(db, d) for d in D.list_for(db, user, ward, day or today_local())]
    for d in out:
        for pid in sorted({ln["patient_id"] for ln in d["lines"]}):
            audit(db, user, "read", "dispensation", d["id"], patient_id=pid, ip=_ip(request))
    db.commit()
    return out


@router.post("/dispensations/{disp_id}/receive")
def receive(disp_id: str, request: Request, user: User = Depends(require_roles("nurse")),
            db: Session = Depends(get_db)) -> dict:
    disp = D.receive_delivery(db, user, disp_id)
    audit(db, user, "update", "dispensation", disp.id, ip=_ip(request))
    out = D.dispensation_out(db, disp)
    db.commit()
    return out
