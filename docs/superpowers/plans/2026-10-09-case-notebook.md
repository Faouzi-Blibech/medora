# Case notebook: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The doctor asks questions about one patient and gets answers built only from that patient's record, with every claim cited and the answer stored for review. It works with no LLM.

**Architecture:**
- **`app/ai/notebook.py`** (pure, no DB) splits sources into passages, ranks them with BM25 over the triage text normaliser, and returns either the passages (no LLM) or a short LLM answer allowed to cite only those passages.
- **`app/services/notebook.py`** builds the sources from the DB.
- **Routes** in `app/routers/ai.py` check access, audit, store a `notebook_entries` row and serve history and review.
- **Web:** a `NotebookPanel` on the doctor's patient page.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, pytest, pure-Python BM25, the existing `app/ai/llm.py` gateway (`LLM_PROVIDER=none|groq|local`), Next.js 16 + React 19 + CSS Modules.

**Spec:** `docs/superpowers/specs/2026-10-09-single-visit-and-case-notebook-design.md` (§5)

**Prerequisites:**
- `backend/app/routers/ai.py` exists on `main` (the `/ai/triage`, `/ai/summary`, `/ai/assistant` PR).
- Plan A Task 2 is merged: the `NotebookEntry` model and the `notebook_entries` table, plus `ExamOrder`/`ExamResult`.

Branch: `faouzi/case-notebook` from `main`.

## Global Constraints

- **Answers come only from the patient's own sources.**
  - The LLM receives only the numbered top passages and must cite at least one.
  - An answer citing nothing, or citing an unknown number, is discarded and the passages are returned instead (`source: "rules"`).
- **Fixed answer strings** (exact):
  - no LLM: `"These passages from the record match your question. Read them before deciding."`
  - no match: `"Nothing in this record matches the question."`
- **Retrieval limits:** `TOP_K = 4` passages and `MAX_PASSAGE = 400` characters; passages are split on sentence ends (`.`, `!`, `?`, `؟`) and newlines.
- **LLM calls go through `app.ai.llm.complete_json("notebook", ...)`** with `names=[first_name, last_name]` so names are stripped. The prompt lives in `app/ai/prompts/notebook.v1.md`.
- **Every answer is stored** as `notebook_entries.ai_suggested = {"answer","citations","source"}`, with `human_confirmed_by` null until the doctor marks it reviewed.
- **Access:** doctor only, through `check_patient_access` (own patients; writes `audit_log` with resource `notebook`). A nurse, admin or patient gets 403.
- **Question length:** 3–500 characters; otherwise 422.
- **UI copy:**
  - Always "AI suggestion · needs review" until reviewed.
  - Never "diagnosis".
  - The panel says "Answers use only this patient's record".
- Commits: Conventional Commits, no Co-Authored-By, no "Generated with". Backend tests with `DATABASE_URL`/`TEST_DATABASE_URL` set (see Plan A). Web: `npm run typecheck && npm run build`.

## Review Focus

- **A question in Arabic or with French accents.** It must still match a note in the other spelling ("fièvre" vs "fievre"). Tested in Task 1 (`test_rank_folds_accents_and_arabic`).
- **A patient with no notes, results or vitals.** Expect the no-match answer, no citations, no crash. Tested in Task 1 (`test_no_sources`) and Task 3 (`test_ask_with_empty_record`).
- **An LLM that invents a citation number or cites nothing.** Expect the passages fallback, `source: "rules"`. Tested in Task 2 (`test_llm_bad_citations_fall_back`).
- **A doctor asking about a patient they don't attend.** Expect 403, with no entry stored. Tested in Task 3 (`test_notebook_access`).
- **A very long note (several thousand characters).** It must split into passages of at most about 400 characters, so citations stay readable. Tested in Task 1 (`test_passages_split_long_text`).

---

### Task 1: Passages and BM25 retrieval

**Files:**
- Create: `backend/app/ai/notebook.py` (retrieval part)
- Test: `backend/tests/test_notebook.py`

**Interfaces:**
- Consumes: `app.ai.triage._normalize(text) -> str`.
- Produces:
  - `Source(id: str, kind: str, title: str, ts: str | None, text: str)`, a frozen dataclass.
  - `Passage(source: Source, text: str)`.
  - `passages(sources: list[Source]) -> list[Passage]` and `tokens(text: str) -> list[str]`.
  - `rank(question: str, ps: list[Passage], k: int = TOP_K) -> list[Passage]`.
  - Constants `TOP_K`, `MAX_PASSAGE`, `NO_LLM_ANSWER`, `NO_MATCH_ANSWER`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_notebook.py
from app.ai import notebook as N

NOTE = N.Source("note:n-0001", "note", "Note by Nurse Ines · 08 Oct 21:40", "2026-10-08T20:40:00Z",
                "Patient slept well. Troponin sample sent at 21:00. Fièvre à 38.2 la nuit.")
EXAM = N.Source("exam:er-0001", "exam_report", "Chest X-ray · 09 Oct", "2026-10-09T08:00:00Z",
                "Chest X-ray: no consolidation, heart size normal.")
RX = N.Source("rx:rx-0001", "prescription", "Prescription · 07 Oct", None,
              "Amlodipine 5mg at 08:00 for 5 days. Monitor blood pressure twice a day.")
AR = N.Source("note:n-0002", "note", "Note · 09 Oct", None, "المريضة تشكو من حمى خفيفة منذ الصباح.")


def test_passages_split_long_text():
    long = N.Source("note:x", "note", "t", None, " ".join(f"Sentence number {i} is here." for i in range(300)))
    ps = N.passages([long])
    assert len(ps) > 5 and all(len(p.text) <= N.MAX_PASSAGE for p in ps)
    assert all(p.source.id == "note:x" for p in ps)


def test_rank_finds_the_right_source():
    top = N.rank("what did the chest x-ray show?", N.passages([NOTE, EXAM, RX]))
    assert top[0].source.id == "exam:er-0001"
    assert N.rank("troponin", N.passages([NOTE, EXAM, RX]))[0].source.id == "note:n-0001"


def test_rank_folds_accents_and_arabic():
    assert N.rank("fievre", N.passages([NOTE, EXAM]))[0].source.id == "note:n-0001"
    assert N.rank("حمى", N.passages([NOTE, AR]))[0].source.id == "note:n-0002"


def test_rank_drops_zero_scores_and_caps():
    assert N.rank("dialysis schedule", N.passages([NOTE, EXAM, RX])) == []
    many = [N.Source(f"note:{i}", "note", "t", None, f"Troponin value {i}.") for i in range(10)]
    assert len(N.rank("troponin", N.passages(many))) == N.TOP_K


def test_no_sources():
    assert N.rank("anything", []) == []
    assert N.rank("", N.passages([NOTE])) == []
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd backend && python -m pytest tests/test_notebook.py -v`
Expected: FAIL with `ImportError: cannot import name 'notebook' from 'app.ai'`

- [ ] **Step 3: Implement**

```python
# backend/app/ai/notebook.py
"""Case notebook (owner: Faouzi): questions about one patient, answered only from that patient's record, every
claim cited. No LLM: the best-matching passages (BM25). With LLM_PROVIDER set: a short answer that may cite only
those passages; anything else falls back to the passages. Spec 2026-10-09 §5."""

import math
import re
from dataclasses import dataclass

from app.ai.triage import _normalize

TOP_K = 4
MAX_PASSAGE = 400
NO_LLM_ANSWER = "These passages from the record match your question. Read them before deciding."
NO_MATCH_ANSWER = "Nothing in this record matches the question."

_SENTENCE = re.compile(r"(?<=[.!?؟])\s+|\n+")
_TOKEN = re.compile(r"\w+", re.UNICODE)
_STOP = {"the", "and", "what", "did", "was", "is", "are", "of", "to", "in", "on", "for", "with", "show",
         "le", "la", "les", "de", "des", "du", "et", "est", "en", "un", "une", "a", "il", "elle", "que", "qui"}


@dataclass(frozen=True)
class Source:
    id: str
    kind: str  # referral | note | exam_report | prescription | vitals
    title: str
    ts: str | None
    text: str


@dataclass(frozen=True)
class Passage:
    source: Source
    text: str


def _chunks(text: str) -> list[str]:
    out, buf = [], ""
    for sent in (s.strip() for s in _SENTENCE.split(text or "")):
        while len(sent) > MAX_PASSAGE:  # one huge sentence: hard split
            out.append(sent[:MAX_PASSAGE])
            sent = sent[MAX_PASSAGE:]
        if not sent:
            continue
        if buf and len(buf) + 1 + len(sent) > MAX_PASSAGE:
            out.append(buf)
            buf = sent
        else:
            buf = f"{buf} {sent}".strip()
    return out + [buf] if buf else out


def passages(sources: list[Source]) -> list[Passage]:
    return [Passage(s, c) for s in sources for c in _chunks(s.text)]


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(_normalize(text)) if len(t) > 1 and t not in _STOP]


def rank(question: str, ps: list[Passage], k: int = TOP_K, k1: float = 1.5, b: float = 0.75) -> list[Passage]:
    q = set(tokens(question))
    if not q or not ps:
        return []
    docs = [tokens(p.text) for p in ps]
    n, avg = len(docs), (sum(map(len, docs)) / len(docs)) or 1.0
    df = {t: sum(1 for d in docs if t in d) for t in q}
    scored = []
    for i, d in enumerate(docs):
        score = 0.0
        for t in q:
            f = d.count(t)
            if f:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(d) / avg))
        if score > 0:
            scored.append((score, i))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [ps[i] for _, i in scored[:k]]
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && python -m pytest tests/test_notebook.py -v`
Expected: PASS. If the Arabic test fails, compare `tokens("حمى")` with `tokens(AR.text)`: `_normalize` maps `ى`→`ي`, so both sides must go through it. Never special-case the test.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/notebook.py backend/tests/test_notebook.py
git commit -m "feat(ai): case notebook passages and BM25 retrieval"
```

---

### Task 2: Cited answer, with the LLM as an optional extra

**Files:**
- Modify: `backend/app/ai/notebook.py` (add `answer()`)
- Create: `backend/app/ai/prompts/notebook.v1.md`
- Test: `backend/tests/test_notebook.py` (append)

**Interfaces:**
- Consumes: `app.ai.llm.complete_json(prompt_name, user_text, schema, *, names)` and `LLMUnavailable`.
- Produces: `answer(question: str, sources: list[Source], *, names: list[str] = ()) -> dict`, returning `{"answer": str, "citations": [{"n","source_id","kind","title","snippet"}], "source": "rules"|"llm"}`.

- [ ] **Step 1: Write the failing tests** (append)

```python
from app.ai.llm import LLMUnavailable


def test_answer_without_llm_returns_cited_passages():
    out = N.answer("troponin", [NOTE, EXAM, RX])
    assert out["source"] == "rules" and out["answer"] == N.NO_LLM_ANSWER
    assert out["citations"][0] == {"n": 1, "source_id": "note:n-0001", "kind": "note",
                                   "title": "Note by Nurse Ines · 08 Oct 21:40",
                                   "snippet": out["citations"][0]["snippet"]}
    assert "Troponin" in out["citations"][0]["snippet"]


def test_answer_no_match():
    assert N.answer("dialysis", [NOTE]) == {"answer": N.NO_MATCH_ANSWER, "citations": [], "source": "rules"}


def test_llm_answer_keeps_only_cited(monkeypatch):
    seen = {}

    def fake(prompt, text, schema, *, names=()):
        seen.update(prompt=prompt, text=text, names=list(names))
        return schema(answer="The X-ray showed no consolidation [2].", cited=[2])

    monkeypatch.setattr(N, "complete_json", fake)
    out = N.answer("chest x-ray troponin", [NOTE, EXAM], names=["Amira", "Ben Salah"])
    assert out["source"] == "llm" and out["answer"].startswith("The X-ray")
    assert [c["n"] for c in out["citations"]] == [2]
    assert seen["prompt"] == "notebook" and "[1]" in seen["text"] and "[2]" in seen["text"]
    assert seen["names"] == ["Amira", "Ben Salah"]


def test_llm_bad_citations_fall_back(monkeypatch):
    for cited in ([], [9], [0]):
        monkeypatch.setattr(N, "complete_json", lambda p, t, schema, *, names=(), c=cited: schema(answer="x", cited=c))
        out = N.answer("troponin", [NOTE, EXAM])
        assert out["source"] == "rules" and out["answer"] == N.NO_LLM_ANSWER


def test_llm_unavailable_falls_back(monkeypatch):
    def down(*a, **k):
        raise LLMUnavailable("offline")

    monkeypatch.setattr(N, "complete_json", down)
    assert N.answer("troponin", [NOTE])["source"] == "rules"
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd backend && python -m pytest tests/test_notebook.py -v`
Expected: the new tests FAIL with `AttributeError: module 'app.ai.notebook' has no attribute 'answer'`

- [ ] **Step 3: Implement.** Add to the imports of `notebook.py`:

```python
from pydantic import BaseModel

from app.ai.llm import LLMUnavailable, complete_json
```

Append:

```python
class _LlmAnswer(BaseModel):
    answer: str
    cited: list[int]


def _citation(n: int, p: Passage) -> dict:
    return {"n": n, "source_id": p.source.id, "kind": p.source.kind, "title": p.source.title, "snippet": p.text}


def answer(question: str, sources: list[Source], *, names: list[str] = ()) -> dict:
    top = rank(question, passages(sources))
    if not top:
        return {"answer": NO_MATCH_ANSWER, "citations": [], "source": "rules"}
    cites = [_citation(i + 1, p) for i, p in enumerate(top)]
    fallback = {"answer": NO_LLM_ANSWER, "citations": cites, "source": "rules"}
    numbered = "\n".join(f"[{c['n']}] ({c['title']}) {c['snippet']}" for c in cites)
    try:
        out = complete_json("notebook", f"Question: {question}\n\nPassages:\n{numbered}", _LlmAnswer, names=names)
    except LLMUnavailable:
        return fallback
    valid = set(range(1, len(cites) + 1))
    if not out.answer.strip() or not out.cited or not set(out.cited) <= valid:
        return fallback
    keep = set(out.cited)
    return {"answer": out.answer.strip(), "citations": [c for c in cites if c["n"] in keep], "source": "llm"}
```

Create `backend/app/ai/prompts/notebook.v1.md`:

```markdown
You answer a doctor's question about one hospitalised patient using ONLY the numbered passages given, which come
from that patient's record (notes, exam reports, prescriptions, vital-sign summary, referral). Names and
identifiers have been replaced by placeholders.

- Answer in at most 3 short sentences, in the language of the question.
- Every sentence must be supported by a passage; put its number in square brackets, e.g. [2].
- If the passages do not answer the question, say so plainly and cite the closest passage.
- Do NOT diagnose, prescribe or add any fact, number or drug that is not in the passages.

Answer with JSON: {"answer": "...", "cited": [passage numbers you used]}

The doctor reviews this answer before relying on it.
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && python -m pytest tests/test_notebook.py tests/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/notebook.py backend/app/ai/prompts/notebook.v1.md backend/tests/test_notebook.py
git commit -m "feat(ai): cited notebook answers with an optional LLM and a passages fallback"
```

---

### Task 3: Sources from the record, and the notebook routes

**Files:**
- Create: `backend/app/services/notebook.py`
- Modify: `backend/app/routers/ai.py` (four routes)
- Test: `backend/tests/test_notebook_api.py`

**Interfaces:**
- Consumes: Task 2 `answer`, `Source`. Models `Appointment`, `Note`, `ExamOrder`, `ExamResult`, `Prescription`, `Vital`, `NotebookEntry`, `User`. `copilot._stats_text(vitals: list[dict]) -> str`. `check_patient_access`, `require_roles`, `new_id`, `iso`.
- Produces:
  - `build_sources(db, patient) -> list[Source]`
  - `entry_out(db, entry) -> dict` with keys `id, patient_id, question, answer, source, citations, human_confirmed_by, created_at`
  - the routes `POST|GET /ai/notebook/{patient_id}`, `GET /ai/notebook/{patient_id}/sources`, `POST /ai/notebook/entries/{id}/review`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_notebook_api.py
from app.models import AuditLog, NotebookEntry
from tests.helpers import login


def test_ask_cites_a_note_and_stores_the_entry(client, db):
    doc = login(client, "doctor@medora.tn")
    client.post("/patients/p-0001/notes", headers=doc, json={"text": "Troponin came back normal this morning."})
    r = client.post("/ai/notebook/p-0001", headers=doc, json={"question": "What was the troponin result?"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source"] == "rules" and body["human_confirmed_by"] is None
    assert body["citations"][0]["kind"] == "note" and "Troponin" in body["citations"][0]["snippet"]
    assert db.get(NotebookEntry, body["id"]).ai_suggested["citations"] == body["citations"]
    assert db.query(AuditLog).filter_by(resource="notebook", patient_id="p-0001").count() >= 1


def test_sources_history_and_review(client):
    doc = login(client, "doctor@medora.tn")
    kinds = {s["kind"] for s in client.get("/ai/notebook/p-0001/sources", headers=doc).json()}
    assert {"vitals", "prescription"} <= kinds
    first = client.post("/ai/notebook/p-0001", headers=doc, json={"question": "blood pressure plan"}).json()
    second = client.post("/ai/notebook/p-0001", headers=doc, json={"question": "heart rate trend"}).json()
    hist = client.get("/ai/notebook/p-0001", headers=doc).json()
    assert [h["id"] for h in hist[:2]] == [second["id"], first["id"]]
    rev = client.post(f"/ai/notebook/entries/{first['id']}/review", headers=doc)
    assert rev.status_code == 200 and rev.json()["human_confirmed_by"] == "u-0001"


def test_ask_with_empty_record(client):
    admin = login(client, "admin@medora.tn")
    p = client.post("/appointments", headers=admin, json={"patient_id": "p-0002", "referral_text": "x"}).json()
    assert p["patient_id"] == "p-0002"
    doc = login(client, "doctor@medora.tn")
    r = client.post("/ai/notebook/p-0002", headers=doc, json={"question": "dialysis sessions"})
    assert r.status_code == 201 and r.json()["citations"] == [] and r.json()["source"] == "rules"


def test_notebook_access(client, db):
    doc = login(client, "doctor@medora.tn")
    assert client.post("/ai/notebook/p-0007", headers=doc, json={"question": "anything"}).status_code == 403
    for email in ("nurse@medora.tn", "admin@medora.tn", "patient@medora.tn"):
        h = login(client, email)
        assert client.post("/ai/notebook/p-0001", headers=h, json={"question": "anything"}).status_code == 403
    assert client.post("/ai/notebook/p-0001", headers=doc, json={"question": "hi"}).status_code == 422
    assert db.query(NotebookEntry).count() == 0
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd backend && python -m pytest tests/test_notebook_api.py -v`
Expected: FAIL (404 on `/ai/notebook/p-0001`)

- [ ] **Step 3: Sources service**

```python
# backend/app/services/notebook.py
"""Sources for the case notebook (owner: Faouzi): the patient's own record only, built on every question so
there is no index to keep in sync. Spec 2026-10-09 §5."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import copilot
from app.ai.notebook import Source
from app.models import Appointment, ExamOrder, ExamResult, Note, Prescription, User, Vital
from app.schemas import iso


def _day(dt: datetime | None) -> str:
    return dt.astimezone(UTC).strftime("%d %b %H:%M") if dt else ""


def build_sources(db: Session, patient) -> list[Source]:
    pid = patient.id
    out: list[Source] = []
    for a in db.scalars(select(Appointment).where(Appointment.patient_id == pid).order_by(Appointment.created_at)):
        if a.referral_text:
            out.append(Source(f"referral:{a.id}", "referral", f"Referral · {_day(a.created_at)}", iso(a.created_at),
                              a.referral_text))
    for n in db.scalars(select(Note).where(Note.patient_id == pid).order_by(Note.created_at)):
        author = db.get(User, n.author_id)
        out.append(Source(f"note:{n.id}", "note", f"Note by {author.name if author else 'staff'} · {_day(n.created_at)}",
                          iso(n.created_at), n.text))
    rows = db.execute(select(ExamResult, ExamOrder).join(ExamOrder, ExamOrder.id == ExamResult.exam_order_id)
                      .where(ExamResult.patient_id == pid).order_by(ExamResult.created_at)).all()
    for r, o in rows:
        text = f"{o.label}: {r.report_text}" if r.report_text else f"{o.label}: result file {r.file_name} (no report line)"
        out.append(Source(f"exam:{r.id}", "exam_report", f"{o.label} · {_day(r.created_at)}", iso(r.created_at), text))
    for rx in db.scalars(select(Prescription).where(Prescription.patient_id == pid, Prescription.active)):
        items = "; ".join(f"{i['med']} at {', '.join(i.get('times', []))} for {i.get('days', '?')} days"
                          for i in rx.items)
        out.append(Source(f"rx:{rx.id}", "prescription", f"Prescription · {_day(rx.created_at)}", iso(rx.created_at),
                          f"{items}. {rx.care_plan or ''}".strip()))
    since = datetime.now(UTC) - timedelta(hours=24)
    vitals = db.scalars(select(Vital).where(Vital.patient_id == pid, Vital.ts >= since).order_by(Vital.ts)).all()
    stats = copilot._stats_text([{"hr": v.hr, "spo2": v.spo2, "temp": v.temp, "news2": v.news2} for v in vitals])
    out.append(Source("vitals:24h", "vitals", "Vitals · last 24 h", iso(datetime.now(UTC)), stats))
    return out
```

- [ ] **Step 4: Routes.** Add to `backend/app/routers/ai.py`, merging its imports with the ones already there:

```python
from fastapi import Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.ai import notebook
from app.auth.deps import check_patient_access, require_roles
from app.errors import not_found
from app.ids import new_id
from app.models import NotebookEntry
from app.schemas import iso
from app.services.notebook import build_sources


class NotebookIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def _entry_out(e: NotebookEntry) -> dict:
    s = e.ai_suggested
    return {"id": e.id, "patient_id": e.patient_id, "question": e.question, "answer": s["answer"],
            "source": s["source"], "citations": s["citations"], "human_confirmed_by": e.human_confirmed_by,
            "created_at": iso(e.created_at)}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.post("/notebook/{patient_id}", status_code=201)
def ask_notebook(patient_id: str, body: NotebookIn, request: Request, user=Depends(require_roles("doctor")),
                 db: Session = Depends(get_db)) -> dict:
    p = check_patient_access(db, user, patient_id, resource="notebook", ip=_client_ip(request))
    result = notebook.answer(body.question.strip(), build_sources(db, p), names=[p.first_name, p.last_name])
    e = NotebookEntry(id=new_id(db, "nb"), patient_id=p.id, user_id=user.id, question=body.question.strip(),
                      ai_suggested=result)
    db.add(e)
    db.flush()
    db.refresh(e)
    out = _entry_out(e)
    db.commit()
    return out


@router.get("/notebook/{patient_id}")
def notebook_history(patient_id: str, request: Request, user=Depends(require_roles("doctor")),
                     db: Session = Depends(get_db)) -> list[dict]:
    check_patient_access(db, user, patient_id, resource="notebook", ip=_client_ip(request))
    rows = db.scalars(select(NotebookEntry).where(NotebookEntry.patient_id == patient_id)
                      .order_by(NotebookEntry.created_at.desc(), NotebookEntry.id.desc()).limit(50)).all()
    db.commit()
    return [_entry_out(e) for e in rows]


@router.get("/notebook/{patient_id}/sources")
def notebook_sources(patient_id: str, request: Request, user=Depends(require_roles("doctor")),
                     db: Session = Depends(get_db)) -> list[dict]:
    p = check_patient_access(db, user, patient_id, resource="notebook", ip=_client_ip(request))
    out = [{"id": s.id, "kind": s.kind, "title": s.title, "ts": s.ts} for s in build_sources(db, p)]
    db.commit()
    return out


@router.post("/notebook/entries/{entry_id}/review")
def review_notebook_entry(entry_id: str, request: Request, user=Depends(require_roles("doctor")),
                          db: Session = Depends(get_db)) -> dict:
    e = db.get(NotebookEntry, entry_id)
    if e is None:
        raise not_found("notebook entry")
    check_patient_access(db, user, e.patient_id, write=True, resource="notebook", ip=_client_ip(request))
    e.human_confirmed_by = user.id
    db.flush()
    out = _entry_out(e)
    db.commit()
    return out
```

Notes:
- The router in `ai.py` must have `prefix="/ai"`; if it uses another style, keep its style and make the full paths match api.md 1.8.
- If `Depends`, `Session` or `get_db` aren't imported yet there, import them as the other routers do.

- [ ] **Step 5: Run the tests**

Run: `cd backend && python -m pytest tests/test_notebook_api.py tests/test_notebook.py -v`
Expected: PASS. In `test_sources_history_and_review` the two entries can share a `created_at` inside one transaction; the `id desc` tiebreak keeps the order.

- [ ] **Step 6: Full suite and lint**

Run: `cd backend && python -m pytest -q && python -m ruff check .`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/notebook.py backend/app/routers/ai.py backend/tests/test_notebook_api.py
git commit -m "feat(backend): case notebook routes with stored, reviewable answers"
```

---

### Task 4: Doctor notebook panel (web)

**Files:**
- Modify: `web/src/lib/types.ts`, `web/src/lib/api.ts`
- Create: `web/src/mocks/notebook.ts`
- Create: `web/src/components/doctor/NotebookPanel.tsx` and `NotebookPanel.module.css`
- Modify: `web/src/components/doctor/PatientDetail.tsx` (right column, under `DailySummary`)

**Interfaces:**
- Produces (TS):

```ts
export interface NotebookCitation { n: number; source_id: string; kind: string; title: string; snippet: string; }
export interface NotebookEntry { id: string; patient_id: string; question: string; answer: string; source: AiSource; citations: NotebookCitation[]; human_confirmed_by: string | null; created_at: string; }
export interface NotebookSource { id: string; kind: string; title: string; ts: string | null; }
```

`api.ts`:
- `askNotebook(patientId: string, question: string): Promise<NotebookEntry>`
- `getNotebook(patientId: string): Promise<NotebookEntry[]>`
- `getNotebookSources(patientId: string): Promise<NotebookSource[]>`
- `reviewNotebookEntry(entryId: string, opts?: ActorOpts): Promise<NotebookEntry>`

- [ ] **Step 1: Types and mocks.** Add the three interfaces to `types.ts`. Create `web/src/mocks/notebook.ts`, which answers from the mock notes with the backend's exact strings:

```ts
// Mock case notebook: keyword match over the patient's mock notes, same answer strings as the backend.
import type { Note, NotebookEntry } from "@/lib/types";

export const NO_LLM_ANSWER = "These passages from the record match your question. Read them before deciding.";
export const NO_MATCH_ANSWER = "Nothing in this record matches the question.";

const fold = (s: string) => s.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();

export function mockNotebookAnswer(id: string, patientId: string, question: string, notes: Note[], at: string): NotebookEntry {
  const words = fold(question).split(/\W+/u).filter((w) => w.length > 2);
  const hits = notes.filter((n) => words.some((w) => fold(n.text).includes(w))).slice(0, 4);
  return {
    id, patient_id: patientId, question, source: "rules", human_confirmed_by: null, created_at: at,
    answer: hits.length ? NO_LLM_ANSWER : NO_MATCH_ANSWER,
    citations: hits.map((n, i) => ({ n: i + 1, source_id: `note:${n.id}`, kind: "note", title: `Note · ${n.created_at.slice(0, 10)}`, snippet: n.text.slice(0, 400) })),
  };
}
```

- [ ] **Step 2: api.ts.** Add `notebook: NotebookEntry[]` to the mock store (`createStore()` → `notebook: []`) and:

```ts
// ── Case notebook (api.md 1.8 proposal) ─────────────────────────────────────

export async function askNotebook(patientId: string, question: string): Promise<NotebookEntry> {
  if (USE_MOCKS)
    return mock((s) => {
      const e = mockNotebookAnswer(`nb-${String(s.notebook.length + 1).padStart(4, "0")}`, patientId, question,
        s.notes.filter((n) => n.patient_id === patientId), iso(now()));
      s.notebook.unshift(e);
      return e;
    });
  return http<NotebookEntry>("POST", `/ai/notebook/${encodeURIComponent(patientId)}`, { question });
}

export async function getNotebook(patientId: string): Promise<NotebookEntry[]> {
  if (USE_MOCKS) return mock((s) => s.notebook.filter((e) => e.patient_id === patientId));
  return http<NotebookEntry[]>("GET", `/ai/notebook/${encodeURIComponent(patientId)}`);
}

export async function getNotebookSources(patientId: string): Promise<NotebookSource[]> {
  if (USE_MOCKS)
    return mock((s) => [
      ...s.notes.filter((n) => n.patient_id === patientId).map((n) => ({ id: `note:${n.id}`, kind: "note", title: `Note · ${n.created_at.slice(0, 10)}`, ts: n.created_at })),
      { id: "vitals:24h", kind: "vitals", title: "Vitals · last 24 h", ts: null },
    ]);
  return http<NotebookSource[]>("GET", `/ai/notebook/${encodeURIComponent(patientId)}/sources`);
}

export async function reviewNotebookEntry(entryId: string, opts: ActorOpts = {}): Promise<NotebookEntry> {
  if (USE_MOCKS)
    return mock((s) => {
      const e = s.notebook.find((x) => x.id === entryId) ?? notFound(`Notebook entry ${entryId}`);
      e.human_confirmed_by = opts.by ?? "u-0001";
      return e;
    });
  return http<NotebookEntry>("POST", `/ai/notebook/entries/${encodeURIComponent(entryId)}/review`, {});
}
```

If the mock notes field in `MockStore` isn't named `notes` with a `patient_id` on each note, use whatever `getNotes` reads in mock mode (`grep -n "export async function getNotes" -A6 web/src/lib/api.ts`).

- [ ] **Step 3: Panel**

```tsx
"use client";

// Case notebook: ask about this patient; answers use only this patient's record and cite it.
// Every answer is an AI suggestion that needs the doctor's review.
import { useEffect, useState } from "react";
import { AiBadge } from "@/components/AiBadge";
import { askNotebook, getNotebook, getNotebookSources, reviewNotebookEntry } from "@/lib/api";
import type { NotebookEntry, NotebookSource } from "@/lib/types";
import styles from "./NotebookPanel.module.css";

export function NotebookPanel({ patientId, actorId }: { patientId: string; actorId: string }) {
  const [question, setQuestion] = useState("");
  const [entries, setEntries] = useState<NotebookEntry[]>([]);
  const [sources, setSources] = useState<NotebookSource[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getNotebook(patientId).then((r) => alive && setEntries(r)).catch(() => undefined);
    getNotebookSources(patientId).then((r) => alive && setSources(r)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [patientId]);

  async function ask() {
    const q = question.trim();
    if (q.length < 3 || busy) return;
    setBusy(true);
    setError(null);
    try {
      const e = await askNotebook(patientId, q);
      setEntries((list) => [e, ...list]);
      setQuestion("");
    } catch {
      setError("Couldn’t answer right now. Your question is still in the box — try again.");
    } finally {
      setBusy(false);
    }
  }

  async function review(id: string) {
    try {
      const e = await reviewNotebookEntry(id, { by: actorId });
      setEntries((list) => list.map((x) => (x.id === id ? e : x)));
    } catch {
      setError("Couldn’t mark it as reviewed.");
    }
  }

  return (
    <section className={styles.card} aria-label="Case notebook">
      <h3 className={styles.h3}>Case notebook</h3>
      <p className={styles.sub}>Answers use only this patient’s record · {sources.length} sources</p>
      <div className={styles.ask}>
        <input
          className={styles.input}
          dir="auto"
          value={question}
          maxLength={500}
          placeholder="Ask about this case, e.g. “What did the chest X-ray show?”"
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void ask()}
        />
        <button className={styles.btn} disabled={busy || question.trim().length < 3} onClick={() => void ask()}>
          {busy ? "Searching…" : "Ask"}
        </button>
      </div>
      {error ? <p className={styles.error} role="alert">{error}</p> : null}
      {entries.map((e) => (
        <article key={e.id} className={styles.entry}>
          <p className={styles.q} dir="auto">{e.question}</p>
          <AiBadge source={e.source} state={e.human_confirmed_by ? "reviewed" : "needs_review"} />
          <p className={styles.a} dir="auto">{e.answer}</p>
          {e.citations.length ? (
            <ol className={styles.cites}>
              {e.citations.map((c) => (
                <li key={c.n} value={c.n}>
                  <span className={styles.citeTitle}>{c.title}</span>
                  <span dir="auto">{c.snippet}</span>
                </li>
              ))}
            </ol>
          ) : null}
          {!e.human_confirmed_by ? (
            <button className={styles.review} onClick={() => void review(e.id)}>Mark as reviewed</button>
          ) : null}
        </article>
      ))}
    </section>
  );
}
```

`NotebookPanel.module.css`:

```css
.card { background: var(--paper); border: 1px solid var(--line); border-radius: 14px; padding: 22px; display: flex; flex-direction: column; gap: 12px; }
.h3 { margin: 0; font: 600 22px/1.2 var(--serif); color: var(--ink); }
.sub { margin: 0; font-size: 13px; color: var(--text); }
.ask { display: flex; gap: 8px; }
.input { flex: 1; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; font: inherit; }
.btn { padding: 10px 16px; border: 0; border-radius: 10px; background: var(--teal); color: #fff; font-weight: 600; cursor: pointer; }
.btn:disabled { opacity: 0.6; cursor: default; }
.error { margin: 0; font-size: 13px; color: var(--warn-ink); }
.entry { display: flex; flex-direction: column; gap: 8px; padding-top: 12px; border-top: 1px solid var(--line); }
.q { margin: 0; font-weight: 600; color: var(--ink); }
.a { margin: 0; font-size: 15px; line-height: 1.55; color: var(--text); }
.cites { margin: 0; padding-left: 22px; display: flex; flex-direction: column; gap: 6px; font-size: 14px; color: var(--text); }
.citeTitle { display: block; font-size: 12px; font-weight: 600; color: var(--ink); }
.review { align-self: flex-start; padding: 6px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--paper); cursor: pointer; }
```

- [ ] **Step 4: Mount it.** In `PatientDetail.tsx`, import `NotebookPanel` and render `<NotebookPanel patientId={id} actorId={DOCTOR_ID} />` right after `<DailySummary … />`.

- [ ] **Step 5: Checks**

Run: `cd web && npm run typecheck && npm run build`
Then in mock mode, on `/doctor/patients/p-0001`:
- Ask a word that appears in a mock note → a cited answer with "Needs review".
- Ask "dialysis" → "Nothing in this record matches the question."
- Click "Mark as reviewed" → the badge says Reviewed.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/types.ts web/src/lib/api.ts web/src/mocks/notebook.ts web/src/mocks/index.ts web/src/components/doctor/NotebookPanel.tsx web/src/components/doctor/NotebookPanel.module.css web/src/components/doctor/PatientDetail.tsx
git commit -m "feat(web): case notebook panel on the doctor's patient page"
```

---

### Task 5: Real-stack check, LLM memory test and PR

- [ ] **Step 1: No-LLM mode on the real stack.**
  - Rebuild the API: `docker compose -p ward -f infra/docker-compose.yml --env-file .env up -d --build api`.
  - With `LLM_PROVIDER=none`, as `doctor@medora.tn` open Amira's page and add a note "Troponin normal this morning".
  - Ask "troponin?".

  Expected: a cited answer, `AI suggestion · Rules fallback · Needs review`, and an audit row:

  `docker exec ward-db-1 psql -U ward -d ward -tAc "select count(*) from audit_log where resource='notebook'"` > 0.
- [ ] **Step 2: LLM mode, only if the laptop has the memory.**
  - Check free RAM: `powershell -c "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB"` (GB). Below 8 GB: skip, and write "LLM mode not tested on the demo laptop" in the PR.
  - Otherwise run Ollama with a small open model, set `LLM_PROVIDER=local` (plus the Ollama variables `llm.py` reads, see `.env.example`), restart `api`, and ask again.

  Expected: a short answer with `[n]` markers and `source: "llm"`. Then switch back to `none`.
- [ ] **Step 3: Full checks.** `cd backend && python -m pytest -q && python -m ruff check .`; `cd web && npm run typecheck && npm run build`.
- [ ] **Step 4: Push and open the PR** against `main`. The body covers what, how it stays grounded (the citations check), no-LLM default, verification and the LLM memory result; no emojis, no attribution lines.

```bash
git push -u origin faouzi/case-notebook
gh pr create --base main --title "feat: case notebook for doctors" --body-file <scratchpad>/pr-body.md
```
