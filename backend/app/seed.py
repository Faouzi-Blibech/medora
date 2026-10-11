"""Synthetic demo dataset (data-model.md → "Seed data"). Idempotent: exits early if doctor@ward.tn exists.

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
    ExamOrder,
    Patient,
    Prescription,
    Staff,
    User,
    Vital,
)
from app.services import exams as E
from app.services.appointments import new_appointment_fields
from app.services.schedule import local_to_utc, rebuild_doses, today_local

# (id, email, name, role, ward, rfid)
STAFF = [
    ("u-0001", "doctor@ward.tn", "Dr Trabelsi", "doctor", "Cardiology", None),
    ("u-0002", "nurse@ward.tn", "Nurse Ines", "nurse", "Cardiology", "04A1B2C3"),
    ("u-0003", "nurse2@ward.tn", "Nurse Sami", "nurse", "Internal Medicine", None),
    ("u-0004", "admin@ward.tn", "Hela Mejri", "admin", None, None),
    ("u-0006", "imaging@ward.tn", "Nurse Rania", "nurse", "Imaging", None),
    ("u-0007", "lab@ward.tn", "Nurse Karim", "nurse", "Laboratory", None),
]

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
        if role != "admin" and db.get(Staff, uid) is None and db.get(User, uid) is not None:
            db.add(Staff(user_id=uid, ward=ward, rfid_uid=rfid))
    db.flush()
    reserve_upto(db, "u", 7)


def seed(db: Session) -> bool:
    """Create the dataset in `db` (caller commits). Returns False if it was already seeded."""
    pw = hash_password(get_settings().seed_password)
    if db.scalar(select(User).where(User.email == "doctor@ward.tn")):
        _upsert_missing_staff(db, pw)
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
        if role != "admin":
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
    for prefix, n in [("u", 7), ("p", len(PATIENTS)), ("adm", 1), ("rx", 1), ("a", len(REQUESTS))]:
        reserve_upto(db, prefix, n)
    return True


if __name__ == "__main__":
    check_secrets(get_settings())
    with SessionLocal() as s:
        created = seed(s)
        n = seed_radiographs(s)
        s.commit()
    print("seeded" if created else "already seeded, nothing to do")
    print(f"demo radiographs: {n} added")
