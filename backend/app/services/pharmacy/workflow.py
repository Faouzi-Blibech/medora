"""Prescription life cycle (pharmacy spec §2): pending_pharmacy → validated | changes_requested | rejected; stopped;
superseded. `active` is derived from the status and kept in its column for the dose/schedule/AI code. Routers call
these, then audit, commit and publish the frames."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.errors import ApiError, not_found
from app.ids import new_id
from app.integrations import n8n
from app.iot.ingest import frame
from app.models import Drug, MedDose, Patient, Prescription, PrescriptionReview, Staff, User
from app.schemas import iso
from app.services import schedule
from app.services.accounts import active_doctor
from app.services.pharmacy import formulary as F
from app.services.pharmacy.checks import Check, PatientInfo, RunningItem, run_checks

LIVE = ("pending_pharmacy", "changes_requested", "validated")


def derive_active(status: str, urgent: bool) -> bool:
    return status == "validated" or (status == "pending_pharmacy" and urgent)


def running_clause():
    """SQL for "running": validated, or pending_pharmacy with urgent (spec §4)."""
    return or_(Prescription.status == "validated",
               and_(Prescription.status == "pending_pharmacy", Prescription.urgent.is_(True)))


def set_status(rx: Prescription, status: str) -> bool:
    """Move rx to `status` and re-derive `active`. True when `active` changed (its doses must be rebuilt)."""
    was = rx.active
    rx.status = status
    rx.active = derive_active(status, rx.urgent)
    return rx.active != was


def lock(db: Session, rx_id: str) -> Prescription:
    """The prescription row under SELECT … FOR UPDATE (spec §8): concurrent decisions serialise here, and the
    second one reads the first one's status."""
    rx = db.scalar(select(Prescription).where(Prescription.id == rx_id).with_for_update()
                   .execution_options(populate_existing=True))
    if rx is None:
        raise not_found("prescription")
    return rx


def chain(db: Session, rx: Prescription, limit: int = 20, *, lock_rows: bool = False) -> list[Prescription]:
    """The versions rx replaces, nearest first (its replaces_id, then that one's, …). `lock_rows` takes each one
    under FOR UPDATE and re-reads it, always newest to oldest, so every path locks in the same order."""
    out: list[Prescription] = []
    seen = {rx.id}
    cur = rx.replaces_id
    while cur and cur not in seen and len(out) < limit:
        prev = db.scalar(select(Prescription).where(Prescription.id == cur).with_for_update()
                         .execution_options(populate_existing=True)) if lock_rows else db.get(Prescription, cur)
        if prev is None:
            break
        out.append(prev)
        seen.add(prev.id)
        cur = prev.replaces_id
    return out


def age_on(dob: date | None, today: date) -> int | None:
    if dob is None:
        return None
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def patient_info(p: Patient) -> PatientInfo:
    return PatientInfo(age=age_on(p.date_of_birth, schedule.today_local()), allergies=tuple(p.allergies or ()))


def ensure_drugs(db: Session, items: list[dict]) -> None:
    ids = {i["drug_id"] for i in items if i.get("drug_id")}
    if not ids:
        return
    found = set(db.scalars(select(Drug.id).where(Drug.id.in_(ids), Drug.active.is_(True))))
    missing = sorted(ids - found)
    if missing:
        raise ApiError(422, "unknown_drug", f"unknown or inactive drug: {', '.join(missing)}")


def checks_for(db: Session, patient: Patient, items: list[dict], exclude: set[str]) -> list[Check]:
    """Run the engine for `items` against the patient's other running prescriptions, minus `exclude` (the
    prescription itself and the versions it replaces). Two queries: running prescriptions, then their drugs."""
    stmt = select(Prescription).where(Prescription.patient_id == patient.id, running_clause())
    if exclude:
        stmt = stmt.where(Prescription.id.not_in(exclude))
    running = [RunningItem(r.id, it.get("med", ""), it.get("drug_id")) for r in db.scalars(stmt) for it in r.items]
    ids = {i["drug_id"] for i in items if i.get("drug_id")} | {r.drug_id for r in running if r.drug_id}
    return run_checks(patient_info(patient), items, running, F.drug_infos(db, ids))


def replace_target(db: Session, replaces_id: str, patient_id: str, *, lock_row: bool) -> Prescription:
    old = lock(db, replaces_id) if lock_row else db.get(Prescription, replaces_id)
    if old is None:
        raise not_found("prescription")
    if old.patient_id != patient_id:
        raise ApiError(409, "conflict", "replaces_id belongs to another patient")
    return old


def has_live_descendant(db: Session, rx: Prescription, limit: int = 50) -> bool:
    """True when any later version of rx, at any depth, is live (pending, changes requested or validated). A fork
    of the chain would run two versions of one therapy at once."""
    frontier, seen = [rx.id], {rx.id}
    while frontier and len(seen) < limit:
        kids = db.execute(select(Prescription.id, Prescription.status)
                          .where(Prescription.replaces_id.in_(frontier))).all()
        if any(status in LIVE for _, status in kids):
            return True
        frontier = [i for i, _ in kids if i not in seen]
        seen.update(frontier)
    return bool(frontier)  # a chain deeper than `limit` is refused rather than guessed at


def exclusions(db: Session, old: Prescription | None) -> set[str]:
    return set() if old is None else {old.id, *(p.id for p in chain(db, old))}


@dataclass
class Outcome:
    rx: Prescription
    touched: list[Prescription] = field(default_factory=list)  # every prescription whose status changed
    doses_changed: bool = False  # some `active` flipped: rebuild + publish the device schedule


def create(db: Session, doctor: User, patient: Patient, body) -> Outcome:
    """A new prescription (or a new version through replaces_id), always `pending_pharmacy`. Every 4xx is raised
    before the first write."""
    items = [i.model_dump() for i in body.items]
    ensure_drugs(db, items)
    old = replace_target(db, body.replaces_id, patient.id, lock_row=True) if body.replaces_id else None
    older = chain(db, old, lock_rows=True) if old is not None else []  # superseded below: lock them now
    if old is not None and (old.status not in LIVE or has_live_descendant(db, old)):
        raise ApiError(409, "conflict", "replaces_id is not the latest version")
    checks = checks_for(db, patient, items, {old.id, *(p.id for p in older)} if old is not None else set())
    reason = (body.override_reason or "").strip() or None
    if reason is None and any(c.severity == "critical" for c in checks):
        raise ApiError(422, "override_required", "a critical check needs an override_reason")
    rx = Prescription(id=new_id(db, "rx"), patient_id=patient.id, doctor_id=doctor.id, items=items,
                      care_plan=body.care_plan, status="pending_pharmacy", urgent=body.urgent,
                      active=derive_active("pending_pharmacy", body.urgent),
                      version=old.version + 1 if old else 1, replaces_id=old.id if old else None,
                      checks=[c.as_dict() for c in checks], override_reason=reason)
    db.add(rx)
    db.flush()
    db.refresh(rx)
    out = Outcome(rx=rx, touched=[rx], doses_changed=rx.active)
    for prev in [old, *older] if old is not None else []:
        if prev.status in ("pending_pharmacy", "changes_requested") and not prev.active:
            set_status(prev, "superseded")  # it never ran: the new version takes its place now
            out.touched.append(prev)
        elif prev.active and rx.urgent:
            set_status(prev, "superseded")  # the urgent version starts now: no double dosing
            out.touched.append(prev)
            out.doses_changed = True
        # a running version otherwise keeps running until the new one is validated (decide)
    db.flush()
    return out


def stop(db: Session, rx: Prescription) -> Outcome:
    """Stopping is always safe and immediate (spec §2). `rx` must come from lock()."""
    if rx.status not in LIVE:
        raise ApiError(409, "bad_status", f"prescription is {rx.status}")
    changed = set_status(rx, "stopped")
    db.flush()
    return Outcome(rx=rx, touched=[rx], doses_changed=changed)


def apply_doses(db: Session, out: Outcome) -> tuple[bool, int | None]:
    """Rebuild the doses of every touched prescription; publish the device schedule if any `active` flipped.
    Returns (published_to_device, the device's schedule_version)."""
    ids = [r.id for r in out.touched]

    def scheduled() -> set[str]:
        return set(db.scalars(select(MedDose.id).where(MedDose.prescription_id.in_(ids),
                                                       MedDose.status == "scheduled")))

    before = scheduled()
    for r in out.touched:
        schedule.rebuild_doses(db, r)
    changed = out.doses_changed or scheduled() != before  # the device must never keep a dose id that is gone
    sent = schedule.push_schedule(db, out.rx.patient_id) if changed else False
    dev = schedule.device_of(db, out.rx.patient_id)
    return sent, dev.schedule_version if dev else None


def status_frames(db: Session, out: Outcome) -> list[dict]:
    """`prescription_status` WS frames (api 1.12), routed by the patient's scope; pharmacists get them all."""
    return [frame(db, "prescription_status", {"prescription_id": r.id, "patient_id": r.patient_id,
                                              "status": r.status, "urgent": r.urgent}, r.patient_id)
            for r in out.touched]


def rx_out(db: Session, rx: Prescription, *, for_patient: bool = False) -> dict:
    """The api.md 1.12 Prescription. Patients see only `status` on top of the 1.0 fields."""
    out = {"id": rx.id, "patient_id": rx.patient_id, "doctor_id": rx.doctor_id, "items": rx.items,
           "care_plan": rx.care_plan, "active": rx.active, "created_at": iso(rx.created_at), "status": rx.status}
    if for_patient:
        return out
    reviewer = db.get(User, rx.reviewed_by) if rx.reviewed_by else None
    return {**out, "urgent": rx.urgent, "version": rx.version, "replaces_id": rx.replaces_id,
            "checks": rx.checks or [], "override_reason": rx.override_reason, "review_comment": rx.review_comment,
            "reviewed_by_name": reviewer.name if reviewer else None, "reviewed_at": iso(rx.reviewed_at)}


DECISIONS = ("validated", "changes_requested", "rejected")


def decide(db: Session, pharmacist: User, rx_id: str, decision: str, comment: str | None, *,
           acknowledged: bool = False) -> Outcome:
    """A pharmacist decision on a pending prescription, under the row lock. The checks are recomputed now (the
    patient's other prescriptions may have changed since the save). Every 4xx is raised before the first write."""
    assert decision in DECISIONS
    rx = lock(db, rx_id)
    if rx.status != "pending_pharmacy":
        raise ApiError(409, "bad_status", f"prescription is {rx.status}")
    ancestors = chain(db, rx, lock_rows=True)  # re-read under lock: a stop that just committed is seen
    checks = checks_for(db, db.get(Patient, rx.patient_id), rx.items, {rx.id, *(a.id for a in ancestors)})
    if decision == "validated" and checks and not acknowledged:
        raise ApiError(422, "ack_required", "tick 'warnings reviewed' before validating")
    now = datetime.now(UTC)
    rx.checks = [c.as_dict() for c in checks]
    rx.reviewed_by, rx.reviewed_at = pharmacist.id, now
    rx.review_comment = (comment or "").strip() or None
    out = Outcome(rx=rx, touched=[rx], doses_changed=set_status(rx, decision))
    if decision == "validated":
        for prev in ancestors:
            if prev.active:  # the new version takes over only now (spec §2: treatment never stops)
                set_status(prev, "superseded")
                out.touched.append(prev)
                out.doses_changed = True
    db.add(PrescriptionReview(id=new_id(db, "pr"), prescription_id=rx.id, pharmacist_id=pharmacist.id,
                              decision=decision, comment=rx.review_comment, checks_snapshot=rx.checks))
    db.flush()
    return out


def emit_review(db: Session, rx: Prescription, decision: str, comment: str | None) -> None:
    """n8n `prescription.review` (n8n-webhooks 1.4), sent only if the transaction commits. A doctor whose account
    is no longer active gets nothing (api 1.9)."""
    doctor = active_doctor(db, rx.doctor_id)
    st = db.get(Staff, rx.doctor_id) if doctor else None
    n8n.emit_after_commit(db, "prescription.review", {
        "prescription_id": rx.id, "patient_id": rx.patient_id, "decision": decision,
        "comment": (comment or "").strip() or None, "doctor_email": doctor.email if doctor else None,
        "doctor_chat_id": st.telegram_chat_id if st else None})
