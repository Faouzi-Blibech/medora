def login(client, email: str) -> dict:
    r = client.post("/auth/login", json={"email": email, "password": "ward1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_user(db, email: str, *, role: str | None = "nurse", status: str = "active", name: str = "Test User",
              ward: str | None = None, supervisor_id: str | None = None, requested_doctor_id: str | None = None,
              password: str = "ward1234"):
    from app.auth.security import hash_password
    from app.ids import new_id
    from app.models import Staff, User

    u = User(id=new_id(db, "u"), email=email, name=name, role=role, status=status,
             password_hash=hash_password(password), requested_doctor_id=requested_doctor_id)
    db.add(u)
    db.flush()
    if role in ("doctor", "nurse") or ward or supervisor_id:
        db.add(Staff(user_id=u.id, ward=ward, supervisor_id=supervisor_id))
        db.flush()
    return u


def make_patient(db, *, attending: str | None = None, ward: str = "Cardiology", first: str = "Test",
                 last: str = "Patient"):
    from app.ids import new_id
    from app.models import Patient

    p = Patient(id=new_id(db, "p"), first_name=first, last_name=last, ward=ward, attending_doctor_id=attending,
                allergies=[], history="")
    db.add(p)
    db.flush()
    return p


def pharmacist(client, db, email: str = "ph.t@medora.tn", name: str = "Pharm Test") -> dict:
    """An active pharmacist account (no staff row) and its auth headers."""
    make_user(db, email, role="pharmacist", name=name)
    return login(client, email)


def make_drug(db, *, dci: str = "Testamycin", strength: str = "100 mg", min_stock: int = 5, **kw):
    """A formulary drug that no seed lot or seed prescription uses (Phase B tests own their stock)."""
    from app.ids import new_id
    from app.models import Drug

    d = Drug(id=new_id(db, "d"), dci=dci, brand_names=[], form="tablet", strength=strength, unit_mg=100,
             max_daily_mg=10000, atc_code="", allergy_classes=[], interaction_groups=[], high_alert=False,
             min_stock=min_stock, active=True, **kw)
    db.add(d)
    db.flush()
    return d


def make_lot(db, drug, number: str, days: int, qty: int):
    """A lot expiring `days` from today (negative = already expired), written directly (no movement)."""
    from datetime import timedelta

    from app.ids import new_id
    from app.models import StockLot
    from app.services.schedule import today_local

    lot = StockLot(id=new_id(db, "lot"), drug_id=drug.id, lot_number=number,
                   expiry_date=today_local() + timedelta(days=days), quantity=qty)
    db.add(lot)
    db.flush()
    return lot
