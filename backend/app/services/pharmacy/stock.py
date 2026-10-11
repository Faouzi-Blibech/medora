"""Drug stock (pharmacy spec §3, §5 Phase B): lots, append-only movements, FEFO. Every quantity change happens on a
locked lot row in the caller's transaction and writes its movement and its audit row. Stock never goes negative."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError, not_found
from app.ids import new_id
from app.models import Drug, StockLot, StockMovement, User
from app.schemas import iso
from app.services.audit import audit
from app.services.schedule import today_local

EXPIRING_DAYS = 30


def fefo_key(lot: StockLot) -> tuple:
    return (lot.expiry_date, lot.received_at, lot.id)


def pick_lot(lots: list[StockLot], need: int, on: date, left: dict[str, int] | None = None) -> StockLot | None:
    """FEFO: among the lots not expired on `on` that still hold `need` units (per `left`, default their quantity),
    the one that expires first; ties go to the oldest receipt, then the id."""
    left = left if left is not None else {lot.id: lot.quantity for lot in lots}
    ok = [lot for lot in lots if lot.expiry_date >= on and left[lot.id] >= need]
    return min(ok, key=fefo_key, default=None)


def on_hand(lots: list[StockLot], on: date) -> int:
    return sum(lot.quantity for lot in lots if lot.expiry_date >= on)


def lot_out(lot: StockLot, today: date) -> dict:
    return {"id": lot.id, "drug_id": lot.drug_id, "lot_number": lot.lot_number,
            "expiry_date": lot.expiry_date.isoformat(), "quantity": lot.quantity, "received_at": iso(lot.received_at),
            "expired": lot.expiry_date < today,
            "expiring": today <= lot.expiry_date <= today + timedelta(days=EXPIRING_DAYS)}


def _locked(stmt):
    return stmt.with_for_update().execution_options(populate_existing=True)


def lock_lots(db: Session, drug_ids: set[str]) -> list[StockLot]:
    """Every lot of these drugs under FOR UPDATE, in id order (one order everywhere: no deadlock)."""
    if not drug_ids:
        return []
    return list(db.scalars(_locked(select(StockLot).where(StockLot.drug_id.in_(sorted(drug_ids)))
                                   .order_by(StockLot.id))))


def move(db: Session, user: User, lot: StockLot, delta: int, reason: str, *, ref_id: str | None = None,
         comment: str | None = None, patient_id: str | None = None, ip: str = "") -> StockMovement:
    """Apply `delta` to a locked lot, write the movement and its audit row. 409 below zero, before any write."""
    if lot.quantity + delta < 0:
        raise ApiError(409, "insufficient_stock", f"lot {lot.lot_number} holds {lot.quantity}",
                       extra={"drug_id": lot.drug_id})
    lot.quantity += delta
    sm = StockMovement(id=new_id(db, "sm"), drug_id=lot.drug_id, lot_id=lot.id, delta=delta, reason=reason,
                       ref_id=ref_id, comment=comment, by_user_id=user.id)
    db.add(sm)
    db.flush()
    audit(db, user, "create", "stock_movement", sm.id, patient_id=patient_id, ip=ip)
    return sm


def receive(db: Session, user: User, drug_id: str, lot_number: str, expiry_date: date, quantity: int,
            ip: str = "") -> StockLot:
    if db.get(Drug, drug_id) is None:
        raise not_found("drug")
    if expiry_date < today_local():
        raise ApiError(422, "invalid", "expiry_date: this lot is already expired")
    lot = db.scalar(_locked(select(StockLot).where(StockLot.drug_id == drug_id, StockLot.lot_number == lot_number)))
    if lot is not None and lot.expiry_date != expiry_date:
        raise ApiError(409, "conflict", f"lot {lot_number} is stocked with expiry {lot.expiry_date.isoformat()}")
    if lot is None:
        lot = StockLot(id=new_id(db, "lot"), drug_id=drug_id, lot_number=lot_number, expiry_date=expiry_date,
                       quantity=0)
        db.add(lot)
        db.flush()
        db.refresh(lot)
    move(db, user, lot, quantity, "receipt", ip=ip)
    return lot


def adjust(db: Session, user: User, lot_id: str, delta: int, reason: str, comment: str, ip: str = "") -> StockLot:
    lot = db.scalar(_locked(select(StockLot).where(StockLot.id == lot_id)))
    if lot is None:
        raise not_found("lot")
    if reason == "expired" and delta >= 0:
        raise ApiError(422, "invalid", "delta: an expired write-off removes stock (negative delta)")
    move(db, user, lot, delta, reason, comment=comment, ip=ip)
    return lot


def _lots_by_drug(db: Session) -> dict[str, list[StockLot]]:
    out: dict[str, list[StockLot]] = defaultdict(list)
    for lot in db.scalars(select(StockLot).where(StockLot.quantity > 0).order_by(StockLot.expiry_date, StockLot.id)):
        out[lot.drug_id].append(lot)
    return out


def stock_view(db: Session, today: date) -> list[dict]:
    lots = _lots_by_drug(db)
    out = []
    for d in db.scalars(select(Drug).where(Drug.active.is_(True)).order_by(Drug.dci, Drug.strength, Drug.id)):
        mine = [lot_out(lot, today) for lot in lots.get(d.id, [])]
        have = on_hand(lots.get(d.id, []), today)
        out.append({"drug_id": d.id, "dci": d.dci, "strength": d.strength, "form": d.form, "on_hand": have,
                    "min_stock": d.min_stock, "lots": mine, "low": have < d.min_stock,
                    "expiring": any(x["expiring"] for x in mine), "expired": any(x["expired"] for x in mine)})
    return out


def reorder(db: Session, today: date) -> list[dict]:
    return [{"drug_id": r["drug_id"], "dci": r["dci"], "strength": r["strength"], "form": r["form"],
             "on_hand": r["on_hand"], "min_stock": r["min_stock"],
             "suggested_quantity": 2 * r["min_stock"] - r["on_hand"]} for r in stock_view(db, today) if r["low"]]


def alert_counts(db: Session, today: date) -> dict:
    view = stock_view(db, today)
    return {"low_stock": sum(1 for r in view if r["low"]),
            "expiring": sum(1 for r in view for lot in r["lots"] if lot["expiring"])}
