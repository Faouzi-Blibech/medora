# Single-visit exam pathway: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A request gets a rules-suggested exam set. A doctor orders it, the department nurse uploads the results, and the doctor sees them before the single visit. The waitlist also shows the hospital's triage-scale label next to our urgency.

**Architecture:**
- **Pure logic:** rules in `app/ai/rules/exam_bundles.v1.json` drive the DB-free `app/ai/exams.py`. Status and access rules live in `app/services/exams.py`.
- **Routes:** `app/routers/exams.py` loads rows, commits, audits and emits n8n events after commit.
- **Files:** stored in MinIO through `app/services/storage.py`.
- **Web:** reads through the `web/src/lib/api.ts` mock/real layer, as every other screen does.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, pytest, MinIO (`minio` Python client), Next.js 16 + React 19 + CSS Modules.

**Spec:** `docs/superpowers/specs/2026-10-09-single-visit-and-case-notebook-design.md`

**Prerequisite:** PR #22 (appointments and n8n routes) is merged into `main`. Branch: `faouzi/single-visit-exams` from `main`.

## Global Constraints

- AI only suggests. Exam rows start `suggested`; only a doctor makes them `ordered` (`human_confirmed_by` = that doctor).
- `ai_suggested` on exam rows is `{"source": "rules", "bundles": [...], "reason": "..."}`. There is no LLM in this plan.
- Status machine: `suggested → ordered → done`; `suggested|ordered → cancelled`. Anything else returns 409 `bad_status`.
- Uploads accept `application/pdf`, `image/jpeg` or `image/png`, at most 15 MB (`15 * 1024 * 1024` bytes). Otherwise 422 with code `bad_file`.
- MinIO key: `exams/{exam_order_id}/{exam_result_id}/{safe_name}`. Files are served only through `GET /exam-results/{id}/file` (auth + audit).
- Every read of a patient's exams or result file writes `audit_log` via `app.services.audit.audit` or `check_patient_access`.
- The patient never sees `suggested` rows, `ai_suggested`, `human_confirmed_by` or files.
- Error envelope: `{"detail","code"}` through `app.errors.ApiError`. IDs: `ex-0001` (orders), `er-0001` (results) via `app.ids.new_id`.
- **Honesty:**
  - UI copy never says AI reads images or results.
  - Exam rules are labelled "illustrative, to be reviewed by the hospital's doctors".
  - The triage-scale label shows "(to confirm)" while `confirmed` is false.
- **Ownership:**
  - Wali owns `app/models/`, `alembic/`, `app/seed.py`, `app/main.py`, `infra/` and `docs/contracts/data-model.md`. Tasks 2, 3 and 5 touch them; open those as part of this PR and tag Wali.
  - Everything else here is Faouzi's.
- Commits: Conventional Commits, no Co-Authored-By, no "Generated with" line. Never commit `web/AGENTS.md`, `web/CLAUDE.md` or `claude design output/`.
- Backend tests run against the local DB:
  - `export DATABASE_URL=postgresql+psycopg://ward:ward@localhost:5544/ward TEST_DATABASE_URL=$DATABASE_URL`
  - Then `cd backend && python -m pytest`. Use port 5432 if your DB is there.
- Web checks: `cd web && npm run typecheck && npm run build`.

## Review Focus

- **A doctor orders an exam id that belongs to another appointment, or one already ordered.** Expect 422 (wrong appointment) or 409 `bad_status`, and nothing changes. Tested in Task 7 (`test_order_rejects_foreign_or_stale_ids`).
- **A nurse from another department uploads to an exam.** Expect 403, and the order stays `ordered`. Tested in Task 7 (`test_upload_rules`).
- **An upload with a disallowed type or over 15 MB.** Expect 422 `bad_file`, no row and no MinIO object. Tested in Task 7 (`test_upload_rules`).
- **`results_ready` fires before every ordered exam of the appointment is done.** It must fire once, on the last upload only. Tested in Task 7 (`test_results_ready_fires_once_on_last_upload`).
- **A patient lists their exams before the doctor ordered anything.** Expect an empty list, never the suggestions. Tested in Task 7 (`test_patient_sees_only_ordered_rows`).

---

### Task 1: Contract changes (data-model 1.4, api 1.8, n8n 1.3)

**Files:**
- Modify: `docs/contracts/data-model.md` (version line, new tables after `ai_summaries`, role-matrix rows, seed lines, changelog)
- Modify: `docs/contracts/api.md` (version line, new section "Proposed in 1.8", changelog)
- Modify: `docs/contracts/n8n-webhooks.md` (version line, two event rows, W7/W8 rows, changelog)

**Interfaces:**
- Produces: the shapes every later task implements, copied from spec §7.

- [ ] **Step 1: data-model.md.** Change the version line to `> **Version:** 1.4 (2026-10-09) · **Owner:** Wali (schema + migrations); everyone reviews`. After the `### ai_summaries` section, add:

```markdown
### `exam_orders`
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `ex-0001` |
| `patient_id` | text FK | |
| `appointment_id` | text FK, null | the request the exam prepares |
| `code` | text | key in `app/ai/rules/exam_bundles.v1.json` → `catalogue` |
| `label` | text | e.g. "Chest X-ray" |
| `department` | text | performing department; matches `staff.ward` (`Imaging`, `Laboratory`, `Cardiology`) |
| `status` | text | `suggested` \| `ordered` \| `done` \| `cancelled` |
| `ai_suggested` | jsonb, null | `{source:"rules", bundles[], reason}`; null when a doctor added the exam by hand |
| `human_confirmed_by` | text FK → users, null | the doctor who ordered it |
| `ordered_at`, `done_at` | timestamptz, null | |
| `created_at` | timestamptz | |

### `exam_results`
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `er-0001` |
| `exam_order_id` | text FK | |
| `patient_id` | text FK | |
| `uploaded_by` | text FK → users | |
| `file_key` | text | MinIO key `exams/{exam_order_id}/{id}/{file_name}` |
| `file_name`, `content_type` | text | PDF, JPEG or PNG |
| `size_bytes` | int | ≤ 15 MB |
| `report_text` | text | short report typed at upload, default `''` |
| `created_at` | timestamptz | |

### `notebook_entries`
| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `nb-0001` |
| `patient_id` | text FK | |
| `user_id` | text FK → users | who asked |
| `question` | text | |
| `ai_suggested` | jsonb | `{answer, citations[], source}` |
| `human_confirmed_by` | text FK → users, null | |
| `created_at` | timestamptz | |
```

In the role matrix, add two rows before `Devices / admissions`:

```markdown
| Exams | R own + any `requested` appointment; W order/cancel | R ward + own department; W upload (own department) | R status only | R self (ordered/done only) |
| Notebook | RW own | — | — | — |
```

Under "Seed data", add the bullet `- 2 department nurses: \`u-0006\` Imaging (\`imaging@medora.tn\`), \`u-0007\` Laboratory (\`lab@medora.tn\`)`. Add the changelog line at the top of the Changelog:

```markdown
- **1.4** (2026-10-09): adds `exam_orders`, `exam_results`, `notebook_entries`, the Exams and Notebook permission rows and two department nurses in the seed (single-visit pathway and case notebook, see `docs/superpowers/specs/2026-10-09-single-visit-and-case-notebook-design.md`). Needs a 👍 from Wali.
```

- [ ] **Step 2: api.md.** Version line → `1.8 (2026-10-09)`. Insert before `## Changelog`:

````markdown
## Proposed in 1.8 (Faouzi: single-visit exams, case notebook)

| Method & path | Roles | Notes |
|---|---|---|
| `GET /exams/catalogue` | doctor | → `[{"code","label","department"}]` |
| `GET /appointments/{id}/exams` | doctor, admin (no results), patient (self; ordered/done only) | → `[ExamOrder]` |
| `GET /patients/{id}/exams` | doctor (own), nurse (ward), patient (self; ordered/done only) | → `[ExamOrder]`, audited |
| `GET /exams?status=ordered` | nurse (own department), admin | Worklist → `[ExamOrder]` with `patient_name` |
| `POST /appointments/{id}/exams/order` | doctor | `{"exam_ids":[...]}`: listed `suggested` rows → `ordered`, the other suggestions → `cancelled`. 422 if an id is not a suggestion of this appointment. Emits `exam.ordered` |
| `POST /exams` | doctor | `{"patient_id","appointment_id"?,"code"}` → `ExamOrder` with `status:"ordered"`. Emits `exam.ordered` |
| `POST /exams/{id}/cancel` | doctor | → `ExamOrder`; 409 `bad_status` |
| `POST /exams/{id}/results` | nurse (own department) | multipart `file` (PDF/JPEG/PNG, ≤ 15 MB) + `report_text` → `ExamOrder` with `status:"done"`; 422 `bad_file`, 409 `bad_status`. Emits `exam.results_ready` when the appointment has no `ordered` exam left |
| `GET /exam-results/{id}/file` | doctor, nurse (as for reading the exam) | → the file bytes, audited |
| `POST /ai/notebook/{patient_id}` | doctor (own) | `{"question"}` → `NotebookEntry` |
| `GET /ai/notebook/{patient_id}` | doctor (own) | → `[NotebookEntry]` newest first |
| `GET /ai/notebook/{patient_id}/sources` | doctor (own) | → `[{"id","kind","title","ts"}]` |
| `POST /ai/notebook/entries/{id}/review` | doctor | → `NotebookEntry` with `human_confirmed_by` |

`Appointment` gains `exams_total` (ordered + done), `exams_done` and `exams_suggested`. `triage` gains `scale: {"name","level","confirmed"}`.

```jsonc
// ExamOrder
{ "id": "ex-0001", "patient_id": "p-0003", "appointment_id": "a-0001", "code": "ecg", "label": "ECG (12-lead)",
  "department": "Cardiology", "status": "suggested|ordered|done|cancelled", "ai_suggested": {"source": "rules", "bundles": ["chest_pain"], "reason": "..."},
  "human_confirmed_by": "u-0001", "ordered_at": "...", "done_at": null, "created_at": "...", "patient_name": "...",
  "results": [{ "id": "er-0001", "file_name": "ecg.pdf", "content_type": "application/pdf", "size_bytes": 81234, "report_text": "Sinus rhythm", "uploaded_by_name": "Nurse Rania", "created_at": "..." }] }
// NotebookEntry
{ "id": "nb-0001", "patient_id": "p-0001", "question": "...", "answer": "...", "source": "rules|llm",
  "citations": [{ "n": 1, "source_id": "note:n-0003", "kind": "note", "title": "Nurse note · 08 Oct 21:40", "snippet": "..." }],
  "human_confirmed_by": null, "created_at": "..." }
```
````

Changelog line: `- **1.8** (2026-10-09): proposes the exam and notebook routes above and the new \`Appointment\`/\`triage\` fields (spec 2026-10-09). Nothing earlier changes. Needs a 👍 from Wali.`

- [ ] **Step 3: n8n-webhooks.md.** Version → `1.3 (2026-10-09)`. Add to the Events table:

```markdown
| `exam.ordered` | `POST /appointments/{id}/exams/order` or `POST /exams` | `{appointment_id, patient_first_name, patient_telegram_chat_id, patient_email, exams:[{label, department}]}` | W7 tells the patient where to go |
| `exam.results_ready` | the last ordered exam of an appointment gets its result | `{appointment_id, patient_first_name, doctor_id, doctor_name, doctor_email, doctor_chat_id}` | W8 tells the ordering doctor |
```

Add to the Workflows table:

```markdown
| W7 | Exams ordered | core for the single-visit demo | event `exam.ordered` → Telegram + email to the patient: "Before your visit, please do: {label} ({department}) …" |
| W8 | Results ready | core for the single-visit demo | event `exam.results_ready` → Telegram + email to the doctor: "{patient_first_name}'s results are in; the visit can be booked" |
```

Changelog: `- **1.3** (2026-10-09): adds \`exam.ordered\` and \`exam.results_ready\` with W7/W8. Emitter: Faouzi (exams router).`

- [ ] **Step 4: Commit**

```bash
git add docs/contracts/data-model.md docs/contracts/api.md docs/contracts/n8n-webhooks.md
git commit -m "docs(contracts): exams and notebook (data-model 1.4, api 1.8, n8n 1.3)"
```

---

### Task 2: Models and migration 0003 (Wali's folder, tag him)

**Files:**
- Create: `backend/app/models/exams.py`
- Modify: `backend/app/models/ai.py` (add `NotebookEntry`)
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0003_exams_notebook.py`
- Test: `backend/tests/test_exam_models.py`

**Interfaces:**
- Produces: `ExamOrder`, `ExamResult` and `NotebookEntry` SQLAlchemy classes with the columns of Task 1. All are exported from `app.models`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_exam_models.py
from app.models import ExamOrder, ExamResult, NotebookEntry


def test_exam_rows_round_trip(seeded):
    db = seeded
    o = ExamOrder(id="ex-0001", patient_id="p-0001", appointment_id=None, code="ecg", label="ECG (12-lead)",
                  department="Cardiology", status="suggested", ai_suggested={"source": "rules", "bundles": ["x"]})
    db.add(o)
    db.flush()
    r = ExamResult(id="er-0001", exam_order_id="ex-0001", patient_id="p-0001", uploaded_by="u-0002",
                   file_key="exams/ex-0001/er-0001/a.pdf", file_name="a.pdf", content_type="application/pdf",
                   size_bytes=10)
    n = NotebookEntry(id="nb-0001", patient_id="p-0001", user_id="u-0001", question="q",
                      ai_suggested={"answer": "a", "citations": [], "source": "rules"})
    db.add_all([r, n])
    db.flush()
    db.refresh(o)
    assert o.created_at is not None and o.ordered_at is None and o.human_confirmed_by is None
    assert db.get(ExamResult, "er-0001").report_text == ""
    assert db.get(NotebookEntry, "nb-0001").human_confirmed_by is None
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && python -m pytest tests/test_exam_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'ExamOrder'`

- [ ] **Step 3: Write the models**

```python
# backend/app/models/exams.py
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ExamOrder(Base):
    __tablename__ = "exam_orders"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    appointment_id: Mapped[str | None] = mapped_column(ForeignKey("appointments.id"), index=True)
    code: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    department: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="suggested")
    ai_suggested: Mapped[dict | None] = mapped_column(JSONB)
    human_confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExamResult(Base):
    __tablename__ = "exam_results"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    exam_order_id: Mapped[str] = mapped_column(ForeignKey("exam_orders.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    file_key: Mapped[str] = mapped_column(String)
    file_name: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    report_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Append to `backend/app/models/ai.py` (add `Text` to the existing `sqlalchemy` import):

```python
class NotebookEntry(Base):
    __tablename__ = "notebook_entries"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    question: Mapped[str] = mapped_column(Text)
    ai_suggested: Mapped[dict] = mapped_column(JSONB)  # {answer, citations, source}
    human_confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

In `backend/app/models/__init__.py`:
- Change the docstring to `(v1.4: exams, notebook)`.
- Add `from app.models.ai import AiSummary, NotebookEntry` and `from app.models.exams import ExamOrder, ExamResult`.
- Add `"ExamOrder"`, `"ExamResult"` and `"NotebookEntry"` to `__all__`, keeping it sorted.

- [ ] **Step 4: Write the migration**

```python
# backend/alembic/versions/0003_exams_notebook.py
"""exam_orders, exam_results, notebook_entries (data-model 1.4)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('exam_orders',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
    sa.Column('appointment_id', sa.String(), sa.ForeignKey('appointments.id'), nullable=True),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('label', sa.String(), nullable=False),
    sa.Column('department', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('ai_suggested', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('human_confirmed_by', sa.String(), sa.ForeignKey('users.id'), nullable=True),
    sa.Column('ordered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_exam_orders_patient_id', 'exam_orders', ['patient_id'])
    op.create_index('ix_exam_orders_appointment_id', 'exam_orders', ['appointment_id'])
    op.create_index('ix_exam_orders_department', 'exam_orders', ['department'])
    op.create_table('exam_results',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('exam_order_id', sa.String(), sa.ForeignKey('exam_orders.id'), nullable=False),
    sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
    sa.Column('uploaded_by', sa.String(), sa.ForeignKey('users.id'), nullable=False),
    sa.Column('file_key', sa.String(), nullable=False),
    sa.Column('file_name', sa.String(), nullable=False),
    sa.Column('content_type', sa.String(), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('report_text', sa.Text(), server_default='', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_exam_results_exam_order_id', 'exam_results', ['exam_order_id'])
    op.create_index('ix_exam_results_patient_id', 'exam_results', ['patient_id'])
    op.create_table('notebook_entries',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
    sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('ai_suggested', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('human_confirmed_by', sa.String(), sa.ForeignKey('users.id'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notebook_entries_patient_id', 'notebook_entries', ['patient_id'])


def downgrade() -> None:
    op.drop_table('notebook_entries')
    op.drop_table('exam_results')
    op.drop_table('exam_orders')
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && python -m pytest tests/test_exam_models.py -v`
Expected: PASS

Then check that the migration applies on the dev DB:

```bash
cd backend && DATABASE_URL=postgresql+psycopg://ward:ward@localhost:5544/ward alembic upgrade head && DATABASE_URL=postgresql+psycopg://ward:ward@localhost:5544/ward alembic downgrade -1 && DATABASE_URL=postgresql+psycopg://ward:ward@localhost:5544/ward alembic upgrade head
```

Expected: no error.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/exams.py backend/app/models/ai.py backend/app/models/__init__.py backend/alembic/versions/0003_exams_notebook.py backend/tests/test_exam_models.py
git commit -m "feat(backend): exam_orders, exam_results and notebook_entries tables"
```

---

### Task 3: Seed the two department nurses (Wali's file, tag him)

**Files:**
- Modify: `backend/app/seed.py` (the `STAFF` list and the `reserve_upto` line)
- Test: `backend/tests/test_seed.py`

**Interfaces:**
- Produces: logins `imaging@medora.tn` (`u-0006`, Staff ward `Imaging`, name `Nurse Rania`) and `lab@medora.tn` (`u-0007`, ward `Laboratory`, name `Nurse Karim`), password `ward1234`.

- [ ] **Step 1: Write the failing test.** Append to `backend/tests/test_seed.py`:

```python
def test_seed_department_nurses(seeded):
    from app.models import Staff, User

    assert seeded.get(User, "u-0006").email == "imaging@medora.tn" and seeded.get(Staff, "u-0006").ward == "Imaging"
    assert seeded.get(User, "u-0007").email == "lab@medora.tn" and seeded.get(Staff, "u-0007").ward == "Laboratory"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && python -m pytest tests/test_seed.py::test_seed_department_nurses -v`
Expected: FAIL (`'NoneType' object has no attribute 'email'`)

- [ ] **Step 3: Implement.** Add two tuples at the end of `STAFF` in `backend/app/seed.py`:

```python
    ("u-0006", "imaging@medora.tn", "Nurse Rania", "nurse", "Imaging", None),
    ("u-0007", "lab@medora.tn", "Nurse Karim", "nurse", "Laboratory", None),
```

Change `("u", 5)` in the `reserve_upto` loop to `("u", 7)`.

- [ ] **Step 4: Run the whole suite** (other tests read seed users)

Run: `cd backend && python -m pytest -q`
Expected: all pass. If a test counts staff rows (for example `GET /staff` length), update its expected number by +2 and say so in the commit body.

- [ ] **Step 5: Commit**

```bash
git add backend/app/seed.py backend/tests/test_seed.py
git commit -m "feat(backend): seed Imaging and Laboratory nurses"
```

---

### Task 4: Exam rules and `suggest_exams`

**Files:**
- Create: `backend/app/ai/rules/exam_bundles.v1.json`
- Create: `backend/app/ai/exams.py`
- Test: `backend/tests/test_exam_rules.py`

**Interfaces:**
- Consumes: `app.ai.triage._normalize(text: str) -> str`.
- Produces:
  - `catalogue() -> dict[str, dict]`, mapping code → `{"label","department"}`.
  - `suggest_exams(text: str, red_flags: list[str]) -> dict`, returning `{"exams": [{"code","label","department"}], "bundles": [str], "source": "rules"}` with at most 4 exams.
  - `DEPARTMENTS = ("Imaging", "Laboratory", "Cardiology")`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_exam_rules.py
from app.ai.exams import DEPARTMENTS, MAX_EXAMS, catalogue, suggest_exams


def codes(text, flags=()):
    return [e["code"] for e in suggest_exams(text, list(flags))["exams"]]


def test_chest_pain_flag_gives_the_cardiac_set():
    out = suggest_exams("douleur thoracique depuis deux jours", ["chest_pain"])
    assert [e["code"] for e in out["exams"]] == ["ecg", "troponin", "chest_xray"]
    assert out["source"] == "rules" and out["bundles"] == ["chest_pain"]
    assert out["exams"][0] == {"code": "ecg", "label": "ECG (12-lead)", "department": "Cardiology"}


def test_keywords_in_three_languages():
    assert codes("Palpitations at night") == ["ecg", "echo"]
    assert codes("Fièvre et toux productive depuis 5 jours") == ["cbc", "crp", "chest_xray"]
    assert codes("حمى وسعال منذ ثلاثة أيام") == ["cbc", "crp", "chest_xray"]
    assert codes("Routine diabetes follow-up, HbA1c review") == ["hba1c", "creatinine"]
    assert codes("Bleeding gums since warfarin dose change") == ["inr", "cbc"]


def test_no_match_and_cap():
    assert codes("Annual check-up, no complaints") == []
    many = codes("chest pain with fever and cough, swelling of the leg", ["chest_pain"])
    assert len(many) == MAX_EXAMS == 4 and len(set(many)) == 4


def test_rules_file_is_consistent():
    cat = catalogue()
    assert all(v["department"] in DEPARTMENTS and v["label"] for v in cat.values())
    from app.ai.exams import _rules

    for b in _rules()["bundles"]:
        assert b["exams"] and all(c in cat for c in b["exams"]), b["id"]
        assert b.get("red_flags") or b.get("keywords"), b["id"]
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd backend && python -m pytest tests/test_exam_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ai.exams'`

- [ ] **Step 3: Write the rules file**

```json
{
  "version": 1,
  "note": "Illustrative exam sets for the prototype, on synthetic data. To be reviewed by the hospital's doctors before any real use.",
  "catalogue": {
    "ecg": {"label": "ECG (12-lead)", "department": "Cardiology"},
    "echo": {"label": "Echocardiography", "department": "Cardiology"},
    "troponin": {"label": "Troponin", "department": "Laboratory"},
    "cbc": {"label": "Complete blood count", "department": "Laboratory"},
    "crp": {"label": "CRP", "department": "Laboratory"},
    "d_dimer": {"label": "D-dimer", "department": "Laboratory"},
    "inr": {"label": "INR", "department": "Laboratory"},
    "hba1c": {"label": "HbA1c", "department": "Laboratory"},
    "creatinine": {"label": "Creatinine", "department": "Laboratory"},
    "chest_xray": {"label": "Chest X-ray", "department": "Imaging"},
    "brain_ct": {"label": "Brain CT scan", "department": "Imaging"},
    "leg_doppler": {"label": "Leg venous Doppler", "department": "Imaging"}
  },
  "bundles": [
    {"id": "chest_pain", "red_flags": ["chest_pain"], "keywords": ["chest pain", "douleur thoracique", "ألم في الصدر"], "exams": ["ecg", "troponin", "chest_xray"]},
    {"id": "stroke", "red_flags": ["stroke_signs"], "exams": ["brain_ct", "cbc"]},
    {"id": "breathing", "red_flags": ["breathing"], "keywords": ["essoufflement", "dyspnea", "short of breath", "ضيق في التنفس"], "exams": ["chest_xray", "cbc", "crp"]},
    {"id": "palpitations", "keywords": ["palpitation", "خفقان"], "exams": ["ecg", "echo"]},
    {"id": "fever_cough", "keywords": ["fever", "fievre", "cough", "toux", "حمى", "سعال"], "exams": ["cbc", "crp", "chest_xray"]},
    {"id": "leg_swelling", "keywords": ["swelling", "gonflement", "oedeme", "edema", "leg pain", "painful leg"], "exams": ["leg_doppler", "d_dimer"]},
    {"id": "anticoagulant_bleeding", "keywords": ["warfarin", "sintrom", "bleeding", "saignement", "نزيف"], "exams": ["inr", "cbc"]},
    {"id": "diabetes", "keywords": ["diabetes", "diabete", "hba1c", "سكري"], "exams": ["hba1c", "creatinine"]}
  ]
}
```

Note: the "Palpitations at night" test expects only `["ecg", "echo"]`, so no other bundle may match the word "night". The breathing keywords are in the breathing bundle on purpose: the seed's "Palpitations ..., short of breath" request then gets `ecg, echo, chest_xray, cbc`, which is fine.

- [ ] **Step 4: Write `app/ai/exams.py`**

```python
"""Exam-set suggestions for a request (owner: Faouzi). Rules only, no LLM: red flags from triage plus keywords in
French, English and Arabic, from rules/exam_bundles.v1.json. A doctor orders or drops each suggestion."""

import json
from functools import lru_cache
from pathlib import Path

from app.ai.triage import _normalize

RULES = Path(__file__).parent / "rules" / "exam_bundles.v1.json"
MAX_EXAMS = 4
DEPARTMENTS = ("Imaging", "Laboratory", "Cardiology")


@lru_cache
def _rules() -> dict:
    data = json.loads(RULES.read_text(encoding="utf-8"))
    for b in data["bundles"]:
        b["norm_keywords"] = [_normalize(k) for k in b.get("keywords", [])]
    return data


def catalogue() -> dict[str, dict]:
    return _rules()["catalogue"]


def _matches(bundle: dict, text: str, red_flags: set[str]) -> bool:
    return bool(red_flags & set(bundle.get("red_flags", []))) or any(k in text for k in bundle["norm_keywords"])


def suggest_exams(text: str, red_flags: list[str]) -> dict:
    t, flags = _normalize(text), set(red_flags)
    hits = [b for b in _rules()["bundles"] if _matches(b, t, flags)]
    codes: list[str] = []
    for b in hits:
        codes += [c for c in b["exams"] if c not in codes]
    cat = catalogue()
    return {"exams": [{"code": c, **cat[c]} for c in codes[:MAX_EXAMS]], "bundles": [b["id"] for b in hits],
            "source": "rules"}
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && python -m pytest tests/test_exam_rules.py -v`
Expected: PASS. If an Arabic keyword fails, print `_normalize("حمى وسعال")` and `_normalize("حمى")` and fix the keyword spelling in the JSON, not the test.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ai/rules/exam_bundles.v1.json backend/app/ai/exams.py backend/tests/test_exam_rules.py
git commit -m "feat(ai): rules-based exam set suggestions"
```

---

### Task 5: File storage in MinIO

**Files:**
- Modify: `backend/requirements.txt` (add `minio==7.*`)
- Create: `backend/app/services/storage.py`
- Modify: `infra/docker-compose.yml` (api `depends_on` minio; Wali's file, tag him)
- Test: `backend/tests/test_storage.py`

**Interfaces:**
- Produces: `storage.put(key: str, data: bytes, content_type: str) -> None` and `storage.get(key: str) -> bytes`. Callers use `from app.services import storage` and call `storage.put(...)` so tests can monkeypatch the module functions.

- [ ] **Step 1: Write the failing test** (an integration test that skips when MinIO isn't reachable)

```python
# backend/tests/test_storage.py
import socket
import uuid

import pytest

from app.config import get_settings


def _minio_up() -> bool:
    host, _, port = get_settings().minio_endpoint.partition(":")
    try:
        with socket.create_connection((host, int(port or 9000)), timeout=1):
            return True
    except OSError:
        return False


@pytest.mark.skipif(not _minio_up(), reason="MinIO not reachable")
def test_put_then_get_round_trip():
    from app.services import storage

    key = f"tests/{uuid.uuid4().hex}.txt"
    storage.put(key, b"hello ward", "text/plain")
    assert storage.get(key) == b"hello ward"
```

- [ ] **Step 2: Run it to make sure it fails or skips**

Run: `cd backend && pip install "minio==7.*" && python -m pytest tests/test_storage.py -v -rs`
Expected: FAIL with `ImportError: cannot import name 'storage'` (or SKIPPED if MinIO is down; then start it with `docker compose -p ward -f infra/docker-compose.yml up -d minio` and rerun until it FAILS on the import).

- [ ] **Step 3: Implement**

Add `minio==7.*` to the end of `backend/requirements.txt`.

```python
# backend/app/services/storage.py
"""Exam files in MinIO (bucket MINIO_BUCKET). Files are only ever served through the API, which checks access
and writes audit_log; there are no public MinIO links. Callers use `storage.put(...)` through the module so tests
can swap it."""

import io
from functools import lru_cache

from minio import Minio

from app.config import get_settings


@lru_cache
def _client() -> Minio:
    s = get_settings()
    client = Minio(s.minio_endpoint, access_key=s.minio_root_user, secret_key=s.minio_root_password, secure=False)
    if not client.bucket_exists(s.minio_bucket):
        client.make_bucket(s.minio_bucket)
    return client


def put(key: str, data: bytes, content_type: str) -> None:
    _client().put_object(get_settings().minio_bucket, key, io.BytesIO(data), len(data), content_type=content_type)


def get(key: str) -> bytes:
    resp = _client().get_object(get_settings().minio_bucket, key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()
```

In `infra/docker-compose.yml`, add under the `api` service's `depends_on`: `minio: { condition: service_started }`.

- [ ] **Step 4: Run the test with MinIO up**

Run: `cd backend && MINIO_ENDPOINT=localhost:9000 python -m pytest tests/test_storage.py -v -rs`
Expected: PASS (needs the `minio` container; its port 9000 is published by compose).

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/app/services/storage.py backend/tests/test_storage.py infra/docker-compose.yml
git commit -m "feat(backend): MinIO storage for exam files"
```

---

### Task 6: Exam service rules (status, access, payloads)

**Files:**
- Create: `backend/app/services/exams.py`
- Test: `backend/tests/test_exams_service.py`

**Interfaces:**
- Consumes: `ExamOrder`, `ExamResult`, `Appointment`, `Patient`, `Staff`, `User` from `app.models`; `staff_ward(db, user)` and `can_access(db, user, patient)` from `app.auth.deps`; `iso` from `app.schemas`.
- Produces:
  - `class BadStatus(Exception)`
  - `suggested_fields(patient_id: str, appointment_id: str, suggestion: dict) -> list[dict]`
  - `order(o, *, user_id: str, now: datetime) -> None`, `cancel(o) -> None`, `mark_done(o, *, now: datetime) -> None`
  - `counts(orders: list) -> dict` returning `{"exams_total","exams_done","exams_suggested"}`
  - `can_read(db, user, o) -> bool` and `can_upload(db, user, o) -> bool`
  - `to_out(db, o, viewer) -> dict`
  - `ordered_event(patient, appointment_id, orders) -> dict` and `results_ready_event(db, appointment_id, patient, doctor_id) -> dict`
  - `safe_name(name: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_exams_service.py
from datetime import UTC, datetime
from types import SimpleNamespace as NS

import pytest

from app.services import exams as E

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


def row(status="suggested", **kw):
    return NS(status=status, human_confirmed_by=None, ordered_at=None, done_at=None, **kw)


def test_status_machine():
    o = row()
    E.order(o, user_id="u-0001", now=NOW)
    assert (o.status, o.human_confirmed_by, o.ordered_at) == ("ordered", "u-0001", NOW)
    E.mark_done(o, now=NOW)
    assert o.status == "done" and o.done_at == NOW
    for bad in (lambda: E.order(o, user_id="u", now=NOW), lambda: E.cancel(o), lambda: E.mark_done(o, now=NOW)):
        with pytest.raises(E.BadStatus):
            bad()
    with pytest.raises(E.BadStatus):
        E.mark_done(row("suggested"), now=NOW)
    c = row("ordered")
    E.cancel(c)
    assert c.status == "cancelled"


def test_counts_ignore_cancelled():
    rows = [row("suggested"), row("ordered"), row("done"), row("done"), row("cancelled")]
    assert E.counts(rows) == {"exams_total": 3, "exams_done": 2, "exams_suggested": 1}


def test_suggested_fields():
    sug = {"exams": [{"code": "ecg", "label": "ECG (12-lead)", "department": "Cardiology"}], "bundles": ["chest_pain"],
           "source": "rules"}
    [f] = E.suggested_fields("p-0003", "a-0001", sug)
    assert f["status"] == "suggested" and f["code"] == "ecg" and f["appointment_id"] == "a-0001"
    assert f["ai_suggested"] == {"source": "rules", "bundles": ["chest_pain"],
                                 "reason": "Suggested by the exam rules for: chest_pain"}


def test_safe_name():
    assert E.safe_name("../../etc/passwd") == "passwd"
    assert E.safe_name("ECG résultat 1.pdf") == "ECG_r_sultat_1.pdf"
    assert E.safe_name("") == "file"


def test_ordered_event_has_first_name_only():
    p = NS(first_name="Amira", last_name="Ben Salah", telegram_chat_id="42", email="a@x.tn")
    ev = E.ordered_event(p, "a-0001", [NS(label="Chest X-ray", department="Imaging")])
    assert ev == {"appointment_id": "a-0001", "patient_first_name": "Amira", "patient_telegram_chat_id": "42",
                  "patient_email": "a@x.tn", "exams": [{"label": "Chest X-ray", "department": "Imaging"}]}
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd backend && python -m pytest tests/test_exams_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'exams' from 'app.services'`

- [ ] **Step 3: Implement**

```python
# backend/app/services/exams.py
"""Exam-order rules (owner: Faouzi): status machine, who may read or upload, response and event shapes.
Spec: docs/superpowers/specs/2026-10-09-single-visit-and-case-notebook-design.md §4."""

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import can_access, staff_ward
from app.models import Appointment, ExamResult, Patient, Staff, User
from app.schemas import iso

ALLOWED_TYPES = ("application/pdf", "image/jpeg", "image/png")
MAX_BYTES = 15 * 1024 * 1024


class BadStatus(Exception):
    """Maps to HTTP 409 {"code": "bad_status"}."""


def suggested_fields(patient_id: str, appointment_id: str, suggestion: dict) -> list[dict]:
    reason = "Suggested by the exam rules for: " + ", ".join(suggestion["bundles"])
    return [{"patient_id": patient_id, "appointment_id": appointment_id, "code": e["code"], "label": e["label"],
             "department": e["department"], "status": "suggested",
             "ai_suggested": {"source": suggestion["source"], "bundles": suggestion["bundles"], "reason": reason}}
            for e in suggestion["exams"]]


def order(o, *, user_id: str, now: datetime) -> None:
    if o.status != "suggested":
        raise BadStatus(f"exam is {o.status}")
    o.status, o.human_confirmed_by, o.ordered_at = "ordered", user_id, now


def cancel(o) -> None:
    if o.status not in ("suggested", "ordered"):
        raise BadStatus(f"exam is {o.status}")
    o.status = "cancelled"


def mark_done(o, *, now: datetime) -> None:
    if o.status != "ordered":
        raise BadStatus(f"exam is {o.status}")
    o.status, o.done_at = "done", now


def counts(orders: list) -> dict:
    s = [o.status for o in orders]
    return {"exams_total": s.count("ordered") + s.count("done"), "exams_done": s.count("done"),
            "exams_suggested": s.count("suggested")}


def can_read(db: Session, user: User, o) -> bool:
    if user.role == "doctor":
        p = db.get(Patient, o.patient_id)
        a = db.get(Appointment, o.appointment_id) if o.appointment_id else None
        return (p is not None and p.attending_doctor_id == user.id) or o.human_confirmed_by == user.id or (
            a is not None and (a.doctor_id == user.id or a.status == "requested"))
    if user.role == "nurse":
        p = db.get(Patient, o.patient_id)
        return o.department == staff_ward(db, user) or (p is not None and can_access(db, user, p))
    if user.role == "patient":
        return user.patient_id == o.patient_id and o.status in ("ordered", "done")
    return user.role == "admin"


def can_upload(db: Session, user: User, o) -> bool:
    return user.role == "nurse" and o.department == staff_ward(db, user)


def _name(db: Session, user_id: str | None) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return u.name if u else None


def to_out(db: Session, o, viewer: User) -> dict:
    p = db.get(Patient, o.patient_id)
    out = {"id": o.id, "patient_id": o.patient_id, "appointment_id": o.appointment_id, "code": o.code,
           "label": o.label, "department": o.department, "status": o.status, "ai_suggested": o.ai_suggested,
           "human_confirmed_by": o.human_confirmed_by, "ordered_at": iso(o.ordered_at), "done_at": iso(o.done_at),
           "created_at": iso(o.created_at), "patient_name": f"{p.first_name} {p.last_name}" if p else None}
    if viewer.role in ("doctor", "nurse"):
        rows = db.scalars(select(ExamResult).where(ExamResult.exam_order_id == o.id)
                          .order_by(ExamResult.created_at)).all()
        out["results"] = [{"id": r.id, "file_name": r.file_name, "content_type": r.content_type,
                           "size_bytes": r.size_bytes, "report_text": r.report_text,
                           "uploaded_by_name": _name(db, r.uploaded_by),
                           "created_at": iso(r.created_at)} for r in rows]
    if viewer.role == "patient":
        out.pop("ai_suggested")
        out.pop("human_confirmed_by")
    return out


def ordered_event(patient, appointment_id: str | None, orders: list) -> dict:
    return {"appointment_id": appointment_id, "patient_first_name": patient.first_name,
            "patient_telegram_chat_id": patient.telegram_chat_id, "patient_email": patient.email,
            "exams": [{"label": o.label, "department": o.department} for o in orders]}


def results_ready_event(db: Session, appointment_id: str, patient, doctor_id: str | None) -> dict:
    doctor = db.get(User, doctor_id) if doctor_id else None
    staff = db.get(Staff, doctor_id) if doctor_id else None
    return {"appointment_id": appointment_id, "patient_first_name": patient.first_name, "doctor_id": doctor_id,
            "doctor_name": doctor.name if doctor else None, "doctor_email": doctor.email if doctor else None,
            "doctor_chat_id": staff.telegram_chat_id if staff else None}


def safe_name(name: str) -> str:
    base = re.split(r"[\\/]", name or "")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._")
    return cleaned[:120] or "file"
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && python -m pytest tests/test_exams_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/exams.py backend/tests/test_exams_service.py
git commit -m "feat(backend): exam order rules, access checks and event payloads"
```

---

### Task 7: Exam routes, suggestions on new requests, counts on appointments

**Files:**
- Create: `backend/app/routers/exams.py`
- Modify: `backend/app/routers/appointments.py` (`create()` adds suggestions; `to_out()` adds counts)
- Modify: `backend/app/main.py` (mount `exams.router`; Wali's file)
- Test: `backend/tests/test_exams_api.py`

**Interfaces:**
- Consumes: Task 4 `suggest_exams`, `catalogue`; Task 5 `storage.put/get`; Task 6 everything; `check_patient_access`, `require_roles`, `new_id`, `audit`, `n8n.emit`.
- Produces: the routes in api.md 1.8 (Task 1) except `/ai/notebook*`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_exams_api.py
import pytest

from app.models import ExamOrder, ExamResult
from tests.helpers import login

CHEST = {"patient_id": "p-0001", "referral_text": "douleur thoracique depuis ce matin", "symptoms": ["chest pain"]}
PDF = ("ecg.pdf", b"%PDF-1.4 fake", "application/pdf")


@pytest.fixture()
def stored(monkeypatch):
    """In-memory MinIO: {key: (bytes, content_type)}."""
    from app.services import storage

    files: dict[str, tuple[bytes, str]] = {}
    monkeypatch.setattr(storage, "put", lambda key, data, ct: files.__setitem__(key, (data, ct)))
    monkeypatch.setattr(storage, "get", lambda key: files[key][0])
    return files


def _request(client):
    a = client.post("/appointments", headers=login(client, "admin@medora.tn"), json=CHEST).json()
    doc = login(client, "doctor@medora.tn")
    return a, doc, client.get(f"/appointments/{a['id']}/exams", headers=doc).json()


def test_new_request_gets_suggestions(client):
    a, doc, exams = _request(client)
    assert [e["code"] for e in exams] == ["ecg", "troponin", "chest_xray"]
    assert all(e["status"] == "suggested" and e["ai_suggested"]["source"] == "rules" for e in exams)
    row = client.get("/appointments/waitlist", headers=doc).json()
    mine = next(r for r in row if r["id"] == a["id"])
    assert (mine["exams_suggested"], mine["exams_total"], mine["exams_done"]) == (3, 0, 0)


def test_order_selected_cancels_the_rest_and_emits(client, emitted):
    a, doc, exams = _request(client)
    keep = [exams[0]["id"], exams[2]["id"]]
    r = client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": keep})
    assert r.status_code == 200, r.text
    st = {e["id"]: e["status"] for e in r.json()}
    assert st == {exams[0]["id"]: "ordered", exams[1]["id"]: "cancelled", exams[2]["id"]: "ordered"}
    assert all(e["human_confirmed_by"] == "u-0001" for e in r.json() if e["status"] == "ordered")
    event, data = emitted[-1]
    assert event == "exam.ordered" and data["patient_first_name"] == "Amira"
    assert [x["label"] for x in data["exams"]] == ["ECG (12-lead)", "Chest X-ray"]


def test_order_rejects_foreign_or_stale_ids(client, db):
    a, doc, exams = _request(client)
    other = client.post("/appointments", headers=login(client, "admin@medora.tn"),
                        json=dict(CHEST, patient_id="p-0002")).json()
    foreign = client.get(f"/appointments/{other['id']}/exams", headers=doc).json()[0]["id"]
    r = client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [foreign]})
    assert r.status_code == 422
    assert db.get(ExamOrder, foreign).status == "suggested"
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [exams[0]["id"]]})
    again = client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [exams[0]["id"]]})
    assert again.status_code == 409 and again.json()["code"] == "bad_status"
    nurse = login(client, "nurse@medora.tn")
    assert client.post(f"/appointments/{a['id']}/exams/order", headers=nurse, json={"exam_ids": []}).status_code == 403


def test_doctor_adds_an_exam_by_hand(client, emitted):
    a, doc, _ = _request(client)
    r = client.post("/exams", headers=doc, json={"patient_id": "p-0001", "appointment_id": a["id"], "code": "echo"})
    assert r.status_code == 201 and r.json()["status"] == "ordered" and r.json()["ai_suggested"] is None
    assert emitted[-1][0] == "exam.ordered"
    assert client.post("/exams", headers=doc, json={"patient_id": "p-0001", "code": "mri_magic"}).status_code == 422
    assert client.get("/exams/catalogue", headers=doc).json()[0].keys() == {"code", "label", "department"}


def test_upload_rules(client, db, stored):
    a, doc, exams = _request(client)
    xray = exams[2]["id"]  # Imaging
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [xray]})
    lab = login(client, "lab@medora.tn")
    assert client.post(f"/exams/{xray}/results", headers=lab, files={"file": PDF}).status_code == 403
    img = login(client, "imaging@medora.tn")
    bad = client.post(f"/exams/{xray}/results", headers=img, files={"file": ("x.exe", b"MZ", "application/x-msdownload")})
    assert bad.status_code == 422 and bad.json()["code"] == "bad_file"
    big = client.post(f"/exams/{xray}/results", headers=img,
                      files={"file": ("big.pdf", b"0" * (15 * 1024 * 1024 + 1), "application/pdf")})
    assert big.status_code == 422 and big.json()["code"] == "bad_file"
    assert stored == {} and db.query(ExamResult).count() == 0 and db.get(ExamOrder, xray).status == "ordered"
    ok = client.post(f"/exams/{xray}/results", headers=img, files={"file": PDF}, data={"report_text": "No consolidation"})
    assert ok.status_code == 200 and ok.json()["status"] == "done"
    [res] = ok.json()["results"]
    assert res["report_text"] == "No consolidation" and res["uploaded_by_name"] == "Nurse Rania"
    assert list(stored)[0] == f"exams/{xray}/{res['id']}/ecg.pdf"
    again = client.post(f"/exams/{xray}/results", headers=img, files={"file": PDF})
    assert again.status_code == 409


def test_results_ready_fires_once_on_last_upload(client, emitted, stored):
    a, doc, exams = _request(client)
    ecg, xray = exams[0]["id"], exams[2]["id"]
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [ecg, xray]})
    client.post(f"/exams/{ecg}/results", headers=login(client, "nurse@medora.tn"), files={"file": PDF})
    assert [e for e, _ in emitted].count("exam.results_ready") == 0
    client.post(f"/exams/{xray}/results", headers=login(client, "imaging@medora.tn"), files={"file": PDF})
    ready = [d for e, d in emitted if e == "exam.results_ready"]
    assert len(ready) == 1 and ready[0]["doctor_id"] == "u-0001" and ready[0]["appointment_id"] == a["id"]


def test_file_download_is_audited_and_guarded(client, db, stored):
    from app.models import AuditLog

    a, doc, exams = _request(client)
    xray = exams[2]["id"]
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [xray]})
    res = client.post(f"/exams/{xray}/results", headers=login(client, "imaging@medora.tn"),
                      files={"file": PDF}).json()["results"][0]
    r = client.get(f"/exam-results/{res['id']}/file", headers=doc)
    assert r.status_code == 200 and r.content == PDF[1] and r.headers["content-type"] == "application/pdf"
    assert db.query(AuditLog).filter_by(resource="exam_result", resource_id=res["id"]).count() == 1
    assert client.get(f"/exam-results/{res['id']}/file", headers=login(client, "nurse2@medora.tn")).status_code == 403
    assert client.get(f"/exam-results/{res['id']}/file", headers=login(client, "patient@medora.tn")).status_code == 403


def test_patient_sees_only_ordered_rows(client):
    patient = login(client, "patient@medora.tn")
    a = client.post("/appointments", headers=patient, json=CHEST).json()
    assert client.get(f"/appointments/{a['id']}/exams", headers=patient).json() == []
    assert client.get("/patients/p-0001/exams", headers=patient).json() == []
    doc = login(client, "doctor@medora.tn")
    first = client.get(f"/appointments/{a['id']}/exams", headers=doc).json()[0]["id"]
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [first]})
    [row] = client.get("/patients/p-0001/exams", headers=patient).json()
    assert row["status"] == "ordered" and "ai_suggested" not in row and "results" not in row
    assert "exams_suggested" in client.get("/appointments", headers=patient).json()[0]


def test_worklist_is_per_department(client):
    a, doc, exams = _request(client)
    client.post(f"/appointments/{a['id']}/exams/order", headers=doc, json={"exam_ids": [e["id"] for e in exams]})
    img = client.get("/exams?status=ordered", headers=login(client, "imaging@medora.tn")).json()
    lab = client.get("/exams?status=ordered", headers=login(client, "lab@medora.tn")).json()
    assert [e["code"] for e in img] == ["chest_xray"] and [e["code"] for e in lab] == ["troponin"]
    assert img[0]["patient_name"] == "Amira Ben Salah"
    assert client.get("/exams", headers=doc).status_code == 403
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd backend && python -m pytest tests/test_exams_api.py -v`
Expected: FAIL (404 on `/appointments/{id}/exams`, and `KeyError: 'exams_suggested'`)

- [ ] **Step 3: Write the router**

```python
# backend/app/routers/exams.py
"""Single-visit exams (owner: Faouzi): suggested at request time, ordered by a doctor, results uploaded by the
performing department's nurse. Contract: api.md 1.8; events: n8n-webhooks 1.3. Rules: app/services/exams.py."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.exams import catalogue
from app.auth.deps import check_patient_access, require_roles, staff_ward
from app.db import get_db
from app.errors import ApiError, forbidden, not_found
from app.ids import new_id
from app.integrations import n8n
from app.models import Appointment, ExamOrder, ExamResult, Patient, User
from app.services import exams as E
from app.services import storage
from app.services.audit import audit

router = APIRouter(tags=["exams"])


class OrderIn(BaseModel):
    exam_ids: list[str]


class ExamIn(BaseModel):
    patient_id: str
    appointment_id: str | None = None
    code: str


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _bad_status(e: E.BadStatus) -> ApiError:
    return ApiError(409, "bad_status", str(e))


def _exam(db: Session, exam_id: str) -> ExamOrder:
    o = db.get(ExamOrder, exam_id)
    if o is None:
        raise not_found("exam")
    return o


def _visible(db: Session, user: User, rows) -> list[ExamOrder]:
    return [o for o in rows if E.can_read(db, user, o)]


@router.get("/exams/catalogue")
def exam_catalogue(user: User = Depends(require_roles("doctor"))) -> list[dict]:
    return [{"code": c, "label": v["label"], "department": v["department"]} for c, v in catalogue().items()]


@router.get("/appointments/{appointment_id}/exams")
def appointment_exams(appointment_id: str, request: Request,
                      user: User = Depends(require_roles("doctor", "admin", "patient")),
                      db: Session = Depends(get_db)) -> list[dict]:
    a = db.get(Appointment, appointment_id)
    if a is None:
        raise not_found("appointment")
    if user.role == "patient" and user.patient_id != a.patient_id:
        raise forbidden("not your appointment")
    rows = _visible(db, user, db.scalars(select(ExamOrder).where(ExamOrder.appointment_id == a.id)
                                         .order_by(ExamOrder.id)).all())
    audit(db, user, "read", "exams", a.id, patient_id=a.patient_id, ip=_ip(request))
    out = [E.to_out(db, o, user) for o in rows]
    db.commit()
    return out


@router.get("/patients/{patient_id}/exams")
def patient_exams(patient_id: str, request: Request, user: User = Depends(require_roles("doctor", "nurse", "patient")),
                  db: Session = Depends(get_db)) -> list[dict]:
    check_patient_access(db, user, patient_id, resource="exams", ip=_ip(request))
    rows = db.scalars(select(ExamOrder).where(ExamOrder.patient_id == patient_id,
                                              ExamOrder.status != "cancelled").order_by(ExamOrder.id)).all()
    out = [E.to_out(db, o, user) for o in _visible(db, user, rows)]
    db.commit()
    return out


@router.get("/exams")
def worklist(request: Request, status: str | None = None, user: User = Depends(require_roles("nurse", "admin")),
             db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(ExamOrder).order_by(ExamOrder.ordered_at, ExamOrder.id)
    if user.role == "nurse":
        stmt = stmt.where(ExamOrder.department == (staff_ward(db, user) or ""))
    if status:
        stmt = stmt.where(ExamOrder.status == status)
    rows = db.scalars(stmt).all()
    audit(db, user, "read", "exam_worklist", status or "", ip=_ip(request))
    out = [E.to_out(db, o, user) for o in rows]
    db.commit()
    return out


@router.post("/appointments/{appointment_id}/exams/order")
def order_selected(appointment_id: str, body: OrderIn, user: User = Depends(require_roles("doctor")),
                   db: Session = Depends(get_db)) -> list[dict]:
    a = db.get(Appointment, appointment_id)
    if a is None:
        raise not_found("appointment")
    rows = db.scalars(select(ExamOrder).where(ExamOrder.appointment_id == a.id).order_by(ExamOrder.id)).all()
    by_id = {o.id: o for o in rows}
    if any(i not in by_id for i in body.exam_ids):
        raise ApiError(422, "invalid", "exam_ids: not an exam of this appointment")
    now = datetime.now(UTC)
    ordered = []
    try:
        for i in body.exam_ids:
            E.order(by_id[i], user_id=user.id, now=now)
            ordered.append(by_id[i])
        for o in rows:
            if o.status == "suggested":
                E.cancel(o)
    except E.BadStatus as e:
        db.rollback()
        raise _bad_status(e) from e
    db.flush()
    event = E.ordered_event(db.get(Patient, a.patient_id), a.id, ordered) if ordered else None
    out = [E.to_out(db, o, user) for o in rows]
    db.commit()
    if event:
        n8n.emit("exam.ordered", event)
    return out


@router.post("/exams", status_code=201)
def add_exam(body: ExamIn, user: User = Depends(require_roles("doctor")), db: Session = Depends(get_db)) -> dict:
    item = catalogue().get(body.code)
    if item is None:
        raise ApiError(422, "invalid", "code: not in the exam catalogue")
    p = db.get(Patient, body.patient_id)
    if p is None:
        raise not_found("patient")
    if body.appointment_id:
        a = db.get(Appointment, body.appointment_id)
        if a is None or a.patient_id != p.id:
            raise ApiError(422, "invalid", "appointment_id: not this patient's appointment")
    elif p.attending_doctor_id != user.id:
        raise forbidden("not your patient")
    o = ExamOrder(id=new_id(db, "ex"), patient_id=p.id, appointment_id=body.appointment_id, code=body.code,
                  label=item["label"], department=item["department"], status="ordered", ai_suggested=None,
                  human_confirmed_by=user.id, ordered_at=datetime.now(UTC))
    db.add(o)
    db.flush()
    db.refresh(o)
    event = E.ordered_event(p, body.appointment_id, [o])
    out = E.to_out(db, o, user)
    db.commit()
    n8n.emit("exam.ordered", event)
    return out


@router.post("/exams/{exam_id}/cancel")
def cancel_exam(exam_id: str, user: User = Depends(require_roles("doctor")), db: Session = Depends(get_db)) -> dict:
    o = _exam(db, exam_id)
    if not E.can_read(db, user, o):
        raise forbidden("not your patient")
    try:
        E.cancel(o)
    except E.BadStatus as e:
        raise _bad_status(e) from e
    db.flush()
    out = E.to_out(db, o, user)
    db.commit()
    return out


@router.post("/exams/{exam_id}/results")
async def upload_result(exam_id: str, request: Request, file: UploadFile = File(...), report_text: str = Form(""),
                        user: User = Depends(require_roles("nurse")), db: Session = Depends(get_db)) -> dict:
    o = _exam(db, exam_id)
    if not E.can_upload(db, user, o):
        raise forbidden("not your department")
    if o.status != "ordered":
        raise _bad_status(E.BadStatus(f"exam is {o.status}"))
    data = await file.read(E.MAX_BYTES + 1)
    if file.content_type not in E.ALLOWED_TYPES or len(data) > E.MAX_BYTES or not data:
        raise ApiError(422, "bad_file", "upload a PDF, JPEG or PNG of at most 15 MB")
    rid, name = new_id(db, "er"), E.safe_name(file.filename or "")
    key = f"exams/{o.id}/{rid}/{name}"
    storage.put(key, data, file.content_type)
    db.add(ExamResult(id=rid, exam_order_id=o.id, patient_id=o.patient_id, uploaded_by=user.id, file_key=key,
                      file_name=name, content_type=file.content_type, size_bytes=len(data),
                      report_text=report_text.strip()[:2000]))
    E.mark_done(o, now=datetime.now(UTC))
    audit(db, user, "create", "exam_result", rid, patient_id=o.patient_id, ip=_ip(request))
    db.flush()
    event = None
    if o.appointment_id:
        still = db.scalar(select(ExamOrder.id).where(ExamOrder.appointment_id == o.appointment_id,
                                                     ExamOrder.status == "ordered").limit(1))
        if still is None:
            event = E.results_ready_event(db, o.appointment_id, db.get(Patient, o.patient_id), o.human_confirmed_by)
    out = E.to_out(db, o, user)
    db.commit()
    if event:
        n8n.emit("exam.results_ready", event)
    return out


@router.get("/exam-results/{result_id}/file")
def result_file(result_id: str, request: Request, user: User = Depends(require_roles("doctor", "nurse")),
                db: Session = Depends(get_db)) -> Response:
    r = db.get(ExamResult, result_id)
    if r is None:
        raise not_found("result")
    if not E.can_read(db, user, db.get(ExamOrder, r.exam_order_id)):
        raise forbidden("not your patient")
    audit(db, user, "read", "exam_result", r.id, patient_id=r.patient_id, ip=_ip(request))
    db.commit()
    return Response(storage.get(r.file_key), media_type=r.content_type,
                    headers={"Content-Disposition": f'inline; filename="{r.file_name}"'})
```

- [ ] **Step 4: Hook suggestions into requests and counts into `Appointment`.** In `backend/app/routers/appointments.py`:

Add imports:

```python
from app.ai.exams import suggest_exams
from app.models import Appointment, ExamOrder, Patient, User
from app.services import exams as E
```

At the end of `to_out()`, before the `if viewer.role == "patient":` block, add:

```python
    orders = db.scalars(select(ExamOrder).where(ExamOrder.appointment_id == a.id)).all()
    out.update(E.counts(orders))
```

In `create()`, after `db.flush()` (the one that follows `db.add(a)`) and before `audit(...)`, add:

```python
    suggestion = suggest_exams(" ".join([body.referral_text, *body.symptoms]), a.ai_suggested.get("red_flags", []))
    for fields in E.suggested_fields(p.id, a.id, suggestion):
        db.add(ExamOrder(id=new_id(db, "ex"), **fields))
```

In `backend/app/main.py`, add `exams` to the routers import and `app.include_router(exams.router)` after the integrations line.

- [ ] **Step 5: Run the tests**

Run: `cd backend && python -m pytest tests/test_exams_api.py tests/test_appointments_api.py -v`
Expected: PASS. Note: `test_new_request_gets_suggestions` expects exactly `ecg, troponin, chest_xray`. If triage adds another red flag for this text, check `out["bundles"]` and fix the test text (not the rules).

- [ ] **Step 6: Run the whole suite and lint**

Run: `cd backend && python -m pytest -q && python -m ruff check .`
Expected: all pass, `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/exams.py backend/app/routers/appointments.py backend/app/main.py backend/tests/test_exams_api.py
git commit -m "feat(backend): exam routes, suggestions on new requests, exam counts on appointments"
```

---

### Task 8: Triage scale label

**Files:**
- Create: `backend/app/ai/rules/triage_scale.v1.json`
- Modify: `backend/app/ai/triage.py` (`TriageResult.scale`, `scale_label()`)
- Test: `backend/tests/test_triage.py` (append)
- Modify: `web/src/lib/types.ts` (`Triage.scale?`), `web/src/components/Waitlist.tsx` (show the label)

**Interfaces:**
- Produces:
  - `scale_label(urgency: int) -> dict` returning `{"name": str, "level": str, "confirmed": bool}`.
  - `TriageResult.scale: dict | None`.
  - TS `Triage.scale?: { name: string; level: string; confirmed: boolean }`.

- [ ] **Step 1: Write the failing test** (append to `backend/tests/test_triage.py`)

```python
def test_scale_label_maps_our_urgency_to_the_hospital_scale():
    from app.ai.triage import scale_label, triage

    assert scale_label(5) == {"name": "FRENCH", "level": "Tri 1", "confirmed": False}
    assert scale_label(1)["level"] == "Tri 5"
    assert triage("douleur thoracique", [], 50).scale == scale_label(5)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && python -m pytest tests/test_triage.py::test_scale_label_maps_our_urgency_to_the_hospital_scale -v`
Expected: FAIL with `ImportError: cannot import name 'scale_label'`

- [ ] **Step 3: Implement**

`backend/app/ai/rules/triage_scale.v1.json`:

```json
{
  "name": "FRENCH",
  "confirmed": false,
  "note": "Display mapping from our urgency (5 = most urgent) to the hospital's triage scale. Set confirmed to true only after the hospital's doctors confirm the scale and the mapping.",
  "levels": {"5": "Tri 1", "4": "Tri 2", "3": "Tri 3", "2": "Tri 4", "1": "Tri 5"}
}
```

In `backend/app/ai/triage.py`:
- Add `SCALE = Path(__file__).parent / "rules" / "triage_scale.v1.json"` under `RULES`.
- Add `scale: dict | None = None` as the last field of `TriageResult`.
- Add:

```python
@lru_cache
def _scale() -> dict:
    return json.loads(SCALE.read_text(encoding="utf-8"))


def scale_label(urgency: int) -> dict:
    s = _scale()
    return {"name": s["name"], "level": s["levels"][str(urgency)], "confirmed": bool(s["confirmed"])}
```

Then in `triage()`'s `return TriageResult(...)`, add `scale=scale_label(urgency)`.

In `backend/app/routers/appointments.py`, add `"scale"` to `_TRIAGE_KEYS`.

- [ ] **Step 4: Web.** In `web/src/lib/types.ts`, add to `interface Triage`:

```ts
  /** The hospital's triage scale for this urgency (display mapping; `confirmed` false until doctors confirm it). */
  scale?: { name: string; level: string; confirmed: boolean } | null;
```

In `web/src/components/Waitlist.tsx`, inside the `.urgencyLine` div after the `Why?` button, add:

```tsx
{a.triage?.scale ? (
  <span className={styles.meta}>
    {a.triage.scale.level} · {a.triage.scale.name}{a.triage.scale.confirmed ? "" : " (to confirm)"}
  </span>
) : null}
```

- [ ] **Step 5: Run the checks**

Run: `cd backend && python -m pytest tests/test_triage.py tests/test_appointments_api.py -q` → PASS
Run: `cd web && npm run typecheck && npm run build` → both succeed

- [ ] **Step 6: Commit**

```bash
git add backend/app/ai/rules/triage_scale.v1.json backend/app/ai/triage.py backend/app/routers/appointments.py backend/tests/test_triage.py web/src/lib/types.ts web/src/components/Waitlist.tsx
git commit -m "feat(ai): show the hospital triage scale level next to our urgency"
```

---

### Task 9: Web data layer for exams (types, api, mocks)

**Files:**
- Modify: `web/src/lib/types.ts`
- Modify: `web/src/lib/api.ts`
- Create: `web/src/mocks/exams.ts`
- Modify: `web/src/mocks/index.ts` (store field `exams`, seeded fixtures)

**Interfaces:**
- Produces (TS, used by Tasks 10–13):

```ts
export type ExamStatus = "suggested" | "ordered" | "done" | "cancelled";
export interface ExamResultFile { id: string; file_name: string; content_type: string; size_bytes: number; report_text: string; uploaded_by_name: string | null; created_at: string; }
export interface ExamOrder { id: string; patient_id: string; appointment_id: string | null; code: string; label: string; department: string; status: ExamStatus; ai_suggested?: { source: AiSource; bundles: string[]; reason: string } | null; human_confirmed_by?: string | null; ordered_at: string | null; done_at: string | null; created_at: string; patient_name: string | null; results?: ExamResultFile[]; }
export interface CatalogueItem { code: string; label: string; department: string; }
// Appointment additions:
exams_total?: number; exams_done?: number; exams_suggested?: number;
```

`api.ts` functions:
- `getAppointmentExams(appointmentId: string): Promise<ExamOrder[]>`
- `getPatientExams(patientId: string): Promise<ExamOrder[]>`
- `getExamWorklist(): Promise<ExamOrder[]>` (status `ordered`, the caller's department)
- `orderExams(appointmentId: string, examIds: string[], opts?: ActorOpts): Promise<ExamOrder[]>`
- `addExam(req: { patient_id: string; appointment_id?: string; code: string }, opts?: ActorOpts): Promise<ExamOrder>`
- `getExamCatalogue(): Promise<CatalogueItem[]>`
- `uploadExamResult(examId: string, file: File, reportText: string, opts?: ActorOpts): Promise<ExamOrder>`
- `examFileUrl(resultId: string): Promise<string>` (an object URL of the authenticated download; mock returns `"/mock-exam.pdf"`)

- [ ] **Step 1: Types.** Add the block above to `web/src/lib/types.ts` after `interface Triage`, and add the three optional `exams_*` fields to `interface Appointment` under the "UI extensions" comment.

- [ ] **Step 2: Mocks.** Create `web/src/mocks/exams.ts`:

```ts
// Synthetic exam orders for the single-visit demo (spec 2026-10-09). The ids match the waitlist fixtures.
import type { CatalogueItem, ExamOrder } from "@/lib/types";

export const EXAM_CATALOGUE: CatalogueItem[] = [
  { code: "ecg", label: "ECG (12-lead)", department: "Cardiology" },
  { code: "echo", label: "Echocardiography", department: "Cardiology" },
  { code: "troponin", label: "Troponin", department: "Laboratory" },
  { code: "cbc", label: "Complete blood count", department: "Laboratory" },
  { code: "crp", label: "CRP", department: "Laboratory" },
  { code: "chest_xray", label: "Chest X-ray", department: "Imaging" },
];

const rules = (bundle: string) => ({ source: "rules" as const, bundles: [bundle], reason: `Suggested by the exam rules for: ${bundle}` });

export function examFixtures(firstAppointmentId: string, patientId: string, patientName: string): ExamOrder[] {
  const base = { patient_id: patientId, appointment_id: firstAppointmentId, ordered_at: null, done_at: null,
    created_at: "2026-10-09T07:40:00Z", patient_name: patientName, human_confirmed_by: null, results: [] };
  return [
    { ...base, id: "ex-0001", code: "ecg", label: "ECG (12-lead)", department: "Cardiology", status: "suggested", ai_suggested: rules("chest_pain") },
    { ...base, id: "ex-0002", code: "troponin", label: "Troponin", department: "Laboratory", status: "suggested", ai_suggested: rules("chest_pain") },
    { ...base, id: "ex-0003", code: "chest_xray", label: "Chest X-ray", department: "Imaging", status: "suggested", ai_suggested: rules("chest_pain") },
  ];
}
```

In `web/src/mocks/index.ts`:
- Add `exams: ExamOrder[]` to `MockStore`.
- In `createStore()`, set `exams: examFixtures(WAITLIST[0].id, WAITLIST[0].patient_id, WAITLIST[0].patient_name ?? "")`, using the first waitlist fixture.
- Re-export `EXAM_CATALOGUE`.

- [ ] **Step 3: api.ts.** Add an `upload` transport next to `http` (no JSON content type; the browser sets the multipart boundary):

```ts
async function upload<T>(path: string, form: FormData): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: form });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string; code?: string };
    throw new ApiError(res.status, err.code ?? "http_error", err.detail ?? res.statusText);
  }
  return (await res.json()) as T;
}
```

Then add, after `acceptOffer`:

```ts
// ── Exams (api.md 1.8 proposal) ─────────────────────────────────────────────

const counted = (s: MockStore, a: Appointment): Appointment => {
  const rows = s.exams.filter((e) => e.appointment_id === a.id);
  const n = (st: string) => rows.filter((e) => e.status === st).length;
  return { ...a, exams_total: n("ordered") + n("done"), exams_done: n("done"), exams_suggested: n("suggested") };
};

export async function getAppointmentExams(appointmentId: string): Promise<ExamOrder[]> {
  if (USE_MOCKS) return mock((s) => s.exams.filter((e) => e.appointment_id === appointmentId));
  return http<ExamOrder[]>("GET", `/appointments/${encodeURIComponent(appointmentId)}/exams`);
}

export async function getPatientExams(patientId: string): Promise<ExamOrder[]> {
  if (USE_MOCKS) return mock((s) => s.exams.filter((e) => e.patient_id === patientId && e.status !== "cancelled"));
  return http<ExamOrder[]>("GET", `/patients/${encodeURIComponent(patientId)}/exams`);
}

export async function getExamWorklist(): Promise<ExamOrder[]> {
  if (USE_MOCKS) return mock((s) => s.exams.filter((e) => e.status === "ordered"));
  return http<ExamOrder[]>("GET", "/exams?status=ordered");
}

export async function getExamCatalogue(): Promise<CatalogueItem[]> {
  if (USE_MOCKS) return mock(() => EXAM_CATALOGUE);
  return http<CatalogueItem[]>("GET", "/exams/catalogue");
}

export async function orderExams(appointmentId: string, examIds: string[], opts: ActorOpts = {}): Promise<ExamOrder[]> {
  if (USE_MOCKS)
    return mock((s) => {
      const rows = s.exams.filter((e) => e.appointment_id === appointmentId);
      const at = iso(now());
      for (const e of rows) {
        if (examIds.includes(e.id) && e.status === "suggested") Object.assign(e, { status: "ordered", human_confirmed_by: opts.by ?? "u-0001", ordered_at: at });
        else if (e.status === "suggested") e.status = "cancelled";
      }
      return rows;
    });
  return http<ExamOrder[]>("POST", `/appointments/${encodeURIComponent(appointmentId)}/exams/order`, { exam_ids: examIds });
}

export async function addExam(req: { patient_id: string; appointment_id?: string; code: string }, opts: ActorOpts = {}): Promise<ExamOrder> {
  if (USE_MOCKS)
    return mock((s) => {
      const item = EXAM_CATALOGUE.find((c) => c.code === req.code) ?? notFound(`Exam ${req.code}`);
      const row: ExamOrder = { id: `ex-${String(s.exams.length + 1).padStart(4, "0")}`, patient_id: req.patient_id,
        appointment_id: req.appointment_id ?? null, ...item, status: "ordered", ai_suggested: null,
        human_confirmed_by: opts.by ?? "u-0001", ordered_at: iso(now()), done_at: null, created_at: iso(now()),
        patient_name: null, results: [] };
      s.exams.push(row);
      return row;
    });
  return http<ExamOrder>("POST", "/exams", req);
}

export async function uploadExamResult(examId: string, file: File, reportText: string, opts: ActorOpts = {}): Promise<ExamOrder> {
  if (USE_MOCKS)
    return mock((s) => {
      const e = s.exams.find((x) => x.id === examId) ?? notFound(`Exam ${examId}`);
      if (e.status !== "ordered") throw new ApiError(409, "bad_status", `exam is ${e.status}`);
      e.status = "done";
      e.done_at = iso(now());
      e.results = [...(e.results ?? []), { id: `er-${examId.slice(3)}`, file_name: file.name, content_type: file.type,
        size_bytes: file.size, report_text: reportText, uploaded_by_name: userName(opts.by ?? "u-0006"), created_at: iso(now()) }];
      return e;
    });
  const form = new FormData();
  form.append("file", file);
  form.append("report_text", reportText);
  return upload<ExamOrder>(`/exams/${encodeURIComponent(examId)}/results`, form);
}

/** Authenticated download → an object URL for a new tab. Revoke it when done. */
export async function examFileUrl(resultId: string): Promise<string> {
  if (USE_MOCKS) return "/mock-exam.pdf";
  const token = getToken();
  const res = await fetch(`${BASE}/exam-results/${encodeURIComponent(resultId)}/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, "http_error", res.statusText);
  return URL.createObjectURL(await res.blob());
}
```

- Wrap the mock branches of `getWaitlist` and `getMyAppointments` with `.map((a) => counted(s, a))`, so mock appointments carry the counts.
- Import `CatalogueItem` and `ExamOrder` from `./types`, and `EXAM_CATALOGUE` from `@/mocks`.
- If `userName` doesn't know `u-0006`, add `{ id: "u-0006", name: "Nurse Rania" }` to the mock `USERS`.
- Add a small `web/public/mock-exam.pdf`. Create it with `printf '%%PDF-1.4\n%% mock exam result (synthetic)\n' > web/public/mock-exam.pdf`.

- [ ] **Step 4: Run the checks**

Run: `cd web && npm run typecheck && npm run build`
Expected: both succeed.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/types.ts web/src/lib/api.ts web/src/mocks/exams.ts web/src/mocks/index.ts web/public/mock-exam.pdf
git commit -m "feat(web): typed exam API with mocks"
```

---

### Task 10: Doctor requests: review and order the suggested exams

**Files:**
- Create: `web/src/components/doctor/ExamSuggestions.tsx` and `ExamSuggestions.module.css`
- Modify: `web/src/components/Waitlist.tsx` (render `ExamSuggestions` under each row's referral, doctor screen only)

**Interfaces:**
- Consumes: `getAppointmentExams`, `orderExams`, `getExamCatalogue`, `addExam` (Task 9).
- Produces: `<ExamSuggestions appointmentId patientId actorId onChanged?>`.

- [ ] **Step 1: Write the component**

```tsx
"use client";

// Suggested exams for one request: the doctor ticks what to keep and orders them before the visit.
// The suggestions come from rules; nothing is ordered until a doctor clicks "Order selected".
import { useEffect, useState } from "react";
import { addExam, getAppointmentExams, getExamCatalogue, orderExams } from "@/lib/api";
import type { CatalogueItem, ExamOrder } from "@/lib/types";
import styles from "./ExamSuggestions.module.css";

export interface ExamSuggestionsProps {
  appointmentId: string;
  patientId: string;
  actorId: string;
  onChanged?: (rows: ExamOrder[]) => void;
}

export function ExamSuggestions({ appointmentId, patientId, actorId, onChanged }: ExamSuggestionsProps) {
  const [rows, setRows] = useState<ExamOrder[] | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [catalogue, setCatalogue] = useState<CatalogueItem[]>([]);
  const [extra, setExtra] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getAppointmentExams(appointmentId)
      .then((r) => {
        if (!alive) return;
        setRows(r);
        setPicked(new Set(r.filter((e) => e.status === "suggested").map((e) => e.id)));
      })
      .catch(() => alive && setError("Couldn’t load the suggested exams."));
    getExamCatalogue().then((c) => alive && setCatalogue(c)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [appointmentId]);

  if (error && !rows) return <p className={styles.error}>{error}</p>;
  if (!rows) return <span className="ward-skeleton" style={{ height: 18, width: 220 }} />;
  const suggested = rows.filter((e) => e.status === "suggested");
  const active = rows.filter((e) => e.status === "ordered" || e.status === "done");

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const next = await orderExams(appointmentId, [...picked], { by: actorId });
      setRows(next);
      onChanged?.(next);
    } catch {
      setError("Couldn’t order the exams. Nothing was changed — try again.");
    } finally {
      setBusy(false);
    }
  }

  async function addOne() {
    if (!extra) return;
    setBusy(true);
    try {
      const row = await addExam({ patient_id: patientId, appointment_id: appointmentId, code: extra }, { by: actorId });
      const next = [...rows!, row];
      setRows(next);
      setExtra("");
      onChanged?.(next);
    } catch {
      setError("Couldn’t add that exam.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.box}>
      {suggested.length ? (
        <>
          <span className={styles.title}>Suggested exams before the visit · rules, needs your review</span>
          {suggested.map((e) => (
            <label key={e.id} className={styles.item}>
              <input
                type="checkbox"
                checked={picked.has(e.id)}
                onChange={() => setPicked((s) => { const n = new Set(s); if (n.has(e.id)) n.delete(e.id); else n.add(e.id); return n; })}
              />
              {e.label} <span className={styles.dept}>{e.department}</span>
            </label>
          ))}
          <button className={styles.order} disabled={busy} onClick={() => void submit()}>
            {picked.size ? `Order selected (${picked.size})` : "Order none"}
          </button>
        </>
      ) : null}
      {active.length ? (
        <span className={styles.status}>
          Exams: {active.filter((e) => e.status === "done").length}/{active.length} results in ·{" "}
          {active.map((e) => e.label).join(", ")}
        </span>
      ) : null}
      {!suggested.length ? (
        <span className={styles.add}>
          <select value={extra} onChange={(ev) => setExtra(ev.target.value)} aria-label="Add an exam">
            <option value="">Add an exam…</option>
            {catalogue.map((c) => <option key={c.code} value={c.code}>{c.label} · {c.department}</option>)}
          </select>
          <button disabled={!extra || busy} onClick={() => void addOne()}>Add</button>
        </span>
      ) : null}
      {error ? <p className={styles.error} role="alert">{error}</p> : null}
    </div>
  );
}
```

`ExamSuggestions.module.css` uses only existing tokens:

```css
.box { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; padding: 10px 12px; border: 1px dashed var(--line); border-radius: 10px; background: var(--canvas); }
.title { font-size: 13px; font-weight: 600; color: var(--ink); }
.item { display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--text); }
.dept { font-size: 12px; color: var(--muted, #5b6b75); }
.order { align-self: flex-start; margin-top: 4px; padding: 6px 12px; border-radius: 8px; border: 0; background: var(--teal); color: #fff; font-weight: 600; cursor: pointer; }
.order:disabled { opacity: 0.6; cursor: default; }
.status { font-size: 13px; color: var(--ink); }
.add { display: flex; gap: 8px; font-size: 13px; }
.error { margin: 0; font-size: 13px; color: var(--warn-ink); }
```

- [ ] **Step 2: Mount it.** In `web/src/components/Waitlist.tsx`, inside the referral column (`styles.ref`) after the flags `div`, render it only on the doctor's screen. Waitlist already receives an `actor`/`actorId`; add a prop `showExams?: boolean`, passed `true` from `components/doctor/RequestsView.tsx`:

```tsx
{showExams ? <ExamSuggestions appointmentId={a.id} patientId={a.patient_id} actorId={actorId ?? "u-0001"} /> : null}
```

Use the id prop name Waitlist already has; check its props interface at the top of the file.

- [ ] **Step 3: Check in the browser (mock mode)**

Run: `cd web && npm run typecheck && npm run build`, then `npm run dev`. Open `http://localhost:3000/doctor/requests`.
Expected:
- The first request shows three ticked suggestions.
- Untick one, then "Order selected (2)": the box switches to "Exams: 0/2 results in · ECG (12-lead), Chest X-ray".

- [ ] **Step 4: Commit**

```bash
git add web/src/components/doctor/ExamSuggestions.tsx web/src/components/doctor/ExamSuggestions.module.css web/src/components/Waitlist.tsx web/src/components/doctor/RequestsView.tsx
git commit -m "feat(web): doctor reviews and orders suggested exams on requests"
```

---

### Task 11: Doctor patient page: exams and results panel

**Files:**
- Create: `web/src/components/shared/ExamsPanel.tsx` and `ExamsPanel.module.css`
- Modify: `web/src/components/doctor/PatientDetail.tsx` (right column, above `DailySummary`)

**Interfaces:**
- Consumes: `getPatientExams`, `examFileUrl` (Task 9).
- Produces: `<ExamsPanel patientId />`, reused by the nurse patient page later.

- [ ] **Step 1: Write the component**

```tsx
"use client";

// Exams for one patient: ordered and done, with the uploaded files and report lines. A person reads the
// results; Medora only stores and shows them.
import { useEffect, useState } from "react";
import { examFileUrl, getPatientExams } from "@/lib/api";
import { tunisDay, tunisTime } from "@/lib/time";
import type { ExamOrder } from "@/lib/types";
import styles from "./ExamsPanel.module.css";

export function ExamsPanel({ patientId }: { patientId: string }) {
  const [rows, setRows] = useState<ExamOrder[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    getPatientExams(patientId).then((r) => alive && setRows(r)).catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [patientId]);

  async function open(resultId: string) {
    const w = window.open("", "_blank");
    try {
      const url = await examFileUrl(resultId);
      if (w) w.location.href = url;
    } catch {
      w?.close();
      setFailed(true);
    }
  }

  const shown = (rows ?? []).filter((e) => e.status === "ordered" || e.status === "done");
  return (
    <section className={styles.card} aria-label="Exams">
      <h3 className={styles.h3}>Exams</h3>
      {failed ? <p className={styles.note}>Couldn’t load the exams.</p> : null}
      {!rows && !failed ? <span className="ward-skeleton" style={{ height: 60, width: "100%" }} /> : null}
      {rows && !shown.length ? <p className={styles.note}>No exams ordered.</p> : null}
      {shown.map((e) => (
        <div key={e.id} className={styles.row}>
          <div className={styles.line}>
            <b>{e.label}</b>
            <span className={styles.dept}>{e.department}</span>
            <span className={e.status === "done" ? styles.done : styles.waiting}>
              {e.status === "done" ? `Result in · ${tunisDay(e.done_at!)} ${tunisTime(e.done_at!)}` : "Waiting for the result"}
            </span>
          </div>
          {(e.results ?? []).map((r) => (
            <div key={r.id} className={styles.result}>
              <button className={styles.file} onClick={() => void open(r.id)}>{r.file_name}</button>
              {r.report_text ? <span>“{r.report_text}”</span> : null}
              {r.uploaded_by_name ? <span className={styles.dept}>· {r.uploaded_by_name}</span> : null}
            </div>
          ))}
        </div>
      ))}
    </section>
  );
}
```

`ExamsPanel.module.css`:

```css
.card { background: var(--paper); border: 1px solid var(--line); border-radius: 14px; padding: 22px; display: flex; flex-direction: column; gap: 12px; }
.h3 { margin: 0; font: 600 22px/1.2 var(--serif); color: var(--ink); }
.note { margin: 0; font-size: 14px; color: var(--text); }
.row { display: flex; flex-direction: column; gap: 4px; padding-bottom: 10px; border-bottom: 1px solid var(--line); }
.row:last-child { border-bottom: 0; padding-bottom: 0; }
.line { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; font-size: 15px; color: var(--ink); }
.dept { font-size: 13px; color: var(--muted, #5b6b75); }
.done { font-size: 13px; color: var(--teal); font-weight: 600; }
.waiting { font-size: 13px; color: var(--warn-ink); }
.result { display: flex; flex-wrap: wrap; gap: 8px; font-size: 14px; color: var(--text); }
.file { border: 0; background: none; padding: 0; color: var(--teal); text-decoration: underline; cursor: pointer; font: inherit; }
```

If `tunisDay` is not exported from `@/lib/time`, use the date formatter the Waitlist uses (`grep -n "export function tunis" web/src/lib/time.ts`).

- [ ] **Step 2: Mount it.** In `PatientDetail.tsx`, import `ExamsPanel` from `@/components/shared/ExamsPanel` and render `<ExamsPanel patientId={id} />` as the first child of the second `styles.col`.

- [ ] **Step 3: Checks**

Run: `cd web && npm run typecheck && npm run build`
Then in mock mode:
- Order exams on `/doctor/requests` (Task 10).
- Open the patient of the first request at `/doctor/patients/<that patient id>`.

Expected: the panel shows "Waiting for the result" rows.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/shared/ExamsPanel.tsx web/src/components/shared/ExamsPanel.module.css web/src/components/doctor/PatientDetail.tsx
git commit -m "feat(web): exams and results panel on the doctor's patient page"
```

---

### Task 12: Nurse exams worklist with upload

**Files:**
- Create: `web/src/components/nurse/ExamWorklist.tsx` and `ExamWorklist.module.css`
- Create: `web/src/app/nurse/exams/page.tsx`
- Modify: `web/src/components/Sidebar.tsx` (nurse nav item "Exams" → `/nurse/exams`, no count pill)

**Interfaces:**
- Consumes: `getExamWorklist`, `uploadExamResult` (Task 9); `useMe` from `@/lib/useMe`; `Toast`/`useToast` from `@/components/Toast`.

- [ ] **Step 1: Write the component**

```tsx
"use client";

// Department worklist: exams ordered for this department, waiting for a result. The nurse attaches the file
// (PDF, JPEG or PNG, at most 15 MB) and a short report line; the ordering doctor then sees it.
import { useCallback, useEffect, useState } from "react";
import { Toast, useToast } from "@/components/Toast";
import { getExamWorklist, uploadExamResult } from "@/lib/api";
import { tunisTime } from "@/lib/time";
import type { ExamOrder } from "@/lib/types";
import styles from "./ExamWorklist.module.css";

const MAX = 15 * 1024 * 1024;
const TYPES = ["application/pdf", "image/jpeg", "image/png"];

function Row({ exam, onDone }: { exam: ExamOrder; onDone: (id: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    if (!file) return;
    if (!TYPES.includes(file.type) || file.size > MAX) {
      setError("Use a PDF, JPEG or PNG of at most 15 MB.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await uploadExamResult(exam.id, file, report.trim());
      onDone(exam.id);
    } catch {
      setError("Upload failed. The file was not saved — try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.row}>
      <div className={styles.who}>
        <b dir="auto">{exam.patient_name}</b>
        <span>{exam.label}</span>
        <span className={styles.meta}>ordered {exam.ordered_at ? tunisTime(exam.ordered_at) : "—"}</span>
      </div>
      <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files?.[0] ?? null)} aria-label={`Result file for ${exam.label}`} />
      <input className={styles.report} placeholder="Short report (optional)" value={report} maxLength={2000} onChange={(e) => setReport(e.target.value)} />
      <button className={styles.send} disabled={!file || busy} onClick={() => void send()}>{busy ? "Uploading…" : "Upload result"}</button>
      {error ? <p className={styles.error} role="alert">{error}</p> : null}
    </div>
  );
}

export function ExamWorklist() {
  const [rows, setRows] = useState<ExamOrder[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [toast, showToast] = useToast<string>();

  const load = useCallback(() => {
    setFailed(false);
    getExamWorklist().then(setRows).catch(() => setFailed(true));
  }, []);
  useEffect(load, [load]);

  return (
    <div className={styles.page}>
      <h1 className={styles.h1}>Exams to complete</h1>
      <p className={styles.sub}>Ordered for your department · the doctor sees the result as soon as you upload it</p>
      {failed ? <p className={styles.error}>Couldn’t load the worklist. <button onClick={load}>Retry</button></p> : null}
      {!rows && !failed ? <span className="ward-skeleton" style={{ height: 80, width: "100%" }} /> : null}
      {rows && !rows.length ? <p className={styles.sub}>Nothing waiting.</p> : null}
      {rows?.map((e) => (
        <Row key={e.id} exam={e} onDone={(id) => { setRows((r) => r?.filter((x) => x.id !== id) ?? r); showToast("Result uploaded. The doctor can see it now."); }} />
      ))}
      {toast ? <Toast>{toast}</Toast> : null}
    </div>
  );
}
```

`ExamWorklist.module.css`:

```css
.page { padding: 32px 40px; display: flex; flex-direction: column; gap: 14px; }
.h1 { margin: 0; font: 600 30px/1.2 var(--serif); color: var(--ink); }
.sub { margin: 0; font-size: 15px; color: var(--text); }
.row { display: grid; grid-template-columns: 1.4fr 1fr 1.4fr auto; gap: 12px; align-items: center; background: var(--paper); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; }
.who { display: flex; flex-direction: column; gap: 2px; font-size: 14px; color: var(--ink); }
.meta { font-size: 12px; color: var(--muted, #5b6b75); }
.report { padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; font: inherit; }
.send { padding: 8px 14px; border: 0; border-radius: 8px; background: var(--teal); color: #fff; font-weight: 600; cursor: pointer; }
.send:disabled { opacity: 0.6; cursor: default; }
.error { grid-column: 1 / -1; margin: 0; font-size: 13px; color: var(--warn-ink); }
@media (max-width: 1100px) { .row { grid-template-columns: 1fr; } }
```

If `Toast`'s props differ (for example a `tone` prop is required), match the usage in `PatientDetail.tsx`.

- [ ] **Step 2: Page and nav.** Create `web/src/app/nurse/exams/page.tsx`:

```tsx
import { Suspense } from "react";
import { ExamWorklist } from "@/components/nurse/ExamWorklist";

export const metadata = { title: "Exams · Medora" };

export default function NurseExamsPage() {
  return (
    <Suspense fallback={null}>
      <ExamWorklist />
    </Suspense>
  );
}
```

In `Sidebar.tsx`, add `{ key: "exams", label: "Exams", href: "/nurse/exams" }` to the nurse nav after `meds`. Make `count` optional in that item type if it isn't already, and render no pill when it's undefined.

- [ ] **Step 3: Checks**

Run: `cd web && npm run typecheck && npm run build`
Then in mock mode:
- Order exams as the doctor.
- Open `/nurse/exams` and upload any small PDF.

Expected: the row disappears and the toast shows; the doctor's ExamsPanel shows "Result in".

- [ ] **Step 4: Commit**

```bash
git add web/src/components/nurse/ExamWorklist.tsx web/src/components/nurse/ExamWorklist.module.css web/src/app/nurse/exams/page.tsx web/src/components/Sidebar.tsx
git commit -m "feat(web): department exams worklist with result upload"
```

---

### Task 13: Patient "Before your visit" card and admin waitlist chip

**Files:**
- Modify: `web/src/components/patient/Home.tsx` (card under the medicines card)
- Modify: `web/src/components/Waitlist.tsx` (chip in the urgency column)

**Interfaces:**
- Consumes: `getPatientExams` (Task 9); `Appointment.exams_total/exams_done/exams_suggested`.

- [ ] **Step 1: Patient card.** In `Home.tsx`, load `getPatientExams(patientId).catch(() => [])` next to the other optional calls. Use the same `.catch(() => …)` "optional call" pattern the file already uses for appointments. When at least one row exists, render, under the medicines card and with the same card class:

```tsx
<section className={styles.card} aria-label="Before your visit">
  <h2 className={styles.cardTitle}>Before your visit</h2>
  {exams.map((e) => (
    <div key={e.id} className={styles.medRow}>
      <span>{e.label}</span>
      <span className={styles.sub}>{e.department}</span>
      <span className={styles.pill}>{e.status === "done" ? "Done" : "To do"}</span>
    </div>
  ))}
  <p className={styles.sub}>Do these before your appointment so the doctor can decide in one visit.</p>
</section>
```

Reuse the class names Home's medicines card already uses (`grep -n "className={styles" web/src/components/patient/Home.tsx`); don't invent new ones unless a needed one is missing, in which case add it to `Patient.module.css`.

- [ ] **Step 2: Admin chip.** In `Waitlist.tsx`'s urgency column, after the scale label from Task 8:

```tsx
{a.exams_total ? (
  <span className={styles.meta}>Exams {a.exams_done ?? 0}/{a.exams_total}{a.exams_done === a.exams_total ? " · results in" : ""}</span>
) : a.exams_suggested ? (
  <span className={styles.meta}>{a.exams_suggested} exams suggested · doctor to review</span>
) : null}
```

- [ ] **Step 3: Checks**

Run: `cd web && npm run typecheck && npm run build`
Expected:
- In mock mode, `/admin/waitlist` shows "3 exams suggested · doctor to review" on the first row.
- After the doctor orders, it shows "Exams 0/2".

- [ ] **Step 4: Commit**

```bash
git add web/src/components/patient/Home.tsx web/src/components/patient/Patient.module.css web/src/components/Waitlist.tsx
git commit -m "feat(web): patient exam checklist and waitlist exam progress"
```

---

### Task 14: Real-stack check and PR

**Files:**
- Modify: `plans/FAOUZI.md` (add a "Single-visit exams" checklist with the items of this plan, ticked)

- [ ] **Step 1: Rebuild the API on the real stack**

```bash
docker compose -p ward -f infra/docker-compose.yml --env-file .env up -d --build api minio
curl -s localhost:8000/health
```

Expected: `{"status":"ok","db":true,"mqtt":true}`. `alembic upgrade head` runs in the api command, so the 0003 tables exist. If the seed already ran before Task 3, add the two nurses by running `docker exec ward-api-1 python -c "from app.seed import ..."` or by re-seeding a fresh DB volume. Say which in the PR.

- [ ] **Step 2: Walk the golden path in real mode** (web on :3000 with `NEXT_PUBLIC_USE_MOCKS=0`)

1. As `patient@medora.tn`, request: "douleur thoracique depuis ce matin".
2. As `doctor@medora.tn`, open `/doctor/requests`: three suggestions → order ECG + chest X-ray.
3. As `imaging@medora.tn`, open `/nurse/exams` → upload a PDF for the chest X-ray. As `nurse@medora.tn` (Cardiology), do the same for the ECG.
4. As the doctor, open the patient page: both results are listed and open in a new tab.
5. As the admin, open `/admin/waitlist`: "Exams 2/2 · results in".
6. As the patient, Home shows "Before your visit" with both rows "Done".

Expected: no 4xx in the browser console except the known ones (`/ai/*` if not built, the admin `/alerts` 403).

- [ ] **Step 3: Full checks**

Run: `cd backend && python -m pytest -q && python -m ruff check .` → all pass
Run: `cd web && npm run typecheck && npm run build` → both succeed

- [ ] **Step 4: Commit the checklist, push, open the PR** (body: what, Wali items (models, migration, seed, compose, main.py, data-model 1.4), contract bumps needing 👍, verification; no emojis, no attribution lines)

```bash
git add plans/FAOUZI.md
git commit -m "docs: single-visit exams checklist"
git push -u origin faouzi/single-visit-exams
gh pr create --base main --title "feat: single-visit exam pathway" --body-file <scratchpad>/pr-body.md
```
