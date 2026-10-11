from sqlalchemy import select

from app.ids import new_id
from app.models import Admission, Appointment, Patient, Prescription, Staff, User, Vital
from app.seed import seed


def test_seed_matches_contract(db):
    seed(db)
    users = {u.email: u for u in db.scalars(select(User))}
    assert users["doctor@ward.tn"].id == "u-0001" and users["doctor@ward.tn"].role == "doctor"
    assert users["patient@ward.tn"].patient_id == "p-0001"
    assert db.get(Staff, "u-0002").rfid_uid == "04A1B2C3"
    assert db.query(Patient).count() == 12
    cardio = db.scalars(select(Patient).where(Patient.ward == "Cardiology")).all()
    assert {p.id for p in cardio} == {f"p-000{i}" for i in range(1, 7)}
    assert all(p.attending_doctor_id == "u-0001" for p in cardio)
    active = {a.patient_id: a for a in db.scalars(select(Admission).where(Admission.discharged_at.is_(None)))}
    assert set(active) == {"p-0001", "p-0005"}
    adm = active["p-0001"]
    assert (adm.patient_id, adm.device_id, adm.bed) == ("p-0001", "bsu-001", "C-12")
    assert db.query(Vital).filter_by(patient_id="p-0001").count() == 48 * 4
    assert db.query(Prescription).filter_by(patient_id="p-0001", active=True).count() == 1
    appts = db.scalars(select(Appointment)).all()
    assert len(appts) == 10 and len({a.urgency_ai for a in appts}) >= 3
    assert all(a.ai_suggested["source"] in ("model", "rules") for a in appts)


def test_seed_is_idempotent(db):
    seed(db)
    seed(db)
    assert db.query(Patient).count() == 12


def test_seed_advances_sequences(db):
    seed(db)
    assert int(new_id(db, "p")[2:]) > 12


def test_seed_generates_doses(db):
    from app.models import MedDose

    seed(db)
    # rx-0001: Amlodipine 08:00 × 5 days + Paracetamol 08:00/20:00 × 5 days
    assert db.query(MedDose).filter_by(prescription_id="rx-0001").count() == 15


def test_seed_after_device_auto_registered(db):
    # the worker can register bsu-001 from its retained `status` before anyone runs the seed
    from app.iot import ingest
    from app.models import Device

    ingest.handle(db, "bsu-001", "status", {"online": True, "fw_version": "0.2.0"})
    seed(db)
    assert db.get(Device, "bsu-001").fw_version == "0.2.0"
    assert db.query(Admission).filter_by(device_id="bsu-001").count() == 1


def test_seed_password_comes_from_settings(db, monkeypatch):
    from app.auth.security import verify_password
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "seed_password", "not-the-default")
    seed(db)
    doctor = db.query(User).filter_by(email="doctor@ward.tn").one()
    assert verify_password("not-the-default", doctor.password_hash)


def test_seed_vitals_normal_and_varied(db):
    from statistics import pstdev

    seed(db)
    rows = db.query(Vital).filter_by(patient_id="p-0001").all()
    assert all(65 <= v.hr <= 90 and 96 <= v.spo2 <= 99 and 36.5 <= v.temp <= 37.4 for v in rows)
    assert pstdev([v.hr for v in rows]) > 3  # a real baseline for the trend z-score


def test_seed_department_nurses(seeded):
    from app.models import Staff, User

    assert seeded.get(User, "u-0006").email == "imaging@ward.tn" and seeded.get(Staff, "u-0006").ward == "Imaging"
    assert seeded.get(User, "u-0007").email == "lab@ward.tn" and seeded.get(Staff, "u-0007").ward == "Laboratory"


def test_seed_adds_missing_staff_on_an_already_seeded_db(db):
    seed(db)
    for uid in ("u-0006", "u-0007"):
        db.delete(db.get(Staff, uid))
    db.flush()
    for uid in ("u-0006", "u-0007"):
        db.delete(db.get(User, uid))
    db.flush()
    assert seed(db) is False
    assert db.get(User, "u-0006").email == "imaging@ward.tn" and db.get(Staff, "u-0006").ward == "Imaging"
    assert db.get(User, "u-0007").email == "lab@ward.tn" and db.get(Staff, "u-0007").ward == "Laboratory"


def test_seed_suggests_exams_for_seeded_requests(db):
    from app.models import ExamOrder

    seed(db)
    codes = {o.code for o in db.query(ExamOrder).filter_by(appointment_id="a-0001", status="suggested")}
    assert {"ecg", "troponin", "chest_xray"} <= codes


def test_seed_second_patient_account(db):
    from app.models import MedDose

    seed(db)
    u = db.query(User).filter_by(email="patient2@ward.tn").one()
    assert (u.id, u.role, u.patient_id) == ("u-0009", "patient", "p-0005")
    adm = db.scalars(select(Admission).where(Admission.patient_id == "p-0005",
                                             Admission.discharged_at.is_(None))).one()
    assert (adm.device_id, adm.bed) == (None, "C-08")
    assert db.query(Vital).filter_by(patient_id="p-0005").count() == 24 * 2
    rx = db.query(Prescription).filter_by(patient_id="p-0005", active=True).one()
    # Metformin 08:00/20:00 × 5 days + Bisoprolol 08:00 × 5 days, given by hand (no slot)
    assert db.query(MedDose).filter_by(prescription_id=rx.id).count() == 15


def test_seed_adds_second_patient_on_an_already_seeded_db(db):
    seed(db)
    u = db.query(User).filter_by(email="patient2@ward.tn").one()
    db.delete(u)
    db.flush()
    assert seed(db) is False
    assert db.query(User).filter_by(email="patient2@ward.tn").one().patient_id == "p-0005"
    assert db.query(Prescription).filter_by(patient_id="p-0005", active=True).count() == 1
