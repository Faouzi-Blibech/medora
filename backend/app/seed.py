"""Synthetic demo dataset (data-model.md → "Seed data"). Idempotent: exits early if doctor@ward.tn exists.

The seed also holds the pharmacist and the pharmacy demo (a pending critical prescription).
Run inside the stack: `docker compose -f infra/docker-compose.yml exec api python -m app.seed`.
Every name, phone and history below is invented. Never put real patients here.
"""

import math
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.config import check_secrets, get_settings
from app.ai.exams import suggest_exams
from app.db import SessionLocal
from app.health_seed import seed_health_events
from app.radiograph_seed import seed_radiographs
from app.ids import new_id, reserve_upto
from app.models import (
    Admission,
    Appointment,
    Device,
    Drug,
    ExamOrder,
    Patient,
    Prescription,
    PrescriptionReview,
    Staff,
    StockLot,
    StockMovement,
    User,
    Vital,
)
from app.services import exams as E
from app.services.appointments import new_appointment_fields
from app.services.pharmacy import formulary as F
from app.services.pharmacy import workflow as W
from app.services.pharmacy.backfill import backfill_drug_ids
from app.services.schedule import local_to_utc, rebuild_doses, today_local

# (id, email, name, role, ward, rfid)
STAFF = [
    ("u-0001", "doctor@ward.tn", "Dr Trabelsi", "doctor", "Cardiology", None),
    ("u-0002", "nurse@ward.tn", "Nurse Ines", "nurse", "Cardiology", "04A1B2C3"),
    ("u-0003", "nurse2@ward.tn", "Nurse Sami", "nurse", "Internal Medicine", None),
    ("u-0004", "admin@ward.tn", "Hela Mejri", "admin", None, None),
    ("u-0006", "imaging@ward.tn", "Nurse Rania", "nurse", "Imaging", None),
    ("u-0007", "lab@ward.tn", "Nurse Karim", "nurse", "Laboratory", None),
    ("u-0008", "pharmacist@ward.tn", "Pharm. Salma", "pharmacist", None, None),
]
PHARMACIST_ID = "u-0008"
STAFF_ROW_ROLES = ("doctor", "nurse")  # only these have a ward or supervisor

# (first, last, dob, sex, allergies, history)
PATIENTS = [
    ("Amira", "Ben Salah", date(1972, 3, 14), "F", ["penicillin"], "Hypertension"),
    ("Hédi", "Mansour", date(1958, 7, 2), "M", [], "Heart failure (NYHA II)"),
    ("Lina", "Bouazizi", date(1989, 11, 23), "F", ["aspirin"], "Palpitations, under evaluation"),
    ("Omar", "Jaziri", date(1965, 1, 9), "M", [], "Atrial fibrillation on warfarin"),
    ("Youssef", "Khelifi", date(1947, 5, 30), "M", ["sulfa"], "Post-MI, type 2 diabetes"),
    ("فاطمة", "العياري", date(1980, 9, 17), "F", [], "Chest pain, rule out ACS"),
    ("Karim", "Ben Ali", date(1970, 4, 4), "M", [], "Community-acquired pneumonia"),
    ("Faouzia", "Mabrouk", date(1962, 12, 12), "F", ["latex"], "COPD exacerbation"),
    ("Adam", "Saidi", date(1995, 6, 21), "M", [], "Dehydration, gastroenteritis"),
    ("Mohamed", "Ayari", date(1951, 2, 28), "M", [], "Chronic kidney disease stage 3"),
    ("Sami", "Gharbi", date(1977, 8, 8), "M", [], "Uncontrolled type 2 diabetes"),
    ("Mounir", "Gharsalli", date(1984, 10, 3), "M", ["penicillin"], "Cellulitis, left leg"),
]

# (patient index, referral text, symptoms, days ago)
REQUESTS = [
    (5, "ألم في الصدر منذ يومين / douleur thoracique depuis deux jours", ["chest pain"], 0),
    (2, "Palpitations at night, short of breath when climbing stairs", ["palpitations", "dyspnea"], 1),
    (6, "Fièvre et toux productive depuis 5 jours", ["fever", "cough"], 2),
    (8, "Routine diabetes follow-up, HbA1c review", ["follow-up"], 6),
    (9, "Swelling of both ankles for two weeks", ["edema"], 3),
    (10, "Renouvellement d'ordonnance, tension stable", ["prescription renewal"], 8),
    (11, "Red painful leg, warm to touch, fever 38.5", ["fever", "leg pain"], 1),
    (7, "Essoufflement qui augmente, sifflements", ["dyspnea", "wheezing"], 2),
    (3, "Bleeding gums since warfarin dose change", ["bleeding"], 0),
    (4, "Annual check-up, no complaints", ["check-up"], 10),
]


def _patient_id(i: int) -> str:
    return f"p-{i + 1:04d}"


def _upsert_missing_staff(db: Session, pw: str) -> None:
    """Staff added to STAFF after a database was first seeded (e.g. the department nurses)."""
    for uid, email, name, role, ward, rfid in STAFF:
        if db.get(User, uid) is None and db.scalar(select(User).where(User.email == email)) is None:
            db.add(User(id=uid, email=email, name=name, role=role, password_hash=pw))
            db.flush()
        if role in STAFF_ROW_ROLES and db.get(Staff, uid) is None and db.get(User, uid) is not None:
            db.add(Staff(user_id=uid, ward=ward, rfid_uid=rfid))
    db.flush()
    reserve_upto(db, "u", 8)


def seed(db: Session) -> bool:
    """Create the dataset in `db` (caller commits). Returns False if it was already seeded."""
    pw = hash_password(get_settings().seed_password)
    if db.scalar(select(User).where(User.email == "doctor@ward.tn")):
        _upsert_missing_staff(db, pw)
        _pharmacy(db, datetime.now(UTC).replace(second=0, microsecond=0))
        _stock(db)
        seed_health_events(db)
        return False
    now = datetime.now(UTC).replace(second=0, microsecond=0)

    for uid, email, name, role, _, _ in STAFF:
        db.add(User(id=uid, email=email, name=name, role=role, password_hash=pw))
    db.flush()  # users <-> patients is an FK cycle, so the unit of work can't order these inserts itself
    for i, (first, last, dob, sex, allergies, history) in enumerate(PATIENTS):
        cardio = i < 6
        db.add(Patient(id=_patient_id(i), first_name=first, last_name=last, date_of_birth=dob, sex=sex,
                       allergies=allergies, history=history,
                       ward="Cardiology" if cardio else "Internal Medicine",
                       attending_doctor_id="u-0001" if cardio else None,
                       phone=f"+216 20 000 {i + 1:03d}", email=f"patient{i + 1}@example.tn"))
    db.flush()
    for uid, _, _, role, ward, rfid in STAFF:
        if role in STAFF_ROW_ROLES:
            db.add(Staff(user_id=uid, ward=ward, rfid_uid=rfid))
    db.add(User(id="u-0005", email="patient@ward.tn", name="Amira Ben Salah", role="patient",
                patient_id="p-0001", password_hash=pw))

    if db.get(Device, "bsu-001") is None:  # the worker may have registered it from its retained status
        db.add(Device(id="bsu-001", fw_version="0.1.0", online=False))
    db.flush()
    db.add(Admission(id="adm-0001", patient_id="p-0001", device_id="bsu-001", bed="C-12",
                     admitted_at=now - timedelta(days=2)))

    # 48 h of normal manual readings every 15 min for the admitted patient: a deterministic wave inside
    # the normal ranges (reproducible, and no pseudo-random generator in the codebase)
    start = now - timedelta(hours=48)
    start = start.replace(minute=start.minute - start.minute % 15)
    for k in range(48 * 4):
        db.add(Vital(ts=start + timedelta(minutes=15 * k), device_id="bsu-001", patient_id="p-0001",
                     hr=77 + round(9 * math.sin(k / 5)) + (k % 5 - 2), spo2=97 + (k % 3),
                     temp=round(36.9 + 0.3 * math.sin(k / 8), 1), news2=0, source="manual"))

    # written at local midnight so all of today's doses exist for the demo
    db.add(Prescription(id="rx-0001", patient_id="p-0001", doctor_id="u-0001", active=True,
                        created_at=local_to_utc(today_local(), "00:00"),
                        care_plan="Monitor blood pressure twice a day",
                        items=[{"med": "Amlodipine 5mg", "times": ["08:00"], "slot": 1, "days": 5},
                               {"med": "Paracetamol 500mg", "times": ["08:00", "20:00"], "slot": 2,
                                "days": 5}]))
    db.flush()
    rebuild_doses(db, db.get(Prescription, "rx-0001"))

    patients = {p.id: p for p in db.scalars(select(Patient))}
    for n, (pi, text_, symptoms, days_ago) in enumerate(REQUESTS, start=1):
        created = now - timedelta(days=days_ago, hours=n)
        fields = new_appointment_fields(patients[_patient_id(pi)], text_, symptoms, today=created.date())
        a = Appointment(id=f"a-{n:04d}", created_at=created, **fields)
        db.add(a)
        db.flush()
        suggestion = suggest_exams(" ".join([text_, *symptoms]), a.ai_suggested.get("red_flags", []))
        for ex in E.suggested_fields(a.patient_id, a.id, suggestion):
            db.add(ExamOrder(id=new_id(db, "ex"), **ex))
    db.flush()

    seed_health_events(db)
    for prefix, n in [("u", 8), ("p", len(PATIENTS)), ("adm", 1), ("rx", 1), ("a", len(REQUESTS))]:
        reserve_upto(db, prefix, n)
    _pharmacy(db, now)
    _stock(db)
    return True


DEMO_CARE_PLAN = "Demo: penicillin allergy, sent with a doctor override (pharmacy spec §7)"
DEMO_ITEMS = [{"med": "Amoxicillin 1 g", "drug_id": "d-0003", "dose_mg": 1000, "units_per_intake": 1,
               "times": ["08:00", "14:00", "20:00"], "slot": None, "days": 7}]


def _pharmacy(db: Session, now: datetime) -> None:
    """Formulary, drug ids on existing items, rx-0001 validated by the seed pharmacist, and the pending critical demo
    prescription. Idempotent, so it also upgrades a database seeded before the pharmacy existed."""
    F.load_formulary(db)
    backfill_drug_ids(db)
    rx = db.get(Prescription, "rx-0001")
    if rx is not None and rx.status == "validated" and rx.reviewed_by is None and db.get(User, PHARMACIST_ID):
        rx.reviewed_by, rx.reviewed_at = PHARMACIST_ID, rx.created_at
        db.add(PrescriptionReview(id=new_id(db, "pr"), prescription_id=rx.id, pharmacist_id=PHARMACIST_ID,
                                  decision="validated", comment=None, checks_snapshot=[]))
    if db.scalar(select(Prescription.id).where(Prescription.care_plan == DEMO_CARE_PLAN)) is None:
        checks = W.checks_for(db, db.get(Patient, "p-0001"), DEMO_ITEMS, set())
        db.add(Prescription(id=new_id(db, "rx"), patient_id="p-0001", doctor_id="u-0001", items=DEMO_ITEMS,
                            care_plan=DEMO_CARE_PLAN, status="pending_pharmacy", urgent=False, active=False,
                            version=1, checks=[c.as_dict() for c in checks],
                            override_reason="Suspected pneumonia; the patient only remembers a mild rash as a child",
                            created_at=min(now - timedelta(minutes=25), local_to_utc(today_local(), "00:00") - timedelta(minutes=1))))
    db.flush()


if __name__ == "__main__":
    check_secrets(get_settings())
    with SessionLocal() as s:
        created = seed(s)
        n = seed_radiographs(s)
        s.commit()
    print("seeded" if created else "already seeded, nothing to do")
    print(f"demo radiographs: {n} added")


# drug id -> seed quantity (others: max(2 x min_stock, 50)). Paracetamol 500 sits exactly at min_stock, so the 20:00
# Cardiology round tips it under (the demo's low-stock alert); enoxaparin starts under min_stock.
SEED_QTY = {"d-0001": 200, "d-0014": 6}


def _seed_lot(db: Session, drug_id: str, number: str, expiry: date, qty: int) -> None:
    lot = StockLot(id=new_id(db, "lot"), drug_id=drug_id, lot_number=number, expiry_date=expiry, quantity=qty)
    db.add(lot)
    db.flush()
    db.add(StockMovement(id=new_id(db, "sm"), drug_id=drug_id, lot_id=lot.id, delta=qty, reason="receipt",
                         by_user_id=PHARMACIST_ID))


def _stock(db: Session) -> None:
    """Phase B demo stock (spec 7). Skipped once any lot exists, or without the seed pharmacist."""
    if db.scalar(select(StockLot.id).limit(1)) is not None or db.get(User, PHARMACIST_ID) is None:
        return
    today = today_local()
    for d in db.scalars(select(Drug).order_by(Drug.id)):
        _seed_lot(db, d.id, f"L{d.id[2:]}-A", today + timedelta(days=365), SEED_QTY.get(d.id, max(2 * d.min_stock, 50)))
    _seed_lot(db, "d-0032", "L0032-B", today + timedelta(days=10), 30)  # amlodipine, expiring: FEFO takes it first
    _seed_lot(db, "d-0018", "L0018-X", today - timedelta(days=5), 20)  # ibuprofen, expired: waiting for write-off
    db.flush()
