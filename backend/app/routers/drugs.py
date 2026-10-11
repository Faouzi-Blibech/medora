"""The hospital drug catalogue (api.md 1.12 → Drug catalogue). Read: staff. Write: pharmacist, admin. Never deleted."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.db import get_db
from app.errors import not_found
from app.models import Drug, User
from app.schemas import DrugIn, DrugPatch
from app.services.audit import audit
from app.services.pharmacy import formulary as F

router = APIRouter(prefix="/drugs", tags=["drugs"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("")
def search(q: str = Query("", max_length=80), active: Literal["true", "false", "all"] = "true",
           user: User = Depends(require_roles("doctor", "nurse", "pharmacist", "admin")),
           db: Session = Depends(get_db)) -> list[dict]:
    return [F.drug_out(d) for d in F.search(db, q, active)]  # no patient data: not audited


@router.post("", status_code=201)
def create(body: DrugIn, request: Request, user: User = Depends(require_roles("pharmacist", "admin")),
           db: Session = Depends(get_db)) -> dict:
    d = F.create_drug(db, body.model_dump())
    audit(db, user, "create", "drug", d.id, ip=_ip(request))
    out = F.drug_out(d)
    db.commit()
    return out


@router.patch("/{drug_id}")
def update(drug_id: str, body: DrugPatch, request: Request,
           user: User = Depends(require_roles("pharmacist", "admin")), db: Session = Depends(get_db)) -> dict:
    d = db.get(Drug, drug_id)
    if d is None:
        raise not_found("drug")
    F.update_drug(db, d, body.model_dump(exclude_unset=True))
    audit(db, user, "update", "drug", d.id, ip=_ip(request))
    out = F.drug_out(d)
    db.commit()
    return out
