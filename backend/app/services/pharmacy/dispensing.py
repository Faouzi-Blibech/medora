"""Dispensing to wards (pharmacy spec §5 Phase B): the round view, the one-transaction dispensation (FEFO), the
nurse's receipt, and each dose's pharmacy status."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import staff_ward
from app.errors import ApiError, forbidden, not_found
from app.ids import new_id
from app.models import Dispensation, DispensationLine, MedDose, Patient, Prescription, StockLot, User
from app.schemas import iso
from app.services.audit import audit
from app.services.pharmacy import stock as S
from app.services.pharmacy.review import bed_of, user_name
from app.services.schedule import local_to_utc, today_local


def item_for_dose(rx: Prescription, dose: MedDose) -> dict | None:
    """The prescription item a dose row came from (same med, slot and time; else the first with that med)."""
    med = dose.meds[0] if dose.meds else None
    for it in rx.items:
        if it.get("med") == med and it.get("slot") == dose.slot and dose.time_of_day in (it.get("times") or []):
            return it
    return next((it for it in rx.items if it.get("med") == med), None)


DISPENSABLE = ("scheduled", "dispensed")  # not yet taken or missed (dispensed = released by the bedside unit)


def quantity_of(item: dict | None) -> int:
    return int((item or {}).get("units_per_intake") or 1)


def pharmacy_status(db: Session, dose_ids: list[str]) -> dict[str, str]:
    """dose_id → sent | received for the doses on a dispensation line (others: none)."""
    if not dose_ids:
        return {}
    rows = db.execute(select(DispensationLine.dose_id, Dispensation.status)
                      .join(Dispensation, Dispensation.id == DispensationLine.dispensation_id)
                      .where(DispensationLine.dose_id.in_(dose_ids))).all()
    return {dose_id: status for dose_id, status in rows}


def _bounds(day: date) -> tuple[datetime, datetime]:
    return local_to_utc(day, "00:00"), local_to_utc(day + timedelta(days=1), "00:00")


def round_view(db: Session, day: date, round_time: str, ward: str | None) -> list[dict]:
    lo, hi = _bounds(day)
    stmt = (select(MedDose, Patient, Prescription).join(Patient, Patient.id == MedDose.patient_id)
            .join(Prescription, Prescription.id == MedDose.prescription_id)
            .where(MedDose.time_of_day == round_time, MedDose.scheduled_at >= lo, MedDose.scheduled_at < hi,
                   Prescription.active.is_(True), Patient.ward.is_not(None)))
    if ward:
        stmt = stmt.where(Patient.ward == ward)
    rows = db.execute(stmt.order_by(Patient.ward, Patient.last_name, Patient.first_name, Patient.id, MedDose.slot,
                                    MedDose.id)).all()
    sent = pharmacy_status(db, [d.id for d, _, _ in rows])
    # a dose already given or missed is not dispensable; keep it only if it was dispensed before
    rows = [(d, p, rx) for d, p, rx in rows if d.status in DISPENSABLE or d.id in sent]
    plans = [(d, p, rx, item_for_dose(rx, d)) for d, p, rx in rows]
    drug_ids = {it["drug_id"] for *_, it in plans if it and it.get("drug_id")}
    lots: dict[str, list[StockLot]] = defaultdict(list)
    if drug_ids:
        for lot in db.scalars(select(StockLot).where(StockLot.drug_id.in_(drug_ids), StockLot.quantity > 0)):
            lots[lot.drug_id].append(lot)
    on = max(day, today_local())
    wards: dict[str, dict[str, dict]] = {}
    for d, p, rx, it in plans:
        drug_id = (it or {}).get("drug_id")
        qty = quantity_of(it)
        lot = S.pick_lot(lots[drug_id], qty, on) if drug_id else None
        patients = wards.setdefault(p.ward, {})
        pt = patients.setdefault(p.id, {"id": p.id, "name": f"{p.first_name} {p.last_name}".strip(),
                                        "bed": bed_of(db, p.id), "doses": []})
        pt["doses"].append({
            "dose_id": d.id, "prescription_id": rx.id, "med": d.meds[0] if d.meds else (it or {}).get("med", ""),
            "drug_id": drug_id, "quantity": qty,
            "suggested_lot": {"id": lot.id, "lot_number": lot.lot_number,
                              "expiry_date": lot.expiry_date.isoformat()} if lot else None,
            "on_hand": S.on_hand(lots[drug_id], on) if drug_id else None, "dispensed": d.id in sent})
    return [{"ward": w, "patients": list(ps.values())} for w, ps in wards.items()]


@dataclass
class _Plan:
    dose: MedDose
    patient_id: str
    drug_id: str | None
    lot_id: str | None
    quantity: int
    med: str


def dispense(db: Session, user: User, ward: str, day: date, round_time: str, lines: list[tuple[str, str | None]],
             ip: str = "") -> Dispensation:
    """Prepare one ward round in one transaction (spec §5). Validate every line, lock the doses and then the lots,
    allocate FEFO in memory (counting what earlier lines took), and only then write the dispensation, its lines,
    the lot decrements and the movements. Every 4xx/409 is raised before the first write."""
    dose_ids = [dose_id for dose_id, _ in lines]
    if len(set(dose_ids)) != len(dose_ids):
        raise ApiError(422, "invalid", "lines: a dose appears twice")
    doses = {d.id: d for d in db.scalars(select(MedDose).where(MedDose.id.in_(dose_ids)).order_by(MedDose.id)
                                         .with_for_update().execution_options(populate_existing=True))}
    missing = [x for x in dose_ids if x not in doses]
    if missing:
        raise not_found(f"dose {missing[0]}")
    done = sorted(db.scalars(select(DispensationLine.dose_id).where(DispensationLine.dose_id.in_(dose_ids))))
    if done:
        raise ApiError(409, "already_dispensed", f"already dispensed: {', '.join(done)}")
    lo, hi = _bounds(day)
    plans: list[_Plan] = []
    for dose_id, lot_id in lines:
        d = doses[dose_id]
        p = db.get(Patient, d.patient_id)
        rx = db.get(Prescription, d.prescription_id)
        if p is None or p.ward != ward or d.time_of_day != round_time or not lo <= d.scheduled_at < hi:
            raise ApiError(422, "invalid", f"dose {dose_id} is not in the {ward} {round_time} round of {day}")
        if rx is None or not rx.active:
            raise ApiError(409, "bad_status", f"dose {dose_id}: prescription is {rx.status if rx else 'missing'}")
        if d.status not in DISPENSABLE:
            raise ApiError(409, "bad_status", f"dose {dose_id} is already {d.status}")
        it = item_for_dose(rx, d)
        drug_id = (it or {}).get("drug_id")
        if lot_id and not drug_id:
            raise ApiError(422, "invalid", f"dose {dose_id}: a non-formulary drug has no lot")
        plans.append(_Plan(dose=d, patient_id=p.id, drug_id=drug_id, lot_id=lot_id, quantity=quantity_of(it),
                           med=d.meds[0] if d.meds else (it or {}).get("med", "")))
    on = max(day, today_local())
    lots = S.lock_lots(db, {pl.drug_id for pl in plans if pl.drug_id})
    by_id = {lot.id: lot for lot in lots}
    left = {lot.id: lot.quantity for lot in lots}
    chosen: list[StockLot | None] = []
    for pl in plans:
        if pl.drug_id is None:
            chosen.append(None)
            continue
        if pl.lot_id:
            lot = by_id.get(pl.lot_id)
            if lot is None or lot.drug_id != pl.drug_id:
                raise ApiError(422, "invalid", f"lot {pl.lot_id} does not hold {pl.med}")
            if lot.expiry_date < on:
                raise ApiError(422, "invalid", f"lot {lot.lot_number} is expired")
            if left[lot.id] < pl.quantity:
                lot = None
        else:
            lot = S.pick_lot([x for x in lots if x.drug_id == pl.drug_id], pl.quantity, on, left)
        if lot is None:
            raise ApiError(409, "insufficient_stock", f"not enough stock for {pl.med}", extra={"drug_id": pl.drug_id})
        left[lot.id] -= pl.quantity
        chosen.append(lot)
    # every check passed: write
    disp = Dispensation(id=new_id(db, "disp"), ward=ward, round_date=day, round_time=round_time, status="sent",
                        prepared_by=user.id)
    db.add(disp)
    for pl, lot in zip(plans, chosen, strict=True):
        db.add(DispensationLine(id=new_id(db, "dl", 6), dispensation_id=disp.id, dose_id=pl.dose.id,
                                patient_id=pl.patient_id, drug_id=pl.drug_id, lot_id=lot.id if lot else None,
                                quantity=pl.quantity, med=pl.med))
    try:
        db.flush()
    except IntegrityError as e:  # a concurrent request dispensed one of these doses first (unique dose_id)
        raise ApiError(409, "already_dispensed", "already dispensed") from e
    for pl, lot in zip(plans, chosen, strict=True):
        if lot is not None:
            S.move(db, user, lot, -pl.quantity, "dispense", ref_id=disp.id, patient_id=pl.patient_id, ip=ip)
    for pid in sorted({pl.patient_id for pl in plans}):
        audit(db, user, "create", "dispensation", disp.id, patient_id=pid, ip=ip)
    db.refresh(disp)
    return disp


def dispensation_out(db: Session, d: Dispensation) -> dict:
    lines = []
    for ln in db.scalars(select(DispensationLine).where(DispensationLine.dispensation_id == d.id)
                         .order_by(DispensationLine.id)):
        p = db.get(Patient, ln.patient_id)
        lot = db.get(StockLot, ln.lot_id) if ln.lot_id else None
        lines.append({"id": ln.id, "dose_id": ln.dose_id, "patient_id": ln.patient_id,
                      "patient_name": f"{p.first_name} {p.last_name}".strip() if p else None,
                      "bed": bed_of(db, ln.patient_id), "drug_id": ln.drug_id, "lot_id": ln.lot_id,
                      "lot_number": lot.lot_number if lot else None, "quantity": ln.quantity, "med": ln.med})
    return {"id": d.id, "ward": d.ward, "round_date": d.round_date.isoformat(), "round_time": d.round_time,
            "status": d.status, "prepared_by": d.prepared_by, "prepared_by_name": user_name(db, d.prepared_by),
            "prepared_at": iso(d.prepared_at), "received_by": d.received_by,
            "received_by_name": user_name(db, d.received_by), "received_at": iso(d.received_at), "lines": lines}


def list_for(db: Session, user: User, ward: str | None, day: date) -> list[Dispensation]:
    """A nurse sees her own ward only (another ward is 403; none without a ward). A pharmacist sees any."""
    if user.role == "nurse":
        own = staff_ward(db, user)
        if ward and ward != own:
            raise forbidden("another ward")
        if own is None:
            return []
        ward = own
    stmt = select(Dispensation).where(Dispensation.round_date == day)
    if ward:
        stmt = stmt.where(Dispensation.ward == ward)
    return list(db.scalars(stmt.order_by(Dispensation.round_time, Dispensation.id)))


def receive_delivery(db: Session, nurse: User, disp_id: str) -> Dispensation:
    """The ward nurse confirms receipt. Idempotent: a second call keeps the first receiver."""
    disp = db.scalar(select(Dispensation).where(Dispensation.id == disp_id).with_for_update()
                     .execution_options(populate_existing=True))
    if disp is None:
        raise not_found("dispensation")
    if staff_ward(db, nurse) != disp.ward:
        raise forbidden("not your ward")
    if disp.status == "sent":
        disp.status, disp.received_by, disp.received_at = "received", nurse.id, datetime.now(UTC)
        db.flush()
    return disp
