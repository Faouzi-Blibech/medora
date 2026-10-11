# Wali (HW-B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core backend that every other lane depends on: schema, auth/RBAC/audit, MQTT ingestion, schedule push, early warning, alerts, WebSocket and the n8n emitter.

**Architecture:**
- FastAPI (sync SQLAlchemy 2.0) in `backend/`, with the same image running two processes: `api` (uvicorn) and `worker` (`python -m app.iot.worker`).
- The worker ingests MQTT into PostgreSQL/TimescaleDB, runs early warning, and relays live frames to the API through the internal MQTT topic `ward/internal/ws`. The API fans those frames out to WebSocket clients.
- Business logic lives in `app/services/`; routers stay thin.

**Tech stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, psycopg 3, PyJWT, bcrypt, paho-mqtt 2, httpx, pytest · Mosquitto 2 · TimescaleDB pg16 · (stretch) real-board wiring: ESP32 + SSD1306 OLED + SG90 servo + DS1307.

**Spec:** `docs/superpowers/specs/2026-10-05-ward-foundation-design.md` · read also `CLAUDE.md`, `docs/architecture.md` and **all** of `docs/contracts/`.

**You are:** Wali, hardware person, HW-B, **Nurse role owner** (the nurse flow must work end-to-end in the demo: simulated badge tap → vitals → alert → ack; the bedside unit has no sensors or RFID, so `simulator/` drives this). Hedi may swap lanes with you; see `CLAUDE.md`.

## Global Constraints

- Contracts are frozen at v1.0 (`docs/contracts/*`). Any change needs a version bump, an announcement, and a 👍 from the other side.
- You own `backend/` except `backend/app/routers/{appointments,ai,integrations}.py` and `backend/app/ai/` (Faouzi's), but you **do** own `backend/app/ai/early_warning.py`. `backend/app/ai/no_show/` is Hedi's. You also own `infra/` and `hardware/`, and co-own `firmware/PINMAP.md`.
- IDs are prefixed text: `u-0001`, `p-0001`, `a-0001`, `rx-0001`, `d-000001`, `al-0001`, `doc-0001`, `adm-0001`, `n-0001`, `bsu-001`.
- MQTT `ts` = epoch seconds UTC. REST = ISO-8601 UTC. Doses use `HH:MM` Africa/Tunis (UTC+1, no DST).
- Every read of a patient record writes `audit_log`. Every AI output row has `ai_suggested` + a confirmer column.
- Seed password for every account: `ward1234`. Synthetic data only.
- No AI attribution in commits/PRs. Branches: `wali/<feature>`. Conventional Commits.
- `main` must always start with `docker compose -f infra/docker-compose.yml up --build`.

## Review Focus

1. **Offline replay duplicates:** the device re-sends buffered messages after reconnect. The same `(device_id, msg_id)` must be stored exactly once (Task 4 test `test_duplicate_msg_id_ignored`).
2. **Vitals with `null` fields** (no finger on the sensor): ingestion must store them and NEWS2 must score only the present parameters, never crash (Task 6 test `test_news2_ignores_missing`).
3. **Vitals for a device with no active admission** (`patient_id: null`): store with `patient_id NULL`, raise no alert, never 500 (Task 4 test `test_vitals_without_patient`).
4. **Unknown RFID UID in `nurse_rfid`:** store the vital with `nurse_id NULL` and log a warning; don't drop it (Task 4 test `test_unknown_rfid_kept`).
5. **Patient role reading another patient** (`GET /patients/p-0002` with p-0001's token) must 403, and a nurse from another ward must 403 (Task 3 test `test_patient_cannot_read_other`).

---

## Interfaces you PROVIDE (others code against these — keep the names exact)

```python
# app/db.py (exists)
Base; SessionLocal; get_db() -> Iterator[Session]

# app/ids.py
def new_id(db: Session, prefix: str, width: int = 4) -> str          # "p" -> "p-0013"

# app/models/*.py — one class per table in docs/contracts/data-model.md
User, Staff, Patient, Device, Admission, Appointment, Prescription, MedDose, Vital,
IngestedMessage, Alert, Note, Document, AiSummary, AuditLog

# app/auth/deps.py
def get_current_user(token=Depends(oauth2_scheme), db=Depends(get_db)) -> User
def require_roles(*roles: str) -> Callable                           # Depends(require_roles("doctor","admin"))
def check_patient_access(db: Session, user: User, patient_id: str, write: bool = False) -> Patient
    # raises 403/404; writes audit_log(action="read"|"update") — call it in every /patients/{id}* route

# app/auth/security.py
def hash_password(p: str) -> str; def verify_password(p: str, h: str) -> bool
def create_token(user: User) -> str

# app/services/audit.py
def audit(db: Session, user: User | None, action: str, resource: str, resource_id: str,
          patient_id: str | None = None, ip: str = "") -> None

# app/integrations/n8n.py
def emit(event: str, data: dict) -> None                             # fire-and-forget, never raises

# app/iot/publisher.py
def publish_schedule(device_id: str, payload: dict) -> None          # retained, QoS1
def publish_command(device_id: str, payload: dict) -> None
def publish_ws_frame(frame: dict) -> None                            # ward/internal/ws

# app/services/schedule.py
def rebuild_doses(db: Session, prescription: Prescription) -> list[MedDose]
def build_schedule_payload(db: Session, patient_id: str | None) -> dict  # MQTT schedule shape
def push_schedule(db: Session, patient_id: str) -> bool             # True if a device received it

# app/ai/early_warning.py
@dataclass News2Result: score: int; severity: str; parts: dict[str, int]
def score_news2(hr: int | None, spo2: int | None, temp: float | None) -> News2Result
def trend_z(history: list[float], value: float) -> float | None

# app/ws/hub.py
hub.broadcast(frame: dict) -> None    # frame = {"type","data","scope":{patient_id,ward,doctor_id}}
```

## Interfaces you CONSUME

- **Hedi:** device and simulator MQTT traffic per `mqtt-topics.md`. Until the device works, use `simulator/sim.py` (Hedi extends it on Day 0–1 with events and scenarios).
- **Faouzi:** nothing blocking. He builds `routers/appointments.py`, `routers/ai.py` and `routers/integrations.py` on your models and deps. Include his routers in `main.py` when he asks; he sends a one-line PR.

## Mocks to use until the real thing is ready

| You need | Until | Use |
|---|---|---|
| Device traffic | Day 3 | `python simulator/sim.py --device bsu-001` (+ `--scenario abnormal` once Hedi adds it) |
| n8n | Day 1 | `emit()` logs to stdout when `N8N_WEBHOOK_URL` is unreachable; test it with `nc -l 5678` or webhook.site |
| Web client for WS | Day 1 | `python -m websockets "ws://localhost:8000/ws?token=..."` (`pip install websockets`) |

---

## Day 0 — Mon 10-05 (afternoon)

### Task 0: Inventory, stack up, branch

- [ ] Review the reduced BOM in `hardware/README.md` (ESP32 + OLED + servo + DS1307; only needed if the real board is built).
- [ ] Review and 👍 the MQTT contract v1.1 (`msg_id` per publisher; ESP + simulator on the same `device_id`). The dedupe on `(device_id, msg_id)` is unchanged.
- [ ] `cp .env.example .env && docker compose -f infra/docker-compose.yml --env-file .env up --build`. Check `curl localhost:8000/health` → `{"status":"ok","db":true,"mqtt":true}`.
- [ ] `docker compose -f infra/docker-compose.yml exec mqtt mosquitto_sub -t 'hospital/#' -v` while Hedi runs the simulator: messages appear.
- [ ] `git checkout -b wali/schema`

**Done when:** the stack is green on your laptop and contract v1.1 is acked.

---

## Day 1 — Tue 10-06

### Task 1: (moved) Real-board wiring

The bedside unit is now ESP32 + SSD1306 OLED + SG90 servo + DS1307, developed by Hedi in Wokwi. Real-board wiring
is a **Day 3 stretch** (see Task 8). Nothing to wire on Day 1; start Task 2.

### Task 2: Schema, migration, IDs, seed

**Files:**
- Create: `backend/app/models/{__init__,user,patient,device,clinical,ai,audit}.py`, `backend/app/ids.py`, `backend/app/seed.py`, `backend/alembic/versions/0001_initial.py`
- Test: `backend/tests/conftest.py`, `backend/tests/test_ids.py`

**Interfaces:** Produces the models listed above, `new_id`, and `python -m app.seed`.

- [ ] **Step 1: Test DB fixture.** Tests run against a real Postgres (the compose `db` service) in a throwaway schema per session:

```python
# backend/tests/conftest.py
import os, uuid, pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.db import Base
import app.models  # noqa: F401

DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://ward:ward@localhost:5432/ward")

@pytest.fixture(scope="session")
def engine():
    schema = f"test_{uuid.uuid4().hex[:8]}"
    eng = create_engine(DB_URL, connect_args={"options": f"-csearch_path={schema},public"})
    with eng.begin() as c:
        c.execute(text(f"CREATE SCHEMA {schema}"))
    Base.metadata.create_all(eng)
    yield eng
    with eng.begin() as c:
        c.execute(text(f"DROP SCHEMA {schema} CASCADE"))

@pytest.fixture()
def db(engine):
    conn = engine.connect(); tx = conn.begin()
    s = sessionmaker(bind=conn, join_transaction_mode="create_savepoint")()
    yield s
    s.close(); tx.rollback(); conn.close()
```

- [ ] **Step 2: Failing test for IDs**

```python
# backend/tests/test_ids.py
from app.ids import new_id

def test_new_id_is_prefixed_and_increments(db):
    a, b = new_id(db, "p"), new_id(db, "p")
    assert a.startswith("p-") and len(a) == 6
    assert int(b[2:]) == int(a[2:]) + 1

def test_dose_ids_are_wider(db):
    assert len(new_id(db, "d", width=6)) == 8
```

Run: `pytest tests/test_ids.py -v`, expected FAIL (`ModuleNotFoundError: app.ids`).

- [ ] **Step 3: Implement**

```python
# backend/app/ids.py
from sqlalchemy import text
from sqlalchemy.orm import Session

def new_id(db: Session, prefix: str, width: int = 4) -> str:
    seq = f"seq_{prefix}"
    db.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq}"))
    n = db.execute(text(f"SELECT nextval('{seq}')")).scalar_one()
    return f"{prefix}-{n:0{width}d}"
```

- [ ] **Step 4: Models.** Write one SQLAlchemy 2.0 `Mapped[...]` class per table, exactly as in `docs/contracts/data-model.md` (column names, types, nullability). Example of the style:

```python
# backend/app/models/clinical.py (excerpt)
from datetime import datetime
from sqlalchemy import ForeignKey, String, Integer, Float, Text, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class Vital(Base):
    __tablename__ = "vitals"
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    device_id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str | None] = mapped_column(String, index=True)
    hr: Mapped[int | None] = mapped_column(Integer)
    spo2: Mapped[int | None] = mapped_column(Integer)
    temp: Mapped[float | None] = mapped_column(Float)
    nurse_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    news2: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String, default="device")

class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"))
    device_id: Mapped[str | None] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    news2: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    ai_suggested: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acked_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

`vitals` has a composite PK `(ts, device_id)` because a Timescale hypertable needs the time column in every unique index.

- [ ] **Step 5: Migration.** Run `alembic revision --autogenerate -m initial` (with the compose `db` up), rename the file to `0001_initial.py`, then append to `upgrade()`:

```python
op.execute("SELECT create_hypertable('vitals', 'ts', if_not_exists => TRUE)")
op.create_index("ix_vitals_patient_ts", "vitals", ["patient_id", sa.text("ts DESC")])
op.execute("CREATE UNIQUE INDEX uq_adm_active_patient ON admissions(patient_id) WHERE discharged_at IS NULL")
op.execute("CREATE UNIQUE INDEX uq_adm_active_device ON admissions(device_id) WHERE discharged_at IS NULL AND device_id IS NOT NULL")
```

Change the `api` container command to `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"` in `infra/docker-compose.yml`.

- [ ] **Step 6: Seed.** `backend/app/seed.py` creates exactly the dataset in `data-model.md` → "Seed data" and is **idempotent** (it exits early if `doctor@medora.tn` exists). Vitals: 48 h every 15 min of normal values for admitted patients (`hr` 65–90, `spo2` 96–99, `temp` 36.5–37.4, `source="manual"`). Run with `docker compose exec api python -m app.seed`.

- [ ] **Step 7:** `pytest -v` passes. Commit `feat(backend): schema, ids, seed`.

### Task 3: Auth, RBAC, audit, patients/notes endpoints

**Files:**
- Create: `backend/app/auth/{__init__,security,deps}.py`, `backend/app/services/audit.py`, `backend/app/routers/{auth,patients}.py`, `backend/app/schemas.py`
- Modify: `backend/app/main.py` (include routers)
- Test: `backend/tests/test_auth.py`, `backend/tests/test_rbac.py`

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_rbac.py
from app.models import AuditLog

# `client` and `seeded` live in tests/conftest.py (shared with Faouzi's tests):
#   @pytest.fixture()
#   def seeded(db): from app.seed import seed; seed(db); return db
#   @pytest.fixture()
#   def client(db, seeded):
#       app.dependency_overrides[get_db] = lambda: db
#       yield TestClient(app)
#       app.dependency_overrides.clear()
#
# tests/helpers.py:
#   def login(client, email):
#       r = client.post("/auth/login", json={"email": email, "password": "ward1234"})
#       assert r.status_code == 200
#       return {"Authorization": f"Bearer {r.json()['access_token']}"}

from tests.helpers import login     # tests/helpers.py — shared with Faouzi's tests

def test_patient_cannot_read_other(client):
    h = login(client, "patient@medora.tn")
    assert client.get("/patients/p-0001", headers=h).status_code == 200
    assert client.get("/patients/p-0002", headers=h).status_code == 403

def test_admin_cannot_read_clinical(client):
    h = login(client, "admin@medora.tn")
    assert client.get("/patients/p-0001/vitals", headers=h).status_code == 403

def test_read_writes_audit(client, db):
    h = login(client, "doctor@medora.tn")
    before = db.query(AuditLog).count()
    client.get("/patients/p-0001", headers=h)
    assert db.query(AuditLog).count() == before + 1
```

Add the `seeded` and `client` fixtures to `conftest.py` and `login` to `tests/helpers.py` exactly as in the comment above (refactor `seed.py` so `seed(db)` takes a session and `__main__` opens one).

- [ ] **Step 2: Implement.** `security.py` uses `bcrypt.hashpw`/`checkpw` and PyJWT HS256, with claims `{sub, role, patient_id, exp}`. `deps.py` implements `get_current_user`, `require_roles` and `check_patient_access` following the matrix in `data-model.md`:
  - doctor → `patient.attending_doctor_id == user.id`
  - nurse → `patient.ward == staff.ward`
  - patient → `user.patient_id == patient_id`
  - admin → read of the summary fields only, through `GET /patients`

  `check_patient_access` calls `audit(...)` before returning.
- [ ] **Step 3: Endpoints** from `api.md` → "Auth" and "Patients and records": `/auth/login`, `/me`, `GET/PATCH /patients...`, `/patients/{id}/vitals`, `/patients/{id}/prescriptions`, `/patients/{id}/notes` (GET/POST). Response shapes match the JSON in `api.md` field-for-field (`schemas.py` holds the Pydantic models).
- [ ] **Step 4:** `pytest -v` passes. Commit `feat(backend): jwt auth, rbac, audit, patient endpoints`. Open a PR and tell Faouzi the API is live, so he can flip `NEXT_PUBLIC_USE_MOCKS=0` for these routes.

### Task 4: MQTT ingestion worker + WS relay

**Files:**
- Create: `backend/app/iot/{ingest,publisher}.py`, `backend/app/ws/{__init__,hub,router}.py`
- Modify: `backend/app/iot/worker.py`, `backend/app/main.py`
- Test: `backend/tests/test_ingest.py`

**Design:**
- `ingest.py` holds **pure functions** taking `(db, device_id, topic_kind, payload: dict)`, so they're testable without a broker.
- `worker.py` is only the paho loop: subscribe → `json.loads` → call `ingest.handle(...)` → commit.
- After commit, the worker calls `publisher.publish_ws_frame(frame)`.
- The API process runs a paho client in a background thread (started in a FastAPI lifespan handler) that subscribes to `ward/internal/ws` and calls `hub.broadcast(frame)`.

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_ingest.py
from app.iot import ingest
from app.models import Vital, Device

V = {"msg_id": 1, "ts": 1759680000, "patient_id": "p-0001", "hr": 80, "spo2": 98, "temp": 36.9}

def _at(db, ts):
    from datetime import UTC, datetime
    return db.query(Vital).filter_by(device_id="bsu-001", ts=datetime.fromtimestamp(ts, UTC))

def test_vitals_stored_with_news2(db, seeded):
    frames = ingest.handle(db, "bsu-001", "vitals", dict(V))
    v = _at(db, V["ts"]).one()
    assert v.hr == 80 and v.news2 == 0 and v.patient_id == "p-0001"
    assert frames[0]["type"] == "vital"

def test_duplicate_msg_id_ignored(db, seeded):
    ingest.handle(db, "bsu-001", "vitals", dict(V, msg_id=77, ts=1759681111))
    frames = ingest.handle(db, "bsu-001", "vitals", dict(V, msg_id=77, ts=1759681111))
    assert frames == []
    assert _at(db, 1759681111).count() == 1

def test_vitals_without_patient(db, seeded):
    frames = ingest.handle(db, "bsu-009", "vitals", dict(V, msg_id=5, patient_id=None))
    assert frames == [] or all(f["type"] != "alert" for f in frames)

def test_unknown_rfid_kept(db, seeded):
    ingest.handle(db, "bsu-001", "vitals", dict(V, msg_id=6, ts=1759682222, nurse_rfid="DEADBEEF"))
    assert _at(db, 1759682222).one().nurse_id is None

def test_known_rfid_resolves_nurse(db, seeded):
    ingest.handle(db, "bsu-001", "vitals", dict(V, msg_id=7, ts=1759683333, nurse_rfid="04A1B2C3"))
    assert _at(db, 1759683333).one().nurse_id == "u-0002"

def test_status_updates_device(db, seeded):
    ingest.handle(db, "bsu-001", "status", {"online": False, "fw_version": "0.1.0"})
    assert db.get(Device, "bsu-001").online is False
```

- [ ] **Step 2: Implement `ingest.handle`:**
  1. If `kind != "status"`, deduplicate: `INSERT INTO ingested_messages … ON CONFLICT DO NOTHING RETURNING msg_id`. If nothing comes back, return `[]`.
  2. Upsert the `devices` row (auto-register unknown devices with `online=True`, and set `last_seen`).
  3. Dispatch on kind:
     - `vitals`: convert `ts` with `datetime.fromtimestamp(ts, UTC)`; resolve `nurse_rfid` through `Staff.rfid_uid`; compute `score_news2` (Task 6; until it lands, store `news2=None`); insert the row; build a `vital` frame.
     - `events`: see Task 7.
     - `status`: set `online`/`fw_version`; build a `device_status` frame.
  4. Return the WS frames to relay, each with a `scope` (`patient_id`, `ward`, `doctor_id` looked up from the patient).
- [ ] **Step 3: Implement the `hub`.** It's a set of `(websocket, user)` pairs. `broadcast(frame)` sends to:
  - nurses whose `staff.ward == scope.ward`
  - doctors whose `id == scope.doctor_id`
  - admins, for `device_status` frames only

  Strip `scope` before sending. `WS /ws?token=` validates the JWT and closes with code 4401 if it's invalid. Broadcasting from the MQTT thread goes through `asyncio.run_coroutine_threadsafe(..., loop)`, where `loop` is captured in the lifespan handler.
- [ ] **Step 4:** Run `pytest -v`. Then do a manual end-to-end check: stack up, simulator on, `websockets` client connected as `nurse@medora.tn`, and `vital` frames arrive every 5 s.
- [ ] **Step 5:** Commit `feat(backend): mqtt ingestion with dedupe + ws relay`.

### Task 5: n8n emitter

**Files:** Create `backend/app/integrations/n8n.py` · Test `backend/tests/test_n8n.py`

```python
# backend/app/integrations/n8n.py
import logging, threading
from datetime import UTC, datetime
import httpx
from app.config import get_settings

log = logging.getLogger("medora.n8n")

def _post(event: str, data: dict) -> None:
    s = get_settings()
    try:
        httpx.post(s.n8n_webhook_url, timeout=3.0, headers={"X-Ward-Secret": s.n8n_event_secret},
                   json={"event": event, "ts": datetime.now(UTC).isoformat(), "data": data})
    except Exception as e:  # never break the API because n8n is down
        log.warning("n8n emit %s failed: %s", event, e)

def emit(event: str, data: dict) -> None:
    threading.Thread(target=_post, args=(event, data), daemon=True).start()
```

- [ ] Test: monkeypatch `httpx.post` to raise `httpx.ConnectError` → `emit()` returns without raising (join the thread in the test through a small `_post` direct call).
- [ ] Commit `feat(backend): n8n event emitter`.

**Day 1 done when:** CP1 passes. Simulator vitals show live on Faouzi's nurse view through the real API and WS. Auth, RBAC, audit and ingestion tests are green.

---

## Day 2 — Wed 10-07

### Task 6: Early warning (NEWS2 partial + trend) and alerts

**Files:** Create `backend/app/ai/early_warning.py`, `backend/app/services/alerts.py`, `backend/app/routers/alerts.py` · Test `backend/tests/test_early_warning.py`

- [ ] **Step 1: Failing tests** (bands from `docs/architecture.md` §6; **verify them against the official RCP NEWS2 chart** and fix both the doc and the code if they differ)

```python
# backend/tests/test_early_warning.py
import pytest
from app.ai.early_warning import score_news2, trend_z

@pytest.mark.parametrize("hr,exp", [(40,3),(41,1),(50,1),(51,0),(90,0),(91,1),(110,1),(111,2),(130,2),(131,3)])
def test_hr_bands(hr, exp):
    assert score_news2(hr, 98, 37.0).parts["hr"] == exp

@pytest.mark.parametrize("spo2,exp", [(91,3),(92,2),(93,2),(94,1),(95,1),(96,0)])
def test_spo2_bands(spo2, exp):
    assert score_news2(80, spo2, 37.0).parts["spo2"] == exp

@pytest.mark.parametrize("t,exp", [(35.0,3),(35.1,1),(36.0,1),(36.1,0),(38.0,0),(38.1,1),(39.0,1),(39.1,2)])
def test_temp_bands(t, exp):
    assert score_news2(80, 98, t).parts["temp"] == exp

def test_severity():
    assert score_news2(80, 98, 37.0).severity == "none"
    assert score_news2(95, 95, 37.0).severity == "low"          # 1+1
    assert score_news2(80, 91, 37.0).severity == "high"         # single 3
    assert score_news2(131, 91, 39.1).severity == "critical"    # 3+3+2 = 8

def test_news2_ignores_missing():
    r = score_news2(None, 97, None)
    assert r.score == 0 and set(r.parts) == {"spo2"}

def test_trend():
    hist = [80, 82, 79, 81, 80, 78, 82, 81, 80, 79]
    assert trend_z(hist, 81) is not None and abs(trend_z(hist, 81)) < 1
    assert trend_z(hist, 120) > 3
    assert trend_z([80, 80], 120) is None   # fewer than 10 points → no trend
```

- [ ] **Step 2: Implement**

```python
# backend/app/ai/early_warning.py
"""NEWS2 partial score (HR, SpO2 scale 1, temperature) + rolling z-score trend.
Thresholds: verify against the official RCP NEWS2 chart before the demo. Not clinically validated."""
from dataclasses import dataclass, field
from statistics import mean, pstdev

@dataclass
class News2Result:
    score: int
    severity: str
    parts: dict[str, int] = field(default_factory=dict)

def _hr(v: int) -> int:
    if v <= 40: return 3
    if v <= 50: return 1
    if v <= 90: return 0
    if v <= 110: return 1
    if v <= 130: return 2
    return 3

def _spo2(v: int) -> int:
    if v <= 91: return 3
    if v <= 93: return 2
    if v <= 95: return 1
    return 0

def _temp(v: float) -> int:
    if v <= 35.0: return 3
    if v <= 36.0: return 1
    if v <= 38.0: return 0
    if v <= 39.0: return 1
    return 2

def score_news2(hr: int | None, spo2: int | None, temp: float | None) -> News2Result:
    parts: dict[str, int] = {}
    if hr is not None: parts["hr"] = _hr(hr)
    if spo2 is not None: parts["spo2"] = _spo2(spo2)
    if temp is not None: parts["temp"] = _temp(round(temp, 1))
    s = sum(parts.values())
    if s >= 7: sev = "critical"
    elif s >= 5 or 3 in parts.values(): sev = "high"
    elif s >= 3: sev = "medium"
    elif s >= 1: sev = "low"
    else: sev = "none"
    return News2Result(s, sev, parts)

def trend_z(history: list[float], value: float) -> float | None:
    if len(history) < 10: return None
    sd = pstdev(history)
    if sd == 0: return None
    return (value - mean(history)) / sd
```

- [ ] **Step 3: `services/alerts.py`:**
  - `create_alert(db, patient, device_id, kind, severity, news2, message, ai_suggested) -> Alert` emits `alert.critical` (payload per `n8n-webhooks.md`) when severity is `high` or `critical`, and returns an `alert` WS frame.
  - Deduplication: don't open a new `news2` alert for a patient while one with the same severity is open (unacked) and was created < 10 min ago.
  - In `ingest` for vitals: severity ≥ `medium` creates a `news2` alert. Also compute a trend alert over the patient's last 30 HR/SpO2 values (`|z| ≥ 3` → `trend`, medium).
- [ ] **Step 4: `routers/alerts.py`:** `GET /alerts?status=open` (scoped by role) and `POST /alerts/{id}/ack`. Tests: a nurse acks → `acked_by` is set; another ward's nurse → 403.
- [ ] **Step 5:** Commit `feat(backend): news2 early warning, alerts, ack`.

### Task 7: Prescriptions → doses → schedule push; device events

**Files:** Create `backend/app/services/schedule.py`, `backend/app/routers/{prescriptions,devices}.py` · Modify `backend/app/iot/ingest.py` · Test `backend/tests/test_schedule.py`

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_schedule.py
from app.services import schedule
from app.models import Prescription, MedDose

def make_rx(db):
    rx = Prescription(id="rx-9001", patient_id="p-0001", doctor_id="u-0001", active=True, care_plan="",
                      items=[{"med": "Paracetamol 500mg", "times": ["08:00", "20:00"], "slot": 1, "days": 2}])
    db.add(rx); db.flush(); return rx

def test_rebuild_doses_days_times(db, seeded):
    doses = schedule.rebuild_doses(db, make_rx(db))
    assert len(doses) == 4 and {d.time_of_day for d in doses} == {"08:00", "20:00"}

def test_payload_shape(db, seeded):
    make_rx(db); schedule.rebuild_doses(db, db.get(Prescription, "rx-9001"))
    p = schedule.build_schedule_payload(db, "p-0001")
    assert p["patient_id"] == "p-0001" and p["patient_first_name"]
    assert all({"dose_id", "time", "meds", "slot"} <= set(d) for d in p["doses"])
    assert len(p["doses"]) <= 8

def test_unassigned_payload(db):
    p = schedule.build_schedule_payload(db, None)
    assert p["patient_id"] is None and p["doses"] == []
```

- [ ] **Step 2: Implement:**
  - `rebuild_doses` deletes the prescription's future `scheduled` doses and creates `days × times` rows. Date = today (Africa/Tunis) + i; `scheduled_at` = local time converted to UTC; IDs from `new_id(db, "d", 6)`.
  - `build_schedule_payload` groups the active doses by `(time_of_day, slot)`, picks today's occurrence `dose_id`, merges `meds`, sorts by time, and caps at 8. `schedule_version` = `device.schedule_version + 1`, stored on the device.
  - `push_schedule` finds the active admission → device and calls `publish_schedule` (retained, QoS 1).
- [ ] **Step 3: Routers:**
  - `POST /prescriptions` and `PATCH /prescriptions/{id}` (doctor, own patients) → rebuild doses → push. Return `published_to_device`.
  - `GET /devices`
  - `POST /devices/{id}/assign` (admin): create the admission, then push
  - `POST /admissions/{id}/discharge`: publish the unassigned schedule, then `emit("patient.discharged", ...)`
  - `POST /devices/{id}/command`
- [ ] **Step 4: Events in `ingest`:**
  - `dose_dispensed`, `dose_taken` and `dose_missed` update the `med_doses.status` (and `taken_method`) of the given `dose_id`, then build a `dose_event` frame.
  - `dose_missed` also creates an alert (`dose_missed`, medium) and emits `dose.missed`.
  - `call_nurse` creates an alert (`call_nurse`, high) plus a `call_nurse` frame.
  - `nurse_tap` is logged only (audit `action="read"` by that nurse on the patient).
  - `schedule_ack` sets `devices.schedule_acked_version`.

  Add a test for each of these.
- [ ] **Step 5:** Commit `feat(backend): prescriptions → doses → retained schedule; device events`.

### Task 8: (stretch, Day 3 afternoon) Real board + servo pill holder

- [ ] Only if CP3 is green: wire the real ESP32 per `firmware/PINMAP.md` (OLED + RTC on I2C 21/22, servo signal on 13, servo on 5 V).
- [ ] Build the 4-slot pill holder on the servo horn (`hardware/README.md` → "Servo dispenser"). Hedi flashes the same firmware as Wokwi.
- [ ] If it isn't reliable, the demo uses the Wokwi device. No server changes either way.

**Day 2 done when:** CP2 passes. A doctor's prescription appears on the Wokwi device, `dose_taken` comes back and `med_doses` updates. The simulator's abnormal scenario produces a critical alert over WS, plus an `alert.critical` POST reaching n8n.

---

## Day 3 — Thu 10-08 (integration)

### Task 9: Golden path as the Nurse owner

- [ ] Run the golden path with the Wokwi device + simulator and fix only blockers. The nurse flow (simulated tap → vitals tagged with the nurse → abnormal → alert on dashboard + Telegram → ack) must pass twice in a row by 13:00 (CP3).
- [ ] Add a `device_offline` alert: in the worker, a `status {online:false}` for a device with an active admission → alert (medium) + frame.
- [ ] Add `tests/test_contracts.py`: load the JSON examples from `docs/contracts/mqtt-topics.md` (copy them into `tests/fixtures/mqtt/*.json`) and assert `ingest.handle` accepts each one.

**Day 3 done when:** CP3 passes and there are no open blockers on the nurse flow.

## Day 4 — Fri 10-09 (polish)

- [ ] Stretch: Postgres RLS on `patients`, `vitals` and `notes` (policy using `current_setting('ward.user_id')`), only if CP3 stays green.
- [ ] Stretch: Mosquitto password auth (`mosquitto_passwd`) + device credentials in `secrets.h`.
- [ ] If the real board was built: tidy the wiring and label `bsu-001`.
- [ ] Rehearse your demo segment (Nurse, ~60 s) three times.

**Day 4 done when:** the backend survives a 30-minute soak with the device and simulator running, and your demo segment is rehearsed.

## Self-review checklist (run before each PR)

- [ ] Every response shape matches `docs/contracts/api.md`.
- [ ] Every `/patients/{id}*` route calls `check_patient_access`.
- [ ] `pytest -v` and `ruff check` are green.
- [ ] No secrets committed; `.env.example` updated for any new variable.
