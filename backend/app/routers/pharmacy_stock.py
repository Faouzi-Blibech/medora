"""Drug stock (api.md 1.12 → Dispensing and stock). Pharmacist writes; the admin reads."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.db import get_db
from app.models import User
from app.schemas import AdjustmentIn, ReceiptIn
from app.services.pharmacy import stock as S
from app.services.schedule import today_local

router = APIRouter(prefix="/pharmacy/stock", tags=["pharmacy-stock"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("")
def stock(user: User = Depends(require_roles("pharmacist", "admin")), db: Session = Depends(get_db)) -> list[dict]:
    return S.stock_view(db, today_local())


@router.get("/reorder")
def reorder(user: User = Depends(require_roles("pharmacist", "admin")), db: Session = Depends(get_db)) -> list[dict]:
    return S.reorder(db, today_local())


@router.post("/receipts", status_code=201)
def receipt(body: ReceiptIn, request: Request, user: User = Depends(require_roles("pharmacist")),
            db: Session = Depends(get_db)) -> dict:
    lot = S.receive(db, user, body.drug_id, body.lot_number, body.expiry_date, body.quantity, ip=_ip(request))
    out = S.lot_out(lot, today_local())
    db.commit()
    return out


@router.post("/adjustments")
def adjustment(body: AdjustmentIn, request: Request, user: User = Depends(require_roles("pharmacist")),
               db: Session = Depends(get_db)) -> dict:
    lot = S.adjust(db, user, body.lot_id, body.delta, body.reason, body.comment, ip=_ip(request))
    out = S.lot_out(lot, today_local())
    db.commit()
    return out
