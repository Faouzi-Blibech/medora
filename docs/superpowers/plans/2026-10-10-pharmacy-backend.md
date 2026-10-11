# Hospital Pharmacy (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the hospital pharmacist between the doctor's prescription and the dose. Phase A builds the safety loop: the pharmacist role, the drug catalogue, a deterministic check engine and prescription validation. Phase B builds logistics: stock, FEFO dispensing to wards and nurse receipt. Phase A works and ships on its own.

**Architecture:**
- A `pharmacy` service package lives inside the existing FastAPI backend:
  - `app/services/pharmacy/checks.py`: a pure rule engine with versioned JSON rule files;
  - `workflow.py`: the prescription status machine, under `SELECT … FOR UPDATE`;
  - `review.py`: what the pharmacist reads;
  - `stock.py` and `dispensing.py`: Phase B.
- Thin routers: `drugs.py`, `pharmacy.py`, `prescriptions.py` (changed), plus `pharmacy_stock.py` and `dispensations.py` for Phase B.
- `prescriptions.active` stays a real column. It is re-derived from `status` on every transition, so the existing dose, schedule and AI code keeps working.
- Side effects reuse what exists:
  - doses: `schedule.rebuild_doses` and `schedule.push_schedule`;
  - WebSocket: a `frame()` passed to `publisher.publish_ws_frame` after commit;
  - n8n: `n8n.emit_after_commit`;
  - audit: `audit()`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (typed `Mapped`), Alembic, Pydantic v2, PostgreSQL 16 + TimescaleDB, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-10-hospital-pharmacy-design.md` (binding). Repo conventions: `CLAUDE.md`.

## Global Constraints

- Python 3.12. FastAPI + SQLAlchemy 2.0 typed `Mapped[...]` + Alembic + Pydantic v2. One router per resource in `backend/app/routers/`. Business logic goes in `backend/app/services/`, not in routers.
- Ruff `line-length = 110`. `ruff check app tests` must pass before every commit.
- "Offline-first, with no LLM. The checks are deterministic, explainable rules." Every test runs with `LLM_PROVIDER=none`.
- "A human always decides. The engine only flags."
- "Every patient-data read is audited." This means `audit_log`. Pharmacist reads use resource `prescription` with `patient_id`. Decisions and stock movements are audited too.
- "Synthetic data only."
- The rule files and the formulary are labelled: "illustrative, not a clinical reference; to be validated by the hospital's pharmacists". Every JSON file's `note` must contain the phrase `not a clinical reference`.
- The rule files live in `backend/app/rules/pharmacy/`. The formulary seed is `backend/app/data/pharmacy/formulary.v1.json`, with about 50 drugs. Rule lists are never inline in code.
- Errors use the existing `{detail, code}` shape. IDs are prefixed strings. REST timestamps are ISO-8601 UTC with `Z`. Dose times are `HH:MM` Africa/Tunis.
- "Role checks go through `require_roles`." "The pharmacist's patient view is a minimal projection and is never the full record."
- "Concurrency: two pharmacists validating at once means the second gets 409 `bad_status`. The status is checked under `SELECT … FOR UPDATE`." "Stock can't go negative, also checked under a row lock."
- Speed: the check engine takes "under 20 ms per check".
- Contract bumps: api 1.11 → 1.12, data-model 1.6 → 1.7, n8n-webhooks 1.3 → 1.4 (`prescription.review`). mqtt-topics stays the same. The contract wins over code until it is bumped.
- Lanes: this plan touches only `backend/` and `docs/contracts/`. It never edits `web/`, `n8n/` or `backend/app/routers/appointments.py`.
- Git: Conventional Commits (`feat(backend): …`, `docs(contracts): …`). No AI attribution, no trailers. Local commits only, no push.
- Tests share one DB session per test (`tests/conftest.py`), and routes never roll back. So **a route must raise every 4xx before its first write**, or the test session keeps half-written rows.
- JSONB columns are only change-tracked on reassignment: write `rx.items = [...]`, never `rx.items[0]["x"] = ...`.
- **TEST** command (Git Bash, from the worktree root):
  `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider <paths>`
- **LINT** command: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app ward-test ruff check app tests`

## Review Focus

1. **A non-urgent prescription validated hours after it was written.** Its doses must start at or after the validation, never in the past; otherwise the nurse sees an instant overdue dose. Pinned by `test_doses_start_at_validation_not_at_writing` (Task 5).
2. **A dose left in the past by a prescription that was then rejected, stopped or superseded.** The nurse's "given" must be refused with 409 `bad_status` and never recorded. Pinned by `test_nurse_cannot_give_a_leftover_dose_of_a_cancelled_prescription` (Task 5).
3. **The doctor stops or replaces a prescription while the pharmacist has it open.** The pharmacist's validate, request-changes or reject must get 409 `bad_status`, and nothing comes back to life. Pinned by `test_decision_after_the_doctor_moved_on_is_409` (Task 5).
4. **A dose already dispensed to the ward, then its prescription is rebuilt (urgent then validated) or stopped.** There must be no FK crash. A kept dose keeps its id; a deleted dose leaves the line with `dose_id = null`. Pinned by `test_rebuild_after_dispensing_keeps_or_detaches_the_line` (Task 11).
5. **Several lines of one dispensation drawing on the same small lot.** The allocation must count what earlier lines took, so no lot goes negative and the next line moves to the next lot. Pinned by `test_lines_share_a_lot_without_going_negative` (Task 11).

---

## File Structure

| File | Phase | Responsibility |
|---|---|---|
| `backend/alembic/versions/0007_pharmacy.py` | A | `drugs`, the new prescription columns + backfill, `prescription_reviews` |
| `backend/alembic/versions/0008_pharmacy_stock.py` | B | `stock_lots`, `stock_movements` (append-only trigger), `dispensations`, `dispensation_lines` |
| `backend/app/models/pharmacy.py` | A, B | `Drug`, `PrescriptionReview`; then `StockLot`, `StockMovement`, `Dispensation`, `DispensationLine` |
| `backend/app/models/clinical.py` | A | `Prescription` gains status, urgent, version, replaces_id, checks, override_reason, reviewed_* |
| `backend/app/data/pharmacy/formulary.v1.json` | A | 51 synthetic formulary drugs |
| `backend/app/rules/pharmacy/{allergy_synonyms,interactions,elderly_caution}.v1.json` | A | The check rules |
| `backend/app/services/pharmacy/checks.py` | A | Pure engine: `run_checks` |
| `backend/app/services/pharmacy/formulary.py` | A | Formulary load, catalogue CRUD helpers, `drug_infos`, name matching + backfill |
| `backend/app/services/pharmacy/workflow.py` | A | Status machine, create/stop/decide, dose side effects, frames, n8n, `rx_out` |
| `backend/app/services/pharmacy/review.py` | A | Pharmacist worklist, detail, summary, minimal patient projection |
| `backend/app/services/pharmacy/stock.py` | B | Lots, movements, FEFO, stock view, reorder, alert counts |
| `backend/app/services/pharmacy/dispensing.py` | B | Round view, dispense transaction, nurse receipt, dose `pharmacy` status |
| `backend/app/routers/drugs.py` | A | `/drugs` |
| `backend/app/routers/prescriptions.py` | A | `/prescriptions`, `/prescriptions/check`, `PATCH` stop |
| `backend/app/routers/pharmacy.py` | A | `/pharmacy/worklist`, `/pharmacy/prescriptions/*`, `/pharmacy/summary` |
| `backend/app/routers/pharmacy_stock.py` | B | `/pharmacy/stock*` |
| `backend/app/routers/dispensations.py` | B | `/pharmacy/dispensing`, `/pharmacy/dispensations`, `/dispensations*` |
| `backend/scripts/pharmacy_smoke.py` | A, B | Demo-path smoke over HTTP (also run in-process by a test) |

---

# Phase A: the safety loop

### Task 1: Migration 0007, models and the formulary loader

**Files:**
- Create: `backend/alembic/versions/0007_pharmacy.py`
- Create: `backend/app/models/pharmacy.py`
- Modify: `backend/app/models/clinical.py` (class `Prescription`)
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/data/pharmacy/formulary.v1.json`
- Create: `backend/app/services/pharmacy/__init__.py` (empty)
- Create: `backend/app/services/pharmacy/formulary.py`
- Modify: `backend/app/seed.py` (call the loader in both paths)
- Test: `backend/tests/test_pharmacy_models.py`

**Interfaces:**
- Consumes: `app.ids.reserve_upto(db, prefix, n)`, `app.db.Base`.
- Produces:
  - `app.models.Drug` (columns from spec §3) and `app.models.PrescriptionReview`.
  - `Prescription.status: str` (default `"validated"`), `.urgent: bool`, `.version: int`, `.replaces_id: str | None`, `.checks: list`, `.override_reason: str | None`, `.reviewed_by: str | None`, `.reviewed_at: datetime | None`, `.review_comment: str | None`.
  - `app.services.pharmacy.formulary.FORMULARY: Path`, `DRUG_FIELDS: tuple[str, ...]`, `formulary_entries(path=FORMULARY) -> list[dict]`, `load_formulary(db, path=FORMULARY) -> int`.
  - Drug IDs are `d-0001`…`d-0051`. They share the `d` sequence with doses (`d-000001`); `load_formulary` advances it past 51.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_pharmacy_models.py`:
```python
"""Migration 0007 shapes (through create_all) and the formulary loader (pharmacy spec §3)."""

from app.ids import new_id
from app.models import Drug, Prescription, PrescriptionReview
from app.seed import seed
from app.services.pharmacy.formulary import formulary_entries, load_formulary


def test_formulary_file_has_about_fifty_unique_drugs():
    entries = formulary_entries()
    assert len(entries) == 51 and len({e["id"] for e in entries}) == 51


def test_formulary_loads_once_and_keeps_edits(db):
    assert load_formulary(db) == 51 and db.query(Drug).count() == 51
    amox = db.get(Drug, "d-0003")
    assert (amox.dci, amox.allergy_classes, float(amox.unit_mg), amox.active) == (
        "Amoxicillin", ["penicillin", "beta_lactam"], 1000.0, True)
    amox.min_stock = 7
    db.flush()
    assert load_formulary(db) == 0 and db.get(Drug, "d-0003").min_stock == 7  # a pharmacist's edit wins
    assert int(new_id(db, "d")[2:]) > 51  # the shared `d` sequence is past the file's ids


def test_prescription_defaults(db, seeded):
    rx = Prescription(id="rx-9400", patient_id="p-0002", doctor_id="u-0001", items=[], care_plan="", active=True)
    db.add(rx)
    db.flush()
    db.refresh(rx)
    assert (rx.status, rx.urgent, rx.version, rx.checks, rx.replaces_id, rx.reviewed_by) == (
        "validated", False, 1, [], None, None)


def test_review_row(db, seeded):
    db.add(Prescription(id="rx-9401", patient_id="p-0002", doctor_id="u-0001", items=[], care_plan="",
                        active=False, status="pending_pharmacy"))
    db.flush()
    db.add(PrescriptionReview(id="pr-9401", prescription_id="rx-9401", pharmacist_id="u-0004",
                              decision="rejected", comment="no", checks_snapshot=[{"code": "allergy"}]))
    db.flush()
    r = db.get(PrescriptionReview, "pr-9401")
    assert (r.decision, r.checks_snapshot, r.created_at is not None) == ("rejected", [{"code": "allergy"}], True)


def test_seed_loads_the_formulary(db):
    seed(db)
    assert db.query(Drug).count() == 51
    seed(db)  # second run: the "already seeded" path loads nothing twice
    assert db.query(Drug).count() == 51
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_pharmacy_models.py`
Expected: it fails during collection with `ImportError: cannot import name 'Drug'`.

- [ ] **Step 3: Models**

`backend/app/models/pharmacy.py`:
```python
"""Hospital pharmacy tables (data-model 1.7, pharmacy spec §3). Phase A: drugs, prescription_reviews."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

EMPTY_JSON = text("'[]'::jsonb")


class Drug(Base):
    """The hospital formulary (livret thérapeutique). Never deleted: `active = false` retires a drug."""

    __tablename__ = "drugs"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # d-0001
    dci: Mapped[str] = mapped_column(String)
    brand_names: Mapped[list] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON)
    form: Mapped[str] = mapped_column(String)  # tablet|capsule|syrup|injection|inhaler|patch|drops|other
    strength: Mapped[str] = mapped_column(String, default="", server_default="")
    unit_mg: Mapped[Decimal | None] = mapped_column(Numeric)
    max_daily_mg: Mapped[Decimal | None] = mapped_column(Numeric)
    atc_code: Mapped[str] = mapped_column(String, default="", server_default="")
    allergy_classes: Mapped[list] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON)
    interaction_groups: Mapped[list] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON)
    high_alert: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    min_stock: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class PrescriptionReview(Base):
    """One pharmacist decision (validated | changes_requested | rejected) with the checks seen at that moment."""

    __tablename__ = "prescription_reviews"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # pr-0001
    prescription_id: Mapped[str] = mapped_column(ForeignKey("prescriptions.id"), index=True)
    pharmacist_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String)
    comment: Mapped[str | None] = mapped_column(Text)
    checks_snapshot: Mapped[list] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

In `backend/app/models/clinical.py`, add these columns to `Prescription`, after `created_at`. The existing columns stay. Change the `items` comment to `# [{med, drug_id?, dose_mg?, units_per_intake, times[], slot, days}]`.
```python
    # pharmacy (data-model 1.7): pending_pharmacy | validated | changes_requested | rejected | stopped | superseded.
    # `active` above is derived: validated, or pending_pharmacy + urgent (services/pharmacy/workflow.py keeps it).
    status: Mapped[str] = mapped_column(String, default="validated", server_default="validated", index=True)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    replaces_id: Mapped[str | None] = mapped_column(ForeignKey("prescriptions.id"))
    checks: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    override_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(Text)
```
`text` is already imported in `clinical.py`. The default `"validated"` matches the backfill and the rows the tests build directly with `active=True`. The router always sets the status explicitly.

In `backend/app/models/__init__.py`, update the docstring version to `v1.7: pharmacy`. Add `from app.models.pharmacy import Drug, PrescriptionReview` and add `"Drug"` and `"PrescriptionReview"` to `__all__` (alphabetical).

- [ ] **Step 4: Migration**

`backend/alembic/versions/0007_pharmacy.py`:
```python
"""Hospital pharmacy, Phase A: drugs (formulary), prescription review status, prescription_reviews (data-model 1.7)

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

EMPTY = sa.text("'[]'::jsonb")
RX_COLUMNS = ("review_comment", "reviewed_at", "reviewed_by", "override_reason", "checks", "replaces_id", "version",
              "urgent", "status")


def upgrade() -> None:
    op.create_table(
        "drugs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dci", sa.String(), nullable=False),
        sa.Column("brand_names", postgresql.JSONB(), nullable=False, server_default=EMPTY),
        sa.Column("form", sa.String(), nullable=False),
        sa.Column("strength", sa.String(), nullable=False, server_default=""),
        sa.Column("unit_mg", sa.Numeric(), nullable=True),
        sa.Column("max_daily_mg", sa.Numeric(), nullable=True),
        sa.Column("atc_code", sa.String(), nullable=False, server_default=""),
        sa.Column("allergy_classes", postgresql.JSONB(), nullable=False, server_default=EMPTY),
        sa.Column("interaction_groups", postgresql.JSONB(), nullable=False, server_default=EMPTY),
        sa.Column("high_alert", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("min_stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("prescriptions", sa.Column("status", sa.String(), nullable=False, server_default="validated"))
    op.add_column("prescriptions", sa.Column("urgent", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("prescriptions", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("prescriptions", sa.Column("replaces_id", sa.String(), sa.ForeignKey("prescriptions.id"),
                                             nullable=True))
    op.add_column("prescriptions", sa.Column("checks", postgresql.JSONB(), nullable=False, server_default=EMPTY))
    op.add_column("prescriptions", sa.Column("override_reason", sa.Text(), nullable=True))
    op.add_column("prescriptions", sa.Column("reviewed_by", sa.String(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("prescriptions", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("prescriptions", sa.Column("review_comment", sa.Text(), nullable=True))
    # backfill (spec §3): running prescriptions predate the gate and count as validated; stopped ones are stopped.
    # drug_id in items and reviewed_by need the formulary and the seed pharmacist: app/seed.py fills them.
    op.execute("UPDATE prescriptions SET status = CASE WHEN active THEN 'validated' ELSE 'stopped' END")
    op.create_index("ix_prescriptions_status", "prescriptions", ["status"])
    op.create_table(
        "prescription_reviews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("prescription_id", sa.String(), sa.ForeignKey("prescriptions.id"), nullable=False),
        sa.Column("pharmacist_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("checks_snapshot", postgresql.JSONB(), nullable=False, server_default=EMPTY),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_prescription_reviews_prescription_id", "prescription_reviews", ["prescription_id"])


def downgrade() -> None:
    op.drop_index("ix_prescription_reviews_prescription_id", table_name="prescription_reviews")
    op.drop_table("prescription_reviews")
    op.drop_index("ix_prescriptions_status", table_name="prescriptions")
    for col in RX_COLUMNS:
        op.drop_column("prescriptions", col)
    op.drop_table("drugs")
```

- [ ] **Step 5: Formulary file**

`backend/app/data/pharmacy/formulary.v1.json`. Write exactly this. Each drug is one line, and the values are illustrative.
```json
{
  "version": 1,
  "note": "Synthetic demo formulary. Illustrative, not a clinical reference; to be validated by the hospital's pharmacists.",
  "drugs": [
    {"id": "d-0001", "dci": "Paracetamol", "brand_names": ["Doliprane", "Efferalgan", "Panadol"], "form": "tablet", "strength": "500 mg", "unit_mg": 500, "max_daily_mg": 4000, "atc_code": "N02BE01", "allergy_classes": ["paracetamol"], "interaction_groups": [], "high_alert": false, "min_stock": 200},
    {"id": "d-0002", "dci": "Paracetamol", "brand_names": ["Doliprane 1000", "Efferalgan 1 g"], "form": "tablet", "strength": "1 g", "unit_mg": 1000, "max_daily_mg": 4000, "atc_code": "N02BE01", "allergy_classes": ["paracetamol"], "interaction_groups": [], "high_alert": false, "min_stock": 100},
    {"id": "d-0003", "dci": "Amoxicillin", "brand_names": ["Clamoxyl", "Hiconcil", "Amoxil"], "form": "tablet", "strength": "1 g", "unit_mg": 1000, "max_daily_mg": 6000, "atc_code": "J01CA04", "allergy_classes": ["penicillin", "beta_lactam"], "interaction_groups": [], "high_alert": false, "min_stock": 100},
    {"id": "d-0004", "dci": "Amoxicillin", "brand_names": ["Clamoxyl 500"], "form": "capsule", "strength": "500 mg", "unit_mg": 500, "max_daily_mg": 6000, "atc_code": "J01CA04", "allergy_classes": ["penicillin", "beta_lactam"], "interaction_groups": [], "high_alert": false, "min_stock": 100},
    {"id": "d-0005", "dci": "Amoxicillin + clavulanic acid", "brand_names": ["Augmentin"], "form": "tablet", "strength": "1 g/125 mg", "unit_mg": 1000, "max_daily_mg": 3000, "atc_code": "J01CR02", "allergy_classes": ["penicillin", "beta_lactam"], "interaction_groups": [], "high_alert": false, "min_stock": 80},
    {"id": "d-0006", "dci": "Azithromycin", "brand_names": ["Zithromax", "Azithrocine"], "form": "tablet", "strength": "250 mg", "unit_mg": 250, "max_daily_mg": 500, "atc_code": "J01FA10", "allergy_classes": ["macrolide"], "interaction_groups": ["qt_prolonging"], "high_alert": false, "min_stock": 60},
    {"id": "d-0007", "dci": "Clarithromycin", "brand_names": ["Zeclar"], "form": "tablet", "strength": "500 mg", "unit_mg": 500, "max_daily_mg": 1000, "atc_code": "J01FA09", "allergy_classes": ["macrolide"], "interaction_groups": ["macrolide_cyp3a4", "qt_prolonging"], "high_alert": false, "min_stock": 40},
    {"id": "d-0008", "dci": "Ceftriaxone", "brand_names": ["Rocephine", "Triaxon"], "form": "injection", "strength": "1 g vial", "unit_mg": 1000, "max_daily_mg": 4000, "atc_code": "J01DD04", "allergy_classes": ["cephalosporin", "beta_lactam"], "interaction_groups": [], "high_alert": false, "min_stock": 50},
    {"id": "d-0009", "dci": "Ciprofloxacin", "brand_names": ["Ciflox"], "form": "tablet", "strength": "500 mg", "unit_mg": 500, "max_daily_mg": 1500, "atc_code": "J01MA02", "allergy_classes": ["fluoroquinolone"], "interaction_groups": ["qt_prolonging"], "high_alert": false, "min_stock": 40},
    {"id": "d-0010", "dci": "Metronidazole", "brand_names": ["Flagyl"], "form": "tablet", "strength": "500 mg", "unit_mg": 500, "max_daily_mg": 4000, "atc_code": "P01AB01", "allergy_classes": ["nitroimidazole"], "interaction_groups": [], "high_alert": false, "min_stock": 40},
    {"id": "d-0011", "dci": "Sulfamethoxazole + trimethoprim", "brand_names": ["Bactrim Forte"], "form": "tablet", "strength": "800 mg/160 mg", "unit_mg": 960, "max_daily_mg": 3840, "atc_code": "J01EE01", "allergy_classes": ["sulfonamide"], "interaction_groups": [], "high_alert": false, "min_stock": 30},
    {"id": "d-0012", "dci": "Warfarin", "brand_names": ["Coumadine"], "form": "tablet", "strength": "5 mg", "unit_mg": 5, "max_daily_mg": 15, "atc_code": "B01AA03", "allergy_classes": [], "interaction_groups": ["anticoagulant"], "high_alert": true, "min_stock": 30},
    {"id": "d-0013", "dci": "Acenocoumarol", "brand_names": ["Sintrom"], "form": "tablet", "strength": "4 mg", "unit_mg": 4, "max_daily_mg": 12, "atc_code": "B01AA07", "allergy_classes": [], "interaction_groups": ["anticoagulant"], "high_alert": true, "min_stock": 30},
    {"id": "d-0014", "dci": "Enoxaparin", "brand_names": ["Lovenox"], "form": "injection", "strength": "4000 IU/0.4 mL", "unit_mg": null, "max_daily_mg": null, "atc_code": "B01AB05", "allergy_classes": ["heparin"], "interaction_groups": ["anticoagulant"], "high_alert": true, "min_stock": 20},
    {"id": "d-0015", "dci": "Heparin", "brand_names": ["Héparine Choay"], "form": "injection", "strength": "25000 IU/5 mL", "unit_mg": null, "max_daily_mg": null, "atc_code": "B01AB01", "allergy_classes": ["heparin"], "interaction_groups": ["anticoagulant"], "high_alert": true, "min_stock": 10},
    {"id": "d-0016", "dci": "Aspirin", "brand_names": ["Aspégic", "Kardégic"], "form": "tablet", "strength": "100 mg", "unit_mg": 100, "max_daily_mg": 4000, "atc_code": "B01AC06", "allergy_classes": ["aspirin"], "interaction_groups": ["antiplatelet"], "high_alert": false, "min_stock": 100},
    {"id": "d-0017", "dci": "Clopidogrel", "brand_names": ["Plavix"], "form": "tablet", "strength": "75 mg", "unit_mg": 75, "max_daily_mg": 300, "atc_code": "B01AC04", "allergy_classes": [], "interaction_groups": ["antiplatelet"], "high_alert": false, "min_stock": 60},
    {"id": "d-0018", "dci": "Ibuprofen", "brand_names": ["Brufen", "Advil"], "form": "tablet", "strength": "400 mg", "unit_mg": 400, "max_daily_mg": 2400, "atc_code": "M01AE01", "allergy_classes": ["nsaid"], "interaction_groups": ["nsaid"], "high_alert": false, "min_stock": 100},
    {"id": "d-0019", "dci": "Diclofenac", "brand_names": ["Voltarène"], "form": "tablet", "strength": "50 mg", "unit_mg": 50, "max_daily_mg": 150, "atc_code": "M01AB05", "allergy_classes": ["nsaid"], "interaction_groups": ["nsaid"], "high_alert": false, "min_stock": 60},
    {"id": "d-0020", "dci": "Ketoprofen", "brand_names": ["Profénid"], "form": "capsule", "strength": "100 mg", "unit_mg": 100, "max_daily_mg": 300, "atc_code": "M01AE03", "allergy_classes": ["nsaid"], "interaction_groups": ["nsaid"], "high_alert": false, "min_stock": 40},
    {"id": "d-0021", "dci": "Morphine", "brand_names": ["Skenan", "Actiskenan"], "form": "tablet", "strength": "10 mg", "unit_mg": 10, "max_daily_mg": null, "atc_code": "N02AA01", "allergy_classes": ["opioid"], "interaction_groups": ["opioid"], "high_alert": true, "min_stock": 40},
    {"id": "d-0022", "dci": "Tramadol", "brand_names": ["Topalgic", "Contramal"], "form": "capsule", "strength": "50 mg", "unit_mg": 50, "max_daily_mg": 400, "atc_code": "N02AX02", "allergy_classes": ["opioid"], "interaction_groups": ["opioid", "serotonergic"], "high_alert": false, "min_stock": 60},
    {"id": "d-0023", "dci": "Insulin glargine", "brand_names": ["Lantus"], "form": "injection", "strength": "100 IU/mL", "unit_mg": null, "max_daily_mg": null, "atc_code": "A10AE04", "allergy_classes": [], "interaction_groups": ["hypoglycemic"], "high_alert": true, "min_stock": 20},
    {"id": "d-0024", "dci": "Insulin aspart", "brand_names": ["NovoRapid"], "form": "injection", "strength": "100 IU/mL", "unit_mg": null, "max_daily_mg": null, "atc_code": "A10AB05", "allergy_classes": [], "interaction_groups": ["hypoglycemic"], "high_alert": true, "min_stock": 20},
    {"id": "d-0025", "dci": "Metformin", "brand_names": ["Glucophage"], "form": "tablet", "strength": "850 mg", "unit_mg": 850, "max_daily_mg": 3000, "atc_code": "A10BA02", "allergy_classes": [], "interaction_groups": ["hypoglycemic"], "high_alert": false, "min_stock": 100},
    {"id": "d-0026", "dci": "Gliclazide", "brand_names": ["Diamicron"], "form": "tablet", "strength": "30 mg", "unit_mg": 30, "max_daily_mg": 120, "atc_code": "A10BB09", "allergy_classes": ["sulfonylurea"], "interaction_groups": ["hypoglycemic"], "high_alert": false, "min_stock": 60},
    {"id": "d-0027", "dci": "Potassium chloride", "brand_names": ["KCl 10%"], "form": "injection", "strength": "1 g/10 mL", "unit_mg": null, "max_daily_mg": null, "atc_code": "B05XA01", "allergy_classes": [], "interaction_groups": ["potassium"], "high_alert": true, "min_stock": 30},
    {"id": "d-0028", "dci": "Potassium chloride", "brand_names": ["Diffu-K"], "form": "capsule", "strength": "600 mg", "unit_mg": 600, "max_daily_mg": 6000, "atc_code": "A12BA01", "allergy_classes": [], "interaction_groups": ["potassium"], "high_alert": false, "min_stock": 40},
    {"id": "d-0029", "dci": "Furosemide", "brand_names": ["Lasilix"], "form": "tablet", "strength": "40 mg", "unit_mg": 40, "max_daily_mg": 500, "atc_code": "C03CA01", "allergy_classes": [], "interaction_groups": ["loop_diuretic"], "high_alert": false, "min_stock": 80},
    {"id": "d-0030", "dci": "Spironolactone", "brand_names": ["Aldactone"], "form": "tablet", "strength": "25 mg", "unit_mg": 25, "max_daily_mg": 200, "atc_code": "C03DA01", "allergy_classes": [], "interaction_groups": ["potassium_sparing"], "high_alert": false, "min_stock": 40},
    {"id": "d-0031", "dci": "Hydrochlorothiazide", "brand_names": ["Esidrex"], "form": "tablet", "strength": "25 mg", "unit_mg": 25, "max_daily_mg": 100, "atc_code": "C03AA03", "allergy_classes": [], "interaction_groups": ["thiazide"], "high_alert": false, "min_stock": 40},
    {"id": "d-0032", "dci": "Amlodipine", "brand_names": ["Amlor", "Norvasc"], "form": "tablet", "strength": "5 mg", "unit_mg": 5, "max_daily_mg": 10, "atc_code": "C08CA01", "allergy_classes": [], "interaction_groups": [], "high_alert": false, "min_stock": 60},
    {"id": "d-0033", "dci": "Ramipril", "brand_names": ["Triatec"], "form": "tablet", "strength": "5 mg", "unit_mg": 5, "max_daily_mg": 10, "atc_code": "C09AA05", "allergy_classes": [], "interaction_groups": ["ace_inhibitor"], "high_alert": false, "min_stock": 60},
    {"id": "d-0034", "dci": "Enalapril", "brand_names": ["Renitec"], "form": "tablet", "strength": "20 mg", "unit_mg": 20, "max_daily_mg": 40, "atc_code": "C09AA02", "allergy_classes": [], "interaction_groups": ["ace_inhibitor"], "high_alert": false, "min_stock": 40},
    {"id": "d-0035", "dci": "Losartan", "brand_names": ["Cozaar"], "form": "tablet", "strength": "50 mg", "unit_mg": 50, "max_daily_mg": 100, "atc_code": "C09CA01", "allergy_classes": [], "interaction_groups": ["arb"], "high_alert": false, "min_stock": 40},
    {"id": "d-0036", "dci": "Bisoprolol", "brand_names": ["Cardensiel", "Concor"], "form": "tablet", "strength": "5 mg", "unit_mg": 5, "max_daily_mg": 20, "atc_code": "C07AB07", "allergy_classes": [], "interaction_groups": ["beta_blocker"], "high_alert": false, "min_stock": 60},
    {"id": "d-0037", "dci": "Atorvastatin", "brand_names": ["Tahor", "Lipitor"], "form": "tablet", "strength": "20 mg", "unit_mg": 20, "max_daily_mg": 80, "atc_code": "C10AA05", "allergy_classes": [], "interaction_groups": ["statin_cyp3a4"], "high_alert": false, "min_stock": 60},
    {"id": "d-0038", "dci": "Simvastatin", "brand_names": ["Zocor"], "form": "tablet", "strength": "20 mg", "unit_mg": 20, "max_daily_mg": 40, "atc_code": "C10AA01", "allergy_classes": [], "interaction_groups": ["statin_cyp3a4"], "high_alert": false, "min_stock": 40},
    {"id": "d-0039", "dci": "Digoxin", "brand_names": ["Digoxine Nativelle"], "form": "tablet", "strength": "0.25 mg", "unit_mg": 0.25, "max_daily_mg": 0.5, "atc_code": "C01AA05", "allergy_classes": [], "interaction_groups": ["cardiac_glycoside"], "high_alert": true, "min_stock": 20},
    {"id": "d-0040", "dci": "Amiodarone", "brand_names": ["Cordarone"], "form": "tablet", "strength": "200 mg", "unit_mg": 200, "max_daily_mg": 1200, "atc_code": "C01BD01", "allergy_classes": [], "interaction_groups": ["qt_prolonging"], "high_alert": false, "min_stock": 30},
    {"id": "d-0041", "dci": "Omeprazole", "brand_names": ["Mopral"], "form": "capsule", "strength": "20 mg", "unit_mg": 20, "max_daily_mg": 80, "atc_code": "A02BC01", "allergy_classes": [], "interaction_groups": [], "high_alert": false, "min_stock": 80},
    {"id": "d-0042", "dci": "Pantoprazole", "brand_names": ["Inipomp"], "form": "tablet", "strength": "40 mg", "unit_mg": 40, "max_daily_mg": 80, "atc_code": "A02BC02", "allergy_classes": [], "interaction_groups": [], "high_alert": false, "min_stock": 60},
    {"id": "d-0043", "dci": "Salbutamol", "brand_names": ["Ventoline"], "form": "inhaler", "strength": "100 µg/dose", "unit_mg": null, "max_daily_mg": null, "atc_code": "R03AC02", "allergy_classes": [], "interaction_groups": [], "high_alert": false, "min_stock": 20},
    {"id": "d-0044", "dci": "Prednisolone", "brand_names": ["Solupred"], "form": "tablet", "strength": "20 mg", "unit_mg": 20, "max_daily_mg": 60, "atc_code": "H02AB06", "allergy_classes": [], "interaction_groups": ["corticosteroid"], "high_alert": false, "min_stock": 40},
    {"id": "d-0045", "dci": "Diazepam", "brand_names": ["Valium"], "form": "tablet", "strength": "10 mg", "unit_mg": 10, "max_daily_mg": 40, "atc_code": "N05BA01", "allergy_classes": [], "interaction_groups": ["benzodiazepine"], "high_alert": false, "min_stock": 30},
    {"id": "d-0046", "dci": "Alprazolam", "brand_names": ["Xanax"], "form": "tablet", "strength": "0.5 mg", "unit_mg": 0.5, "max_daily_mg": 4, "atc_code": "N05BA12", "allergy_classes": [], "interaction_groups": ["benzodiazepine"], "high_alert": false, "min_stock": 30},
    {"id": "d-0047", "dci": "Sertraline", "brand_names": ["Zoloft"], "form": "tablet", "strength": "50 mg", "unit_mg": 50, "max_daily_mg": 200, "atc_code": "N06AB06", "allergy_classes": [], "interaction_groups": ["serotonergic"], "high_alert": false, "min_stock": 30},
    {"id": "d-0048", "dci": "Amitriptyline", "brand_names": ["Laroxyl"], "form": "tablet", "strength": "25 mg", "unit_mg": 25, "max_daily_mg": 150, "atc_code": "N06AA09", "allergy_classes": [], "interaction_groups": ["serotonergic", "qt_prolonging"], "high_alert": false, "min_stock": 20},
    {"id": "d-0049", "dci": "Ondansetron", "brand_names": ["Zophren"], "form": "tablet", "strength": "8 mg", "unit_mg": 8, "max_daily_mg": 24, "atc_code": "A04AA01", "allergy_classes": [], "interaction_groups": ["qt_prolonging"], "high_alert": false, "min_stock": 30},
    {"id": "d-0050", "dci": "Haloperidol", "brand_names": ["Haldol"], "form": "tablet", "strength": "5 mg", "unit_mg": 5, "max_daily_mg": 20, "atc_code": "N05AD01", "allergy_classes": [], "interaction_groups": ["qt_prolonging"], "high_alert": false, "min_stock": 20},
    {"id": "d-0051", "dci": "Levothyroxine", "brand_names": ["Levothyrox"], "form": "tablet", "strength": "100 µg", "unit_mg": 0.1, "max_daily_mg": 0.3, "atc_code": "H03AA01", "allergy_classes": [], "interaction_groups": [], "high_alert": false, "min_stock": 40}
  ]
}
```

- [ ] **Step 6: Loader**

`backend/app/services/pharmacy/__init__.py` is empty. Create `backend/app/services/pharmacy/formulary.py`:
```python
"""The hospital formulary (livret thérapeutique): the seed file and catalogue helpers (pharmacy spec §3, §5)."""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ids import reserve_upto
from app.models import Drug

FORMULARY = Path(__file__).resolve().parents[2] / "data" / "pharmacy" / "formulary.v1.json"
DRUG_FIELDS = ("dci", "brand_names", "form", "strength", "unit_mg", "max_daily_mg", "atc_code", "allergy_classes",
               "interaction_groups", "high_alert", "min_stock")


def formulary_entries(path: Path = FORMULARY) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["drugs"]


def load_formulary(db: Session, path: Path = FORMULARY) -> int:
    """Insert the file's drugs that are not in the table yet (matched by id). Never overwrites: a pharmacist's edits
    win. Advances the `d` sequence (shared with dose ids) past the file's ids. Returns how many rows were inserted."""
    entries = formulary_entries(path)
    have = set(db.scalars(select(Drug.id)))
    added = 0
    for e in entries:
        if e["id"] not in have:
            db.add(Drug(id=e["id"], active=True, **{k: e[k] for k in DRUG_FIELDS}))
            added += 1
    db.flush()
    reserve_upto(db, "d", max(int(e["id"].split("-")[1]) for e in entries))
    return added
```

In `backend/app/seed.py`:
- add the import `from app.services.pharmacy.formulary import load_formulary`;
- in `seed()`, call `load_formulary(db)` right after `_upsert_missing_staff(db, pw)` in the "already seeded" branch, before `return False`;
- in the fresh path, call it right after the first `db.flush()` that follows the STAFF users loop, so drug ids are reserved before any dose id is drawn.

Task 7 replaces both calls with `_pharmacy(db, now)`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider`
Expected: all pass, the existing suite included. Existing direct `Prescription(..., active=True)` rows get status `validated`.

- [ ] **Step 8: Verify the migration up, down and backfill on a scratch database**

Run each line in Git Bash from the worktree root:
```bash
docker exec ward-db-1 psql -U ward -d postgres -c "DROP DATABASE IF EXISTS ward_mig" -c "CREATE DATABASE ward_mig"
cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward_mig ward-test alembic upgrade 0006 && cd ..
docker exec ward-db-1 psql -U ward -d ward_mig -c "INSERT INTO users(id,email,password_hash,name,role) VALUES ('u-1','m@x.tn','x','M','doctor'); INSERT INTO patients(id,first_name,last_name,allergies,history) VALUES ('p-1','A','B','[]',''); INSERT INTO prescriptions(id,patient_id,doctor_id,items,care_plan,active) VALUES ('rx-1','p-1','u-1','[]','',true),('rx-2','p-1','u-1','[]','',false);"
cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward_mig ward-test sh -c "alembic upgrade head && alembic downgrade 0006 && alembic upgrade head" && cd ..
docker exec ward-db-1 psql -U ward -d ward_mig -c "SELECT id, status FROM prescriptions ORDER BY id"
docker exec ward-db-1 psql -U ward -d postgres -c "DROP DATABASE ward_mig"
```
Expected: no alembic error. The SELECT prints `rx-1 | validated` and `rx-2 | stopped`.

- [ ] **Step 9: Lint and commit**

Run LINT (Global Constraints). Expected: `All checks passed!`
```bash
git add backend/alembic/versions/0007_pharmacy.py backend/app/models/pharmacy.py backend/app/models/clinical.py backend/app/models/__init__.py backend/app/data/pharmacy/formulary.v1.json backend/app/services/pharmacy/__init__.py backend/app/services/pharmacy/formulary.py backend/app/seed.py backend/tests/test_pharmacy_models.py
git commit -m "feat(backend): pharmacy formulary and prescription review columns (migration 0007)"
```

---

### Task 2: The check engine and its rule files

**Files:**
- Create: `backend/app/rules/pharmacy/allergy_synonyms.v1.json`
- Create: `backend/app/rules/pharmacy/interactions.v1.json`
- Create: `backend/app/rules/pharmacy/elderly_caution.v1.json`
- Create: `backend/app/services/pharmacy/checks.py`
- Test: `backend/tests/test_pharmacy_checks.py`

**Interfaces:**
- Consumes: `formulary_entries()` and `FORMULARY` (Task 1), used by tests only.
- Produces (`app.services.pharmacy.checks`):
  - `SEVERITY_RANK: dict[str, int]` = `{"critical": 0, "major": 1, "moderate": 2, "info": 3}`; `RULES_DIR: Path`.
  - Frozen dataclasses:
    - `DrugInfo(id, dci, brand_names=(), atc_code="", unit_mg=None, max_daily_mg=None, allergy_classes=(), interaction_groups=(), high_alert=False)`;
    - `PatientInfo(age: int | None, allergies: tuple[str, ...] = ())`;
    - `RunningItem(prescription_id: str, med: str, drug_id: str | None)`;
    - `Check(code, severity, item_index: int, drug_id: str | None, params: dict, message: str)` with `.as_dict() -> dict`.
  - `norm(s: str) -> str`, `load_rules() -> Rules` (cached), `allergy_classes(allergy: str, rules: Rules) -> set[str]`, `daily_mg(item: dict, drug: DrugInfo) -> float | None`.
  - `run_checks(patient: PatientInfo, items: list[dict], running: list[RunningItem], drugs: dict[str, DrugInfo], rules: Rules | None = None) -> list[Check]`, sorted by `(SEVERITY_RANK, item_index, code)`.
  - `params` per code:
    - `allergy`: `{med, allergy, class}`;
    - `interaction`: `{med, groups[2], note, with_med, with_drug_id, with_item_index, with_prescription_id}`;
    - `max_daily_dose`: `{med, daily_mg, max_daily_mg}`;
    - `duplicate_therapy`: `{med, reason: same_dci|same_atc_class, with_med, with_drug_id, with_item_index, with_prescription_id}`;
    - `non_formulary`: `{med}`;
    - `high_alert`: `{med}`;
    - `elderly`: `{med, age}`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_pharmacy_checks.py`:
```python
"""The pure check engine (pharmacy spec §4): one test per rule, the fr/ar synonyms, the ×2 dose threshold."""

import json
import time

import pytest

from app.services.pharmacy.checks import (RULES_DIR, DrugInfo, PatientInfo, RunningItem, load_rules, norm,
                                          run_checks)
from app.services.pharmacy.formulary import FORMULARY, formulary_entries

DRUGS = {e["id"]: DrugInfo(id=e["id"], dci=e["dci"], brand_names=tuple(e["brand_names"]), atc_code=e["atc_code"],
                           unit_mg=e["unit_mg"], max_daily_mg=e["max_daily_mg"],
                           allergy_classes=tuple(e["allergy_classes"]),
                           interaction_groups=tuple(e["interaction_groups"]), high_alert=e["high_alert"])
         for e in formulary_entries()}
ADULT = PatientInfo(age=40)


def item(drug_id=None, med="X", times=("08:00",), **kw):
    return {"med": med, "drug_id": drug_id, "times": list(times), "units_per_intake": 1, **kw}


def codes(checks):
    return [(c.code, c.severity, c.item_index) for c in checks]


def test_allergy_english():
    checks = run_checks(PatientInfo(40, ("penicillin",)), [item("d-0003")], [], DRUGS)
    assert codes(checks) == [("allergy", "critical", 0)]
    assert checks[0].params == {"med": "X", "allergy": "penicillin", "class": "penicillin"}
    assert checks[0].drug_id == "d-0003"


@pytest.mark.parametrize("allergy", ["Pénicilline", "PENICILLINES", "بنسلين", "البنسلين", "حساسية من البنسلين",
                                     "allergie à la pénicilline", "beta-lactam"])
def test_allergy_french_arabic_and_free_text(allergy):
    assert codes(run_checks(PatientInfo(40, (allergy,)), [item("d-0003")], [], DRUGS)) == [("allergy", "critical", 0)]


def test_sulfa_allergy_flags_cotrimoxazole():
    checks = run_checks(PatientInfo(79, ("sulfa",)), [item("d-0011")], [], DRUGS)
    assert codes(checks) == [("allergy", "critical", 0)] and checks[0].params["class"] == "sulfonamide"


def test_no_false_allergy():
    assert run_checks(PatientInfo(40, ("latex",)), [item("d-0003")], [], DRUGS) == []
    assert run_checks(PatientInfo(40, ("penicillin",)), [item("d-0006")], [], DRUGS) == []


@pytest.mark.parametrize("allergy", ["Ibuprofen", "advil"])
def test_allergy_named_by_drug_or_brand(allergy):
    checks = run_checks(PatientInfo(40, (allergy,)), [item("d-0018")], [], DRUGS)
    assert codes(checks) == [("allergy", "critical", 0)] and checks[0].params["class"] == "ibuprofen"


def test_max_daily_dose_thresholds():
    four = ("06:00", "12:00", "18:00", "23:00")
    assert run_checks(ADULT, [item("d-0001", times=four, units_per_intake=2)], [], DRUGS) == []  # 4000 = max
    major = run_checks(ADULT, [item("d-0001", times=four, units_per_intake=3)], [], DRUGS)  # 6000
    assert codes(major) == [("max_daily_dose", "major", 0)]
    assert major[0].params == {"med": "X", "daily_mg": 6000.0, "max_daily_mg": 4000}
    assert codes(run_checks(ADULT, [item("d-0001", times=four, dose_mg=2000)], [], DRUGS)) == [
        ("max_daily_dose", "major", 0)]  # exactly 2x is still major
    assert codes(run_checks(ADULT, [item("d-0001", times=four, dose_mg=2500)], [], DRUGS)) == [
        ("max_daily_dose", "critical", 0)]  # 10000 > 2 x 4000
    assert run_checks(ADULT, [item("d-0001", times=four, dose_mg=1000, units_per_intake=3)], [], DRUGS) == []


def test_no_dose_check_without_mg_data():
    assert codes(run_checks(ADULT, [item("d-0014", times=("08:00", "20:00"))], [], DRUGS)) == [
        ("high_alert", "info", 0)]


def test_interaction_with_a_running_prescription():
    checks = run_checks(ADULT, [item("d-0018", med="Ibuprofen")], [RunningItem("rx-1", "Warfarin 5 mg", "d-0012")],
                        DRUGS)
    assert codes(checks) == [("interaction", "major", 0)]
    assert checks[0].params == {"med": "Ibuprofen", "groups": ["anticoagulant", "nsaid"], "note": "bleeding risk",
                                "with_med": "Warfarin 5 mg", "with_drug_id": "d-0012", "with_item_index": None,
                                "with_prescription_id": "rx-1"}


def test_interactions_inside_one_prescription():
    checks = run_checks(ADULT, [item("d-0021"), item("d-0045")], [], DRUGS)  # morphine + diazepam
    assert codes(checks) == [("interaction", "critical", 0), ("high_alert", "info", 0)]
    assert checks[0].params["with_item_index"] == 1
    assert codes(run_checks(ADULT, [item("d-0027"), item("d-0030")], [], DRUGS)) == [
        ("interaction", "critical", 0), ("high_alert", "info", 0)]  # KCl IV + spironolactone
    assert codes(run_checks(ADULT, [item("d-0047"), item("d-0022")], [], DRUGS)) == [("interaction", "major", 0)]
    assert run_checks(ADULT, [item("d-0022")], [], DRUGS) == []  # one serotonergic drug alone


def test_duplicate_therapy():
    same = run_checks(ADULT, [item("d-0001"), item("d-0002")], [], DRUGS)
    assert codes(same) == [("duplicate_therapy", "major", 0)] and same[0].params["reason"] == "same_dci"
    cls = run_checks(ADULT, [item("d-0018")], [RunningItem("rx-2", "Ketoprofen", "d-0020")], DRUGS)
    assert codes(cls) == [("duplicate_therapy", "major", 0)]
    assert (cls[0].params["reason"], cls[0].params["with_prescription_id"]) == ("same_atc_class", "rx-2")


def test_non_formulary_item():
    checks = run_checks(PatientInfo(40, ("penicillin",)), [item(None, med="Herbal tea")],
                        [RunningItem("rx-3", "Unknown", None)], DRUGS)
    assert codes(checks) == [("non_formulary", "moderate", 0)]
    assert (checks[0].drug_id, checks[0].params) == (None, {"med": "Herbal tea"})


def test_high_alert_and_elderly():
    assert codes(run_checks(ADULT, [item("d-0012")], [], DRUGS)) == [("high_alert", "info", 0)]
    assert codes(run_checks(PatientInfo(75), [item("d-0045")], [], DRUGS)) == [("elderly", "moderate", 0)]
    assert run_checks(PatientInfo(74), [item("d-0045")], [], DRUGS) == []
    assert run_checks(PatientInfo(None), [item("d-0045")], [], DRUGS) == []


def test_sorted_by_severity_then_item():
    checks = run_checks(PatientInfo(80, ("penicillin",)), [item("d-0045"), item("d-0003"), item("d-0021")], [],
                        DRUGS)
    assert codes(checks) == [("interaction", "critical", 0), ("allergy", "critical", 1), ("elderly", "moderate", 0),
                             ("high_alert", "info", 2)]
    assert set(checks[0].as_dict()) == {"code", "severity", "item_index", "drug_id", "params", "message"}
    assert checks == run_checks(PatientInfo(80, ("penicillin",)),
                                [item("d-0045"), item("d-0003"), item("d-0021")], [], DRUGS)  # deterministic


def test_under_20_ms():
    items = [item(d) for d in ("d-0001", "d-0003", "d-0006", "d-0012", "d-0018", "d-0021", "d-0045", "d-0047")]
    ids = list(DRUGS)
    running = [RunningItem(f"rx-{n}", "x", ids[n % len(ids)]) for n in range(30)]
    patient = PatientInfo(80, ("penicillin", "sulfa", "بنسلين"))
    run_checks(patient, items, running, DRUGS)  # warm the rule cache
    best = min(_timed(lambda: run_checks(patient, items, running, DRUGS)) for _ in range(5))
    assert best < 0.020


def _timed(fn) -> float:
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


def test_rule_files_are_consistent_and_labelled():
    rules = load_rules()
    classes = set(json.loads((RULES_DIR / "allergy_synonyms.v1.json").read_text("utf-8"))["classes"])
    entries = formulary_entries()
    assert all(set(e["allergy_classes"]) <= classes for e in entries)
    groups = {g for e in entries for g in e["interaction_groups"]}
    assert all(r.a in groups and r.b in groups and r.severity in ("critical", "major", "moderate")
               for r in rules.interactions)
    assert rules.elderly_dci <= {norm(e["dci"]) for e in entries} and rules.elderly_min_age == 75
    for name in ("allergy_synonyms.v1.json", "interactions.v1.json", "elderly_caution.v1.json"):
        assert "not a clinical reference" in json.loads((RULES_DIR / name).read_text("utf-8"))["note"]
    assert "not a clinical reference" in json.loads(FORMULARY.read_text("utf-8"))["note"]
    demo = {"amoxicillin", "azithromycin", "warfarin", "ibuprofen", "enoxaparin", "insulin glargine", "morphine",
            "potassium chloride", "metformin", "furosemide", "amlodipine", "paracetamol"}
    assert demo <= {norm(e["dci"]) for e in entries}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_pharmacy_checks.py`
Expected: it fails during collection with `ModuleNotFoundError: No module named 'app.services.pharmacy.checks'`.

- [ ] **Step 3: Rule files**

`backend/app/rules/pharmacy/allergy_synonyms.v1.json`:
```json
{
  "version": 1,
  "note": "Illustrative, not a clinical reference; to be validated by the hospital's pharmacists. A patient allergy matches a class when one of its terms appears as a whole word, after lower-casing and removing accents and Arabic marks. The class name itself is also a term.",
  "classes": {
    "penicillin": ["penicillin", "penicillins", "pénicilline", "pénicillines", "بنسلين", "البنسلين", "amoxicillin", "amoxicilline", "أموكسيسيلين", "augmentin"],
    "beta_lactam": ["beta-lactam", "beta-lactams", "bêta-lactamine", "bêta-lactamines", "betalactamine", "بيتا لاكتام"],
    "cephalosporin": ["cephalosporin", "cephalosporins", "céphalosporine", "céphalosporines", "سيفالوسبورين"],
    "macrolide": ["macrolide", "macrolides", "azithromycin", "azithromycine", "clarithromycin", "clarithromycine", "ماكروليد"],
    "fluoroquinolone": ["fluoroquinolone", "fluoroquinolones", "quinolone", "quinolones", "فلوروكينولون"],
    "nitroimidazole": ["metronidazole", "métronidazole", "flagyl", "ميترونيدازول"],
    "sulfonamide": ["sulfa", "sulfas", "sulfonamide", "sulfonamides", "sulfamide", "sulfamides", "bactrim", "سلفا", "السلفا"],
    "nsaid": ["nsaid", "nsaids", "ains", "anti-inflammatoire", "anti-inflammatoires", "مضادات الالتهاب"],
    "aspirin": ["aspirin", "aspirine", "acetylsalicylic acid", "acide acétylsalicylique", "أسبرين", "الأسبرين"],
    "paracetamol": ["paracétamol", "acetaminophen", "باراسيتامول"],
    "heparin": ["héparine", "هيبارين", "الهيبارين"],
    "opioid": ["opioids", "opiacé", "opiacés", "opiate", "opiates", "morphine", "codeine", "codéine", "مورفين", "المورفين"],
    "sulfonylurea": ["sulfonylureas", "sulfonylurée", "sulfonylurées"]
  }
}
```

`backend/app/rules/pharmacy/interactions.v1.json`:
```json
{
  "version": 1,
  "note": "Illustrative, not a clinical reference; to be validated by the hospital's pharmacists. A pair matches when one drug carries the first group and another drug the second (either order). Severity: critical, major or moderate.",
  "pairs": [
    {"groups": ["opioid", "benzodiazepine"], "severity": "critical", "note": "respiratory depression"},
    {"groups": ["potassium", "potassium_sparing"], "severity": "critical", "note": "hyperkalaemia"},
    {"groups": ["anticoagulant", "nsaid"], "severity": "major", "note": "bleeding risk"},
    {"groups": ["anticoagulant", "antiplatelet"], "severity": "major", "note": "bleeding risk"},
    {"groups": ["anticoagulant", "anticoagulant"], "severity": "major", "note": "double anticoagulation, bleeding risk"},
    {"groups": ["potassium", "ace_inhibitor"], "severity": "major", "note": "hyperkalaemia"},
    {"groups": ["potassium", "arb"], "severity": "major", "note": "hyperkalaemia"},
    {"groups": ["ace_inhibitor", "potassium_sparing"], "severity": "major", "note": "hyperkalaemia"},
    {"groups": ["macrolide_cyp3a4", "statin_cyp3a4"], "severity": "major", "note": "myopathy, rhabdomyolysis"},
    {"groups": ["serotonergic", "serotonergic"], "severity": "major", "note": "serotonin syndrome"},
    {"groups": ["opioid", "opioid"], "severity": "major", "note": "additive respiratory depression"},
    {"groups": ["qt_prolonging", "qt_prolonging"], "severity": "moderate", "note": "QT prolongation"},
    {"groups": ["cardiac_glycoside", "loop_diuretic"], "severity": "moderate", "note": "low potassium raises digoxin toxicity"},
    {"groups": ["nsaid", "ace_inhibitor"], "severity": "moderate", "note": "weaker blood-pressure control, kidney injury"},
    {"groups": ["nsaid", "loop_diuretic"], "severity": "moderate", "note": "weaker diuretic effect, kidney injury"}
  ]
}
```

`backend/app/rules/pharmacy/elderly_caution.v1.json`:
```json
{
  "version": 1,
  "note": "Illustrative Beers-style list, not a clinical reference; to be validated by the hospital's pharmacists.",
  "min_age": 75,
  "dci": ["Diazepam", "Alprazolam", "Amitriptyline", "Haloperidol", "Digoxin", "Ibuprofen", "Diclofenac", "Ketoprofen", "Tramadol", "Gliclazide"]
}
```

- [ ] **Step 4: The engine**

`backend/app/services/pharmacy/checks.py`:
```python
"""Prescription safety checks (pharmacy spec §4). Pure and deterministic: no database, no clock, no LLM.

The engine only flags; a pharmacist decides. `message` is English for logs; the web translates by `code` + `params`.
Rule files: app/rules/pharmacy/*.v1.json (illustrative, not a clinical reference; to be validated by the hospital's
pharmacists).
"""

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parents[2] / "rules" / "pharmacy"
SEVERITY_RANK = {"critical": 0, "major": 1, "moderate": 2, "info": 3}


@dataclass(frozen=True)
class DrugInfo:
    """The formulary facts the checks need (one `drugs` row)."""

    id: str
    dci: str
    brand_names: tuple[str, ...] = ()
    atc_code: str = ""
    unit_mg: float | None = None
    max_daily_mg: float | None = None
    allergy_classes: tuple[str, ...] = ()
    interaction_groups: tuple[str, ...] = ()
    high_alert: bool = False


@dataclass(frozen=True)
class PatientInfo:
    age: int | None
    allergies: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunningItem:
    """One item of another running prescription of the same patient."""

    prescription_id: str
    med: str
    drug_id: str | None


@dataclass(frozen=True)
class Check:
    code: str
    severity: str  # critical | major | moderate | info
    item_index: int
    drug_id: str | None
    params: dict = field(default_factory=dict)
    message: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class InteractionRule:
    a: str
    b: str
    severity: str
    note: str


@dataclass(frozen=True)
class Rules:
    synonyms: tuple[tuple[str, str], ...]  # (normalised term, allergy class)
    interactions: tuple[InteractionRule, ...]
    elderly_dci: frozenset[str]
    elderly_min_age: int


def norm(s: str) -> str:
    """Casefold, drop accents and Arabic marks, and collapse spaces/dashes/underscores: 'Pénicilline' → 'penicilline',
    'أسبرين' → 'اسبرين', 'beta_lactam' → 'beta lactam'."""
    s = unicodedata.normalize("NFKD", (s or "").casefold())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[\s\-_/']+", " ", s).strip()


def _read(name: str) -> dict:
    return json.loads((RULES_DIR / name).read_text(encoding="utf-8"))


@lru_cache
def load_rules() -> Rules:
    syn = _read("allergy_synonyms.v1.json")["classes"]
    pairs = tuple((norm(term), cls) for cls, terms in syn.items() for term in (cls, *terms))
    inter = tuple(InteractionRule(p["groups"][0], p["groups"][1], p["severity"], p["note"])
                  for p in _read("interactions.v1.json")["pairs"])
    eld = _read("elderly_caution.v1.json")
    return Rules(pairs, inter, frozenset(norm(d) for d in eld["dci"]), int(eld["min_age"]))


def allergy_classes(allergy: str, rules: Rules) -> set[str]:
    """The allergy classes a patient's allergy text names (whole-word match of any synonym, any language)."""
    text = norm(allergy)
    return {cls for term, cls in rules.synonyms
            if term and (text == term or re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text))}


def daily_mg(item: dict, drug: DrugInfo) -> float | None:
    """mg per day: `dose_mg` (per intake) or units_per_intake × unit_mg, times the intakes per day."""
    per = item.get("dose_mg")
    if per is None and drug.unit_mg is not None:
        per = int(item.get("units_per_intake") or 1) * drug.unit_mg
    return None if per is None else float(per) * len(item.get("times") or [])


def _duplicate(a: DrugInfo, b: DrugInfo) -> str | None:
    if norm(a.dci) == norm(b.dci):
        return "same_dci"
    if len(a.atc_code) >= 5 and a.atc_code[:5] == b.atc_code[:5]:
        return "same_atc_class"
    return None


def _interactions(a: DrugInfo, b: DrugInfo, rules: Rules) -> list[InteractionRule]:
    ga, gb = set(a.interaction_groups), set(b.interaction_groups)
    return [r for r in rules.interactions if (r.a in ga and r.b in gb) or (r.b in ga and r.a in gb)]


def _single(i: int, item: dict, d: DrugInfo, patient: PatientInfo, patient_classes: dict[str, str],
            rules: Rules) -> list[Check]:
    """Checks that look at one item alone: allergy, daily dose, high alert, elderly."""
    med = item.get("med", "")
    out: list[Check] = []
    hit = next(((c, patient_classes[c]) for c in d.allergy_classes if c in patient_classes), None)
    if hit is None:  # an allergy written as the drug's own name or brand
        names = {norm(d.dci), *(norm(b) for b in d.brand_names)}
        direct = next((a for a in patient.allergies if norm(a) in names), None)
        hit = (norm(d.dci), direct) if direct else None
    if hit:
        out.append(Check("allergy", "critical", i, d.id, {"med": med, "allergy": hit[1], "class": hit[0]},
                         f"{d.dci}: the patient is allergic to {hit[1]} ({hit[0]})"))
    daily = daily_mg(item, d) if d.max_daily_mg else None
    if daily is not None and daily > d.max_daily_mg:
        sev = "critical" if daily > 2 * d.max_daily_mg else "major"
        out.append(Check("max_daily_dose", sev, i, d.id,
                         {"med": med, "daily_mg": daily, "max_daily_mg": d.max_daily_mg},
                         f"{d.dci}: {daily:g} mg/day is above the {d.max_daily_mg:g} mg/day maximum"))
    if d.high_alert:
        out.append(Check("high_alert", "info", i, d.id, {"med": med}, f"{d.dci}: high-alert drug, double-check"))
    if patient.age is not None and patient.age >= rules.elderly_min_age and norm(d.dci) in rules.elderly_dci:
        out.append(Check("elderly", "moderate", i, d.id, {"med": med, "age": patient.age},
                         f"{d.dci}: use with caution at age {patient.age}"))
    return out


def run_checks(patient: PatientInfo, items: list[dict], running: list[RunningItem], drugs: dict[str, DrugInfo],
               rules: Rules | None = None) -> list[Check]:
    """Every check for the candidate `items` against each other and the patient's other running prescriptions,
    most severe first (then by item index, then by code). Items without a known drug are only `non_formulary`."""
    rules = rules or load_rules()
    patient_classes: dict[str, str] = {}
    for a in patient.allergies:
        for c in sorted(allergy_classes(a, rules)):
            patient_classes.setdefault(c, a)
    out: list[Check] = []
    cands: list[tuple[int, dict, DrugInfo]] = []
    for i, it in enumerate(items):
        d = drugs.get(it.get("drug_id") or "")
        if d is None:
            med = it.get("med", "")
            out.append(Check("non_formulary", "moderate", i, None, {"med": med},
                             f"{med}: not in the hospital formulary"))
            continue
        cands.append((i, it, d))
        out += _single(i, it, d, patient, patient_classes, rules)
    others = [(r, drugs[r.drug_id]) for r in running if r.drug_id and r.drug_id in drugs]
    for n, (i, it, d) in enumerate(cands):
        med = it.get("med", "")
        partners = [(j, jt.get("med", ""), e, None) for j, jt, e in cands[n + 1:]]
        partners += [(None, r.med, e, r.prescription_id) for r, e in others]
        for j, other_med, e, rx_id in partners:
            with_ = {"with_med": other_med, "with_drug_id": e.id, "with_item_index": j,
                     "with_prescription_id": rx_id}
            reason = _duplicate(d, e)
            if reason:
                out.append(Check("duplicate_therapy", "major", i, d.id, {"med": med, "reason": reason, **with_},
                                 f"{d.dci} duplicates {other_med} ({reason})"))
            for rule in _interactions(d, e, rules):
                out.append(Check("interaction", rule.severity, i, d.id,
                                 {"med": med, "groups": [rule.a, rule.b], "note": rule.note, **with_},
                                 f"{d.dci} + {other_med}: {rule.note}"))
    return sorted(out, key=lambda c: (SEVERITY_RANK[c.severity], c.item_index, c.code))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_pharmacy_checks.py`
Expected: all pass.

- [ ] **Step 6: Lint and commit**

Run LINT. Then:
```bash
git add backend/app/rules/pharmacy backend/app/services/pharmacy/checks.py backend/tests/test_pharmacy_checks.py
git commit -m "feat(backend): deterministic prescription check engine and rule files"
```

---

### Task 3: The drug catalogue router

**Files:**
- Modify: `backend/app/services/pharmacy/formulary.py` (catalogue helpers)
- Modify: `backend/app/schemas.py` (add `# --- pharmacy ---` section)
- Create: `backend/app/routers/drugs.py`
- Modify: `backend/app/main.py` (include the router)
- Modify: `backend/tests/helpers.py` (add `pharmacist`)
- Test: `backend/tests/test_drugs_api.py`

**Interfaces:**
- Consumes: `Drug` (Task 1), `require_roles`, `audit`, `iso`, `new_id`.
- Produces:
  - `formulary.drug_out(d: Drug) -> dict`: the `Drug` shape `{id, dci, brand_names[], form, strength, unit_mg, max_daily_mg, atc_code, allergy_classes[], interaction_groups[], high_alert, min_stock, active, created_at, updated_at}`;
  - `formulary.search(db, q: str, active: str) -> list[Drug]`, where `active` is `"true"|"false"|"all"` (max 50);
  - `formulary.create_drug(db, data: dict) -> Drug`;
  - `formulary.update_drug(db, d: Drug, changes: dict) -> Drug`;
  - schemas `DrugIn`, `DrugPatch`, `Comment` (an `Annotated[str, …]` trimmed to 1–500 characters, used from Task 5);
  - the test helper `tests.helpers.pharmacist(client, db, email="ph.t@medora.tn", name="Pharm Test") -> dict`, which returns auth headers.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/helpers.py`:
```python
def pharmacist(client, db, email: str = "ph.t@medora.tn", name: str = "Pharm Test") -> dict:
    """An active pharmacist account (no staff row) and its auth headers."""
    make_user(db, email, role="pharmacist", name=name)
    return login(client, email)
```

`backend/tests/test_drugs_api.py`:
```python
"""GET/POST/PATCH /drugs (api 1.12 → Drug catalogue)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, Drug
from tests.helpers import login, pharmacist

NEW = {"dci": "Nitrofurantoin", "brand_names": ["Furadantine"], "form": "capsule", "strength": "50 mg", "unit_mg": 50,
       "max_daily_mg": 400, "atc_code": "j01xe01", "allergy_classes": [" Nitrofuran "], "interaction_groups": [],
       "high_alert": False, "min_stock": 20}


def _ids(rows):
    return {r["id"] for r in rows}


@pytest.mark.parametrize("q,expected", [("amox", {"d-0003", "d-0004", "d-0005"}), ("doliprane", {"d-0001", "d-0002"}),
                                        ("J01FA", {"d-0006", "d-0007"}), ("j01fa", {"d-0006", "d-0007"})])
def test_search_by_dci_brand_or_atc(client, q, expected):
    r = client.get("/drugs", params={"q": q}, headers=login(client, "doctor@medora.tn"))
    assert r.status_code == 200 and _ids(r.json()) == expected


def test_search_shape_and_limit(client):
    rows = client.get("/drugs", headers=login(client, "nurse@medora.tn")).json()
    assert len(rows) == 50  # 51 drugs, capped
    assert set(rows[0]) == {"id", "dci", "brand_names", "form", "strength", "unit_mg", "max_daily_mg", "atc_code",
                            "allergy_classes", "interaction_groups", "high_alert", "min_stock", "active", "created_at",
                            "updated_at"}
    amox = next(r for r in client.get("/drugs", params={"q": "clamoxyl"},
                                      headers=login(client, "nurse@medora.tn")).json() if r["id"] == "d-0003")
    assert (amox["unit_mg"], amox["max_daily_mg"], amox["active"]) == (1000.0, 6000.0, True)


@pytest.mark.parametrize("q", ["%", "_", "باراسيتامول", "a'b"])
def test_search_input_is_literal(client, q):
    r = client.get("/drugs", params={"q": q}, headers=login(client, "doctor@medora.tn"))
    assert r.status_code == 200 and r.json() == []


def test_read_roles(client):
    for email in ("doctor@medora.tn", "nurse@medora.tn", "admin@medora.tn"):
        assert client.get("/drugs", headers=login(client, email)).status_code == 200
    assert client.get("/drugs", headers=login(client, "patient@medora.tn")).status_code == 403
    assert client.get("/drugs").status_code == 401


def test_pharmacist_creates_a_drug(client, db):
    r = client.post("/drugs", headers=pharmacist(client, db), json=NEW)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["id"].startswith("d-") and (d["atc_code"], d["allergy_classes"], d["active"]) == (
        "J01XE01", ["nitrofuran"], True)
    assert db.scalar(select(AuditLog.id).where(AuditLog.resource == "drug", AuditLog.action == "create",
                                               AuditLog.resource_id == d["id"]))
    again = client.post("/drugs", headers=login(client, "ph.t@medora.tn"), json={**NEW, "dci": "nitrofurantoin"})
    assert again.status_code == 409 and again.json()["code"] == "conflict"


def test_who_may_write(client, db):
    assert client.post("/drugs", headers=login(client, "doctor@medora.tn"), json=NEW).status_code == 403
    assert client.post("/drugs", headers=login(client, "nurse@medora.tn"), json=NEW).status_code == 403
    assert client.post("/drugs", headers=login(client, "admin@medora.tn"), json=NEW).status_code == 201
    assert client.patch("/drugs/d-0001", headers=login(client, "doctor@medora.tn"),
                        json={"min_stock": 1}).status_code == 403


@pytest.mark.parametrize("bad", [{"form": "powder"}, {"atc_code": "XYZ"}, {"allergy_classes": ["Penicillin!"]},
                                 {"unit_mg": 0}, {"min_stock": -1}, {"dci": ""}, {"colour": "red"}])
def test_invalid_drug_is_422(client, db, bad):
    r = client.post("/drugs", headers=pharmacist(client, db), json={**NEW, **bad})
    assert r.status_code == 422 and r.json()["code"] == "invalid"


def test_patch_and_deactivate(client, db):
    h = pharmacist(client, db)
    r = client.patch("/drugs/d-0041", headers=h, json={"min_stock": 30, "brand_names": ["Mopral", "Zoltum"]})
    assert r.status_code == 200 and (r.json()["min_stock"], r.json()["brand_names"]) == (30, ["Mopral", "Zoltum"])
    assert client.patch("/drugs/d-0041", headers=h, json={"active": False}).json()["active"] is False
    assert "d-0041" not in _ids(client.get("/drugs", params={"q": "omepra"}, headers=h).json())
    assert _ids(client.get("/drugs", params={"q": "omepra", "active": "false"}, headers=h).json()) == {"d-0041"}
    assert "d-0041" in _ids(client.get("/drugs", params={"q": "omepra", "active": "all"}, headers=h).json())
    assert db.get(Drug, "d-0041") is not None  # deactivated, never deleted
    assert client.patch("/drugs/d-0041", headers=h, json={"dci": None}).status_code == 422
    assert client.patch("/drugs/d-9999", headers=h, json={"min_stock": 1}).status_code == 404
    assert client.patch("/drugs/d-0002", headers=h, json={"strength": "500 mg"}).status_code == 409  # = d-0001
    assert client.delete("/drugs/d-0041", headers=h).status_code == 405
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_drugs_api.py`
Expected: FAIL with 404s, because `/drugs` doesn't exist yet.

- [ ] **Step 3: Schemas**

Append to `backend/app/schemas.py`. Add `Literal` to the typing import and `StringConstraints` to the pydantic import.
```python
# --- pharmacy (api 1.12) ---
Comment = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
DrugForm = Literal["tablet", "capsule", "syrup", "injection", "inhaler", "patch", "drops", "other"]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[a-z][a-z0-9_]{0,39}$")]
Brand = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Dci = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Strength = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
Atc = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^$|^[A-Z]\d{2}[A-Z]{2}\d{2}$")]


class DrugIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dci: Dci
    brand_names: list[Brand] = Field(default_factory=list, max_length=20)
    form: DrugForm
    strength: Strength = ""
    unit_mg: float | None = Field(default=None, gt=0, le=100000)
    max_daily_mg: float | None = Field(default=None, gt=0, le=1000000)
    atc_code: Atc = ""
    allergy_classes: list[Tag] = Field(default_factory=list, max_length=20)
    interaction_groups: list[Tag] = Field(default_factory=list, max_length=20)
    high_alert: bool = False
    min_stock: int = Field(default=0, ge=0, le=1000000)
    active: bool = True


class DrugPatch(BaseModel):
    """Only the fields sent change. `unit_mg` and `max_daily_mg` may be set to null; the others may not."""

    model_config = ConfigDict(extra="forbid")
    dci: Dci | None = None
    brand_names: list[Brand] | None = Field(default=None, max_length=20)
    form: DrugForm | None = None
    strength: Strength | None = None
    unit_mg: float | None = Field(default=None, gt=0, le=100000)
    max_daily_mg: float | None = Field(default=None, gt=0, le=1000000)
    atc_code: Atc | None = None
    allergy_classes: list[Tag] | None = Field(default=None, max_length=20)
    interaction_groups: list[Tag] | None = Field(default=None, max_length=20)
    high_alert: bool | None = None
    min_stock: int | None = Field(default=None, ge=0, le=1000000)
    active: bool | None = None
```

- [ ] **Step 4: Catalogue helpers**

Append to `backend/app/services/pharmacy/formulary.py`. Extend the imports with `from decimal import Decimal`, `from sqlalchemy import Text, cast, func, or_`, `from app.errors import ApiError`, `from app.ids import new_id` and `from app.schemas import iso`.
```python
SEARCH_LIMIT = 50
NULLABLE = {"unit_mg", "max_daily_mg"}


def _num(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def drug_out(d: Drug) -> dict:
    return {"id": d.id, "dci": d.dci, "brand_names": list(d.brand_names or []), "form": d.form,
            "strength": d.strength, "unit_mg": _num(d.unit_mg), "max_daily_mg": _num(d.max_daily_mg),
            "atc_code": d.atc_code, "allergy_classes": list(d.allergy_classes or []),
            "interaction_groups": list(d.interaction_groups or []), "high_alert": d.high_alert,
            "min_stock": d.min_stock, "active": d.active, "created_at": iso(d.created_at),
            "updated_at": iso(d.updated_at)}


def _like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(db: Session, q: str, active: str) -> list[Drug]:
    """DCI or brand (substring) or ATC code (prefix), case-insensitive; `active` is true | false | all."""
    stmt = select(Drug)
    if active != "all":
        stmt = stmt.where(Drug.active.is_(active == "true"))
    q = q.strip()
    if q:
        sub, pre = f"%{_like(q)}%", f"{_like(q)}%"
        stmt = stmt.where(or_(Drug.dci.ilike(sub, escape="\\"), cast(Drug.brand_names, Text).ilike(sub, escape="\\"),
                              Drug.atc_code.ilike(pre, escape="\\")))
    return list(db.scalars(stmt.order_by(Drug.dci, Drug.strength, Drug.id).limit(SEARCH_LIMIT)))


def _duplicate(db: Session, dci: str, strength: str, form: str, exclude_id: str | None = None) -> bool:
    stmt = select(Drug.id).where(func.lower(Drug.dci) == dci.lower(), Drug.strength == strength, Drug.form == form)
    if exclude_id:
        stmt = stmt.where(Drug.id != exclude_id)
    return db.scalar(stmt.limit(1)) is not None


def create_drug(db: Session, data: dict) -> Drug:
    if _duplicate(db, data["dci"], data["strength"], data["form"]):
        raise ApiError(409, "conflict", "this drug, strength and form is already in the formulary")
    d = Drug(id=new_id(db, "d"), **data)
    db.add(d)
    db.flush()
    db.refresh(d)
    return d


def update_drug(db: Session, d: Drug, changes: dict) -> Drug:
    nulls = sorted(k for k, v in changes.items() if v is None and k not in NULLABLE)
    if nulls:
        raise ApiError(422, "invalid", f"{nulls[0]}: cannot be null")
    merged = {k: changes.get(k, getattr(d, k)) for k in ("dci", "strength", "form")}
    if _duplicate(db, merged["dci"], merged["strength"], merged["form"], exclude_id=d.id):
        raise ApiError(409, "conflict", "this drug, strength and form is already in the formulary")
    for k, v in changes.items():
        setattr(d, k, v)
    db.flush()
    db.refresh(d)
    return d
```

- [ ] **Step 5: Router**

`backend/app/routers/drugs.py`:
```python
"""The hospital drug catalogue (api.md 1.12 → Drug catalogue). Read: staff. Write: pharmacist, admin. Never deleted."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.db import get_db
from app.errors import not_found
from app.models import Drug, User
from app.schemas import DrugIn, DrugPatch
from app.services.audit import audit
from app.services.pharmacy import formulary as F

router = APIRouter(prefix="/drugs", tags=["drugs"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("")
def search(q: str = Query("", max_length=80), active: Literal["true", "false", "all"] = "true",
           user: User = Depends(require_roles("doctor", "nurse", "pharmacist", "admin")),
           db: Session = Depends(get_db)) -> list[dict]:
    return [F.drug_out(d) for d in F.search(db, q, active)]  # no patient data: not audited


@router.post("", status_code=201)
def create(body: DrugIn, request: Request, user: User = Depends(require_roles("pharmacist", "admin")),
           db: Session = Depends(get_db)) -> dict:
    d = F.create_drug(db, body.model_dump())
    audit(db, user, "create", "drug", d.id, ip=_ip(request))
    out = F.drug_out(d)
    db.commit()
    return out


@router.patch("/{drug_id}")
def update(drug_id: str, body: DrugPatch, request: Request,
           user: User = Depends(require_roles("pharmacist", "admin")), db: Session = Depends(get_db)) -> dict:
    d = db.get(Drug, drug_id)
    if d is None:
        raise not_found("drug")
    F.update_drug(db, d, body.model_dump(exclude_unset=True))
    audit(db, user, "update", "drug", d.id, ip=_ip(request))
    out = F.drug_out(d)
    db.commit()
    return out
```
In `backend/app/main.py`, add `drugs` to the `from app.routers import …` line and `app.include_router(drugs.router)` after `prescriptions.router`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_drugs_api.py`
Expected: all pass.

- [ ] **Step 7: Lint and commit**

Run LINT. Then:
```bash
git add backend/app/services/pharmacy/formulary.py backend/app/schemas.py backend/app/routers/drugs.py backend/app/main.py backend/tests/helpers.py backend/tests/test_drugs_api.py
git commit -m "feat(backend): drug catalogue routes (/drugs)"
```

---

### Task 4: The status machine and the doctor side of prescribing

**Files:**
- Create: `backend/app/services/pharmacy/workflow.py`
- Modify: `backend/app/services/pharmacy/formulary.py` (`to_info`, `drug_infos`)
- Modify: `backend/app/schemas.py` (`RxItemIn`, `PrescriptionIn`, new `PrescriptionCheckIn`, `PrescriptionPatch`; delete the now-unused `PrescriptionOut` and `PrescriptionPublished`)
- Modify: `backend/app/routers/prescriptions.py` (rewrite)
- Modify: `backend/app/routers/patients.py:86-95` (`get_prescriptions`)
- Modify: `backend/app/services/record_sources.py:93-101` (the prescription label)
- Modify: `backend/tests/test_rx_devices_api.py` (`test_prescribe_publishes_schedule`, `test_prescribe_patient_without_device`, `test_stop_prescription`)
- Test: `backend/tests/test_prescribing.py`

**Interfaces:**
- Consumes:
  - `run_checks`, `Check`, `PatientInfo`, `RunningItem`, `DrugInfo` (Task 2);
  - `schedule.rebuild_doses / push_schedule / device_of / today_local`;
  - `app.iot.ingest.frame(db, type_, data, patient_id) -> dict`;
  - `publisher.publish_ws_frame`.
- Produces (`app.services.pharmacy.workflow`, imported as `W`):
  - `LIVE = ("pending_pharmacy", "changes_requested", "validated")`;
  - `derive_active(status, urgent) -> bool`; `running_clause()` (SQL); `set_status(rx, status) -> bool` (True when `active` changed);
  - `lock(db, rx_id) -> Prescription` (FOR UPDATE, 404); `chain(db, rx) -> list[Prescription]` (ancestors, nearest first);
  - `age_on(dob, today) -> int | None`; `patient_info(p) -> PatientInfo`;
  - `ensure_drugs(db, items) -> None` (422 `unknown_drug`);
  - `checks_for(db, patient, items, exclude: set[str]) -> list[Check]`;
  - `replace_target(db, replaces_id, patient_id, *, lock_row: bool) -> Prescription`; `exclusions(db, old) -> set[str]`;
  - `@dataclass Outcome(rx, touched: list[Prescription], doses_changed: bool)`;
  - `create(db, doctor, patient, body: PrescriptionIn) -> Outcome`; `stop(db, rx) -> Outcome`;
  - `apply_doses(db, out) -> tuple[bool, int | None]` (published, schedule_version); `status_frames(db, out) -> list[dict]`;
  - `rx_out(db, rx, *, for_patient=False) -> dict`.
- `formulary.to_info(d: Drug) -> DrugInfo` and `formulary.drug_infos(db, ids: set[str]) -> dict[str, DrugInfo]` load inactive drugs too.
- The Prescription shape (doctor, nurse and pharmacist) has these keys: `id, patient_id, doctor_id, items, care_plan, active, created_at, status, urgent, version, replaces_id, checks, override_reason, review_comment, reviewed_by_name, reviewed_at`. The patient shape is `id, patient_id, doctor_id, items, care_plan, active, created_at, status`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_prescribing.py`:
```python
"""The doctor side (api 1.12 → Prescriptions): dry run, gate, urgent, override, versions, stop, shapes."""

from sqlalchemy import select

from app.models import AuditLog, MedDose, Patient, Prescription
from app.services import schedule
from tests.helpers import login, pharmacist

DOC = "doctor@medora.tn"
RX_OK = {"patient_id": "p-0001", "care_plan": "",
         "items": [{"med": "Omeprazole 20 mg", "drug_id": "d-0041", "times": ["20:00"], "slot": 3, "days": 3}]}
RX_ALLERGY = {"patient_id": "p-0001", "care_plan": "",
              "items": [{"med": "Amoxicillin 1 g", "drug_id": "d-0003", "dose_mg": 1000,
                         "times": ["08:00", "14:00", "20:00"], "days": 7}]}
DOCTOR_KEYS = {"id", "patient_id", "doctor_id", "items", "care_plan", "active", "created_at", "status", "urgent",
               "version", "replaces_id", "checks", "override_reason", "review_comment", "reviewed_by_name",
               "reviewed_at"}
PATIENT_KEYS = {"id", "patient_id", "doctor_id", "items", "care_plan", "active", "created_at", "status"}


def _post(client, body, **extra):
    return client.post("/prescriptions", headers=login(client, DOC), json={**body, **extra})


def _future(db, rx_id):
    return db.scalars(select(MedDose).where(MedDose.prescription_id == rx_id,
                                            MedDose.scheduled_at > schedule.now_utc())).all()


def _frames(published):
    return [p["data"] for t, p, *_ in published if t == "ward/internal/ws" and p.get("type") == "prescription_status"]


def test_check_is_a_dry_run(client, db):
    before = db.query(Prescription).count()
    r = client.post("/prescriptions/check", headers=login(client, DOC),
                    json={"patient_id": "p-0001", "items": RX_ALLERGY["items"]})
    assert r.status_code == 200, r.text
    checks = r.json()["checks"]
    assert [(c["code"], c["severity"], c["item_index"], c["drug_id"]) for c in checks] == [
        ("allergy", "critical", 0, "d-0003")]
    assert set(checks[0]) == {"code", "severity", "item_index", "drug_id", "params", "message"}
    assert db.query(Prescription).count() == before
    assert db.scalar(select(AuditLog.id).where(AuditLog.resource == "prescription_check",
                                               AuditLog.patient_id == "p-0001"))


def test_check_permissions(client):
    body = {"patient_id": "p-0001", "items": RX_OK["items"]}
    assert client.post("/prescriptions/check", headers=login(client, "nurse@medora.tn"), json=body).status_code == 403
    assert client.post("/prescriptions/check", headers=login(client, DOC),
                       json={**body, "patient_id": "p-0007"}).status_code == 403
    assert client.post("/prescriptions/check", headers=login(client, DOC),
                       json={**body, "patient_id": "p-9999"}).status_code == 404


def test_new_prescription_waits_for_the_pharmacist(client, db, published):
    r = _post(client, RX_OK)
    assert r.status_code == 201, r.text
    b = r.json()
    assert (b["status"], b["active"], b["urgent"], b["version"], b["replaces_id"], b["checks"]) == (
        "pending_pharmacy", False, False, 1, None, [])
    assert set(b) == DOCTOR_KEYS | {"schedule_version", "published_to_device"} and b["published_to_device"] is False
    assert db.query(MedDose).filter_by(prescription_id=b["id"]).count() == 0
    assert not [p for p in published if p[0].endswith("/schedule")]
    assert {"prescription_id": b["id"], "patient_id": "p-0001", "status": "pending_pharmacy",
            "urgent": False} in _frames(published)


def test_urgent_starts_now(client, db, published):
    b = _post(client, RX_OK, urgent=True).json()
    assert (b["status"], b["active"], b["urgent"], b["published_to_device"]) == ("pending_pharmacy", True, True, True)
    assert db.query(MedDose).filter_by(prescription_id=b["id"]).count() == 3
    assert [p for p in published if p[0] == "hospital/device/bsu-001/schedule"]


def test_critical_needs_an_override_reason(client, db):
    before = db.query(Prescription).count()
    for extra in ({}, {"override_reason": "   "}):
        r = _post(client, RX_ALLERGY, **extra)
        assert r.status_code == 422 and r.json()["code"] == "override_required"
    assert db.query(Prescription).count() == before
    b = _post(client, RX_ALLERGY, override_reason=" Severe infection ").json()
    assert (b["override_reason"], b["checks"][0]["code"], b["status"]) == (
        "Severe infection", "allergy", "pending_pharmacy")


def test_unknown_or_inactive_drug_is_422(client, db):
    ghost = [{"med": "Ghost", "drug_id": "d-9999", "times": ["08:00"]}]
    for url in ("/prescriptions/check", "/prescriptions"):
        r = client.post(url, headers=login(client, DOC), json={"patient_id": "p-0001", "care_plan": "", "items": ghost})
        assert r.status_code == 422 and r.json()["code"] == "unknown_drug"


def test_a_deactivated_drug_still_counts_for_running_prescriptions(client, db):
    ph = pharmacist(client, db)
    running = _post(client, RX_OK, urgent=True).json()
    assert client.patch("/drugs/d-0041", headers=ph, json={"active": False}).status_code == 200
    h = login(client, DOC)
    r = client.post("/prescriptions/check", headers=h, json={"patient_id": "p-0001", "items": RX_OK["items"]})
    assert r.status_code == 422 and r.json()["code"] == "unknown_drug"
    panto = [{"med": "Pantoprazole 40 mg", "drug_id": "d-0042", "times": ["08:00"]}]
    checks = client.post("/prescriptions/check", headers=h, json={"patient_id": "p-0001", "items": panto}).json()["checks"]
    assert [(c["code"], c["params"]["reason"], c["params"]["with_prescription_id"]) for c in checks] == [
        ("duplicate_therapy", "same_atc_class", running["id"])]


def test_a_version_that_never_ran_is_replaced_at_once(client, db):
    v1 = _post(client, RX_OK).json()
    v2 = _post(client, RX_OK, replaces_id=v1["id"]).json()
    assert (v2["version"], v2["replaces_id"], v2["status"]) == (2, v1["id"], "pending_pharmacy")
    assert db.get(Prescription, v1["id"]).status == "superseded"


def test_urgent_new_version_replaces_the_running_one_at_once(client, db):
    v1 = _post(client, RX_OK, urgent=True).json()
    v2 = _post(client, RX_OK, urgent=True, replaces_id=v1["id"]).json()
    assert v2["checks"] == []  # the replaced version is not a duplicate of its successor
    assert db.get(Prescription, v1["id"]).status == "superseded" and not db.get(Prescription, v1["id"]).active
    assert _future(db, v1["id"]) == [] and len(_future(db, v2["id"])) == 3


def test_replaces_id_rules(client, db):
    v1 = _post(client, RX_OK, urgent=True).json()
    v2 = _post(client, RX_OK, replaces_id=v1["id"]).json()
    assert db.get(Prescription, v1["id"]).status == "pending_pharmacy" and db.get(Prescription, v1["id"]).active
    again = _post(client, RX_OK, replaces_id=v1["id"])  # v1 already has a live newer version
    assert again.status_code == 409 and again.json()["code"] == "conflict"
    assert _post(client, RX_OK, replaces_id="rx-9999").status_code == 404
    other = _post(client, {**RX_OK, "patient_id": "p-0002"}).json()
    assert _post(client, RX_OK, replaces_id=other["id"]).status_code == 409
    assert client.patch(f"/prescriptions/{v2['id']}", headers=login(client, DOC), json={"active": False}).status_code == 200
    assert _post(client, RX_OK, replaces_id=v2["id"]).status_code == 409  # stopped is not live


def test_stop(client, db, published):
    h = login(client, DOC)
    rx = _post(client, RX_OK, urgent=True).json()
    r = client.patch(f"/prescriptions/{rx['id']}", headers=h, json={"active": False})
    assert r.status_code == 200 and (r.json()["status"], r.json()["active"]) == ("stopped", False)
    assert _future(db, rx["id"]) == []
    twice = client.patch(f"/prescriptions/{rx['id']}", headers=h, json={"active": False})
    assert twice.status_code == 409 and twice.json()["code"] == "bad_status"
    assert client.patch(f"/prescriptions/{rx['id']}", headers=h, json={"active": True}).status_code == 422
    pending = _post(client, RX_OK).json()
    assert client.patch(f"/prescriptions/{pending['id']}", headers=h, json={"active": False}).json()["status"] == "stopped"
    assert client.patch("/prescriptions/rx-9999", headers=h, json={"active": False}).status_code == 404


def test_get_shapes_by_role(client):
    _post(client, RX_OK)
    rows = client.get("/patients/p-0001/prescriptions", headers=login(client, DOC)).json()
    assert rows and all(set(r) == DOCTOR_KEYS for r in rows)
    assert all(set(r) == DOCTOR_KEYS for r in client.get("/patients/p-0001/prescriptions",
                                                          headers=login(client, "nurse@medora.tn")).json())
    mine = client.get("/patients/p-0001/prescriptions", headers=login(client, "patient@medora.tn")).json()
    assert mine and all(set(r) == PATIENT_KEYS for r in mine)


def test_ai_record_labels_a_pending_prescription(client, db):
    from app.services.record_sources import build

    rx = _post(client, RX_OK).json()
    src = next(s for s in build(db, db.get(Patient, "p-0001"), "doctor") if s.id == f"rx:{rx['id']}")
    assert src.text.startswith("Prescription pending pharmacy review:")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_prescribing.py`
Expected: FAIL. `/prescriptions/check` returns 404 or 405, and the responses lack `status`.

- [ ] **Step 3: Schemas**

In `backend/app/schemas.py`, replace `RxItemIn`, `PrescriptionIn` and `PrescriptionPatch`, add `PrescriptionCheckIn`, and delete `PrescriptionOut` and `PrescriptionPublished`. Their only users, `routers/patients.py` and `routers/prescriptions.py`, change in this task.
```python
class RxItemIn(BaseModel):
    med: str = Field(min_length=1, max_length=80)  # display string; checks use drug_id
    drug_id: str | None = Field(default=None, max_length=20)  # null = non-formulary ("hors livret")
    dose_mg: float | None = Field(default=None, gt=0, le=100000)  # mg per intake; overrides units × unit_mg
    units_per_intake: int = Field(default=1, ge=1, le=10)
    times: list[Annotated[str, Field(pattern=HHMM)]] = Field(min_length=1, max_length=8)
    slot: int | None = Field(default=None, ge=1, le=4)
    days: int = Field(default=1, ge=1, le=60)


class PrescriptionIn(BaseModel):
    patient_id: str
    items: list[RxItemIn] = Field(min_length=1, max_length=8)
    care_plan: str = ""
    urgent: bool = False
    override_reason: str | None = Field(default=None, max_length=500)
    replaces_id: str | None = Field(default=None, max_length=20)


class PrescriptionCheckIn(BaseModel):
    patient_id: str
    items: list[RxItemIn] = Field(min_length=1, max_length=8)
    replaces_id: str | None = Field(default=None, max_length=20)


class PrescriptionPatch(BaseModel):
    active: Literal[False]  # stop only; edits are a new version through replaces_id
```

- [ ] **Step 4: Formulary facts for the engine**

Append to `backend/app/services/pharmacy/formulary.py`. Add the import `from app.services.pharmacy.checks import DrugInfo`.
```python
def to_info(d: Drug) -> DrugInfo:
    return DrugInfo(id=d.id, dci=d.dci, brand_names=tuple(d.brand_names or ()), atc_code=d.atc_code or "",
                    unit_mg=_num(d.unit_mg), max_daily_mg=_num(d.max_daily_mg),
                    allergy_classes=tuple(d.allergy_classes or ()),
                    interaction_groups=tuple(d.interaction_groups or ()), high_alert=bool(d.high_alert))


def drug_infos(db: Session, ids: set[str]) -> dict[str, DrugInfo]:
    """Formulary facts for these ids, inactive drugs included (a running prescription may still use one)."""
    if not ids:
        return {}
    return {d.id: to_info(d) for d in db.scalars(select(Drug).where(Drug.id.in_(ids)))}
```

- [ ] **Step 5: The workflow service**

`backend/app/services/pharmacy/workflow.py`:
```python
"""Prescription life cycle (pharmacy spec §2): pending_pharmacy → validated | changes_requested | rejected; stopped;
superseded. `active` is derived from the status and kept in its column for the dose/schedule/AI code. Routers call
these, then audit, commit and publish the frames."""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.errors import ApiError, not_found
from app.ids import new_id
from app.iot.ingest import frame
from app.models import Drug, Patient, Prescription, User
from app.schemas import iso
from app.services import schedule
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


def chain(db: Session, rx: Prescription, limit: int = 20) -> list[Prescription]:
    """The versions rx replaces, nearest first (its replaces_id, then that one's, …)."""
    out: list[Prescription] = []
    seen = {rx.id}
    cur = rx.replaces_id
    while cur and cur not in seen and len(out) < limit:
        prev = db.get(Prescription, cur)
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
    if old is not None:
        newer = db.scalar(select(Prescription.id).where(Prescription.replaces_id == old.id,
                                                        Prescription.status.in_(LIVE)).limit(1))
        if old.status not in LIVE or newer is not None:
            raise ApiError(409, "conflict", "replaces_id is not the latest version")
    checks = checks_for(db, patient, items, exclusions(db, old))
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
    for prev in [old, *chain(db, old)] if old is not None else []:
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
    for r in out.touched:
        schedule.rebuild_doses(db, r)
    sent = schedule.push_schedule(db, out.rx.patient_id) if out.doses_changed else False
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
```

- [ ] **Step 6: The prescriptions router**

Replace `backend/app/routers/prescriptions.py`:
```python
"""Prescribing (api.md 1.12 → Prescriptions). The life cycle lives in app/services/pharmacy/workflow.py."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import can_access, check_patient_access, require_roles
from app.db import get_db
from app.errors import forbidden, not_found
from app.iot import publisher
from app.models import Patient, User
from app.schemas import PrescriptionCheckIn, PrescriptionIn, PrescriptionPatch
from app.services.audit import audit
from app.services.pharmacy import workflow as W

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _finish(db: Session, out: W.Outcome) -> dict:
    """Doses + device schedule, then commit, then the WS frames (never for a rolled-back change)."""
    sent, version = W.apply_doses(db, out)
    frames = W.status_frames(db, out)
    body = {**W.rx_out(db, out.rx), "schedule_version": version, "published_to_device": sent}
    db.commit()
    for f in frames:
        publisher.publish_ws_frame(f)
    return body


@router.post("/check")
def check(body: PrescriptionCheckIn, request: Request, user: User = Depends(require_roles("doctor")),
          db: Session = Depends(get_db)) -> dict:
    """Dry run while the doctor types: the warnings the pharmacist will see. Writes only the audit row."""
    patient = db.get(Patient, body.patient_id)
    if patient is None:
        raise not_found("patient")
    if not can_access(db, user, patient, write=True):
        raise forbidden("not your patient")
    items = [i.model_dump() for i in body.items]
    W.ensure_drugs(db, items)
    old = W.replace_target(db, body.replaces_id, patient.id, lock_row=False) if body.replaces_id else None
    checks = W.checks_for(db, patient, items, W.exclusions(db, old))
    audit(db, user, "read", "prescription_check", patient.id, patient_id=patient.id, ip=_ip(request))
    db.commit()
    return {"checks": [c.as_dict() for c in checks]}


@router.post("", status_code=201)
def create(body: PrescriptionIn, request: Request, user: User = Depends(require_roles("doctor")),
           db: Session = Depends(get_db)) -> dict:
    patient = check_patient_access(db, user, body.patient_id, write=True, resource="prescription", ip=_ip(request))
    out = W.create(db, user, patient, body)
    audit(db, user, "create", "prescription", out.rx.id, patient_id=patient.id, ip=_ip(request))
    for prev in out.touched[1:]:
        audit(db, user, "update", "prescription", prev.id, patient_id=patient.id, ip=_ip(request))
    return _finish(db, out)


@router.patch("/{rx_id}")
def stop(rx_id: str, body: PrescriptionPatch, request: Request, user: User = Depends(require_roles("doctor")),
         db: Session = Depends(get_db)) -> dict:
    rx = W.lock(db, rx_id)
    check_patient_access(db, user, rx.patient_id, write=True, resource="prescription", ip=_ip(request))
    return _finish(db, W.stop(db, rx))
```

In `backend/app/routers/patients.py`:
- remove `PrescriptionOut` from the schemas import;
- add `from app.services.pharmacy import workflow as W`;
- replace `get_prescriptions` with this:
```python
@router.get("/{patient_id}/prescriptions")
def get_prescriptions(patient_id: str, request: Request,
                      user: User = Depends(require_roles("doctor", "nurse", "patient")),
                      db: Session = Depends(get_db)) -> list[dict]:
    check_patient_access(db, user, patient_id, resource="prescription", ip=_ip(request))
    rows = db.scalars(select(Prescription).where(Prescription.patient_id == patient_id)
                      .order_by(Prescription.created_at.desc(), Prescription.id.desc())).all()
    out = [W.rx_out(db, r, for_patient=user.role == "patient") for r in rows]
    db.commit()
    return out
```

In `backend/app/services/record_sources.py`, a pending prescription must not read as "Stopped" to the AI assistant. Add this at module level:
```python
RX_LABEL = {"validated": "Active prescription", "pending_pharmacy": "Prescription pending pharmacy review",
            "changes_requested": "Prescription returned by the pharmacist for changes",
            "rejected": "Prescription rejected by the pharmacist", "stopped": "Stopped prescription",
            "superseded": "Replaced prescription"}
```
Then replace the line `text = f"{'Active' if rx.active else 'Stopped'} prescription: {items}."` with:
```python
        label = ("Urgent prescription, running, pending pharmacy review"
                 if rx.status == "pending_pharmacy" and rx.urgent else RX_LABEL.get(rx.status, "Prescription"))
        text = f"{label}: {items}."
```

- [ ] **Step 7: Update the three existing tests whose behaviour changed (spec §2: the gate)**

In `backend/tests/test_rx_devices_api.py`, replace these three tests:
```python
def _schedules(published):
    return [p for p in published if p[0].endswith("/schedule")]


def test_prescribe_publishes_schedule(client, published):
    r = client.post("/prescriptions", headers=login(client, "doctor@medora.tn"), json=dict(RX, urgent=True))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"].startswith("rx-") and body["doctor_id"] == "u-0001" and body["active"] is True
    assert (body["status"], body["urgent"]) == ("pending_pharmacy", True)
    assert body["published_to_device"] is True and body["schedule_version"] == 1
    topic, payload, _, retain = _schedules(published)[-1]
    assert topic == "hospital/device/bsu-001/schedule" and retain
    assert payload["schedule_version"] == 1 and any(d["time"] == "20:00" for d in payload["doses"])


def test_prescribe_patient_without_device(client, published):
    r = client.post("/prescriptions", headers=login(client, "doctor@medora.tn"),
                    json=dict(RX, patient_id="p-0002", urgent=True))
    assert r.status_code == 201 and r.json()["published_to_device"] is False
    assert _schedules(published) == []


def test_stop_prescription(client, db, published):
    h = login(client, "doctor@medora.tn")
    rx = client.post("/prescriptions", headers=h, json=dict(RX, urgent=True)).json()
    r = client.patch(f"/prescriptions/{rx['id']}", headers=h, json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False and r.json()["schedule_version"] == 2
    payload = _schedules(published)[-1][1]
    assert all("Paracetamol 500mg" not in d["meds"] or d["slot"] != 1 for d in payload["doses"])
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider`
Expected: the whole suite passes, `test_team_and_sharing.py` included (a shared doctor still gets 403 on `POST /prescriptions`).

- [ ] **Step 9: Lint and commit**

Run LINT. Then:
```bash
git add backend/app/services/pharmacy/workflow.py backend/app/services/pharmacy/formulary.py backend/app/schemas.py backend/app/routers/prescriptions.py backend/app/routers/patients.py backend/app/services/record_sources.py backend/tests/test_rx_devices_api.py backend/tests/test_prescribing.py
git commit -m "feat(backend): pharmacy gate on prescriptions (check dry run, urgent, override, versions, stop)"
```

---

### Task 5: Pharmacist worklist, review, decisions and their side effects

**Files:**
- Modify: `backend/app/services/pharmacy/workflow.py` (`decide`, `emit_review`)
- Create: `backend/app/services/pharmacy/review.py`
- Create: `backend/app/routers/pharmacy.py`
- Modify: `backend/app/main.py` (include the `pharmacy` router)
- Modify: `backend/app/schemas.py` (`ValidateIn`, `CommentIn`)
- Modify: `backend/app/services/schedule.py` (`course_start`; `rebuild_doses` uses it)
- Modify: `backend/app/ws/hub.py` (`wants`: the pharmacist branch)
- Modify: `backend/app/routers/doses.py` (`given`: refuse doses of a non-active prescription)
- Test: `backend/tests/test_pharmacy_review.py`

**Interfaces:**
- Consumes: everything from Task 4 (`W.*`); `active_doctor(db, user_id)` from `app.services.accounts`; `n8n.emit_after_commit`.
- Produces:
  - `W.decide(db, pharmacist: User, rx_id: str, decision: str, comment: str | None, *, acknowledged: bool = False) -> Outcome`, where `decision` is `"validated"|"changes_requested"|"rejected"`;
  - `W.emit_review(db, rx, decision, comment) -> None`;
  - `schedule.course_start(rx) -> datetime`;
  - in `review` (imported as `R`): `bed_of(db, patient_id) -> str | None`, `user_name(db, user_id) -> str | None`, `patient_view(db, p) -> dict`, `max_severity(checks: list[dict]) -> str | None`, `worklist(db, status) -> list[dict]`, `review_out(db, r) -> dict`, `detail(db, rx) -> dict`, `summary(db) -> dict`;
  - the frame `{"type": "prescription_status", "data": {prescription_id, patient_id, status, urgent}}`, which pharmacists receive (and only this frame type).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_pharmacy_review.py`:
```python
"""Pharmacist side (api 1.12 → Pharmacist): decisions, side effects, worklist, detail, summary, permissions."""

from datetime import date, timedelta

import pytest
from sqlalchemy import event, select

from app.models import AuditLog, MedDose, Prescription, PrescriptionReview
from app.services import schedule
from app.services.pharmacy.workflow import age_on
from app.ws.hub import Client, wants
from tests.helpers import login, pharmacist

DOC = "doctor@medora.tn"
RX_OK = {"patient_id": "p-0001", "care_plan": "",
         "items": [{"med": "Omeprazole 20 mg", "drug_id": "d-0041", "times": ["20:00"], "slot": 3, "days": 3}]}
RX_MAJOR = {"patient_id": "p-0002", "care_plan": "",
            "items": [{"med": "Ibuprofen 400 mg", "drug_id": "d-0018", "units_per_intake": 2,
                       "times": ["06:00", "12:00", "18:00", "23:00"], "days": 2}]}
RX_ALLERGY = {"patient_id": "p-0001", "care_plan": "",
              "items": [{"med": "Amoxicillin 1 g", "drug_id": "d-0003", "dose_mg": 1000,
                         "times": ["08:00", "14:00", "20:00"], "days": 7}]}
AZI = {"patient_id": "p-0001", "care_plan": "",
       "items": [{"med": "Azithromycin 250 mg", "drug_id": "d-0006", "units_per_intake": 2, "times": ["08:00"],
                  "days": 3}]}


def _rx(client, body, **extra):
    r = client.post("/prescriptions", headers=login(client, DOC), json={**body, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _act(client, h, rx_id, action, **body):
    return client.post(f"/pharmacy/prescriptions/{rx_id}/{action}", headers=h, json=body)


def _future(db, rx_id):
    return db.scalars(select(MedDose).where(MedDose.prescription_id == rx_id,
                                            MedDose.scheduled_at > schedule.now_utc())).all()


def _schedules(published):
    return [p for t, p, *_ in published if t.endswith("/schedule")]


def _frames(published):
    return [p["data"] for t, p, *_ in published if t == "ward/internal/ws" and p.get("type") == "prescription_status"]


def test_validate_without_checks_is_one_click(client, db, published, emitted):
    rx = _rx(client, RX_OK)
    assert _future(db, rx["id"]) == []
    ph = pharmacist(client, db)
    r = _act(client, ph, rx["id"], "validate")
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["status"], b["active"], b["reviewed_by_name"], b["review_comment"]) == (
        "validated", True, "Pharm Test", None)
    assert len(_future(db, rx["id"])) == 3
    assert any(d["time"] == "20:00" and "Omeprazole 20 mg" in d["meds"] for d in _schedules(published)[-1]["doses"])
    review = db.scalars(select(PrescriptionReview).where(PrescriptionReview.prescription_id == rx["id"])).one()
    assert (review.decision, review.checks_snapshot) == ("validated", [])
    assert ("prescription.review", {"prescription_id": rx["id"], "patient_id": "p-0001", "decision": "validated",
                                    "comment": None, "doctor_email": "doctor@medora.tn",
                                    "doctor_chat_id": None}) in emitted
    assert {"prescription_id": rx["id"], "patient_id": "p-0001", "status": "validated",
            "urgent": False} in _frames(published)
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "update", AuditLog.resource == "prescription",
                                               AuditLog.resource_id == rx["id"], AuditLog.role == "pharmacist"))


def test_checks_need_acknowledgement(client, db):
    rx = _rx(client, RX_MAJOR)
    assert [(c["code"], c["severity"]) for c in rx["checks"]] == [("max_daily_dose", "major")]
    ph = pharmacist(client, db)
    r = _act(client, ph, rx["id"], "validate", acknowledged=False)
    assert r.status_code == 422 and r.json()["code"] == "ack_required"
    assert db.get(Prescription, rx["id"]).status == "pending_pharmacy"
    r = _act(client, ph, rx["id"], "validate", acknowledged=True, comment="dose reduced on the ward")
    assert r.status_code == 200 and r.json()["review_comment"] == "dose reduced on the ward"


def test_second_decision_is_409(client, db):
    rx = _rx(client, RX_OK)
    ph = pharmacist(client, db)
    assert _act(client, ph, rx["id"], "validate").status_code == 200
    for action, body in (("validate", {}), ("reject", {"comment": "late"}), ("request-changes", {"comment": "x"})):
        r = _act(client, ph, rx["id"], action, **body)
        assert r.status_code == 409 and r.json()["code"] == "bad_status"


def test_request_changes_and_reject_need_a_comment(client, db, emitted):
    rx = _rx(client, RX_OK)
    ph = pharmacist(client, db)
    for bad in ({}, {"comment": ""}, {"comment": "   "}, {"comment": "x" * 501}):
        assert client.post(f"/pharmacy/prescriptions/{rx['id']}/request-changes", headers=ph,
                           json=bad).status_code == 422
        assert client.post(f"/pharmacy/prescriptions/{rx['id']}/reject", headers=ph, json=bad).status_code == 422
    r = _act(client, ph, rx["id"], "request-changes", comment="allergie pénicilline → azithromycine")
    assert (r.json()["status"], r.json()["review_comment"]) == (
        "changes_requested", "allergie pénicilline → azithromycine")
    assert emitted[-1][0] == "prescription.review" and emitted[-1][1]["decision"] == "changes_requested"


def test_reject_gives_nothing(client, db):
    rx = _rx(client, RX_OK)
    r = _act(client, pharmacist(client, db), rx["id"], "reject", comment="not indicated")
    assert (r.json()["status"], r.json()["active"]) == ("rejected", False)
    assert db.query(MedDose).filter_by(prescription_id=rx["id"]).count() == 0
    mine = client.get("/patients/p-0001/prescriptions", headers=login(client, DOC)).json()
    assert next(x for x in mine if x["id"] == rx["id"])["review_comment"] == "not indicated"


def test_urgent_then_rejected_cancels_future_doses(client, db, published):
    rx = _rx(client, RX_OK, urgent=True)
    assert len(_future(db, rx["id"])) == 3
    n = len(_schedules(published))
    r = _act(client, pharmacist(client, db), rx["id"], "reject", comment="wrong patient")
    assert (r.json()["status"], r.json()["active"]) == ("rejected", False)
    assert _future(db, rx["id"]) == [] and len(_schedules(published)) == n + 1
    assert all("Omeprazole 20 mg" not in d["meds"] for d in _schedules(published)[-1]["doses"])


def test_supersede_keeps_v1_until_v2_is_validated(client, db, published):
    ph = pharmacist(client, db)
    v1 = _rx(client, RX_OK)
    _act(client, ph, v1["id"], "validate")
    v1_doses = {d.id for d in _future(db, v1["id"])}
    twice = {**RX_OK, "items": [{**RX_OK["items"][0], "times": ["08:00", "20:00"]}]}
    v2 = _rx(client, twice, replaces_id=v1["id"])
    assert (v2["version"], v2["replaces_id"], v2["status"], v2["checks"]) == (2, v1["id"], "pending_pharmacy", [])
    assert db.get(Prescription, v1["id"]).status == "validated" and {d.id for d in _future(db, v1["id"])} == v1_doses
    assert _act(client, ph, v2["id"], "validate").status_code == 200
    old = db.get(Prescription, v1["id"])
    assert (old.status, old.active) == ("superseded", False)
    assert _future(db, v1["id"]) == [] and len(_future(db, v2["id"])) == 6
    assert {"prescription_id": v1["id"], "patient_id": "p-0001", "status": "superseded",
            "urgent": False} in _frames(published)


def test_rejected_v2_leaves_v1_running(client, db):
    ph = pharmacist(client, db)
    v1 = _rx(client, RX_OK)
    _act(client, ph, v1["id"], "validate")
    v2 = _rx(client, RX_OK, replaces_id=v1["id"])
    _act(client, ph, v2["id"], "reject", comment="keep the current one")
    assert db.get(Prescription, v1["id"]).status == "validated" and len(_future(db, v1["id"])) == 3


def test_demo_path_changes_then_resubmit(client, db):
    ph = pharmacist(client, db)
    v1 = _rx(client, RX_ALLERGY, override_reason="Severe infection; allergy history unclear")
    _act(client, ph, v1["id"], "request-changes", comment="allergie pénicilline → azithromycine")
    v2 = _rx(client, AZI, replaces_id=v1["id"])
    assert db.get(Prescription, v1["id"]).status == "superseded" and v2["checks"] == []
    assert _act(client, ph, v2["id"], "validate").status_code == 200  # no checks: one click
    d = client.get(f"/pharmacy/prescriptions/{v2['id']}", headers=ph).json()
    # newest first; inside one test transaction now() is constant, so the review id breaks the tie
    assert [(h["prescription_id"], h["decision"]) for h in d["history"]] == [
        (v2["id"], "validated"), (v1["id"], "changes_requested")]


def test_decision_after_the_doctor_moved_on_is_409(client, db):
    ph = pharmacist(client, db)
    rx = _rx(client, RX_OK)
    assert client.patch(f"/prescriptions/{rx['id']}", headers=login(client, DOC),
                        json={"active": False}).status_code == 200
    r = _act(client, ph, rx["id"], "validate")
    assert r.status_code == 409 and r.json()["code"] == "bad_status"
    old = _rx(client, RX_OK)
    _rx(client, RX_OK, replaces_id=old["id"])  # old never ran: superseded at once
    r = _act(client, ph, old["id"], "request-changes", comment="x")
    assert r.status_code == 409 and db.get(Prescription, old["id"]).status == "superseded"


def test_decisions_lock_the_prescription_row(client, db):
    rx = _rx(client, RX_OK)
    ph = pharmacist(client, db)
    seen: list[str] = []

    def spy(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    conn = db.connection()
    event.listen(conn, "before_cursor_execute", spy)
    try:
        assert _act(client, ph, rx["id"], "validate").status_code == 200
    finally:
        event.remove(conn, "before_cursor_execute", spy)
    assert any("FROM prescriptions" in s and "FOR UPDATE" in s for s in seen)


def test_worklist_order_projection_and_audit(client, db):
    normal = _rx(client, RX_OK)
    critical = _rx(client, RX_ALLERGY, override_reason="reason")
    urgent = _rx(client, {**RX_OK, "patient_id": "p-0003"}, urgent=True)
    ph = pharmacist(client, db)
    rows = client.get("/pharmacy/worklist", headers=ph).json()
    ids = {normal["id"], critical["id"], urgent["id"]}
    assert [w["prescription"]["id"] for w in rows if w["prescription"]["id"] in ids] == [
        urgent["id"], critical["id"], normal["id"]]
    w = next(w for w in rows if w["prescription"]["id"] == critical["id"])
    assert set(w) == {"prescription", "patient", "doctor_name", "checks", "urgent", "waiting_since", "max_severity"}
    assert w["patient"] == {"id": "p-0001", "name": "Amira Ben Salah",
                            "age": age_on(date(1972, 3, 14), schedule.today_local()), "sex": "F",
                            "ward": "Cardiology", "bed": "C-12", "allergies": ["penicillin"]}
    assert (w["max_severity"], w["doctor_name"], w["urgent"]) == ("critical", "Dr Trabelsi", False)
    audited = set(db.scalars(select(AuditLog.resource_id).where(AuditLog.action == "read",
                                                                AuditLog.resource == "prescription",
                                                                AuditLog.role == "pharmacist")))
    assert ids <= audited
    _act(client, ph, normal["id"], "request-changes", comment="x")
    changes = client.get("/pharmacy/worklist?status=changes_requested", headers=ph).json()
    assert changes and all(x["prescription"]["status"] == "changes_requested" for x in changes)
    assert normal["id"] in {x["prescription"]["id"] for x in client.get("/pharmacy/worklist?status=all",
                                                                       headers=ph).json()}
    assert client.get("/pharmacy/worklist?status=validated", headers=ph).status_code == 422


def test_review_detail(client, db):
    ph = pharmacist(client, db)
    v1 = _rx(client, RX_OK)
    _act(client, ph, v1["id"], "validate")
    v2 = _rx(client, {**RX_OK, "items": [{**RX_OK["items"][0], "times": ["08:00"]}]}, replaces_id=v1["id"])
    d = client.get(f"/pharmacy/prescriptions/{v2['id']}", headers=ph).json()
    assert set(d) == {"prescription", "patient", "doctor_name", "running", "checks", "history", "replaces"}
    assert d["replaces"]["id"] == v1["id"] and v1["id"] not in {r["id"] for r in d["running"]}
    assert "rx-0001" in {r["id"] for r in d["running"]} and d["checks"] == []
    assert [h["decision"] for h in d["history"]] == ["validated"]
    assert set(d["history"][0]) == {"id", "prescription_id", "pharmacist_id", "pharmacist_name", "decision",
                                    "comment", "checks_snapshot", "created_at"}
    assert db.scalar(select(AuditLog.id).where(AuditLog.resource == "prescription", AuditLog.resource_id == v2["id"],
                                               AuditLog.action == "read", AuditLog.patient_id == "p-0001"))
    assert client.get("/pharmacy/prescriptions/rx-9999", headers=ph).status_code == 404


def test_summary_counts(client, db):
    ph = pharmacist(client, db)
    before = client.get("/pharmacy/summary", headers=ph).json()
    assert {"pending", "urgent_pending", "critical_pending", "changes_requested"} <= set(before)
    _rx(client, RX_OK)
    _rx(client, RX_ALLERGY, override_reason="r")
    _rx(client, {**RX_OK, "patient_id": "p-0003"}, urgent=True)
    c = _rx(client, {**RX_OK, "patient_id": "p-0002"})
    _act(client, ph, c["id"], "request-changes", comment="x")
    after = client.get("/pharmacy/summary", headers=ph).json()
    assert {k: after[k] - before[k] for k in ("pending", "urgent_pending", "critical_pending",
                                              "changes_requested")} == {
        "pending": 3, "urgent_pending": 1, "critical_pending": 1, "changes_requested": 1}


def test_pharmacists_get_prescription_status_frames_only():
    ph = Client(ws=None, user_id="u-0008", role="pharmacist", ward=None)
    assert wants(ph, {"type": "prescription_status", "data": {}, "scope": {"ward": "Cardiology"}})
    for t in ("vital", "alert", "dose_event", "device_status", "call_nurse"):
        assert not wants(ph, {"type": t, "data": {}, "scope": {"ward": "Cardiology", "doctor_id": "u-0001"}})


def test_doses_start_at_validation_not_at_writing(db, seeded):
    midnight = schedule.local_to_utc(schedule.today_local(), "00:00")
    noon = schedule.local_to_utc(schedule.today_local(), "12:00")
    items = [{"med": "Z", "times": ["08:00", "20:00"], "slot": None, "days": 1}]
    late = Prescription(id="rx-9300", patient_id="p-0002", doctor_id="u-0001", items=items, care_plan="",
                        status="validated", active=True, urgent=False, created_at=midnight, reviewed_at=noon)
    urgent = Prescription(id="rx-9301", patient_id="p-0002", doctor_id="u-0001", items=items, care_plan="",
                          status="validated", active=True, urgent=True, created_at=midnight, reviewed_at=noon)
    db.add_all([late, urgent])
    db.flush()
    late_doses = schedule.rebuild_doses(db, late)
    assert len(late_doses) == 2 and all(d.scheduled_at >= noon for d in late_doses)
    urgent_doses = schedule.rebuild_doses(db, urgent)
    assert len(urgent_doses) == 2 and min(d.scheduled_at for d in urgent_doses) < noon  # started when written


def test_nurse_cannot_give_a_leftover_dose_of_a_cancelled_prescription(client, db):
    db.add(Prescription(id="rx-9302", patient_id="p-0001", doctor_id="u-0001", care_plan="", status="rejected",
                        active=False, urgent=True, items=[{"med": "Z", "times": ["08:00"], "slot": None, "days": 1}]))
    db.flush()
    db.add(MedDose(id="d-rej001", prescription_id="rx-9302", patient_id="p-0001",
                   scheduled_at=schedule.now_utc() - timedelta(hours=1), time_of_day="08:00", meds=["Z"], slot=None,
                   status="scheduled"))
    db.flush()
    r = client.post("/doses/d-rej001/given", headers=login(client, "nurse@medora.tn"))
    assert r.status_code == 409 and r.json()["code"] == "bad_status"
    assert db.get(MedDose, "d-rej001").status == "scheduled"


@pytest.mark.parametrize("email", ["doctor@medora.tn", "nurse@medora.tn", "admin@medora.tn", "patient@medora.tn"])
def test_only_pharmacists_use_pharmacy_routes(client, db, email):
    rx = _rx(client, RX_OK)
    h = login(client, email)
    base = f"/pharmacy/prescriptions/{rx['id']}"
    for method, url, body in (("GET", "/pharmacy/worklist", None), ("GET", "/pharmacy/summary", None),
                              ("GET", base, None), ("POST", f"{base}/validate", {}),
                              ("POST", f"{base}/request-changes", {"comment": "x"}),
                              ("POST", f"{base}/reject", {"comment": "x"})):
        assert client.request(method, url, headers=h, json=body).status_code == 403, (email, url)


def test_pharmacist_cannot_prescribe_or_read_records(client, db):
    ph = pharmacist(client, db)
    rx = _rx(client, RX_OK)
    assert client.post("/prescriptions", headers=ph, json=RX_OK).status_code == 403
    assert client.post("/prescriptions/check", headers=ph, json=RX_OK).status_code == 403
    assert client.patch(f"/prescriptions/{rx['id']}", headers=ph, json={"active": False}).status_code == 403
    for url in ("/patients", "/patients/p-0001", "/patients/p-0001/vitals", "/patients/p-0001/notes",
                "/patients/p-0001/prescriptions", "/patients/p-0001/doses"):
        assert client.get(url, headers=ph).status_code == 403, url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_pharmacy_review.py`
Expected: FAIL. The `/pharmacy/...` routes return 404, and the hub and dose tests fail.

- [ ] **Step 3: Schemas**

Append to `backend/app/schemas.py`:
```python
class ValidateIn(BaseModel):
    acknowledged: bool = False  # "warnings reviewed": required when the prescription has any check
    comment: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class CommentIn(BaseModel):
    comment: Comment  # 1–500 characters after trimming
```

- [ ] **Step 4: Doses start when the prescription may first be given**

In `backend/app/services/schedule.py`, add this above `rebuild_doses`:
```python
def course_start(rx: Prescription) -> datetime:
    """When the course starts (pharmacy spec §2): at once for an urgent prescription or one that predates the
    pharmacy gate, else when the pharmacist validated it, so no dose is ever born overdue."""
    written = rx.created_at or now_utc()
    if not rx.urgent and rx.reviewed_at is not None:
        return max(rx.reviewed_at, written)
    return written
```
In `rebuild_doses`, replace `written = rx.created_at or now_utc()` with `written = course_start(rx)`.

- [ ] **Step 5: Decide and notify**

Append to `backend/app/services/pharmacy/workflow.py`. Add these imports: `from datetime import UTC, datetime`, `from app.integrations import n8n`, `from app.models import PrescriptionReview, Staff` (merge into the existing models import) and `from app.services.accounts import active_doctor`.
```python
DECISIONS = ("validated", "changes_requested", "rejected")


def decide(db: Session, pharmacist: User, rx_id: str, decision: str, comment: str | None, *,
           acknowledged: bool = False) -> Outcome:
    """A pharmacist decision on a pending prescription, under the row lock. The checks are recomputed now (the
    patient's other prescriptions may have changed since the save). Every 4xx is raised before the first write."""
    assert decision in DECISIONS
    rx = lock(db, rx_id)
    if rx.status != "pending_pharmacy":
        raise ApiError(409, "bad_status", f"prescription is {rx.status}")
    ancestors = chain(db, rx)
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
```

- [ ] **Step 6: What the pharmacist reads**

`backend/app/services/pharmacy/review.py`:
```python
"""What the pharmacist reads (pharmacy spec §2, §5): the worklist, one prescription under review, the counts.
The patient part is a minimal projection (name, age, sex, ward, bed, allergies), never the full record. Routers
write the audit rows."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Admission, Patient, Prescription, PrescriptionReview, User
from app.schemas import iso
from app.services import schedule
from app.services.pharmacy import workflow as W
from app.services.pharmacy.checks import SEVERITY_RANK

WORKLIST_LIMIT = 200


def bed_of(db: Session, patient_id: str) -> str | None:
    return db.scalar(select(Admission.bed).where(Admission.patient_id == patient_id,
                                                 Admission.discharged_at.is_(None)))


def user_name(db: Session, user_id: str | None) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return u.name if u else None


def patient_view(db: Session, p: Patient) -> dict:
    return {"id": p.id, "name": f"{p.first_name} {p.last_name}".strip(),
            "age": W.age_on(p.date_of_birth, schedule.today_local()), "sex": p.sex, "ward": p.ward,
            "bed": bed_of(db, p.id), "allergies": list(p.allergies or [])}


def max_severity(checks: list[dict]) -> str | None:
    found = [c.get("severity") for c in checks if c.get("severity") in SEVERITY_RANK]
    return min(found, key=SEVERITY_RANK.__getitem__, default=None)


def _sort_key(rx: Prescription) -> tuple:
    sev = max_severity(rx.checks or [])
    return (not rx.urgent, SEVERITY_RANK.get(sev, len(SEVERITY_RANK)) if sev else len(SEVERITY_RANK),
            rx.created_at, rx.id)


def worklist_item(db: Session, rx: Prescription) -> dict:
    checks = rx.checks or []
    return {"prescription": W.rx_out(db, rx), "patient": patient_view(db, db.get(Patient, rx.patient_id)),
            "doctor_name": user_name(db, rx.doctor_id), "checks": checks, "urgent": rx.urgent,
            "waiting_since": iso(rx.created_at), "max_severity": max_severity(checks)}


def worklist(db: Session, status: str) -> list[dict]:
    """`status`: pending_pharmacy | changes_requested | all (every status, newest 200). Urgent first, then the
    highest stored severity, then the oldest."""
    stmt = select(Prescription)
    if status != "all":
        stmt = stmt.where(Prescription.status == status)
    rows = db.scalars(stmt.order_by(Prescription.created_at.desc(), Prescription.id.desc())
                      .limit(WORKLIST_LIMIT)).all()
    return [worklist_item(db, r) for r in sorted(rows, key=_sort_key)]


def review_out(db: Session, r: PrescriptionReview) -> dict:
    return {"id": r.id, "prescription_id": r.prescription_id, "pharmacist_id": r.pharmacist_id,
            "pharmacist_name": user_name(db, r.pharmacist_id), "decision": r.decision, "comment": r.comment,
            "checks_snapshot": r.checks_snapshot or [], "created_at": iso(r.created_at)}


def detail(db: Session, rx: Prescription) -> dict:
    p = db.get(Patient, rx.patient_id)
    ancestors = W.chain(db, rx)
    exclude = {rx.id, *(a.id for a in ancestors)}
    running = db.scalars(select(Prescription).where(Prescription.patient_id == p.id, W.running_clause(),
                                                    Prescription.id.not_in(exclude))
                         .order_by(Prescription.created_at, Prescription.id)).all()
    history = db.scalars(select(PrescriptionReview).where(PrescriptionReview.prescription_id.in_(exclude))
                         .order_by(PrescriptionReview.created_at.desc(), PrescriptionReview.id.desc())).all()
    replaces = db.get(Prescription, rx.replaces_id) if rx.replaces_id else None
    return {"prescription": W.rx_out(db, rx), "patient": patient_view(db, p),
            "doctor_name": user_name(db, rx.doctor_id), "running": [W.rx_out(db, r) for r in running],
            "checks": [c.as_dict() for c in W.checks_for(db, p, rx.items, exclude)],
            "history": [review_out(db, r) for r in history],
            "replaces": W.rx_out(db, replaces) if replaces else None}


def summary(db: Session) -> dict:
    pending = db.scalars(select(Prescription).where(Prescription.status == "pending_pharmacy")).all()
    changes = db.scalar(select(func.count()).select_from(Prescription)
                        .where(Prescription.status == "changes_requested"))
    return {"pending": len(pending), "urgent_pending": sum(1 for r in pending if r.urgent),
            "critical_pending": sum(1 for r in pending if max_severity(r.checks or []) == "critical"),
            "changes_requested": changes or 0}
```

- [ ] **Step 7: The pharmacy router**

`backend/app/routers/pharmacy.py`:
```python
"""The pharmacist's routes (api.md 1.12 → Pharmacist). Pharmacist only; every prescription read is audited with
its patient."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.db import get_db
from app.errors import not_found
from app.iot import publisher
from app.models import Prescription, User
from app.schemas import CommentIn, ValidateIn
from app.services.audit import audit
from app.services.pharmacy import review as R
from app.services.pharmacy import workflow as W

router = APIRouter(prefix="/pharmacy", tags=["pharmacy"])
PHARMACIST = require_roles("pharmacist")


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("/worklist")
def worklist(request: Request, status: Literal["pending_pharmacy", "changes_requested", "all"] = "pending_pharmacy",
             user: User = Depends(PHARMACIST), db: Session = Depends(get_db)) -> list[dict]:
    rows = R.worklist(db, status)
    for w in rows:
        audit(db, user, "read", "prescription", w["prescription"]["id"], patient_id=w["patient"]["id"],
              ip=_ip(request))
    db.commit()
    return rows


@router.get("/summary")
def summary(user: User = Depends(PHARMACIST), db: Session = Depends(get_db)) -> dict:
    out = R.summary(db)  # counts only, no patient data
    db.commit()
    return out


@router.get("/prescriptions/{rx_id}")
def review(rx_id: str, request: Request, user: User = Depends(PHARMACIST), db: Session = Depends(get_db)) -> dict:
    rx = db.get(Prescription, rx_id)
    if rx is None:
        raise not_found("prescription")
    out = R.detail(db, rx)
    audit(db, user, "read", "prescription", rx.id, patient_id=rx.patient_id, ip=_ip(request))
    db.commit()
    return out


def _decide(db: Session, user: User, request: Request, rx_id: str, decision: str, comment: str | None,
            acknowledged: bool = False) -> dict:
    out = W.decide(db, user, rx_id, decision, comment, acknowledged=acknowledged)
    W.apply_doses(db, out)
    audit(db, user, "update", "prescription", out.rx.id, patient_id=out.rx.patient_id, ip=_ip(request))
    W.emit_review(db, out.rx, decision, comment)
    frames = W.status_frames(db, out)
    body = W.rx_out(db, out.rx)
    db.commit()
    for f in frames:
        publisher.publish_ws_frame(f)
    return body


@router.post("/prescriptions/{rx_id}/validate")
def validate(rx_id: str, body: ValidateIn, request: Request, user: User = Depends(PHARMACIST),
             db: Session = Depends(get_db)) -> dict:
    return _decide(db, user, request, rx_id, "validated", body.comment, body.acknowledged)


@router.post("/prescriptions/{rx_id}/request-changes")
def request_changes(rx_id: str, body: CommentIn, request: Request, user: User = Depends(PHARMACIST),
                    db: Session = Depends(get_db)) -> dict:
    return _decide(db, user, request, rx_id, "changes_requested", body.comment)


@router.post("/prescriptions/{rx_id}/reject")
def reject(rx_id: str, body: CommentIn, request: Request, user: User = Depends(PHARMACIST),
           db: Session = Depends(get_db)) -> dict:
    return _decide(db, user, request, rx_id, "rejected", body.comment)
```
In `backend/app/main.py`, add `pharmacy` to the routers import and `app.include_router(pharmacy.router)` after `drugs.router`.

- [ ] **Step 8: Hub and dose guard**

In `backend/app/ws/hub.py`, add a module constant `PHARMACIST_FRAMES = {"prescription_status"}`. Insert this into `wants()` right after the admin branch:
```python
    if c.role == "pharmacist":  # hospital-wide, but only the pharmacy frame: no vitals, alerts or doses
        return frame.get("type") in PHARMACIST_FRAMES
```
Update the module docstring: "…an admin only `device_status`, a pharmacist only `prescription_status`."

In `backend/app/routers/doses.py`, change the models import to `from app.models import MedDose, Prescription, User` and add `from app.errors import ApiError, not_found`. In `given`, insert this right after `check_patient_access(...)`:
```python
    rx = db.get(Prescription, d.prescription_id)
    if rx is not None and not rx.active and d.status != "taken":  # validated or urgent only (pharmacy spec §2)
        raise ApiError(409, "bad_status", f"prescription is {rx.status}: this dose must not be given")
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider`
Expected: the whole suite passes.

- [ ] **Step 10: Lint and commit**

Run LINT. Then:
```bash
git add backend/app/services/pharmacy/workflow.py backend/app/services/pharmacy/review.py backend/app/routers/pharmacy.py backend/app/main.py backend/app/schemas.py backend/app/services/schedule.py backend/app/ws/hub.py backend/app/routers/doses.py backend/tests/test_pharmacy_review.py
git commit -m "feat(backend): pharmacist worklist, review and decisions with dose, WS and n8n side effects"
```

---

### Task 6: The pharmacist role in sign-up and approval

**Files:**
- Modify: `backend/app/routers/auth.py` (`RegisterIn`)
- Modify: `backend/app/services/accounts.py` (`ROLES`, approve message)
- Test: `backend/tests/test_pharmacist_accounts.py`

**Interfaces:**
- Consumes: the existing `/auth/register` and `/users/{id}/approve`.
- Produces: `RegisterIn.role` allows `"pharmacist"`. `accounts.ROLES = ("patient", "nurse", "doctor", "pharmacist", "admin")`. Only the admin approves a pharmacist (`DOCTOR_MAY_APPROVE` is unchanged). A pharmacist gets no `staff` row.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_pharmacist_accounts.py`:
```python
"""The 4th staff role (pharmacy spec §2): sign-up, admin-only approval, login, WebSocket."""

from sqlalchemy import select

from app.models import Staff, User
from tests.helpers import login, make_user

GOOD = "a-Long-and-unusual-passphrase-42"


def _reg(client, **over):
    body = {"name": "Salma Test", "email": "salma.t@medora.tn", "password": GOOD, "role": "pharmacist"}
    return client.post("/auth/register", json={**body, **over})


def _user(db, email):
    return db.scalar(select(User).where(User.email == email))


def test_pharmacist_can_be_requested(client, db):
    assert _reg(client).status_code == 202
    u = _user(db, "salma.t@medora.tn")
    assert (u.requested_role, u.role, u.status) == ("pharmacist", None, "pending")


def test_a_pharmacist_request_cannot_name_a_doctor(client, db):
    r = _reg(client, requested_doctor_id="u-0001")
    assert r.status_code == 422 and r.json()["code"] == "invalid"
    assert _user(db, "salma.t@medora.tn") is None


def test_only_the_admin_approves_a_pharmacist(client, db):
    named = make_user(db, "ph.req@medora.tn", role=None, status="pending", requested_doctor_id="u-0001")
    named.requested_role = "pharmacist"
    db.flush()
    r = client.post(f"/users/{named.id}/approve", headers=login(client, "doctor@medora.tn"), json={"role": "pharmacist"})
    assert r.status_code == 403
    r = client.post(f"/users/{named.id}/approve", headers=login(client, "admin@medora.tn"),
                    json={"role": "pharmacist", "ward": "Cardiology"})
    assert r.status_code == 200 and (r.json()["role"], r.json()["status"], r.json()["ward"]) == (
        "pharmacist", "active", None)
    assert db.get(Staff, named.id) is None
    bad = make_user(db, "x.req@medora.tn", role=None, status="pending")
    assert client.post(f"/users/{bad.id}/approve", headers=login(client, "admin@medora.tn"),
                       json={"role": "chemist"}).status_code == 422


def test_an_approved_pharmacist_logs_in_and_connects(client, db):
    make_user(db, "ph.ok@medora.tn", role="pharmacist")
    h = login(client, "ph.ok@medora.tn")
    assert client.get("/me", headers=h).json()["role"] == "pharmacist"
    token = h["Authorization"].split()[1]
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_pharmacist_accounts.py`
Expected: FAIL. Register returns 422 for `role: pharmacist`, and approve returns 422.

- [ ] **Step 3: Implement**

In `backend/app/routers/auth.py` (`RegisterIn`):
```python
    role: Literal["patient", "nurse", "doctor", "pharmacist"]  # a request: the approver may change it
    ...
    @model_validator(mode="after")
    def _staff_pick_no_doctor(self) -> "RegisterIn":
        if self.role in ("doctor", "pharmacist") and self.requested_doctor_id:
            raise ValueError("requested_doctor_id: doctors and pharmacists do not pick a doctor")
        return self
```
In `backend/app/services/accounts.py`:
- set `ROLES = ("patient", "nurse", "doctor", "pharmacist", "admin")`;
- change the 422 message in `approve` to `"role: patient, nurse, doctor, pharmacist or admin"`;
- update the module docstring: "Hospital admin: any account, any role (only the admin approves a pharmacist)."

`DOCTOR_MAY_APPROVE` stays `("patient", "nurse")`, and the staff-row block stays `if role in ("doctor", "nurse")`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_pharmacist_accounts.py tests/test_register.py tests/test_signup_approval.py tests/test_user_admin.py`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

Run LINT. Then:
```bash
git add backend/app/routers/auth.py backend/app/services/accounts.py backend/tests/test_pharmacist_accounts.py
git commit -m "feat(backend): pharmacist role in sign-up and admin-only approval"
```

---

### Task 7: Seed (pharmacist, mapped prescriptions, critical demo) and the demo-path smoke

**Files:**
- Modify: `backend/app/services/pharmacy/formulary.py` (`split_med`, `match_drug`, `backfill_drug_ids`)
- Modify: `backend/app/seed.py`
- Modify: `backend/tests/test_followups.py` (`test_staff_list` expected ids)
- Create: `backend/scripts/pharmacy_smoke.py`
- Test: `backend/tests/test_pharmacy_seed.py`, `backend/tests/test_pharmacy_demo_path.py`

**Interfaces:**
- Consumes: `load_formulary`, `W.checks_for`, `PrescriptionReview`.
- Produces:
  - `formulary.split_med(med) -> tuple[str, str]`, `formulary.match_drug(drugs: list[Drug], med: str) -> str | None`, `formulary.backfill_drug_ids(db) -> int`;
  - in `seed`: `PHARMACIST_ID = "u-0008"`, `DEMO_CARE_PLAN: str`, `_pharmacy(db, now) -> None` (idempotent);
  - `scripts.pharmacy_smoke.run_phase_a(c, password: str, patient_id: str = "p-0001") -> dict`, where `c` is any client with `.get/.post(url, headers=, json=, params=)`;
  - the seed account `pharmacist@medora.tn` / "Pharm. Salma" / `u-0008`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_pharmacy_seed.py`:
```python
"""Seed (pharmacy spec §7): pharmacist account, formulary, mapped and validated seed prescription, critical demo."""

from sqlalchemy import select

from app.models import Drug, MedDose, Prescription, PrescriptionReview, Staff, User
from app.seed import DEMO_CARE_PLAN, seed
from app.services.pharmacy.formulary import backfill_drug_ids, match_drug


def test_seed_pharmacist_and_prescriptions(db):
    seed(db)
    ph = db.get(User, "u-0008")
    assert (ph.email, ph.name, ph.role, ph.status) == ("pharmacist@medora.tn", "Pharm. Salma", "pharmacist", "active")
    assert db.get(Staff, "u-0008") is None
    rx = db.get(Prescription, "rx-0001")
    assert [i["drug_id"] for i in rx.items] == ["d-0032", "d-0001"]
    assert (rx.status, rx.reviewed_by) == ("validated", "u-0008")
    assert db.query(PrescriptionReview).filter_by(prescription_id="rx-0001", decision="validated").count() == 1
    demo = db.scalars(select(Prescription).where(Prescription.care_plan == DEMO_CARE_PLAN)).one()
    assert (demo.patient_id, demo.status, demo.urgent, demo.active) == ("p-0001", "pending_pharmacy", False, False)
    assert [(c["code"], c["severity"]) for c in demo.checks] == [("allergy", "critical")] and demo.override_reason
    assert db.query(MedDose).filter_by(prescription_id=demo.id).count() == 0


def test_seed_is_idempotent_with_pharmacy(db):
    seed(db)
    seed(db)
    assert db.query(Drug).count() == 51
    assert len(db.scalars(select(Prescription).where(Prescription.care_plan == DEMO_CARE_PLAN)).all()) == 1
    assert db.query(PrescriptionReview).filter_by(prescription_id="rx-0001").count() == 1


def test_match_drug(db):
    seed(db)
    drugs = list(db.scalars(select(Drug)))
    assert match_drug(drugs, "Amlodipine 5mg") == "d-0032"
    assert match_drug(drugs, "paracetamol 1 g") == "d-0002"
    assert match_drug(drugs, "Doliprane") == "d-0001"
    assert match_drug(drugs, "Aspirin") == "d-0016"
    assert match_drug(drugs, "Zzz 5mg") is None


def test_backfill_fills_only_missing_keys(db):
    seed(db)
    db.add(Prescription(id="rx-9500", patient_id="p-0002", doctor_id="u-0001", care_plan="", active=False,
                        status="stopped", items=[{"med": "Paracetamol 500mg", "times": ["08:00"]},
                                                 {"med": "Herbal tea", "times": ["08:00"]}]))
    db.flush()
    assert backfill_drug_ids(db) == 1
    assert [i["drug_id"] for i in db.get(Prescription, "rx-9500").items] == ["d-0001", None]
    assert backfill_drug_ids(db) == 0


def test_seed_pharmacist_sees_the_critical_demo_first(client):
    from tests.helpers import login

    rows = client.get("/pharmacy/worklist", headers=login(client, "pharmacist@medora.tn")).json()
    assert rows[0]["prescription"]["care_plan"] == DEMO_CARE_PLAN and rows[0]["max_severity"] == "critical"
```

`backend/tests/test_pharmacy_demo_path.py`:
```python
"""The spec §7 demo path, steps 1-5, through the API in-process (the same code as scripts/pharmacy_smoke.py)."""

from scripts import pharmacy_smoke


def test_demo_path_phase_a(client):
    out = pharmacy_smoke.run_phase_a(client, "ward1234")
    assert out["v1"]["status"] == "pending_pharmacy" and out["v2"]["status"] == "validated"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_pharmacy_seed.py tests/test_pharmacy_demo_path.py`
Expected: it fails during collection with `ImportError: cannot import name 'DEMO_CARE_PLAN'`.

- [ ] **Step 3: Name matching and backfill**

Append to `backend/app/services/pharmacy/formulary.py`. Add `import re`, `from app.models import Prescription` (merge into the existing models import) and `from app.services.pharmacy.checks import norm`.
```python
def split_med(med: str) -> tuple[str, str]:
    """'Amlodipine 5mg' → ('amlodipine', '5mg'): the name is the text before the first digit (spec §3 backfill)."""
    m = re.search(r"\d", med or "")
    name, rest = (med[:m.start()], med[m.start():]) if m else (med or "", "")
    return norm(name), re.sub(r"\s+", "", rest.casefold())


def match_drug(drugs: list[Drug], med: str) -> str | None:
    """Case-insensitive match on the DCI or a brand; among several strengths the one written wins, else the
    lowest id."""
    name, strength = split_med(med)
    if not name:
        return None
    hits = [d for d in drugs if name == norm(d.dci) or name in {norm(b) for b in d.brand_names or []}]
    if not hits:
        return None
    same = [d for d in hits if re.sub(r"\s+", "", (d.strength or "").casefold()) == strength]
    return min(same or hits, key=lambda d: d.id).id


def backfill_drug_ids(db: Session) -> int:
    """Set `drug_id` on every prescription item that has no such key yet (null when nothing matches). Returns how
    many prescriptions changed. JSONB: the list is reassigned so SQLAlchemy sees the change."""
    drugs = list(db.scalars(select(Drug).where(Drug.active.is_(True))))
    changed = 0
    for rx in db.scalars(select(Prescription)):
        if all("drug_id" in it for it in rx.items):
            continue
        rx.items = [it if "drug_id" in it else {**it, "drug_id": match_drug(drugs, it.get("med", ""))}
                    for it in rx.items]
        changed += 1
    db.flush()
    return changed
```

- [ ] **Step 4: Seed**

In `backend/app/seed.py`:
- Add `("u-0008", "pharmacist@medora.tn", "Pharm. Salma", "pharmacist", None, None),` to `STAFF`.
- Add the constants `PHARMACIST_ID = "u-0008"` and `STAFF_ROW_ROLES = ("doctor", "nurse")` (only these have a ward or supervisor).
- In `_upsert_missing_staff` and in the fresh path, replace both `if role != "admin"` conditions with `if role in STAFF_ROW_ROLES`.
- Change `reserve_upto(db, "u", 7)` and the `("u", 7)` tuple to 8.
- Imports: add `PrescriptionReview` to the models import, `from app.services.pharmacy import formulary as F` and `from app.services.pharmacy import workflow as W`. Remove the Task 1 `load_formulary` import.
- Add the code below. Then call `_pharmacy(db, now)` in place of both Task 1 `load_formulary(db)` calls:
  - in the already-seeded branch: `_upsert_missing_staff(db, pw)`, then `_pharmacy(db, datetime.now(UTC).replace(second=0, microsecond=0))`, then `return False`;
  - in the fresh path: delete the early `load_formulary(db)` call and call `_pharmacy(db, now)` right after the final `reserve_upto` loop, before `return True`. The `d` sequence is still advanced: `load_formulary` reserves it, and dose ids drawn earlier never collide with the explicit `d-0001…d-0051` drug ids, because they live in another table and have another width.
```python
DEMO_CARE_PLAN = "Demo: penicillin allergy, sent with a doctor override (pharmacy spec §7)"
DEMO_ITEMS = [{"med": "Amoxicillin 1 g", "drug_id": "d-0003", "dose_mg": 1000, "units_per_intake": 1,
               "times": ["08:00", "14:00", "20:00"], "slot": None, "days": 7}]


def _pharmacy(db: Session, now: datetime) -> None:
    """Formulary, drug ids on existing items, rx-0001 validated by the seed pharmacist, and the pending critical demo
    prescription. Idempotent, so it also upgrades a database seeded before the pharmacy existed."""
    F.load_formulary(db)
    F.backfill_drug_ids(db)
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
                            created_at=now - timedelta(minutes=25)))
    db.flush()
```
`p-0001` (Amira) is already allergic to penicillin in `PATIENTS`, so no patient changes. Update the module docstring's seed list with "the pharmacist and the pharmacy demo".

In `backend/tests/test_followups.py::test_staff_list`, change the expected id set to `{"u-0001", "u-0002", "u-0003", "u-0004", "u-0006", "u-0007", "u-0008"}`.

- [ ] **Step 5: The smoke script**

`backend/scripts/pharmacy_smoke.py`:
```python
"""Demo-path smoke for the hospital pharmacy (spec 2026-10-10 §7, §9), over HTTP:

    python scripts/pharmacy_smoke.py --base http://localhost:8000

Needs the seed (`python -m app.seed`); the password comes from SEED_PASSWORD (default ward1234).
tests/test_pharmacy_demo_path.py runs the same functions through the in-process TestClient.
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta

import httpx

AMOX = {"med": "Amoxicillin 1 g", "drug_id": "d-0003", "dose_mg": 1000, "times": ["08:00", "14:00", "20:00"],
        "days": 7}
AZI = {"med": "Azithromycin 250 mg", "drug_id": "d-0006", "units_per_intake": 2, "times": ["08:00"], "days": 3}


def _check(cond: bool, what: str) -> None:
    if not cond:
        raise SystemExit(f"smoke failed: {what}")


def _ok(r, status: int = 200) -> dict | list:
    _check(r.status_code == status, f"{r.request.method} {r.request.url} -> {r.status_code} {r.text}")
    return r.json()


def _login(c, email: str, password: str) -> dict:
    token = _ok(c.post("/auth/login", json={"email": email, "password": password}))["access_token"]
    return {"Authorization": f"Bearer {token}"}


def tunis_day(offset_days: int = 0) -> str:
    return (datetime.now(UTC) + timedelta(hours=1, days=offset_days)).date().isoformat()


def run_phase_a(c, password: str, patient_id: str = "p-0001") -> dict:
    """Steps 1-5: live allergy warning, send with a reason, red on the worklist, change requested, resubmit with
    azithromycin, validate, doses on the nurse round."""
    doc, ph = _login(c, "doctor@medora.tn", password), _login(c, "pharmacist@medora.tn", password)
    nurse = _login(c, "nurse@medora.tn", password)
    checks = _ok(c.post("/prescriptions/check", headers=doc, json={"patient_id": patient_id, "items": [AMOX]}))
    _check(any(x["code"] == "allergy" and x["severity"] == "critical" for x in checks["checks"]), "allergy warning")
    body = {"patient_id": patient_id, "items": [AMOX], "care_plan": ""}
    r = c.post("/prescriptions", headers=doc, json=body)
    _check(r.status_code == 422 and r.json()["code"] == "override_required", "override required")
    v1 = _ok(c.post("/prescriptions", headers=doc, json={**body, "override_reason": "Smoke: allergy unclear"}), 201)
    row = next((w for w in _ok(c.get("/pharmacy/worklist", headers=ph)) if w["prescription"]["id"] == v1["id"]), None)
    _check(row is not None and row["max_severity"] == "critical", "critical row on the worklist")
    _ok(c.post(f"/pharmacy/prescriptions/{v1['id']}/request-changes", headers=ph,
               json={"comment": "allergie pénicilline → azithromycine"}))
    v2 = _ok(c.post("/prescriptions", headers=doc, json={"patient_id": patient_id, "items": [AZI], "care_plan": "",
                                                         "replaces_id": v1["id"]}), 201)
    done = _ok(c.post(f"/pharmacy/prescriptions/{v2['id']}/validate", headers=ph,
                      json={"acknowledged": bool(v2["checks"])}))
    _check(done["status"] == "validated", "v2 validated")
    doses = [d for day in (tunis_day(0), tunis_day(1))
             for d in _ok(c.get(f"/patients/{patient_id}/doses", headers=nurse, params={"date": day}))]
    _check(any(d["prescription_id"] == v2["id"] for d in doses), "azithromycin doses on the nurse round")
    return {"v1": v1, "v2": done}  # v1 as saved (pending_pharmacy); it is superseded by now


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pharmacy demo-path smoke test")
    ap.add_argument("--base", default="http://localhost:8000")
    args = ap.parse_args(argv)
    password = os.environ.get("SEED_PASSWORD", "ward1234")
    with httpx.Client(base_url=args.base, timeout=10) as c:
        run_phase_a(c, password)
    print("pharmacy smoke: phase A ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider`
Expected: the whole suite passes, `test_seed.py` and `test_followups.py` included.

- [ ] **Step 7: Lint and commit**

Run LINT. Then:
```bash
git add backend/app/services/pharmacy/formulary.py backend/app/seed.py backend/tests/test_followups.py backend/scripts/pharmacy_smoke.py backend/tests/test_pharmacy_seed.py backend/tests/test_pharmacy_demo_path.py
git commit -m "feat(backend): pharmacy seed (pharmacist, mapped prescriptions, critical demo) and demo smoke"
```

---

### Task 8: Contracts (api 1.12, data-model 1.7, n8n-webhooks 1.4)

**Files:**
- Modify: `docs/contracts/api.md`
- Modify: `docs/contracts/data-model.md`
- Modify: `docs/contracts/n8n-webhooks.md`

**Interfaces:**
- Consumes: the shapes built in Tasks 1–7, plus the Phase B shapes of Tasks 9–12, documented now as "Phase B: planned" so the web side can build its mocks against them.
- Produces: the frozen contract the web plan mirrors.

- [ ] **Step 1: api.md**

1. Header: `> **Version:** 1.12 (2026-10-10) · **Owners:** Wali (core, IoT, alerts), Faouzi (appointments, AI, integrations, exams, notebook), Hedi (pharmacy)`.
2. Conventions:
   - the JWT `role` list becomes `doctor|nurse|admin|patient|pharmacist`;
   - append to the IDs line: `` `d-0001` drug (formulary; shares the counter with doses but has 4 digits), `pr-0001` prescription review, `lot-0001` stock lot, `sm-0001` stock movement, `disp-0001` dispensation, `dl-000001` dispensation line ``.
3. The seed accounts line: add `` `pharmacist@medora.tn` ``.
4. In "Accounts and access":
   - `POST /auth/register`: the role list becomes `patient`/`nurse`/`doctor`/`pharmacist`. Add: "`role: "pharmacist"` with a `requested_doctor_id` is 422."
   - `POST /users/{id}/approve`: the role list becomes "patient, nurse, doctor, pharmacist or admin". Add: "**Only the admin approves a pharmacist**; a pharmacist has no ward and no team."
5. Replace the whole "## Prescriptions → schedule" section with:

````markdown
## Prescriptions → pharmacy review → schedule

Changed in 1.12 (spec `docs/superpowers/specs/2026-10-10-hospital-pharmacy-design.md`). A new prescription waits for the pharmacist: it has no dose until it is validated, unless the doctor ticks `urgent`.

| Method & path | Roles | Notes |
|---|---|---|
| `POST /prescriptions/check` | doctor (attending) | Dry run while typing: `{patient_id, items[], replaces_id?}` → `{"checks": [Check]}`. Writes only an audit row (`prescription_check`). 422 `unknown_drug`; 404 unknown patient or `replaces_id`; 409 `conflict` if `replaces_id` is another patient's. |
| `POST /prescriptions` | doctor (attending) | `{patient_id, items[], care_plan, urgent?: bool = false, override_reason?: str ≤ 500, replaces_id?: str}` → 201 `Prescription` + `schedule_version`, `published_to_device`. Always saved as `pending_pharmacy`. `urgent: true`: doses are created and the schedule published at once. |
| `PATCH /prescriptions/{id}` | doctor (attending) | `{"active": false}` only (`true` is 422): stops it at once (status `stopped`, future doses deleted, schedule re-published) → same shape as POST. Allowed from `pending_pharmacy`, `changes_requested`, `validated`; otherwise 409 `bad_status`. Other edits = a new version through `replaces_id`. |

Item: `{med, drug_id?, dose_mg?, units_per_intake?, times[], slot?, days?}`. `med` (1–80) is the display string. `drug_id` is null for a non-formulary drug. `dose_mg` (> 0) is mg **per intake**; when absent the dose check uses `units_per_intake` (integer 1–10, default 1) × the drug's `unit_mg`. `times` has 1–8 `HH:MM`, `slot` is 1–4 or null, and `days` is 1–60 (default 1).

Errors: 422 `override_required` (a `critical` check and no non-blank `override_reason`; nothing is saved), 422 `unknown_drug` (unknown or inactive `drug_id`), 409 `conflict` (`replaces_id` belongs to another patient, is not `pending_pharmacy`/`changes_requested`/`validated`, or already has a live newer version), 404 (`replaces_id` unknown).

Versions: the new row gets `version = old.version + 1` and `replaces_id = old.id`. A replaced version that never ran (`pending_pharmacy` without urgent, or `changes_requested`) becomes `superseded` at once. A running one keeps running until the new version is validated, then becomes `superseded`. **Exception:** an `urgent` new version supersedes the running one at once (no double dosing); if that urgent version is then rejected, the old one is not restored. A rejected non-urgent new version leaves the old one as it was.

`active` is derived: true for `validated`, and for `pending_pharmacy` with `urgent`. Doses of a non-urgent prescription start at its validation time; an urgent one's start when it was written.

```jsonc
// Prescription (doctor, nurse, pharmacist)
{ "id": "rx-0002", "patient_id": "p-0001", "doctor_id": "u-0001", "items": [ ... ], "care_plan": "",
  "active": false, "created_at": "...", "status": "pending_pharmacy",   // pending_pharmacy|validated|changes_requested|rejected|stopped|superseded
  "urgent": false, "version": 1, "replaces_id": null, "checks": [Check],  // the checks stored at the last save or decision
  "override_reason": "…", "review_comment": null, "reviewed_by_name": null, "reviewed_at": null }
// Prescription (patient, self): only id, patient_id, doctor_id, items, care_plan, active, created_at, status
// POST/PATCH response: Prescription + "schedule_version": 4 | null, "published_to_device": bool (false when no dose changed)

// Check (sorted: critical, major, moderate, info; then item_index; then code)
{ "code": "allergy", "severity": "critical", "item_index": 0, "drug_id": "d-0003",
  "params": { "med": "Amoxicillin 1 g", "allergy": "penicillin", "class": "penicillin" },
  "message": "Amoxicillin: the patient is allergic to penicillin (penicillin)" }   // English, for logs; the web translates by code + params
```

| `code` | severity | `params` |
|---|---|---|
| `allergy` | critical | `med, allergy` (the patient's wording), `class` |
| `interaction` | critical \| major \| moderate | `med, groups[2], note, with_med, with_drug_id, with_item_index` (null when the other drug is in another prescription), `with_prescription_id` (null inside the same prescription) |
| `max_daily_dose` | major; critical above 2× | `med, daily_mg, max_daily_mg` |
| `duplicate_therapy` | major | `med, reason` (`same_dci`\|`same_atc_class`), `with_med, with_drug_id, with_item_index, with_prescription_id` |
| `non_formulary` | moderate | `med` |
| `high_alert` | info | `med` |
| `elderly` | moderate | `med, age` |

`GET /patients/{id}/prescriptions` returns the role's Prescription shape. `GET /patients/{id}/doses` is unchanged in Phase A: the nurse view shows the "pending pharmacy review" badge by joining `prescription_id` to this list (`status == "pending_pharmacy" && urgent`). `POST /doses/{id}/given` returns 409 `bad_status` when the dose's prescription is not active.
````

6. Add these sections after "Prescriptions → pharmacy review → schedule":

````markdown
## Drug catalogue (1.12)

| Method & path | Roles | Notes |
|---|---|---|
| `GET /drugs?q=&active=true` | doctor, nurse, pharmacist, admin | → `[Drug]`, at most 50, ordered by DCI then strength. `q` (≤ 80) matches the DCI or a brand (substring) or the ATC code (prefix), case-insensitive, taken literally (`%`, `_` are not wildcards). `active`: `true` (default, active only), `false` (inactive only), `all`. Not audited (no patient data). |
| `POST /drugs` | pharmacist, admin | `DrugIn` → 201 `Drug`. 409 `conflict` if the same DCI (case-insensitive) + strength + form exists. Audited (`drug`). |
| `PATCH /drugs/{id}` | pharmacist, admin | Any `DrugIn` field → `Drug`. `unit_mg`/`max_daily_mg` may be set to null; other nulls are 422. `{"active": false}` retires a drug; there is no DELETE (405). Audited. |

```jsonc
// Drug
{ "id": "d-0003", "dci": "Amoxicillin", "brand_names": ["Clamoxyl"], "form": "tablet", "strength": "1 g",
  "unit_mg": 1000.0, "max_daily_mg": 6000.0, "atc_code": "J01CA04", "allergy_classes": ["penicillin", "beta_lactam"],
  "interaction_groups": [], "high_alert": false, "min_stock": 100, "active": true, "created_at": "...", "updated_at": "..." }
// DrugIn: dci (1–120), brand_names (≤ 20 × 1–80), form (tablet|capsule|syrup|injection|inhaler|patch|drops|other),
// strength (≤ 40), unit_mg (> 0 | null), max_daily_mg (> 0 | null), atc_code ("" or e.g. J01CA04; upper-cased),
// allergy_classes / interaction_groups (≤ 20 tags, lower-cased, ^[a-z][a-z0-9_]{0,39}$), high_alert, min_stock (≥ 0), active
```

## Pharmacist (1.12)

Role `pharmacist` only (403 for everyone else). Every worklist row and every review read writes `audit_log` (resource `prescription`, with `patient_id`), and so does every decision. The patient part is a minimal projection, never the full record: `{id, name, age, sex, ward, bed, allergies}` (no weight column exists; age is null without a date of birth).

| Method & path | Notes |
|---|---|
| `GET /pharmacy/worklist?status=pending_pharmacy` | `status`: `pending_pharmacy` (default), `changes_requested`, `all` (every status, the newest 200); anything else 422 → `[WorklistItem]`, urgent first, then the highest severity, then the oldest |
| `GET /pharmacy/prescriptions/{id}` | → `ReviewDetail`; 404 unknown |
| `POST /pharmacy/prescriptions/{id}/validate` | `{acknowledged?: bool = false, comment?: str ≤ 500}` → `Prescription`. 409 `bad_status` unless `pending_pharmacy`; 422 `ack_required` if the checks recomputed now are not empty and `acknowledged` is false |
| `POST /pharmacy/prescriptions/{id}/request-changes` | `{comment}` (1–500 after trimming; required) → `Prescription`; 409 `bad_status` |
| `POST /pharmacy/prescriptions/{id}/reject` | `{comment}` (1–500; required) → `Prescription`; 409 `bad_status` |
| `GET /pharmacy/summary` | → `{pending, urgent_pending, critical_pending, changes_requested}`; Phase B adds `low_stock` (drugs under `min_stock`) and `expiring` (lots with stock expiring within 30 days) |

Two pharmacists deciding at once: the status is checked under `SELECT … FOR UPDATE`, so the second gets 409 `bad_status`.

Side effects of a decision: the checks are recomputed and stored. A `prescription_reviews` row is written. Doses are rebuilt and the device schedule is re-published when something starts or stops: on validation, and on rejecting or requesting changes on an urgent prescription (future doses deleted). On validation, the version it replaces is superseded. Then the `prescription_status` WS frame goes out, and the n8n event `prescription.review`.

```jsonc
// WorklistItem
{ "prescription": Prescription, "patient": { "id": "p-0001", "name": "Amira Ben Salah", "age": 54, "sex": "F",
  "ward": "Cardiology", "bed": "C-12", "allergies": ["penicillin"] }, "doctor_name": "Dr Trabelsi",
  "checks": [Check], "urgent": false, "waiting_since": "...", "max_severity": "critical" }   // null without checks
// ReviewDetail
{ "prescription": Prescription, "patient": {…}, "doctor_name": "…",
  "running": [Prescription],   // the patient's other running prescriptions, without this one and the versions it replaces
  "checks": [Check],           // recomputed now
  "history": [Review],         // decisions on this prescription and the versions it replaces, newest first
  "replaces": Prescription | null }
// Review
{ "id": "pr-0001", "prescription_id": "rx-0002", "pharmacist_id": "u-0008", "pharmacist_name": "Pharm. Salma",
  "decision": "changes_requested", "comment": "…", "checks_snapshot": [Check], "created_at": "..." }
```

## Dispensing and stock (1.12, Phase B: planned)

| Method & path | Roles | Notes |
|---|---|---|
| `GET /pharmacy/dispensing?date=YYYY-MM-DD&round=HH:MM&ward=` | pharmacist | `round` required; `date` defaults to today (Africa/Tunis); `ward` optional → `[{ward, patients: [{id, name, bed, doses: [RoundDose]}]}]`. Only doses of active prescriptions (validated, or urgent pending). Audited per patient. |
| `POST /pharmacy/dispensations` | pharmacist | `{ward, date, round_time, lines: [{dose_id, lot_id?}]}` (1–200 lines) → 201 `Dispensation` (`sent`). One transaction: dispensation, lot decrements (FEFO when `lot_id` is missing), stock movements. 409 `insufficient_stock` (body adds `drug_id`), 409 `already_dispensed`, 409 `bad_status` (prescription no longer active), 422 `invalid` (dose not in that ward/date/round, a dose twice, a lot of another drug, an expired lot, a lot on a non-formulary dose), 404 unknown dose. A refused request writes nothing. |
| `GET /dispensations?ward=&date=` | nurse (own ward only; another ward is 403), pharmacist | `date` defaults to today → `[Dispensation]` |
| `POST /dispensations/{id}/receive` | nurse of that ward | → `Dispensation` (`received`); idempotent; another ward 403 |
| `GET /pharmacy/stock` | pharmacist, admin | → `[StockItem]` for every active drug |
| `POST /pharmacy/stock/receipts` | pharmacist | `{drug_id, lot_number (1–40), expiry_date, quantity (1–100000)}` → 201 `Lot`. Tops up the lot when `(drug_id, lot_number)` exists; 409 `conflict` if it exists with another expiry; 422 if already expired; 404 unknown drug |
| `POST /pharmacy/stock/adjustments` | pharmacist | `{lot_id, delta (≠ 0, ±100000), reason: adjustment\|expired\|return, comment (1–500)}` → `Lot`. `expired` needs a negative delta (422). Below zero: 409 `insufficient_stock` (+ `drug_id`) |
| `GET /pharmacy/stock/reorder` | pharmacist, admin | → `[{drug_id, dci, strength, form, on_hand, min_stock, suggested_quantity}]` for drugs with `on_hand < min_stock`; `suggested_quantity = 2 × min_stock − on_hand` |

```jsonc
// RoundDose
{ "dose_id": "d-000123", "prescription_id": "rx-0001", "med": "Paracetamol 500mg", "drug_id": "d-0001", "quantity": 1,
  "suggested_lot": { "id": "lot-0001", "lot_number": "L0001-A", "expiry_date": "2027-10-10" } | null,
  "on_hand": 200 | null,   // null for a non-formulary dose
  "dispensed": false }
// Dispensation
{ "id": "disp-0001", "ward": "Cardiology", "round_date": "2026-10-10", "round_time": "20:00", "status": "sent",
  "prepared_by": "u-0008", "prepared_by_name": "Pharm. Salma", "prepared_at": "...",
  "received_by": null, "received_by_name": null, "received_at": null,
  "lines": [{ "id": "dl-000001", "dose_id": "d-000123" | null, "patient_id": "p-0001", "patient_name": "Amira Ben Salah",
              "bed": "C-12", "drug_id": "d-0001" | null, "lot_id": "lot-0001" | null, "lot_number": "L0001-A" | null,
              "quantity": 1, "med": "Paracetamol 500mg" }] }   // dose_id becomes null if the dose was later cancelled
// StockItem
{ "drug_id": "d-0001", "dci": "Paracetamol", "strength": "500 mg", "form": "tablet", "on_hand": 200, "min_stock": 200,
  "lots": [Lot], "low": false, "expiring": false, "expired": false }
// Lot (lots[] lists lots with quantity > 0)
{ "id": "lot-0001", "drug_id": "d-0001", "lot_number": "L0001-A", "expiry_date": "2027-10-10", "quantity": 200,
  "received_at": "...", "expired": false, "expiring": false }
```

`on_hand` is the sum of the lots that are not expired. `low` means `on_hand < min_stock`. A lot is `expiring` when it has stock and expires within 30 days (today included), and `expired` when its expiry is before today. FEFO takes, among the lots that are not expired on the round date and hold the whole line, the one that expires first (ties: oldest receipt, then id). One line takes from one lot.

Nurse round: each `Dose` in `GET /patients/{id}/doses` (and `POST /doses/{id}/given`) adds `"pharmacy": "none"|"sent"|"received"`. A dose can still be given when it is not dispensed (ward stock).
````

7. WebSocket section:
   - add the frame line `{ "type": "prescription_status", "data": { "prescription_id": "rx-0002", "patient_id": "p-0001", "status": "validated", "urgent": false } }`;
   - extend the filtering sentence: "…an admin only `device_status`, a pharmacist only `prescription_status` (every patient). `prescription_status` is sent on every status change (save, stop, decision, supersede) to the attending doctor, the patient's ward nurses and every pharmacist."
8. Changelog (top): `- **1.12** (2026-10-10): hospital pharmacy. Role `pharmacist` (sign-up; only the admin approves). Drug catalogue (`/drugs`). Prescriptions gain a pharmacy status, `urgent`, versions (`replaces_id`), `checks`, `override_reason` and review fields; `POST /prescriptions/check` dry run; 422 `override_required`/`unknown_drug`; `PATCH` only stops. Pharmacist worklist, review and decisions (`/pharmacy/*`), WS `prescription_status`; `POST /doses/{id}/given` refuses doses of inactive prescriptions. Phase B (planned): dispensing, nurse receipt, stock, the dose `pharmacy` field. Owner: Hedi.`

- [ ] **Step 2: data-model.md**

1. Header: `> **Version:** 1.7 (2026-10-10) · …` (rest unchanged).
2. Entity diagram: add these lines:
   `drugs ||--o{ stock_lots : stocked_as`, `prescriptions ||--o{ prescription_reviews : reviewed_in`, `dispensations ||--o{ dispensation_lines : contains`, `med_doses ||--o| dispensation_lines : dispensed_as`.
3. `users.role`: `` `doctor` \| `nurse` \| `admin` \| `patient` \| `pharmacist` ``. `requested_role`: add `` \| `pharmacist` ``.
4. Replace the `prescriptions` table with:

```markdown
### `prescriptions`
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `rx-0001` |
| `patient_id`, `doctor_id` | text FK | |
| `items` | jsonb | `[{med, drug_id?, dose_mg?, units_per_intake (default 1), times[], slot, days}]`; `med` is the display string, `drug_id` null = non-formulary |
| `care_plan` | text | |
| `active` | bool | derived (1.7): `status = validated`, or `pending_pharmacy` with `urgent`; kept for the dose and schedule code |
| `created_at` | timestamptz | |
| `status` | text, default `validated` (1.7) | `pending_pharmacy` \| `validated` \| `changes_requested` \| `rejected` \| `stopped` \| `superseded`; indexed |
| `urgent` | bool, default false (1.7) | doses start at once; reviewed right after |
| `version` | int, default 1 (1.7) | |
| `replaces_id` | text FK → prescriptions, null (1.7) | the version this one replaces |
| `checks` | jsonb, default `[]` (1.7) | the last check results (api.md → Check) |
| `override_reason` | text, null (1.7) | required by the API when a check is critical |
| `reviewed_by` | text FK → users, null (1.7) | the pharmacist of the last decision |
| `reviewed_at` | timestamptz, null (1.7) | non-urgent doses start here |
| `review_comment` | text, null (1.7) | |

Migration 0007 backfill: `active` rows become `validated`, the others `stopped`. The seed fills `items[].drug_id` (case-insensitive match on the DCI or a brand, on the text before the first digit) and validates the seed prescription with the seed pharmacist.
```

5. Add these sections before "## AI-output convention":

```markdown
### `drugs` (1.7, migration 0007)
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `d-0001` (shares the `d` sequence with doses) |
| `dci` | text | generic name |
| `brand_names` | jsonb text[] | for search |
| `form` | text | tablet \| capsule \| syrup \| injection \| inhaler \| patch \| drops \| other |
| `strength` | text | display only |
| `unit_mg`, `max_daily_mg` | numeric, null | mg per unit; adult max per day (null = no dose check) |
| `atc_code` | text, default `''` | |
| `allergy_classes`, `interaction_groups` | jsonb text[] | tags used by the checks |
| `high_alert` | bool | |
| `min_stock` | int, default 0 | Phase B |
| `active` | bool | never deleted |
| `created_at`, `updated_at` | timestamptz | |

Seed: `backend/app/data/pharmacy/formulary.v1.json` (51 synthetic drugs; illustrative, not a clinical reference). Rules: `backend/app/rules/pharmacy/*.v1.json`.

### `prescription_reviews` (1.7, migration 0007)
`id` (`pr-0001`), `prescription_id` → prescriptions (indexed), `pharmacist_id` → users, `decision` (`validated` \| `changes_requested` \| `rejected`), `comment` (text, null), `checks_snapshot` jsonb, `created_at`.

### Phase B tables (1.7, migration 0008, planned)
| Table | Columns |
|---|---|
| `stock_lots` | `id` (`lot-0001`), `drug_id` → drugs, `lot_number`, `expiry_date` date, `quantity` int ≥ 0 (check constraint), `received_at`; unique (`drug_id`, `lot_number`) |
| `stock_movements` | `id` (`sm-0001`), `drug_id` → drugs, `lot_id` → stock_lots (null), `delta` int, `reason` (`receipt` \| `dispense` \| `adjustment` \| `expired` \| `return`), `ref_id` (null; the dispensation id for `dispense`), `comment` (text, null), `by_user_id` → users, `created_at`. **Append-only** (a trigger refuses UPDATE and DELETE). Lot quantities change in the same transaction as their movement. |
| `dispensations` | `id` (`disp-0001`), `ward`, `round_date` date, `round_time` `HH:MM`, `status` (`sent` \| `received`), `prepared_by` → users, `prepared_at`, `received_by` → users (null), `received_at` (null) |
| `dispensation_lines` | `id` (`dl-000001`), `dispensation_id` → dispensations, `dose_id` → med_doses (null; **unique**; `ON DELETE SET NULL`), `patient_id` → patients, `drug_id` → drugs (null = non-formulary), `lot_id` → stock_lots (null), `quantity` int, `med` text |
```

6. Role permission matrix: add a `Pharmacist` column. Give every existing row `—`, with these exceptions:
   - `Patient demographics`: `R (name, age, sex, ward, bed, allergies) all, via /pharmacy only`;
   - `Prescriptions`: `R all; W review decision`;
   - `Med doses`: `—` (Phase B: `R` round view).

   Then add these rows:
   - `| Drug catalogue | R | R | RW | — | RW |`
   - `| Stock (Phase B) | — | — | R | — | RW |`
   - `| Dispensations (Phase B) | — | R/receive ward | — | — | RW |`

   Column order: Doctor, Nurse, Admin, Patient, Pharmacist. In the existing `Prescriptions` row, the doctor stays `RW own`.
7. Seed data list: add `` - 1 pharmacist (`u-0008`, `pharmacist@medora.tn`, "Pharm. Salma") ``, `- 51 formulary drugs (d-0001…d-0051)`, and `` - the seed prescription mapped to drugs and validated by the pharmacist, plus 1 pending demo prescription (amoxicillin for penicillin-allergic `p-0001`, with an override reason: a critical allergy check) ``.
8. Changelog: `- **1.7** (2026-10-10): hospital pharmacy. `drugs`, `prescription_reviews` and the new `prescriptions` columns (migration 0007); Phase B tables `stock_lots`, `stock_movements`, `dispensations`, `dispensation_lines` (migration 0008, planned); role `pharmacist`. Owner: Hedi.`

- [ ] **Step 3: n8n-webhooks.md**

1. Header: `> **Version:** 1.4 (2026-10-10) · …`.
2. Add to the events table: `| `prescription.review` | a pharmacist validates, requests changes on or rejects a prescription | `{prescription_id, patient_id, decision, comment, doctor_email, doctor_chat_id}`; `decision` is `validated` \| `changes_requested` \| `rejected`; `comment` null when empty; `doctor_email`/`doctor_chat_id` null when the doctor's account is not active or has no chat id. Emitted only after the decision commits. | W9 (optional) |`
3. Add to the workflows table: `| W9 | Prescription review notice | optional (Faouzi) | event `prescription.review` → Telegram (`doctor_chat_id`) + email (`doctor_email`) to the prescribing doctor: "Pharmacy: {decision} for {prescription_id}: {comment}" |`
4. Changelog: `- **1.4** (2026-10-10): adds `prescription.review` (hospital pharmacy) and optional W9. Emitter: `app/services/pharmacy/workflow.py`. Owner: Hedi; workflow: Faouzi.`

- [ ] **Step 4: Check the contract against the code**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_prescribing.py tests/test_pharmacy_review.py tests/test_drugs_api.py`
Expected: PASS. These tests assert the key sets documented above. Re-read each documented field list against `rx_out`, `worklist_item`, `detail`, `review_out` and `drug_out`.

- [ ] **Step 5: Commit**

```bash
git add docs/contracts/api.md docs/contracts/data-model.md docs/contracts/n8n-webhooks.md
git commit -m "docs(contracts): hospital pharmacy (api 1.12, data-model 1.7, n8n-webhooks 1.4)"
```

**Phase A ends here.** Run the full TEST and LINT commands once more. Phase A is complete: the role, the catalogue, the checks, the gate with its urgent bypass, the review, the seed, the smoke script and the contracts.

---

# Phase B: logistics

### Task 9: Migration 0008 and the stock and dispensing models

**Files:**
- Create: `backend/alembic/versions/0008_pharmacy_stock.py`
- Modify: `backend/app/models/pharmacy.py` (four classes + trigger DDL)
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_pharmacy_stock_models.py`

**Interfaces:**
- Produces: `StockLot`, `StockMovement` (append-only), `Dispensation`, `DispensationLine` (unique `dose_id`, `ON DELETE SET NULL`). All are exported from `app.models`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_pharmacy_stock_models.py`:
```python
"""Migration 0008 invariants through create_all: no negative lot, one lot number per drug, append-only movements,
one line per dose, a cancelled dose detaches its line."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import Dispensation, DispensationLine, MedDose, Prescription, StockLot, StockMovement


def _lot(db, lot_id="lot-t1", number="T1", qty=5):
    db.add(StockLot(id=lot_id, drug_id="d-0001", lot_number=number, expiry_date=date.today() + timedelta(days=90),
                    quantity=qty))
    db.flush()


def test_lot_quantity_cannot_go_negative(db, seeded):
    with pytest.raises(IntegrityError), db.begin_nested():
        _lot(db, qty=-1)


def test_one_lot_number_per_drug(db, seeded):
    _lot(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        _lot(db, lot_id="lot-t2")


def test_movements_are_append_only(db, seeded):
    _lot(db)
    db.add(StockMovement(id="sm-t1", drug_id="d-0001", lot_id="lot-t1", delta=5, reason="receipt",
                         by_user_id="u-0004"))
    db.flush()
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(update(StockMovement).where(StockMovement.id == "sm-t1").values(delta=6))
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(delete(StockMovement).where(StockMovement.id == "sm-t1"))


def _dose(db, dose_id="d-t00001"):
    """A prescription, one dose and an empty dispensation to hang lines on."""
    db.add(Prescription(id="rx-t1", patient_id="p-0001", doctor_id="u-0001", items=[], care_plan="", active=True))
    db.flush()
    db.add(MedDose(id=dose_id, prescription_id="rx-t1", patient_id="p-0001", scheduled_at=datetime.now(UTC),
                   time_of_day="20:00", meds=["X"], slot=None))
    db.add(Dispensation(id="disp-t1", ward="Cardiology", round_date=date.today(), round_time="20:00", status="sent",
                        prepared_by="u-0004"))
    db.flush()


def test_one_line_per_dose_and_cancel_detaches(db, seeded):
    _dose(db)
    db.add(DispensationLine(id="dl-t1", dispensation_id="disp-t1", dose_id="d-t00001", patient_id="p-0001",
                            drug_id=None, lot_id=None, quantity=1, med="X"))
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(DispensationLine(id="dl-t2", dispensation_id="disp-t1", dose_id="d-t00001", patient_id="p-0001",
                                drug_id=None, lot_id=None, quantity=1, med="X"))
        db.flush()
    db.execute(delete(MedDose).where(MedDose.id == "d-t00001"))
    db.expire_all()
    assert db.get(DispensationLine, "dl-t1").dose_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_pharmacy_stock_models.py`
Expected: it fails during collection with `ImportError: cannot import name 'StockLot'`.

- [ ] **Step 3: Models**

Append to `backend/app/models/pharmacy.py`. Extend the imports with `from datetime import date`, `from sqlalchemy import DDL, CheckConstraint, Date, Index, UniqueConstraint, event`.
```python
class StockLot(Base):
    __tablename__ = "stock_lots"
    __table_args__ = (CheckConstraint("quantity >= 0", name="ck_stock_lots_quantity_nonneg"),
                      UniqueConstraint("drug_id", "lot_number", name="uq_stock_lots_drug_lot"))
    id: Mapped[str] = mapped_column(String, primary_key=True)  # lot-0001
    drug_id: Mapped[str] = mapped_column(ForeignKey("drugs.id"), index=True)
    lot_number: Mapped[str] = mapped_column(String)
    expiry_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StockMovement(Base):
    """Append-only: a trigger refuses UPDATE and DELETE (like audit_log)."""

    __tablename__ = "stock_movements"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # sm-0001
    drug_id: Mapped[str] = mapped_column(ForeignKey("drugs.id"), index=True)
    lot_id: Mapped[str | None] = mapped_column(ForeignKey("stock_lots.id"))
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String)  # receipt | dispense | adjustment | expired | return
    ref_id: Mapped[str | None] = mapped_column(String)
    comment: Mapped[str | None] = mapped_column(Text)
    by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


STOCK_APPEND_ONLY_SQL = """
CREATE OR REPLACE FUNCTION stock_movements_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'stock_movements is append-only'; END $$;
CREATE TRIGGER stock_movements_append_only BEFORE UPDATE OR DELETE ON stock_movements
FOR EACH ROW EXECUTE FUNCTION stock_movements_append_only();
"""
event.listen(StockMovement.__table__, "after_create", DDL(STOCK_APPEND_ONLY_SQL))


class Dispensation(Base):
    __tablename__ = "dispensations"
    __table_args__ = (Index("ix_dispensations_ward_round_date", "ward", "round_date"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)  # disp-0001
    ward: Mapped[str] = mapped_column(String)
    round_date: Mapped[date] = mapped_column(Date)
    round_time: Mapped[str] = mapped_column(String)  # HH:MM Africa/Tunis
    status: Mapped[str] = mapped_column(String, default="sent", server_default="sent")  # sent | received
    prepared_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    received_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DispensationLine(Base):
    __tablename__ = "dispensation_lines"
    __table_args__ = (Index("uq_dispensation_lines_dose_id", "dose_id", unique=True),)
    id: Mapped[str] = mapped_column(String, primary_key=True)  # dl-000001
    dispensation_id: Mapped[str] = mapped_column(ForeignKey("dispensations.id"), index=True)
    # SET NULL: a rebuild may delete a future dose that was already sent; the line stays as the record
    dose_id: Mapped[str | None] = mapped_column(ForeignKey("med_doses.id", ondelete="SET NULL"))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    drug_id: Mapped[str | None] = mapped_column(ForeignKey("drugs.id"))
    lot_id: Mapped[str | None] = mapped_column(ForeignKey("stock_lots.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    med: Mapped[str] = mapped_column(Text)
```
Export the four classes from `app/models/__init__.py`.

- [ ] **Step 4: Migration**

`backend/alembic/versions/0008_pharmacy_stock.py`:
```python
"""Hospital pharmacy, Phase B: stock_lots, stock_movements (append-only), dispensations, dispensation_lines
(data-model 1.7)

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_lots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("drug_id", sa.String(), sa.ForeignKey("drugs.id"), nullable=False),
        sa.Column("lot_number", sa.String(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_stock_lots_quantity_nonneg"),
        sa.UniqueConstraint("drug_id", "lot_number", name="uq_stock_lots_drug_lot"),
    )
    op.create_index("ix_stock_lots_drug_id", "stock_lots", ["drug_id"])
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("drug_id", sa.String(), sa.ForeignKey("drugs.id"), nullable=False),
        sa.Column("lot_id", sa.String(), sa.ForeignKey("stock_lots.id"), nullable=True),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("ref_id", sa.String(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_stock_movements_drug_id", "stock_movements", ["drug_id"])
    # same SQL as app.models.pharmacy.STOCK_APPEND_ONLY_SQL (which covers create_all in tests)
    op.execute("""
CREATE OR REPLACE FUNCTION stock_movements_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'stock_movements is append-only'; END $$;
CREATE TRIGGER stock_movements_append_only BEFORE UPDATE OR DELETE ON stock_movements
FOR EACH ROW EXECUTE FUNCTION stock_movements_append_only();
""")
    op.create_table(
        "dispensations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("ward", sa.String(), nullable=False),
        sa.Column("round_date", sa.Date(), nullable=False),
        sa.Column("round_time", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="sent"),
        sa.Column("prepared_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("received_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_dispensations_ward_round_date", "dispensations", ["ward", "round_date"])
    op.create_table(
        "dispensation_lines",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dispensation_id", sa.String(), sa.ForeignKey("dispensations.id"), nullable=False),
        sa.Column("dose_id", sa.String(), sa.ForeignKey("med_doses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("patient_id", sa.String(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("drug_id", sa.String(), sa.ForeignKey("drugs.id"), nullable=True),
        sa.Column("lot_id", sa.String(), sa.ForeignKey("stock_lots.id"), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("med", sa.Text(), nullable=False),
    )
    op.create_index("ix_dispensation_lines_dispensation_id", "dispensation_lines", ["dispensation_id"])
    op.create_index("uq_dispensation_lines_dose_id", "dispensation_lines", ["dose_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_dispensation_lines_dose_id", table_name="dispensation_lines")
    op.drop_index("ix_dispensation_lines_dispensation_id", table_name="dispensation_lines")
    op.drop_table("dispensation_lines")
    op.drop_index("ix_dispensations_ward_round_date", table_name="dispensations")
    op.drop_table("dispensations")
    op.execute("DROP TRIGGER IF EXISTS stock_movements_append_only ON stock_movements")
    op.execute("DROP FUNCTION IF EXISTS stock_movements_append_only()")
    op.drop_index("ix_stock_movements_drug_id", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index("ix_stock_lots_drug_id", table_name="stock_lots")
    op.drop_table("stock_lots")
```

- [ ] **Step 5: Run tests, then the migration round trip**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_pharmacy_stock_models.py`
Expected: PASS.
Then:
```bash
docker exec ward-db-1 psql -U ward -d postgres -c "DROP DATABASE IF EXISTS ward_mig" -c "CREATE DATABASE ward_mig"
cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward_mig ward-test sh -c "alembic upgrade head && alembic downgrade 0006 && alembic upgrade head" && cd ..
docker exec ward-db-1 psql -U ward -d postgres -c "DROP DATABASE ward_mig"
```
Expected: no error.

- [ ] **Step 6: Lint and commit**

Run LINT. Then:
```bash
git add backend/alembic/versions/0008_pharmacy_stock.py backend/app/models/pharmacy.py backend/app/models/__init__.py backend/tests/test_pharmacy_stock_models.py
git commit -m "feat(backend): stock and dispensing tables (migration 0008)"
```

---

### Task 10: Stock (receipts, adjustments, view, reorder, FEFO, alerts)

**Files:**
- Modify: `backend/app/errors.py` (`ApiError(..., extra=)`)
- Create: `backend/app/services/pharmacy/stock.py`
- Create: `backend/app/routers/pharmacy_stock.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas.py` (`ReceiptIn`, `AdjustmentIn`)
- Modify: `backend/app/services/pharmacy/review.py` (`summary` adds the stock counts)
- Modify: `backend/tests/helpers.py` (`make_drug`, `make_lot`)
- Test: `backend/tests/test_pharmacy_stock.py`

**Interfaces:**
- Consumes: the models from Task 9, `today_local()`, `audit`, `new_id`.
- Produces:
  - `ApiError(status_code, code, detail="", extra: dict | None = None)`: the error body becomes `{**extra, "detail", "code"}`;
  - in `app.services.pharmacy.stock` (imported as `S`): `EXPIRING_DAYS = 30`; `fefo_key(lot) -> tuple`; `pick_lot(lots, need: int, on: date, left: dict[str, int] | None = None) -> StockLot | None`; `on_hand(lots, on: date) -> int`; `lot_out(lot, today) -> dict`; `lock_lots(db, drug_ids: set[str]) -> list[StockLot]`; `move(db, user, lot, delta, reason, *, ref_id=None, comment=None, patient_id=None, ip="") -> StockMovement`; `receive(db, user, drug_id, lot_number, expiry_date, quantity, ip="") -> StockLot`; `adjust(db, user, lot_id, delta, reason, comment, ip="") -> StockLot`; `stock_view(db, today) -> list[dict]`; `reorder(db, today) -> list[dict]`; `alert_counts(db, today) -> dict`;
  - test helpers `make_drug(db, **kw) -> Drug` and `make_lot(db, drug, number, days, qty) -> StockLot`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/helpers.py`:
```python
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
```

`backend/tests/test_pharmacy_stock.py`:
```python
"""Stock (api 1.12 → Dispensing and stock): receipts, adjustments, the stock view, reorder, FEFO, alerts."""

from datetime import timedelta

from sqlalchemy import select

from app.models import AuditLog, StockLot, StockMovement
from app.services.pharmacy.stock import pick_lot
from app.services.schedule import today_local
from tests.helpers import login, make_drug, make_lot, pharmacist


def _day(n: int) -> str:
    return (today_local() + timedelta(days=n)).isoformat()


def test_receipt_creates_then_tops_up_a_lot(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    body = {"drug_id": drug.id, "lot_number": " T-1 ", "expiry_date": _day(200), "quantity": 40}
    r = client.post("/pharmacy/stock/receipts", headers=ph, json=body)
    assert r.status_code == 201, r.text
    lot = r.json()
    assert (lot["lot_number"], lot["quantity"], lot["expired"], lot["expiring"]) == ("T-1", 40, False, False)
    again = client.post("/pharmacy/stock/receipts", headers=ph, json={**body, "quantity": 10}).json()
    assert (again["id"], again["quantity"]) == (lot["id"], 50)
    moves = db.scalars(select(StockMovement).where(StockMovement.lot_id == lot["id"])).all()
    assert sorted((m.reason, m.delta) for m in moves) == [("receipt", 10), ("receipt", 40)]
    assert db.query(AuditLog).filter(AuditLog.resource == "stock_movement",
                                     AuditLog.resource_id.in_([m.id for m in moves])).count() == 2


def test_receipt_errors(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    base = {"drug_id": drug.id, "lot_number": "T-2", "expiry_date": _day(100), "quantity": 5}
    assert client.post("/pharmacy/stock/receipts", headers=ph, json=base).status_code == 201
    r = client.post("/pharmacy/stock/receipts", headers=ph, json={**base, "expiry_date": _day(101)})
    assert r.status_code == 409 and r.json()["code"] == "conflict"
    assert client.post("/pharmacy/stock/receipts", headers=ph,
                       json={**base, "lot_number": "T-3", "expiry_date": _day(-1)}).status_code == 422
    assert client.post("/pharmacy/stock/receipts", headers=ph, json={**base, "quantity": 0}).status_code == 422
    assert client.post("/pharmacy/stock/receipts", headers=ph, json={**base, "drug_id": "d-9999"}).status_code == 404


def test_adjustment_never_goes_negative(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    lot = make_lot(db, drug, "A", 100, 50)
    r = client.post("/pharmacy/stock/adjustments", headers=ph,
                    json={"lot_id": lot.id, "delta": -20, "reason": "adjustment", "comment": "inventory count"})
    assert r.status_code == 200 and r.json()["quantity"] == 30
    before = db.query(StockMovement).count()
    r = client.post("/pharmacy/stock/adjustments", headers=ph,
                    json={"lot_id": lot.id, "delta": -31, "reason": "adjustment", "comment": "x"})
    assert r.status_code == 409 and r.json()["code"] == "insufficient_stock" and r.json()["drug_id"] == drug.id
    assert db.get(StockLot, lot.id).quantity == 30 and db.query(StockMovement).count() == before
    for bad in ({"delta": 5, "reason": "expired", "comment": "x"}, {"delta": 0, "reason": "adjustment", "comment": "x"},
                {"delta": -1, "reason": "adjustment"}, {"delta": -1, "reason": "lost", "comment": "x"}):
        assert client.post("/pharmacy/stock/adjustments", headers=ph,
                           json={"lot_id": lot.id, **bad}).status_code == 422, bad
    assert client.post("/pharmacy/stock/adjustments", headers=ph,
                       json={"lot_id": "lot-9999", "delta": -1, "reason": "return", "comment": "x"}).status_code == 404


def test_stock_view_flags_and_reorder(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db, min_stock=10)
    make_lot(db, drug, "OK", 100, 5)
    make_lot(db, drug, "SOON", 10, 3)
    make_lot(db, drug, "DEAD", -1, 7)
    make_lot(db, drug, "EMPTY", 200, 0)
    row = next(r for r in client.get("/pharmacy/stock", headers=ph).json() if r["drug_id"] == drug.id)
    assert (row["on_hand"], row["min_stock"], row["low"], row["expiring"], row["expired"]) == (8, 10, True, True, True)
    assert sorted(lot["lot_number"] for lot in row["lots"]) == ["DEAD", "OK", "SOON"]
    re = next(r for r in client.get("/pharmacy/stock/reorder", headers=ph).json() if r["drug_id"] == drug.id)
    assert (re["on_hand"], re["suggested_quantity"]) == (8, 12)
    full = make_drug(db, dci="Fullamycin", min_stock=1)
    make_lot(db, full, "F", 100, 5)
    assert full.id not in {r["drug_id"] for r in client.get("/pharmacy/stock/reorder", headers=ph).json()}


def test_summary_has_stock_alerts(client, db):
    ph = pharmacist(client, db)
    before = client.get("/pharmacy/summary", headers=ph).json()
    drug = make_drug(db, min_stock=10)
    make_lot(db, drug, "SOON", 5, 2)
    after = client.get("/pharmacy/summary", headers=ph).json()
    assert (after["low_stock"] - before["low_stock"], after["expiring"] - before["expiring"]) == (1, 1)


def test_stock_roles(client, db):
    for email in ("doctor@medora.tn", "nurse@medora.tn", "patient@medora.tn"):
        assert client.get("/pharmacy/stock", headers=login(client, email)).status_code == 403
    admin = login(client, "admin@medora.tn")
    assert client.get("/pharmacy/stock", headers=admin).status_code == 200
    assert client.get("/pharmacy/stock/reorder", headers=admin).status_code == 200
    body = {"drug_id": "d-0001", "lot_number": "X", "expiry_date": _day(10), "quantity": 1}
    assert client.post("/pharmacy/stock/receipts", headers=admin, json=body).status_code == 403
    assert client.post("/pharmacy/stock/adjustments", headers=admin,
                       json={"lot_id": "lot-x", "delta": 1, "reason": "return", "comment": "x"}).status_code == 403


def test_fefo_pick(db, seeded):
    drug = make_drug(db)
    late = make_lot(db, drug, "LATE", 300, 10)
    early = make_lot(db, drug, "EARLY", 30, 10)
    small = make_lot(db, drug, "SMALL", 20, 1)
    dead = make_lot(db, drug, "DEAD", -1, 10)
    lots = [late, early, small, dead]
    on = today_local()
    assert pick_lot(lots, 1, on) is small  # earliest expiry that holds the line
    assert pick_lot(lots, 2, on) is early  # SMALL cannot hold 2; DEAD is expired
    assert pick_lot(lots, 2, on, {late.id: 10, early.id: 1, small.id: 1, dead.id: 10}) is late  # what's left counts
    assert pick_lot(lots, 11, on) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_pharmacy_stock.py`
Expected: it fails during collection with `ModuleNotFoundError: No module named 'app.services.pharmacy.stock'`.

- [ ] **Step 3: Error extra fields**

In `backend/app/errors.py`:
```python
class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, detail: str = "", extra: dict | None = None):
        super().__init__(status_code=status_code, detail=detail or code.replace("_", " "))
        self.code = code
        self.extra = extra or {}  # added to the body, e.g. {"drug_id": ...} on insufficient_stock (api 1.12)
```
And in `_http`: `return JSONResponse({**getattr(exc, "extra", {}), "detail": exc.detail, "code": code}, …)`.

- [ ] **Step 4: Schemas**

Append to `backend/app/schemas.py`. Add `field_validator` to the pydantic import if it is missing.
```python
class ReceiptIn(BaseModel):
    drug_id: str = Field(max_length=20)
    lot_number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    expiry_date: date
    quantity: int = Field(ge=1, le=100000)


class AdjustmentIn(BaseModel):
    lot_id: str = Field(max_length=20)
    delta: int = Field(ge=-100000, le=100000)
    reason: Literal["adjustment", "expired", "return"]
    comment: Comment

    @field_validator("delta")
    @classmethod
    def _nonzero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("delta must not be 0")
        return v
```

- [ ] **Step 5: The stock service**

`backend/app/services/pharmacy/stock.py`:
```python
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
```

- [ ] **Step 6: Router and summary**

`backend/app/routers/pharmacy_stock.py`:
```python
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
```
Include it in `main.py` (`pharmacy_stock`).

In `backend/app/services/pharmacy/review.py::summary`, return `{…the four counts…, **S.alert_counts(db, schedule.today_local())}`, with `from app.services.pharmacy import stock as S`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider`
Expected: the whole suite passes.

- [ ] **Step 8: Lint and commit**

Run LINT. Then:
```bash
git add backend/app/errors.py backend/app/services/pharmacy/stock.py backend/app/routers/pharmacy_stock.py backend/app/main.py backend/app/schemas.py backend/app/services/pharmacy/review.py backend/tests/helpers.py backend/tests/test_pharmacy_stock.py
git commit -m "feat(backend): pharmacy stock (receipts, adjustments, FEFO, reorder, alerts)"
```

---

### Task 11: Dispensing, nurse receipt and the dose `pharmacy` field

**Files:**
- Create: `backend/app/services/pharmacy/dispensing.py`
- Create: `backend/app/routers/dispensations.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas.py` (`DispenseLineIn`, `DispenseIn`; `DoseOut.pharmacy`)
- Modify: `backend/app/routers/doses.py` (`list_doses`, `given`: the `pharmacy` field)
- Modify: `backend/app/services/schedule.py` (`rebuild_doses` keeps matching future doses)
- Test: `backend/tests/test_dispensing.py`

**Interfaces:**
- Consumes: `S.pick_lot`, `S.lock_lots`, `S.move`, `S.on_hand` (Task 10); `R.bed_of`, `R.user_name` (Task 5); `staff_ward` (auth deps); `local_to_utc`, `today_local`.
- Produces (`app.services.pharmacy.dispensing`, imported as `D`):
  - `item_for_dose(rx, dose) -> dict | None`, `quantity_of(item) -> int`;
  - `pharmacy_status(db, dose_ids: list[str]) -> dict[str, str]`;
  - `round_view(db, day, round_time, ward) -> list[dict]`;
  - `dispense(db, user, ward, day, round_time, lines: list[tuple[str, str | None]], ip="") -> Dispensation`;
  - `dispensation_out(db, d) -> dict`;
  - `list_for(db, user, ward, day) -> list[Dispensation]`;
  - `receive_delivery(db, nurse, disp_id) -> Dispensation`;
  - `DoseOut.pharmacy: str = "none"`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_dispensing.py`:
```python
"""Dispensing (api 1.12 → Dispensing and stock): round view, FEFO transaction, idempotence, nurse receipt."""

from sqlalchemy import select

from app.models import Dispensation, DispensationLine, MedDose, Prescription, StockLot, StockMovement
from app.services import schedule
from tests.helpers import login, make_drug, make_lot, pharmacist

DOC = "doctor@medora.tn"


def _urgent(client, patient_id, drug=None, units=1, times=("22:00",)):
    item = {"med": f"{drug.dci} {drug.strength}" if drug else "Herbal tea", "drug_id": drug.id if drug else None,
            "units_per_intake": units, "times": list(times), "days": 2}
    r = client.post("/prescriptions", headers=login(client, DOC),
                    json={"patient_id": patient_id, "care_plan": "", "items": [item], "urgent": True})
    assert r.status_code == 201, r.text
    return r.json()


def _first(db, rx_id) -> MedDose:
    return min(db.scalars(select(MedDose).where(MedDose.prescription_id == rx_id)), key=lambda d: d.scheduled_at)


def _round(db, rx_id) -> tuple[str, str, str]:
    d = _first(db, rx_id)
    return d.scheduled_at.astimezone(schedule.TUNIS).date().isoformat(), d.time_of_day, d.id


def _dispense(client, h, day, hhmm, lines, ward="Cardiology"):
    return client.post("/pharmacy/dispensations", headers=h,
                       json={"ward": ward, "date": day, "round_time": hhmm, "lines": lines})


def test_round_view_lists_due_doses_with_a_fefo_suggestion(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    make_lot(db, drug, "OLD", 40, 10)
    make_lot(db, drug, "NEW", 200, 10)
    make_lot(db, drug, "DEAD", -1, 10)
    rx = _urgent(client, "p-0001", drug, units=2)
    day, hhmm, dose_id = _round(db, rx["id"])
    rows = client.get("/pharmacy/dispensing", headers=ph, params={"date": day, "round": hhmm, "ward": "Cardiology"})
    assert rows.status_code == 200, rows.text
    w = rows.json()
    assert [x["ward"] for x in w] == ["Cardiology"]
    p = w[0]["patients"][0]
    assert (p["id"], p["name"], p["bed"]) == ("p-0001", "Amira Ben Salah", "C-12")
    d = next(x for x in p["doses"] if x["dose_id"] == dose_id)
    assert (d["drug_id"], d["quantity"], d["suggested_lot"]["lot_number"], d["on_hand"], d["dispensed"]) == (
        drug.id, 2, "OLD", 20, False)
    assert set(d) == {"dose_id", "prescription_id", "med", "drug_id", "quantity", "suggested_lot", "on_hand",
                      "dispensed"}


def test_dispense_decrements_the_fefo_lot(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    old = make_lot(db, drug, "OLD", 40, 10)
    make_lot(db, drug, "NEW", 200, 10)
    rx = _urgent(client, "p-0001", drug, units=2)
    day, hhmm, dose_id = _round(db, rx["id"])
    r = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}])
    assert r.status_code == 201, r.text
    disp = r.json()
    assert (disp["status"], disp["prepared_by_name"], disp["round_time"]) == ("sent", "Pharm Test", hhmm)
    assert (disp["lines"][0]["lot_number"], disp["lines"][0]["quantity"], disp["lines"][0]["bed"]) == ("OLD", 2, "C-12")
    assert db.get(StockLot, old.id).quantity == 8
    sm = db.scalars(select(StockMovement).where(StockMovement.lot_id == old.id)).one()
    assert (sm.reason, sm.delta, sm.ref_id) == ("dispense", -2, disp["id"])
    view = client.get("/pharmacy/dispensing", headers=ph, params={"date": day, "round": hhmm}).json()
    assert next(x for w in view for p in w["patients"] for x in p["doses"] if x["dose_id"] == dose_id)["dispensed"]


def test_an_explicit_lot_is_used(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    make_lot(db, drug, "OLD", 40, 10)
    new = make_lot(db, drug, "NEW", 200, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    assert _dispense(client, ph, day, hhmm, [{"dose_id": dose_id, "lot_id": new.id}]).status_code == 201
    assert db.get(StockLot, new.id).quantity == 9


def test_insufficient_stock_writes_nothing(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    lot = make_lot(db, drug, "OLD", 40, 1)
    rx = _urgent(client, "p-0001", drug, units=2)
    day, hhmm, dose_id = _round(db, rx["id"])
    before = db.query(Dispensation).count()
    r = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}])
    assert r.status_code == 409 and r.json()["code"] == "insufficient_stock" and r.json()["drug_id"] == drug.id
    assert db.get(StockLot, lot.id).quantity == 1 and db.query(Dispensation).count() == before
    assert db.query(StockMovement).filter_by(drug_id=drug.id).count() == 0


def test_already_dispensed(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    lot = make_lot(db, drug, "OLD", 40, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    assert _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}]).status_code == 201
    r = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}])
    assert r.status_code == 409 and r.json()["code"] == "already_dispensed"
    assert db.get(StockLot, lot.id).quantity == 9


def test_lines_share_a_lot_without_going_negative(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    old = make_lot(db, drug, "OLD", 40, 3)
    new = make_lot(db, drug, "NEW", 200, 10)
    a = _urgent(client, "p-0001", drug, units=2)
    b = _urgent(client, "p-0002", drug, units=2)
    day, hhmm, da = _round(db, a["id"])
    _, _, dbb = _round(db, b["id"])
    r = _dispense(client, ph, day, hhmm, [{"dose_id": da}, {"dose_id": dbb}])
    assert r.status_code == 201, r.text
    assert [ln["lot_number"] for ln in r.json()["lines"]] == ["OLD", "NEW"]
    assert (db.get(StockLot, old.id).quantity, db.get(StockLot, new.id).quantity) == (1, 8)


def test_lines_outside_the_round_are_422(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    make_lot(db, drug, "OLD", 40, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    assert _dispense(client, ph, day, "06:00", [{"dose_id": dose_id}]).status_code == 422
    assert _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}], ward="Internal Medicine").status_code == 422
    assert _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}, {"dose_id": dose_id}]).status_code == 422
    assert _dispense(client, ph, day, hhmm, [{"dose_id": "d-999999"}]).status_code == 404


def test_non_formulary_dose_is_sent_without_stock(client, db):
    ph = pharmacist(client, db)
    rx = _urgent(client, "p-0001")
    day, hhmm, dose_id = _round(db, rx["id"])
    r = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}])
    assert r.status_code == 201 and (r.json()["lines"][0]["drug_id"], r.json()["lines"][0]["lot_id"]) == (None, None)


def test_nurse_lists_and_receives_her_ward_delivery(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    make_lot(db, drug, "OLD", 40, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    disp = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}]).json()
    nurse, other = login(client, "nurse@medora.tn"), login(client, "nurse2@medora.tn")
    assert disp["id"] in {d["id"] for d in client.get("/dispensations", headers=nurse, params={"date": day}).json()}
    assert client.get("/dispensations", headers=other, params={"date": day, "ward": "Cardiology"}).status_code == 403
    assert client.post(f"/dispensations/{disp['id']}/receive", headers=other).status_code == 403
    r = client.post(f"/dispensations/{disp['id']}/receive", headers=nurse)
    assert r.status_code == 200 and (r.json()["status"], r.json()["received_by"]) == ("received", "u-0002")
    assert client.post(f"/dispensations/{disp['id']}/receive", headers=nurse).json()["status"] == "received"
    assert disp["id"] in {d["id"] for d in client.get("/dispensations", headers=ph, params={"date": day}).json()}


def test_dose_pharmacy_field(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    make_lot(db, drug, "OLD", 40, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    nurse = login(client, "nurse@medora.tn")

    def status():
        rows = client.get("/patients/p-0001/doses", headers=nurse, params={"date": day}).json()
        return {r["id"]: r["pharmacy"] for r in rows}

    assert status()[dose_id] == "none"
    disp = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}]).json()
    assert status()[dose_id] == "sent"
    client.post(f"/dispensations/{disp['id']}/receive", headers=nurse)
    assert status()[dose_id] == "received" and set(status().values()) <= {"none", "sent", "received"}


def test_rebuild_after_dispensing_keeps_or_detaches_the_line(client, db):
    ph = pharmacist(client, db)
    drug = make_drug(db)
    make_lot(db, drug, "OLD", 40, 10)
    rx = _urgent(client, "p-0001", drug)
    day, hhmm, dose_id = _round(db, rx["id"])
    disp = _dispense(client, ph, day, hhmm, [{"dose_id": dose_id}]).json()
    assert client.post(f"/pharmacy/prescriptions/{rx['id']}/validate", headers=ph, json={}).status_code == 200
    assert db.get(MedDose, dose_id) is not None  # validating an urgent prescription rebuilds it: same ids
    assert client.patch(f"/prescriptions/{rx['id']}", headers=login(client, DOC),
                        json={"active": False}).status_code == 200
    db.expire_all()
    line = db.scalars(select(DispensationLine).where(DispensationLine.dispensation_id == disp["id"])).one()
    assert line.dose_id is None and db.get(MedDose, dose_id) is None


def test_rebuild_keeps_ids_of_matching_future_doses(db, seeded):
    rx = Prescription(id="rx-9600", patient_id="p-0002", doctor_id="u-0001", care_plan="", active=True,
                      items=[{"med": "Z", "times": ["23:59"], "slot": None, "days": 2}])
    db.add(rx)
    db.flush()
    first = {d.id for d in schedule.rebuild_doses(db, rx)}
    assert {d.id for d in schedule.rebuild_doses(db, rx)} == first


def test_dispensing_roles(client, db):
    assert client.get("/pharmacy/dispensing", headers=login(client, DOC), params={"round": "20:00"}).status_code == 403
    assert client.post("/pharmacy/dispensations", headers=login(client, "nurse@medora.tn"),
                       json={"ward": "Cardiology", "date": "2026-10-10", "round_time": "20:00",
                             "lines": [{"dose_id": "d-000001"}]}).status_code == 403
    assert client.get("/dispensations", headers=login(client, "patient@medora.tn")).status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_dispensing.py`
Expected: FAIL. The routes return 404, and the rebuild test fails because the dose ids change.

- [ ] **Step 3: `rebuild_doses` keeps matching future doses**

Without this, every rebuild deletes and recreates the future doses, and a dispensed dose would lose its line. Replace `rebuild_doses` in `backend/app/services/schedule.py`:
```python
def rebuild_doses(db: Session, prescription: Prescription) -> list[MedDose]:
    """Make the prescription's doses match its items. When active: `days × times` rows from course_start(rx) on (a
    time already past on day 0 moves to the end of the course). Future `scheduled` rows that are no longer wanted
    (all of them once inactive) are deleted; rows that still match keep their ids, so a dose the pharmacy already
    sent survives a rebuild. Idempotent."""
    rx = prescription
    future = list(db.scalars(select(MedDose).where(MedDose.prescription_id == rx.id, MedDose.status == "scheduled",
                                                   MedDose.scheduled_at > now_utc())))
    if not rx.active:
        _drop(db, future)
        return []
    existing = {(d.scheduled_at, d.slot, tuple(d.meds)): d
                for d in db.scalars(select(MedDose).where(MedDose.prescription_id == rx.id))}
    written = course_start(rx)
    start = written.astimezone(TUNIS).date()
    out: list[MedDose] = []
    for item in rx.items:
        days = int(item.get("days", 1))
        candidates = sorted(at for i in range(days + 1) for hhmm in item["times"]
                            if (at := local_to_utc(start + timedelta(days=i), hhmm)) >= written)
        for at in candidates[:days * len(item["times"])]:
            hhmm = at.astimezone(TUNIS).strftime("%H:%M")
            key = (at, item.get("slot"), (item["med"],))
            dose = existing.get(key)
            if dose is None:
                dose = MedDose(id=new_id(db, "d", 6), prescription_id=rx.id, patient_id=rx.patient_id,
                               scheduled_at=at, time_of_day=hhmm, meds=[item["med"]], slot=item.get("slot"),
                               status="scheduled")
                db.add(dose)
                existing[key] = dose
            out.append(dose)
    keep = {d.id for d in out}
    _drop(db, [d for d in future if d.id not in keep])
    return out


def _drop(db: Session, doses: list[MedDose]) -> None:
    """Delete these doses (a dispensation line pointing at one keeps its record: dose_id → NULL)."""
    if doses:
        db.execute(delete(MedDose).where(MedDose.id.in_([d.id for d in doses])))
    db.flush()
```

- [ ] **Step 4: Schemas**

In `backend/app/schemas.py`, add the field `pharmacy: str = "none"` to `DoseOut` (`none | sent | received`, api 1.12 Phase B), and append:
```python
class DispenseLineIn(BaseModel):
    dose_id: str = Field(max_length=20)
    lot_id: str | None = Field(default=None, max_length=20)  # null = FEFO


class DispenseIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    ward: str = Field(min_length=1, max_length=60)
    day: date = Field(alias="date")
    round_time: str = Field(pattern=HHMM)
    lines: list[DispenseLineIn] = Field(min_length=1, max_length=200)
```

- [ ] **Step 5: The dispensing service**

`backend/app/services/pharmacy/dispensing.py`:
```python
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
```

- [ ] **Step 6: Routers and the dose field**

`backend/app/routers/dispensations.py`:
```python
"""Dispensing to wards (api.md 1.12 → Dispensing and stock). Pharmacist prepares; the ward nurse receives."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.db import get_db
from app.models import User
from app.schemas import HHMM, DispenseIn
from app.services.audit import audit
from app.services.pharmacy import dispensing as D
from app.services.schedule import today_local

router = APIRouter(tags=["dispensing"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("/pharmacy/dispensing")
def round_view(request: Request, round_time: str = Query(alias="round", pattern=HHMM),
               day: date | None = Query(None, alias="date"), ward: str | None = Query(None, max_length=60),
               user: User = Depends(require_roles("pharmacist")), db: Session = Depends(get_db)) -> list[dict]:
    day = day or today_local()
    rows = D.round_view(db, day, round_time, ward)
    for w in rows:
        for p in w["patients"]:
            audit(db, user, "read", "dose", f"{day.isoformat()} {round_time}", patient_id=p["id"], ip=_ip(request))
    db.commit()
    return rows


@router.post("/pharmacy/dispensations", status_code=201)
def dispense(body: DispenseIn, request: Request, user: User = Depends(require_roles("pharmacist")),
             db: Session = Depends(get_db)) -> dict:
    disp = D.dispense(db, user, body.ward, body.day, body.round_time,
                      [(ln.dose_id, ln.lot_id) for ln in body.lines], ip=_ip(request))
    out = D.dispensation_out(db, disp)
    db.commit()
    return out


@router.get("/dispensations")
def list_dispensations(request: Request, ward: str | None = Query(None, max_length=60),
                       day: date | None = Query(None, alias="date"),
                       user: User = Depends(require_roles("nurse", "pharmacist")),
                       db: Session = Depends(get_db)) -> list[dict]:
    out = [D.dispensation_out(db, d) for d in D.list_for(db, user, ward, day or today_local())]
    for d in out:
        for pid in sorted({ln["patient_id"] for ln in d["lines"]}):
            audit(db, user, "read", "dispensation", d["id"], patient_id=pid, ip=_ip(request))
    db.commit()
    return out


@router.post("/dispensations/{disp_id}/receive")
def receive(disp_id: str, request: Request, user: User = Depends(require_roles("nurse")),
            db: Session = Depends(get_db)) -> dict:
    disp = D.receive_delivery(db, user, disp_id)
    audit(db, user, "update", "dispensation", disp.id, ip=_ip(request))
    out = D.dispensation_out(db, disp)
    db.commit()
    return out
```
Include it in `main.py` (`dispensations`).

In `backend/app/routers/doses.py`:
- add `from app.services.pharmacy.dispensing import pharmacy_status`;
- in `list_doses`, replace `return rows` (after the `db.commit()`) with:
```python
    st = pharmacy_status(db, [d.id for d in rows])
    return [DoseOut.model_validate(d).model_copy(update={"pharmacy": st.get(d.id, "none")}) for d in rows]
```
  Compute `st` before `db.commit()`.
- in `given`, replace `out = DoseOut.model_validate(d).model_dump(mode="json")` with:
```python
    st = pharmacy_status(db, [d.id]).get(d.id, "none")
    out = DoseOut.model_validate(d).model_copy(update={"pharmacy": st}).model_dump(mode="json")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider`
Expected: the whole suite passes, `test_schedule.py` included (the rebuild stays idempotent and the deactivation still drops future doses).

- [ ] **Step 8: Lint and commit**

Run LINT. Then:
```bash
git add backend/app/services/pharmacy/dispensing.py backend/app/routers/dispensations.py backend/app/main.py backend/app/schemas.py backend/app/routers/doses.py backend/app/services/schedule.py backend/tests/test_dispensing.py
git commit -m "feat(backend): ward dispensing with FEFO, nurse receipt and the dose pharmacy status"
```

---

### Task 12: Phase B seed, demo smoke and contract update

**Files:**
- Modify: `backend/app/seed.py` (`_stock`)
- Modify: `backend/scripts/pharmacy_smoke.py` (`run_phase_b`, `--phase`)
- Modify: `backend/tests/test_pharmacy_demo_path.py`
- Modify: `docs/contracts/api.md`, `docs/contracts/data-model.md` (drop "planned")
- Test: `backend/tests/test_pharmacy_stock_seed.py`

**Interfaces:**
- Consumes: `StockLot`, `StockMovement`, `S.stock_view`, `S.reorder`, `PHARMACIST_ID`.
- Produces:
  - `seed._stock(db) -> None` (idempotent): a lot for every formulary drug, paracetamol 500 at exactly `min_stock`, enoxaparin under `min_stock`, an amlodipine lot expiring in 10 days, and an expired ibuprofen lot;
  - `pharmacy_smoke.run_phase_b(c, password, ward="Cardiology", round_time="20:00") -> dict`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_pharmacy_stock_seed.py`:
```python
"""Phase B seed (spec §7): a lot per drug, one under min_stock, one expiring in 10 days, one expired."""

from app.models import StockLot, StockMovement
from app.seed import seed
from app.services.pharmacy import stock as S
from app.services.schedule import today_local


def test_seed_stock(db):
    seed(db)
    view = {r["drug_id"]: r for r in S.stock_view(db, today_local())}
    assert len(view) == 51 and all(r["lots"] for r in view.values())
    assert (view["d-0001"]["on_hand"], view["d-0001"]["min_stock"], view["d-0001"]["low"]) == (200, 200, False)
    assert view["d-0014"]["low"] is True
    assert view["d-0032"]["expiring"] is True and view["d-0018"]["expired"] is True
    assert [r["drug_id"] for r in S.reorder(db, today_local())] == ["d-0014"]
    assert db.query(StockMovement).filter_by(reason="receipt").count() == db.query(StockLot).count() == 53


def test_seed_stock_is_idempotent(db):
    seed(db)
    seed(db)
    assert db.query(StockLot).count() == 53
```

Replace `backend/tests/test_pharmacy_demo_path.py`:
```python
"""The spec §7 demo path through the API in-process (the same code as scripts/pharmacy_smoke.py)."""

from scripts import pharmacy_smoke


def test_demo_path(client):
    a = pharmacy_smoke.run_phase_a(client, "ward1234")
    assert a["v1"]["status"] == "pending_pharmacy" and a["v2"]["status"] == "validated"
    b = pharmacy_smoke.run_phase_b(client, "ward1234")
    assert b["dispensation"]["status"] == "sent"
    assert b["summary_after"]["low_stock"] == b["summary_before"]["low_stock"] + 1  # paracetamol 200 → 199
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider tests/test_pharmacy_stock_seed.py tests/test_pharmacy_demo_path.py`
Expected: FAIL. There are no lots, and `run_phase_b` does not exist.

- [ ] **Step 3: Seed stock**

In `backend/app/seed.py`, add `Drug, StockLot, StockMovement` to the models import, then add:
```python
# drug id → seed quantity (others: max(2 × min_stock, 50)). Paracetamol 500 sits exactly at min_stock, so the 20:00
# Cardiology round tips it under (the demo's low-stock alert); enoxaparin starts under min_stock.
SEED_QTY = {"d-0001": 200, "d-0014": 6}


def _seed_lot(db: Session, drug_id: str, number: str, expiry: date, qty: int) -> None:
    lot = StockLot(id=new_id(db, "lot"), drug_id=drug_id, lot_number=number, expiry_date=expiry, quantity=qty)
    db.add(lot)
    db.flush()
    db.add(StockMovement(id=new_id(db, "sm"), drug_id=drug_id, lot_id=lot.id, delta=qty, reason="receipt",
                         by_user_id=PHARMACIST_ID))


def _stock(db: Session) -> None:
    """Phase B demo stock (spec §7). Skipped once any lot exists, or without the seed pharmacist."""
    if db.scalar(select(StockLot.id).limit(1)) is not None or db.get(User, PHARMACIST_ID) is None:
        return
    today = today_local()
    for d in db.scalars(select(Drug).order_by(Drug.id)):
        _seed_lot(db, d.id, f"L{d.id[2:]}-A", today + timedelta(days=365), SEED_QTY.get(d.id, max(2 * d.min_stock, 50)))
    _seed_lot(db, "d-0032", "L0032-B", today + timedelta(days=10), 30)  # amlodipine, expiring: FEFO takes it first
    _seed_lot(db, "d-0018", "L0018-X", today - timedelta(days=5), 20)  # ibuprofen, expired: waiting for write-off
    db.flush()
```
Call `_stock(db)` right after each `_pharmacy(...)` call, in both paths.

- [ ] **Step 4: Smoke phase B**

Add to `backend/scripts/pharmacy_smoke.py`:
```python
def run_phase_b(c, password: str, ward: str = "Cardiology", round_time: str = "20:00") -> dict:
    """Step 6: the pharmacist prepares the round, the nurse confirms receipt, the stock goes down, and a
    low-stock alert shows on the pharmacy dashboard."""
    ph, nurse = _login(c, "pharmacist@medora.tn", password), _login(c, "nurse@medora.tn", password)
    day = tunis_day()
    before = _ok(c.get("/pharmacy/summary", headers=ph))
    view = _ok(c.get("/pharmacy/dispensing", headers=ph, params={"date": day, "round": round_time, "ward": ward}))
    lines = [{"dose_id": d["dose_id"]} for w in view for p in w["patients"] for d in p["doses"] if not d["dispensed"]]
    if not lines:
        print(f"pharmacy smoke: the {ward} {round_time} round of {day} is already dispensed")
        return {"dispensation": None, "summary_before": before, "summary_after": before}
    disp = _ok(c.post("/pharmacy/dispensations", headers=ph,
                      json={"ward": ward, "date": day, "round_time": round_time, "lines": lines}), 201)
    listed = _ok(c.get("/dispensations", headers=nurse, params={"date": day}))
    _check(any(d["id"] == disp["id"] for d in listed), "the nurse sees the delivery")
    _check(_ok(c.post(f"/dispensations/{disp['id']}/receive", headers=nurse))["status"] == "received", "received")
    after = _ok(c.get("/pharmacy/summary", headers=ph))
    _check(after["low_stock"] >= 1, "a low-stock alert after the round")
    return {"dispensation": disp, "summary_before": before, "summary_after": after}
```
In `main()`, add `ap.add_argument("--phase", choices=["a", "b", "all"], default="all")`. Run `run_phase_a` when the phase is `a` or `all` and `run_phase_b` when it is `b` or `all`, and print `pharmacy smoke: phase A ok` and `pharmacy smoke: phase B ok`. In the test, `disp` is the response of the POST, so its status is `sent`.

- [ ] **Step 5: Contracts: Phase B is built**

- `docs/contracts/api.md`: change the heading `## Dispensing and stock (1.12, Phase B: planned)` to `## Dispensing and stock (1.12, Phase B)`. In the 1.12 changelog line, replace `Phase B (planned):` with `Phase B:`.
- `docs/contracts/data-model.md`: change `### Phase B tables (1.7, migration 0008, planned)` to `### Phase B tables (1.7, migration 0008)`. In the 1.7 changelog line, drop `, planned`. Add these lines to "Seed data": `` - Phase B stock: a lot for every formulary drug (`L0001-A`…), paracetamol 500 mg exactly at `min_stock` (the 20:00 Cardiology round tips it under), enoxaparin under `min_stock`, an amlodipine lot expiring in 10 days, an expired ibuprofen lot ``.

There is no version bump. Nothing from 1.12/1.7 has been released, because the branch is local.

- [ ] **Step 6: Run the full suite, lint and the live smoke**

Run: `cd backend && MSYS_NO_PATHCONV=1 docker run --rm --network ward_default -v "$(pwd -W):/app" -w /app -e TEST_DATABASE_URL=postgresql+psycopg://ward:ward@db:5432/ward -e LLM_PROVIDER=none ward-test pytest -q -p no:cacheprovider`
Expected: everything passes. Run LINT and expect `All checks passed!`.

Optional, and only when the user has rebuilt the stack from this branch (`docker compose -f infra/docker-compose.yml --env-file .env up --build`, then `docker compose -f infra/docker-compose.yml exec api python -m app.seed`):
`cd backend && python scripts/pharmacy_smoke.py --base http://localhost:8000`
Expected: `pharmacy smoke: phase A ok` and `pharmacy smoke: phase B ok`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/seed.py backend/scripts/pharmacy_smoke.py backend/tests/test_pharmacy_demo_path.py backend/tests/test_pharmacy_stock_seed.py docs/contracts/api.md docs/contracts/data-model.md
git commit -m "feat(backend): pharmacy stock seed and the full demo-path smoke"
```

---

## Contract decisions

The spec left these points open. Both the backend and the web plan use these answers.

1. **Drug IDs** are `d-0001` as the spec says. They share the `d` sequence with dose ids (`d-000001`, a different width), and the formulary load advances that sequence.
2. **`dose_mg`** is mg **per intake**. **`units_per_intake`** is an integer from 1 to 10, default 1 (no half tablets). Both live in the item JSON.
3. **`GET /drugs?active=`** takes `true` (default), `false` (inactive only) or `all`. `q` is literal: `%` and `_` are not wildcards.
4. **Catalogue reads are not audited** (they hold no patient data). Catalogue writes are audited (resource `drug`).
5. **Catalogue duplicates:** same DCI (case-insensitive) + strength + form gives 409 `conflict`. Tags are lower snake case; `atc_code` is empty or 7 characters, upper-cased.
6. **Unknown or inactive `drug_id`** on a save or a dry run gives 422 `unknown_drug`. Checks still load inactive drugs for prescriptions that are already running.
7. **`replaces_id` errors:**
   - unknown: 404;
   - another patient's prescription, or one whose status is not `pending_pharmacy`/`changes_requested`/`validated`, or one that already has a live newer version: 409 `conflict`.
8. **Version handling:**
   - A replaced version that never ran becomes `superseded` as soon as the new one is saved.
   - An **urgent** new version supersedes the running old one at once (no double dosing). A rejected urgent v2 does not bring v1 back.
9. **Requesting changes on an urgent prescription** also stops its future doses, because `active` is derived from the status.
10. **Doses of a non-urgent prescription** start at validation time (`reviewed_at`), not at the time it was written.
11. **`PATCH /prescriptions/{id}`** only takes `{"active": false}`; `true` is 422. A stop works from `pending_pharmacy`, `changes_requested` or `validated`; from any other status it is 409 `bad_status`.
12. **POST/PATCH responses** are the full Prescription plus `schedule_version` and `published_to_device`. `published_to_device` is false when no dose changed.
13. **Prescription shapes:**
    - Doctor, nurse and pharmacist see all 16 keys listed in api.md.
    - The patient sees only the 1.0 fields plus `status`.
14. **Decision routes** return the updated Prescription.
15. **Validate body:** `{acknowledged=false, comment?}`.
    - "Has checks" means any check, `info` included, recomputed at decision time.
    - The recomputed checks are stored on the prescription and in the review snapshot.
16. **Comments** (request-changes, reject, adjustments) are trimmed and must be 1–500 characters. Blank is 422.
17. **The worklist** shows the checks stored at the last save or decision; the detail view recomputes them. `status=all` returns every status, newest 200 first, then sorted.
18. **The pharmacist's patient projection** has no weight: no weight column exists.
19. **Detail view, `running` and `history`:**
    - `running` excludes the prescription itself and the versions it replaces.
    - `history` covers the whole replaced chain, newest first.
    - The Review shape is defined in api.md.
20. **`GET /pharmacy/summary`:**
    - Phase A has 4 keys.
    - Phase B adds `low_stock` (a count of drugs) and `expiring` (a count of lots).
21. **The WS `prescription_status` frame** goes out on every status change: save, stop, decision and supersede. Pharmacists receive only this frame type.
22. **n8n `prescription.review`:**
    - `comment` is null when empty.
    - `doctor_email` is null when the doctor's account is not active.
23. **Error bodies may carry extra keys:** 409 `insufficient_stock` adds `drug_id` next to `detail` and `code`.
24. **Phase A nurse badge:** there is no new dose field. The web joins `prescription_id` to `GET /patients/{id}/prescriptions` to show "pending pharmacy review".
25. **Stock levels:**
    - `on_hand` leaves out expired lots.
    - `lots[]` lists only lots with stock.
    - "Expiring" means within 30 days, today included.
26. **FEFO:**
    - One line takes from one lot, the earliest-expiring usable lot that holds the whole line.
    - An explicit `lot_id` that is expired or holds another drug is 422.
    - A dose outside the round or ward, or a dose listed twice, is 422.
    - A prescription that is no longer active is 409 `bad_status`.
27. **`stock_movements` gains a `comment` column.** The spec's adjustment body has a comment, but its table did not.
28. **Expiry rules:** a receipt with a past expiry is 422. A receipt for an existing lot number with a different expiry is 409. `reason: expired` needs a negative delta.
29. **Nurse receipt:**
    - Receipt is idempotent.
    - `GET /dispensations` is limited to the nurse's own ward, and another ward is 403.
    - `date` defaults to today (Africa/Tunis).
30. **Rebuilds after dispensing:**
    - `rebuild_doses` keeps the ids of future doses that still match.
    - A dispensed dose that is later cancelled leaves its line with `dose_id: null`.
31. **The check engine uses two queries,** one for the running prescriptions and one for their drugs, still well under 20 ms. The spec says "one query per call".
