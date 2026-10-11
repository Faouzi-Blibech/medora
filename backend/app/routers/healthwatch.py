"""Health watch routes (owner: Faouzi): weather-health alerts for the hospital's city and health news.

Staff (doctor, nurse, admin) see the forecast, the alerts with the patients they can access who belong to an
at-risk group, and the news. A patient sees the alerts with advice, marked when they concern them. n8n reads the
alerts every morning (GET /integrations/n8n/health-watch) and sends advice on WhatsApp; no patient data leaves.
"""

from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import weather_health as W
from app.auth.deps import can_access, require_roles
from app.config import get_settings
from app.db import get_db
from app.errors import not_found
from app.models import Appointment, Patient, User
from app.routers.integrations import require_n8n
from app.services import healthwatch as H
from app.services.audit import audit

router = APIRouter(tags=["health-watch"])

DEMO = {
    "heatwave": {"day": 1, "set": {"apparent_max": 41.0, "tmax": 39.0}},
    "dust": {"day": 2, "set": {"dust_max": 320.0, "pm10_max": 410.0, "aqi_max": 180}},
    "cold": {"day": 1, "set": {"tmin": 2.0}},
}


def _age(dob: date | None) -> int | None:
    if dob is None:
        return None
    t = date.today()
    return t.year - dob.year - ((t.month, t.day) < (dob.month, dob.day))


def _forecast() -> dict:
    w = H.weather()
    days = [dict(d) for d in w["days"]]
    scenario = get_settings().health_watch_demo
    if scenario in DEMO and len(days) > DEMO[scenario]["day"]:
        days[DEMO[scenario]["day"]].update(DEMO[scenario]["set"])
    return {"city": w["city"], "available": w["available"], "days": days, "demo": scenario if scenario in DEMO else None,
            "alerts": W.evaluate(days) if days else []}


def _patient_text(db: Session, p: Patient) -> str:
    referrals = db.scalars(select(Appointment.referral_text).where(Appointment.patient_id == p.id)).all()
    return " ".join([p.history or "", *referrals])


def _at_risk(db: Session, patients: list[Patient], groups: list[str]) -> list[dict]:
    out = []
    for p in patients:
        hit = W.patient_groups(_age(p.date_of_birth), _patient_text(db, p)) & set(groups)
        if hit:
            out.append({"id": p.id, "name": f"{p.first_name} {p.last_name}", "groups": sorted(hit)})
    return out


@router.get("/health-watch")
def health_watch(request: Request, user: User = Depends(require_roles("doctor", "nurse", "admin")),
                 db: Session = Depends(get_db)) -> dict:
    f = _forecast()
    patients = [p for p in db.scalars(select(Patient).order_by(Patient.id)) if user.role == "admin" or can_access(db, user, p)]
    ip = request.client.host if request.client else ""
    listed = set()
    for a in f["alerts"]:
        risk = _at_risk(db, patients, a["groups"])
        a["at_risk_count"] = len(risk)
        a["at_risk"] = [] if user.role == "admin" else risk  # admin: counts only
        listed |= {r["id"] for r in a["at_risk"]}
    for pid in sorted(listed):  # names and risk groups come from the record: audited
        audit(db, user, "read", "health_watch", pid, patient_id=pid, ip=ip)
    db.commit()
    return {**f, "days": f["days"][1:], "news": H.news(), "updated_at": H.now_iso()}


@router.get("/health-watch/me")
def my_health_watch(user: User = Depends(require_roles("patient")), db: Session = Depends(get_db)) -> dict:
    p = db.get(Patient, user.patient_id) if user.patient_id else None
    if p is None:
        raise not_found("patient")
    f = _forecast()
    mine = W.patient_groups(_age(p.date_of_birth), _patient_text(db, p))
    alerts = [{k: a[k] for k in ("id", "date", "severity", "value", "groups", "title", "patient")}
              | {"concerns_me": bool(mine & set(a["groups"]))} for a in f["alerts"]]
    return {"city": f["city"], "available": f["available"], "demo": f["demo"], "days": f["days"][1:], "alerts": alerts}


@router.get("/integrations/n8n/health-watch", dependencies=[Depends(require_n8n)])
def n8n_health_watch(db: Session = Depends(get_db)) -> dict:
    """The morning WhatsApp: alerts with staff and patient advice and how many patients are at risk (no names)."""
    f = _forecast()
    patients = list(db.scalars(select(Patient)))
    alerts = [{k: a[k] for k in ("id", "date", "severity", "value", "groups", "title", "staff", "patient")}
              | {"at_risk_count": len(_at_risk(db, patients, a["groups"]))} for a in f["alerts"]]
    return {"city": f["city"], "demo": f["demo"], "alerts": alerts}
