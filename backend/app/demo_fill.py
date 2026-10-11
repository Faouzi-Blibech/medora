"""OPT-IN live-demo data: a full ward so no page opens empty. Synthetic only.

    python -m app.demo_fill            # add patients, beds, vitals up to now, doses, alerts, notes, exams (idempotent)
    python -m app.demo_fill            # run again just before the demo: tops the vitals up to now
    python -m app.demo_fill --reset    # remove only what this script created

Marked rows: ids `p-d01`, `adm-d01`, `rx-d01`, `al-d01`, `n-d001`, `ex-d001`, `er-d001`; vitals use device ids `demo-<bed>`;
bedside units bsu-002..bsu-004 have fw_version `demo`.
"""

import argparse
import math
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.early_warning import score_news2
from app.models import (Admission, Alert, Device, ExamOrder, ExamResult, MedDose, Note, Patient, Prescription,
                        PrescriptionReview, Vital)
from app.services import storage
from app.services.pharmacy import workflow as W
from app.services.pharmacy.backfill import backfill_drug_ids
from app.services.schedule import local_to_utc, rebuild_doses, today_local

DOCTOR, PHARMACIST = "u-0001", "u-0008"
NURSE = {"Cardiology": "u-0002", "Internal Medicine": "u-0003"}
# new patients: (id, first, last, dob, sex, allergies, history, ward)
NEW = [
    ("p-d01", "Rafik", "Chaabane", date(1949, 2, 11), "M", ["iodine"], "Unstable angina", "Cardiology"),
    ("p-d02", "Sonia", "Ferchichi", date(1968, 6, 4), "F", [], "Hypertensive crisis", "Cardiology"),
    ("p-d03", "Anis", "Belhaj", date(2001, 9, 19), "M", [], "Syncope, under evaluation", "Cardiology"),
    ("p-d04", "Nour", "Hamdi", date(1990, 1, 27), "F", [], "Acute asthma attack", "Internal Medicine"),
    ("p-d05", "Walid", "Dridi", date(1975, 3, 15), "M", [], "Diabetic foot infection", "Internal Medicine"),
    ("p-d06", "Leila", "Mansouri", date(1956, 11, 2), "F", ["penicillin"], "Pneumonia", "Internal Medicine"),
]
# beds: (patient, bed, device or None, profile, meds)
BEDS = [
    ("p-0002", "C-03", "bsu-002", "high", [("Furosemide 40mg", ["08:00"]), ("Bisoprolol 5mg", ["08:00"])]),
    ("p-0003", "C-05", "bsu-003", "normal", [("Bisoprolol 5mg", ["08:00"])]),
    ("p-0004", "C-10", None, "low", [("Warfarin 5mg", ["20:00"]), ("Digoxin 0.25mg", ["08:00"])]),
    ("p-0006", "C-15", "bsu-004", "normal", [("Aspirin 100mg", ["08:00"]), ("Atorvastatin 20mg", ["20:00"])]),
    ("p-d01", "C-02", None, "medium", [("Aspirin 100mg", ["08:00"]), ("Enoxaparin 4000 IU", ["20:00"])]),
    ("p-d02", "C-07", None, "low", [("Amlodipine 5mg", ["08:00"]), ("Ramipril 5mg", ["08:00"])]),
    ("p-d03", "C-14", None, "normal", [("Paracetamol 500mg", ["08:00", "20:00"])]),
    ("p-0007", "M-01", None, "medium", [("Ceftriaxone 1g", ["08:00"]), ("Paracetamol 500mg", ["08:00", "14:00", "20:00"])]),
    ("p-0008", "M-03", None, "high", [("Prednisolone 20mg", ["08:00"]), ("Salbutamol 100µg", ["08:00", "14:00", "20:00"])]),
    ("p-0009", "M-04", None, "normal", [("Ondansetron 8mg", ["08:00", "20:00"])]),
    ("p-0010", "M-06", None, "normal", [("Furosemide 40mg", ["08:00"])]),
    ("p-d04", "M-02", None, "low", [("Salbutamol 100µg", ["08:00", "14:00", "20:00"])]),
    ("p-d05", "M-05", None, "low", [("Metformin 850mg", ["08:00", "20:00"]), ("Ciprofloxacin 500mg", ["08:00", "20:00"])]),
    ("p-d06", "M-08", None, "medium", [("Azithromycin 250mg", ["08:00"]), ("Paracetamol 500mg", ["08:00", "20:00"])]),
]
TOPUP = [("p-0001", "C-12"), ("p-0005", "C-08")]  # the seed's two admitted patients: vitals up to now
PROFILE = {"normal": (78, 97, 36.9), "low": (100, 95, 37.7), "medium": (112, 93, 38.3), "high": (124, 90, 38.8)}
NOTES = ["Patient comfortable, family visited.", "Pain 3/10 after paracetamol.", "Ate half of lunch, mobilised to the chair.",
         "IV line checked, site clean.", "Asked to call if chest pain comes back."]
# exams: (patient, code, label, department, status, report text for done ones)
EXAMS = [
    ("p-0002", "echo", "Echocardiography", "Cardiology", "ordered", None),
    ("p-d01", "ecg", "ECG (12-lead)", "Cardiology", "ordered", None),
    ("p-d03", "ecg", "ECG (12-lead)", "Cardiology", "ordered", None),
    ("p-d02", "echo", "Echocardiography", "Cardiology", "ordered", None),
    ("p-d01", "troponin", "Troponin", "Laboratory", "ordered", None),
    ("p-0004", "inr", "INR", "Laboratory", "ordered", None),
    ("p-0007", "cbc", "Complete blood count", "Laboratory", "ordered", None),
    ("p-0007", "crp", "CRP", "Laboratory", "ordered", None),
    ("p-d05", "hba1c", "HbA1c", "Laboratory", "ordered", None),
    ("p-d06", "cbc", "Complete blood count", "Laboratory", "ordered", None),
    ("p-0010", "creatinine", "Creatinine", "Laboratory", "ordered", None),
    ("p-d06", "chest_xray", "Chest X-ray", "Imaging", "ordered", None),
    ("p-0008", "chest_xray", "Chest X-ray", "Imaging", "ordered", None),
    ("p-d05", "leg_doppler", "Leg venous Doppler", "Imaging", "ordered", None),
    ("p-d03", "brain_ct", "Brain CT scan", "Imaging", "ordered", None),
    ("p-0002", "creatinine", "Creatinine", "Laboratory", "done", "Creatinine 128 umol/L (ref 60-110), slightly high. Potassium 4.6 mmol/L."),
    ("p-d01", "ecg", "ECG (12-lead)", "Cardiology", "done", "Sinus rhythm 96/min. ST depression 1 mm in V4-V6. No ST elevation."),
    ("p-0004", "cbc", "Complete blood count", "Laboratory", "done", "Hb 12.9 g/dL, WBC 7.1 G/L, platelets 231 G/L. Within normal limits."),
    ("p-0007", "troponin", "Troponin", "Laboratory", "done", "High-sensitivity troponin 9 ng/L (ref < 14). Negative."),
    ("p-d05", "crp", "CRP", "Laboratory", "done", "CRP 86 mg/L (ref < 5), raised."),
]


def _vital(profile: str, k: int, late: bool) -> tuple[int, int, float]:
    hr, spo2, temp = PROFILE["normal" if (profile == "high" and not late) else profile]
    return hr + round(5 * math.sin(k / 3)) + k % 3 - 1, min(100, spo2 + (k % 3) - 1), round(temp + 0.2 * math.sin(k / 5), 1)


def _vitals(db: Session, pid: str, bed: str, profile: str, device: str | None, ward: str, now: datetime) -> int:
    start = (now - timedelta(hours=24)).replace(second=0, microsecond=0)
    start -= timedelta(minutes=start.minute % 30)
    dev = f"demo-{bed}"
    have = set(db.scalars(select(Vital.ts).where(Vital.device_id == dev, Vital.ts >= start)))
    n, k = 0, 0
    while (ts := start + timedelta(minutes=30 * k)) <= now:
        if ts not in have:
            hr, spo2, temp = _vital(profile, k, ts > now - timedelta(hours=6))
            db.add(Vital(ts=ts, device_id=dev, patient_id=pid, hr=hr, spo2=spo2, temp=temp,
                         news2=score_news2(hr, spo2, temp).score, source="simulator" if device else "manual",
                         nurse_id=None if device else NURSE[ward]))
            n += 1
        k += 1
    return n


def fill(db: Session) -> None:
    now = datetime.now(UTC)
    for pid, first, last, dob, sex, allergies, history, ward in NEW:
        if db.get(Patient, pid) is None:
            db.add(Patient(id=pid, first_name=first, last_name=last, date_of_birth=dob, sex=sex, allergies=allergies,
                           history=history, ward=ward, attending_doctor_id=DOCTOR if ward == "Cardiology" else None,
                           phone=None, email=None))
    db.flush()
    vit = 0
    for i, (pid, bed, device, profile, meds) in enumerate(BEDS, start=1):
        p = db.get(Patient, pid)
        if device and db.get(Device, device) is None:
            db.add(Device(id=device, fw_version="demo", online=True, last_seen=now))
            db.flush()
        if db.get(Admission, f"adm-d{i:02d}") is None:
            if p.ward == "Cardiology" and p.attending_doctor_id is None:
                p.attending_doctor_id = DOCTOR
            db.add(Admission(id=f"adm-d{i:02d}", patient_id=pid, device_id=device, bed=bed,
                             admitted_at=now - timedelta(days=1 + i % 3)))
            db.flush()
            created = local_to_utc(today_local() - timedelta(days=1), "00:00")
            rx = Prescription(id=f"rx-d{i:02d}", patient_id=pid, doctor_id=DOCTOR, created_at=created, active=True,
                              status="validated", reviewed_by=PHARMACIST, reviewed_at=created,
                              care_plan=f"{p.history}: monitor vitals every 4 h",
                              items=[{"med": m, "times": t, "slot": None, "days": 5} for m, t in meds])
            db.add(rx)
            db.flush()
            db.add(PrescriptionReview(id=f"pr-d{i:02d}", prescription_id=rx.id, pharmacist_id=PHARMACIST,
                                      decision="validated", comment=None, checks_snapshot=[]))
            for j, d in enumerate(rebuild_doses(db, rx)):
                if d.scheduled_at < now - timedelta(minutes=30):
                    d.status = "missed" if (profile == "high" and j == 1) else "taken"
            for n in range(2):
                db.add(Note(id=f"n-d{i:02d}{n}", patient_id=pid, author_id=NURSE[p.ward],
                            text=NOTES[(i + n) % len(NOTES)], created_at=now - timedelta(hours=2 + 5 * n)))
        vit += _vitals(db, pid, bed, profile, device, p.ward, now)
    for pid, bed in TOPUP:
        if db.get(Patient, pid) is not None:
            vit += _vitals(db, pid, bed, "normal", None, "Cardiology", now)
    db.flush()

    alerts = [("p-0002", "news2", "high", 7, "NEWS2 7: SpO2 90 %, HR 124, temp 38.8 °C"),
              ("p-0008", "news2", "high", 8, "NEWS2 8: SpO2 89 %, HR 125, temp 38.9 °C"),
              ("p-d01", "news2", "medium", 5, "NEWS2 5: HR 113, temp 38.3 °C"),
              ("p-0007", "trend", "medium", None, "Temperature rising over the last 6 hours"),
              ("p-0002", "dose_missed", "medium", None, "Furosemide 40mg (08:00) not marked taken")]
    for n, (pid, kind, sev, score, msg) in enumerate(alerts, start=1):
        if db.get(Alert, f"al-d{n:02d}") is None:
            db.add(Alert(id=f"al-d{n:02d}", patient_id=pid, kind=kind, severity=sev, news2=score, message=msg,
                         ai_suggested={"source": "rules", "score": score} if score else {"source": "rules"},
                         created_at=now - timedelta(minutes=8 * n)))

    for n, (pid, code, label, dept, status, report) in enumerate(EXAMS, start=1):
        oid = f"ex-d{n:03d}"
        if db.get(ExamOrder, oid) is not None:
            continue
        db.add(ExamOrder(id=oid, patient_id=pid, code=code, label=label, department=dept, status=status,
                         human_confirmed_by=DOCTOR, ordered_at=now - timedelta(hours=3 + n % 5),
                         done_at=now - timedelta(hours=1) if status == "done" else None))
        db.flush()
        if report:
            rid, data = f"er-d{n:03d}", report.encode()
            key = f"exams/{oid}/{rid}/{code}.txt"
            storage.put(key, data, "text/plain")
            db.add(ExamResult(id=rid, exam_order_id=oid, patient_id=pid, uploaded_by="u-0007" if dept == "Laboratory" else "u-0002",
                              file_key=key, file_name=f"{code}.txt", content_type="text/plain", size_bytes=len(data),
                              report_text=report))

    # two prescriptions waiting for the pharmacist
    for n, (pid, items) in enumerate([("p-d06", [{"med": "Amoxicillin 1 g", "times": ["08:00", "20:00"], "slot": None, "days": 7}]),
                                       ("p-d01", [{"med": "Clopidogrel 75mg", "times": ["08:00"], "slot": None, "days": 30}])], start=1):
        if db.get(Prescription, f"rx-dp{n}") is None:
            checks = W.checks_for(db, db.get(Patient, pid), items, set())
            db.add(Prescription(id=f"rx-dp{n}", patient_id=pid, doctor_id=DOCTOR, items=items, status="pending_pharmacy",
                                active=False, version=1, checks=[c.as_dict() for c in checks],
                                care_plan="New treatment, waiting for pharmacy review",
                                override_reason="Benefit outweighs the risk; patient monitored" if any(c.severity == "critical" for c in checks) else None,
                                created_at=now - timedelta(minutes=20 * n)))
    db.flush()
    backfill_drug_ids(db)
    print(f"demo data ready: {len(BEDS) + len(TOPUP)} beds, {vit} new vitals")


def reset(db: Session) -> None:
    rx = select(Prescription.id).where(Prescription.id.like("rx-d%"))
    for stmt in (delete(MedDose).where(MedDose.prescription_id.in_(rx)),
                 delete(PrescriptionReview).where(PrescriptionReview.id.like("pr-d%")),
                 delete(Prescription).where(Prescription.id.like("rx-d%")),
                 delete(ExamResult).where(ExamResult.id.like("er-d%")), delete(ExamOrder).where(ExamOrder.id.like("ex-d%")),
                 delete(Alert).where(Alert.id.like("al-d%")), delete(Note).where(Note.id.like("n-d%")),
                 delete(Vital).where(Vital.device_id.like("demo-%")), delete(Admission).where(Admission.id.like("adm-d%")),
                 delete(Device).where(Device.fw_version == "demo"), delete(Patient).where(Patient.id.like("p-d%"))):
        db.execute(stmt)
    print("demo data removed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    from app.db import SessionLocal

    with SessionLocal() as s:
        reset(s) if args.reset else fill(s)
        s.commit()
