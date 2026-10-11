# AI Radiograph Reading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local open vision model (Qwen3-VL via Ollama) drafts a structured reading of every radiograph uploaded to a patient's record; a doctor reviews, edits and confirms it.

**Architecture:** Upload endpoints enqueue a `radiograph_readings` row; a daemon thread in the existing `worker` claims queued rows, re-encodes the image, calls Ollama through `app/ai/llm.py`, and stores the draft (or a blank template when no model is available). Doctors read and confirm through three endpoints; the web `ExamsPanel` shows and polls the reading.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, Pillow, httpx, Ollama `/api/chat`; Next.js 16 / React 19 / strict TS / CSS Modules.

**Spec:** `docs/superpowers/specs/2026-10-10-radiograph-reading-design.md` (read it first).

## Global Constraints

- Branch `wali/radiograph-reading` (on top of `wali/health-calendar`). Conventional Commits. **No AI attribution** (no `Co-Authored-By`, no "Generated with").
- Contracts win: api → **1.14**, data-model → **1.8**, each with a changelog line (numbers assume Task 1 put the calendar at api 1.13 / data-model 1.7 — verify after Task 1 and use the next free numbers).
- Migration **0008** with `down_revision` = the calendar migration (`0007`).
- Statuses (exact): `queued`, `running`, `ready`, `unavailable`, `failed`. Likelihoods: `low`, `medium`, `high`. Radiograph codes: `chest_xray`, `xray`, `xray_outside`. Image types: `image/jpeg`, `image/png`.
- Disclaimer text (exact): `AI draft from a prototype, not a diagnosis and not clinically validated. A doctor must review it.`
- Images never leave the machine: vision calls only when `VISION_PROVIDER=local`; never via Groq.
- Every LLM call goes through `app/ai/llm.py`; prompts and rules live in versioned files (`prompts/*.v1.md`, `rules/*.v1.json`).
- Every read of a reading by a doctor writes `audit_log`.
- Python: run from `backend/` with `"D:/Projects 2026/smarty-hospital-/backend/.venv/Scripts/python" -m pytest …`; Postgres on localhost:5432. Install Pillow into that venv if missing (`… -m pip install "pillow==11.*"`).
- Web: from `web/`: `npm run typecheck`, `npm run build`. Mock clock `2026-10-05T08:12:00Z`.

## Review Focus

1. A corrupted or non-image file uploaded as `image/png` → reading `failed` with a template, worker keeps running (Task 4/5 tests).
2. Doctor confirms while the reading is still `queued`/`running` → the worker must not overwrite `final_text` (Task 5 test).
3. Worker killed mid-job → row stuck in `running` is re-queued on the next start (`recover`, Task 5 test).
4. A PDF uploaded for a `chest_xray` order → no reading is created (Task 6 test).
5. A nurse or a doctor without access asks for the reading → status only / 403, no draft text leaks (Task 6 test).

---

## File Structure

Backend:
- Modify `backend/app/config.py`, `.env.example`, `backend/requirements.txt`, `infra/docker-compose.yml`
- Create `backend/app/models/radiology.py`; modify `backend/app/models/__init__.py`
- Create `backend/alembic/versions/0008_radiograph_readings.py`
- Modify `backend/app/ai/llm.py` (vision call)
- Create `backend/app/ai/radiology.py`, `backend/app/ai/prompts/radiograph_report.v1.md`, `backend/app/ai/rules/radiograph.v1.json`
- Modify `backend/app/ai/rules/exam_bundles.v1.json` (catalogue `xray`)
- Create `backend/app/services/radiology.py`; modify `backend/app/iot/worker.py`
- Create `backend/app/routers/radiology.py`; modify `backend/app/routers/exams.py`, `backend/app/services/exams.py`, `backend/app/main.py`
- Create `backend/app/radiograph_seed.py`, `backend/app/ai/assets/radiographs/*.jpg`, `backend/app/ai/assets/radiographs/CREDITS.md`; modify `backend/app/seed.py` (`__main__` only)
- Tests: `backend/tests/test_radiology_ai.py`, `test_radiology_service.py`, `test_radiology_api.py`, `test_radiograph_seed.py`

Web:
- Modify `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/mocks/exams.ts` (+ `mocks/index.ts` if the store needs it), `web/src/lib/labels.ts`, `web/src/i18n/messages/index.ts`, `web/src/i18n/messages/shared.ts` (exam code labels)
- Create `web/src/i18n/messages/radiology.ts`, `web/src/components/shared/RadiographReadingCard.tsx` + `.module.css`
- Modify `web/src/components/shared/ExamsPanel.tsx` (+ `.module.css`), `web/src/components/doctor/PatientDetail.tsx` (pass `role="doctor"`)

---

### Task 1: Bring the calendar branch up to date with main, then branch on it

**Files:** merge only; contract renumbering in `docs/contracts/api.md` (and code comments that cite the calendar's api version).

- [ ] **Step 1:** In the worktree `D:/Projects 2026/ward-health-calendar`: `git fetch origin`, `git checkout wali/health-calendar`, `git merge origin/main` (do NOT rebase: the branch is pushed).
- [ ] **Step 2:** Resolve conflicts keeping main's content and adding the calendar's on top. Main's api.md is **1.12 (health watch)**, so the calendar section/changelog becomes **api 1.13**; data-model stays **1.7** unless main moved past 1.6 (then next free); migration stays `0007` unless main added a `0007` (then renumber to the next free number and fix `down_revision`). n8n: main uses W10 for health watch and reserves W9 for the calendar — keep both routes in `W0-router.json` (indexes must be unique and the Switch outputs/connections must line up). Update code comments citing "api.md 1.12" for the calendar (`git grep -n "1\.12" -- backend web` and judge each hit).
- [ ] **Step 3:** Verify: `… -m pytest -q` (all pass except the known timing test `test_huge_input_stays_fast` if it still fails on main), `"D:/Projects 2026/smarty-hospital-/backend/.venv/Scripts/python" -m alembic heads` from `backend/` → one head; `npm run typecheck` in `web/`.
- [ ] **Step 4:** Commit the merge (`merge: origin/main into wali/health-calendar (calendar on api 1.13)`), `git push origin wali/health-calendar`.
- [ ] **Step 5:** `git checkout wali/radiograph-reading && git merge wali/health-calendar` (fast-forward or merge commit). Commit any leftover spec/plan files already on this branch first if needed.

---

### Task 2: Contracts

**Files:** `docs/contracts/api.md`, `docs/contracts/data-model.md`

- [ ] **Step 1:** data-model.md → next version (1.8): add `### radiograph_readings` with the spec's column table and the `ai_suggested` shapes; add `radiograph_reading` as an example `resource` in `audit_log`; permission matrix row "Radiograph readings | R/W (result access) | R status (result access) | — | —" in the matrix's own column order; changelog `- **1.8** (2026-10-10): \`radiograph_readings\` (AI radiograph draft per image, doctor-confirmed report). Migration 0008.`
- [ ] **Step 2:** api.md → next version (1.14): section `## Radiograph reading (1.14 — Wali)` with the endpoint table from the spec, the reading JSON example (below), the `reading` field added to `ExamOrder.results[]`, the new exam codes (`xray`, `xray_outside`), and the WS frame `radiograph_reading` in the WebSocket frames list. Changelog `- **1.14** (2026-10-10): radiograph reading — \`GET/PUT /exam-results/{id}/reading\`, \`POST /patients/{id}/radiographs\`, \`results[].reading\`, exam codes \`xray\`/\`xray_outside\`, WS frame \`radiograph_reading\`.`

```json
{"id":"rr-0001","exam_result_id":"er-0901","patient_id":"p-0001","status":"ready","hint":"Chest X-ray",
 "ai_suggested":{"source":"llm","model":"qwen3-vl:4b","region":"chest","projection":"PA","quality":"adequate",
   "findings":["Clear lung fields"],"impression":"No acute abnormality seen.",
   "possible_conditions":[{"name":"No acute cardiopulmonary disease","likelihood":"high","evidence":"normal lungs, heart size"}],
   "urgent_flags":[],"recommendation":"","draft_text":"Technique : …","disclaimer":"AI draft from a prototype, not a diagnosis and not clinically validated. A doctor must review it."},
 "final_text":null,"human_confirmed_by":null,"confirmed_by_name":null,"confirmed_at":null,
 "created_at":"2026-10-10T09:00:00Z","finished_at":"2026-10-10T09:00:40Z"}
```

- [ ] **Step 3:** Commit `docs(contracts): api 1.14, data-model 1.8 for AI radiograph reading`.

---

### Task 3: Settings, dependency, model and migration

**Files:** `backend/app/config.py`, `.env.example`, `backend/requirements.txt`, `infra/docker-compose.yml`, `backend/app/models/radiology.py`, `backend/app/models/__init__.py`, `backend/alembic/versions/0008_radiograph_readings.py`, test `backend/tests/test_radiology_service.py` (first test only)

**Interfaces — Produces:** `Settings.vision_provider: str`, `.llm_vision_model: str`, `.llm_vision_timeout_s: float`, `.radiology_report_lang: str`; `app.models.RadiographReading`.

- [ ] **Step 1: Failing test** `backend/tests/test_radiology_service.py`

```python
from app.models import ExamOrder, ExamResult, RadiographReading


def make_result(db, *, code="chest_xray", content_type="image/png", patient="p-0001", n=1):
    o = ExamOrder(id=f"ex-80{n:02d}", patient_id=patient, code=code, label="Chest X-ray", department="Imaging",
                  status="done", human_confirmed_by="u-0001")
    db.add(o)
    db.flush()
    r = ExamResult(id=f"er-80{n:02d}", exam_order_id=o.id, patient_id=patient, uploaded_by="u-0006",
                   file_key=f"exams/{o.id}/x.png", file_name="x.png", content_type=content_type, size_bytes=10)
    db.add(r)
    db.flush()
    return o, r


def test_reading_roundtrip(db, seeded):
    _, r = make_result(db)
    db.add(RadiographReading(id="rr-8001", exam_result_id=r.id, patient_id="p-0001", hint="Chest X-ray"))
    db.flush()
    got = db.get(RadiographReading, "rr-8001")
    assert got.status == "queued" and got.ai_suggested is None and got.final_text is None
```

- [ ] **Step 2:** Run `… -m pytest tests/test_radiology_service.py -q` → FAIL (ImportError).
- [ ] **Step 3: Implement.**

`backend/app/config.py` after `llm_timeout_s`:
```python
    vision_provider: str = "none"  # none | local — radiograph images never go to a hosted API
    llm_vision_model: str = "qwen3-vl:4b"
    llm_vision_timeout_s: float = 180.0
    radiology_report_lang: str = "fr"  # fr | en
```

`.env.example` after the LLM block:
```
# AI radiograph reading (local Ollama vision model only; images never leave the machine)
VISION_PROVIDER=none
LLM_VISION_MODEL=qwen3-vl:4b
LLM_VISION_TIMEOUT_S=180
RADIOLOGY_REPORT_LANG=fr
# Ollama on the host as seen from the containers
DOCKER_OLLAMA_URL=http://host.docker.internal:11434
```

`backend/requirements.txt`: add `pillow==11.*`.

`infra/docker-compose.yml` `worker` service: add the same `MINIO_*` environment entries the `api` service has (copy them exactly), `LLM_LOCAL_BASE_URL: ${DOCKER_OLLAMA_URL:-http://host.docker.internal:11434}`, and `extra_hosts: ["host.docker.internal:host-gateway"]`.

`backend/app/models/radiology.py`:
```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RadiographReading(Base):
    """AI draft reading of one radiograph image, confirmed by a doctor (data-model 1.8)."""

    __tablename__ = "radiograph_readings"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    exam_result_id: Mapped[str] = mapped_column(ForeignKey("exam_results.id"), unique=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    status: Mapped[str] = mapped_column(String, index=True, default="queued", server_default="queued")
    hint: Mapped[str] = mapped_column(String, default="", server_default="")
    ai_suggested: Mapped[dict | None] = mapped_column(JSONB)
    final_text: Mapped[str | None] = mapped_column(Text)
    human_confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```
Register in `models/__init__.py` (import + `__all__`, alphabetical; docstring version → 1.8).

Migration `0008_radiograph_readings.py` (`revision='0008'`, `down_revision='0007'` — or the numbers from Task 1), matching the model exactly (unique constraint on `exam_result_id`, indexes `ix_radiograph_readings_patient_id` and `ix_radiograph_readings_status`, `server_default` "queued" and ""), following the style of `0007_health_calendar.py`; downgrade drops indexes then table.

- [ ] **Step 4:** Test → PASS; `alembic heads` → single head 0008; full suite once.
- [ ] **Step 5:** Commit `feat(backend): radiograph_readings table (migration 0008), vision settings, pillow`.

---

### Task 4: AI module — image prep, vision call, draft, template

**Files:** `backend/app/ai/llm.py`, `backend/app/ai/radiology.py`, `backend/app/ai/prompts/radiograph_report.v1.md`, `backend/app/ai/rules/radiograph.v1.json`, test `backend/tests/test_radiology_ai.py`

**Interfaces — Produces:** `llm.complete_vision_json(prompt_name: str, image_png: bytes, user_text: str, schema: type[T]) -> T`; `radiology.DISCLAIMER`, `radiology.MAX_SIDE`, `radiology.RadiographDraft`, `radiology.prepare_image(data: bytes) -> bytes`, `radiology.render(draft: RadiographDraft, lang: str) -> str`, `radiology.template(lang: str, reason: str) -> dict`, `radiology.read(data: bytes, hint: str) -> tuple[str, dict]`, `radiology.RULES: dict` (`codes`, `image_types`).

- [ ] **Step 1: Failing tests** `backend/tests/test_radiology_ai.py`

```python
import io
import json

import httpx
import pytest
from PIL import Image

from app.ai import llm, radiology
from app.config import get_settings


def jpeg_with_exif(w=2000, h=1500) -> bytes:
    im = Image.new("RGB", (w, h), (90, 90, 90))
    exif = Image.Exif()
    exif[0x010E] = "Patient: Amira Ben Salah"  # ImageDescription
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


DRAFT = {"region": "chest", "projection": "PA", "quality": "adequate", "findings": ["Clear lung fields"],
         "impression": "No acute abnormality seen.",
         "possible_conditions": [{"name": "Normal chest", "likelihood": "high", "evidence": "clear lungs"}],
         "urgent_flags": [], "recommendation": ""}


class FakeResp:
    def __init__(self, content: str, status: int = 200):
        self._content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)

    def json(self):
        return {"message": {"content": self._content}}


@pytest.fixture()
def local_vision(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "vision_provider", "local")
    monkeypatch.setattr(s, "llm_vision_model", "qwen3-vl:4b")
    return s


def test_prepare_image_strips_metadata_and_caps_size():
    png = radiology.prepare_image(jpeg_with_exif())
    im = Image.open(io.BytesIO(png))
    assert im.format == "PNG" and max(im.size) == radiology.MAX_SIDE and im.mode == "L"
    assert "exif" not in im.info and not im.getexif()


def test_prepare_image_rejects_garbage():
    with pytest.raises(Exception):
        radiology.prepare_image(b"not an image")


def test_vision_call_payload(monkeypatch, local_vision):
    seen = {}

    def fake_post(url, timeout, json):  # noqa: A002
        seen.update(url=url, timeout=timeout, body=json)
        return FakeResp(__import__("json").dumps(DRAFT))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.complete_vision_json("radiograph_report", b"PNGDATA", "Exam: Chest X-ray", radiology.RadiographDraft)
    assert out.region == "chest"
    body = seen["body"]
    assert seen["url"].endswith("/api/chat") and body["model"] == "qwen3-vl:4b" and body["stream"] is False
    user = body["messages"][-1]
    assert user["images"] == ["UE5HREFUQQ=="] and "format" in body


def test_vision_needs_local_provider(monkeypatch):
    monkeypatch.setattr(get_settings(), "vision_provider", "none")
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_vision_json("radiograph_report", b"x", "", radiology.RadiographDraft)


def test_read_ready(monkeypatch, local_vision):
    monkeypatch.setattr(llm.httpx, "post", lambda url, timeout, json: FakeResp(__import__("json").dumps(DRAFT)))
    status, ai = radiology.read(jpeg_with_exif(), "Chest X-ray")
    assert status == "ready" and ai["source"] == "llm" and ai["model"] == "qwen3-vl:4b"
    assert ai["disclaimer"] == radiology.DISCLAIMER and "No acute abnormality" in ai["draft_text"]
    assert ai["possible_conditions"][0]["likelihood"] == "high"


@pytest.mark.parametrize("content", ["not json", json.dumps({"possible_conditions": [{"name": "x", "likelihood": "certain"}]})])
def test_read_invalid_output_is_unavailable(monkeypatch, local_vision, content):
    monkeypatch.setattr(llm.httpx, "post", lambda url, timeout, json: FakeResp(content))
    status, ai = radiology.read(jpeg_with_exif(), "")
    assert status == "unavailable" and ai["source"] == "rules" and ai["draft_text"]


def test_read_timeout_is_unavailable(monkeypatch, local_vision):
    def boom(url, timeout, json):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(llm.httpx, "post", boom)
    assert radiology.read(jpeg_with_exif(), "")[0] == "unavailable"


def test_read_without_model_gives_template(monkeypatch):
    monkeypatch.setattr(get_settings(), "vision_provider", "none")
    monkeypatch.setattr(get_settings(), "radiology_report_lang", "fr")
    status, ai = radiology.read(jpeg_with_exif(), "")
    assert status == "unavailable" and ai["draft_text"].startswith("Technique")
    assert "Conclusion" in ai["draft_text"]


def test_read_garbage_is_failed():
    status, ai = radiology.read(b"%PDF-1.4 nope", "")
    assert status == "failed" and ai["source"] == "rules" and ai["draft_text"]


def test_render_english(monkeypatch):
    d = radiology.RadiographDraft.model_validate(DRAFT | {"urgent_flags": ["Possible pneumothorax"]})
    text = radiology.render(d, "en")
    assert text.index("Findings") < text.index("Impression") and "Possible pneumothorax" in text
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement.**

Append to `backend/app/ai/llm.py` (add `import base64`):
```python
def complete_vision_json(prompt_name: str, image_png: bytes, user_text: str, schema: type[T]) -> T:
    """One image + text → JSON, local Ollama only: an image can carry burned-in names that strip_pii cannot reach,
    so images never go to a hosted provider. Any failure (off, timeout, bad JSON, schema) → LLMUnavailable."""
    s = get_settings()
    if s.vision_provider != "local":
        raise LLMUnavailable(f"vision_provider={s.vision_provider}")
    try:
        r = httpx.post(f"{s.llm_local_base_url}/api/chat", timeout=s.llm_vision_timeout_s, json={
            "model": s.llm_vision_model, "stream": False, "format": schema.model_json_schema(),
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": _prompt(prompt_name)},
                         {"role": "user", "content": strip_pii(user_text),
                          "images": [base64.b64encode(image_png).decode("ascii")]}]})
        r.raise_for_status()
        return schema.model_validate(json.loads(r.json()["message"]["content"]))
    except Exception as e:
        raise LLMUnavailable(str(e)) from e
```

`backend/app/ai/rules/radiograph.v1.json`:
```json
{"codes": ["chest_xray", "xray", "xray_outside"], "image_types": ["image/jpeg", "image/png"]}
```

`backend/app/ai/prompts/radiograph_report.v1.md` — write the prompt (English instructions), covering: you are drafting a preliminary radiograph reading for a doctor in a hospital *prototype*; describe only what is visible; first identify region and projection; if the image is not a radiograph or is unreadable, say so in `quality`, leave findings empty and set `impression` accordingly; list findings as short factual sentences; `impression` 1–3 sentences; `possible_conditions` at most 5, each with `likelihood` low/medium/high and the visual `evidence`, never certainty words ("definitely", "confirms"); `urgent_flags` only for findings needing same-day attention (pneumothorax, displaced fracture, free air, large effusion, malpositioned line/tube…), otherwise empty; `recommendation` optional (e.g. "lateral view", "compare with prior"); write every text field in the language named in the user message; no patient names, ages or identifiers; output JSON only.

`backend/app/ai/radiology.py`:
```python
"""AI radiograph reading (spec 2026-10-10-radiograph-reading-design.md). The model only drafts; a doctor confirms.
Works with no model: `template()` is the blank structured report (source "rules").

Smoke test on the demo laptop:  VISION_PROVIDER=local python -m app.ai.radiology path/to/xray.jpg
"""

import io
import json
import sys
import time
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from app.ai import llm
from app.config import get_settings

MAX_SIDE = 1024
DISCLAIMER = "AI draft from a prototype, not a diagnosis and not clinically validated. A doctor must review it."
RULES = json.loads((Path(__file__).parent / "rules" / "radiograph.v1.json").read_text(encoding="utf-8"))
LANG_NAME = {"fr": "French", "en": "English"}
HEAD = {
    "fr": ("Technique", "Résultats", "Conclusion", "Diagnostics possibles", "Signes urgents", "Recommandation"),
    "en": ("Technique", "Findings", "Impression", "Possible conditions", "Urgent signs", "Recommendation"),
}
LIKELY = {"fr": {"low": "faible", "medium": "moyenne", "high": "élevée"},
          "en": {"low": "low", "medium": "medium", "high": "high"}}


class Condition(BaseModel):
    name: str = Field(max_length=160)
    likelihood: Literal["low", "medium", "high"]
    evidence: str = Field(default="", max_length=400)


class RadiographDraft(BaseModel):
    region: str = Field(default="", max_length=80)
    projection: str = Field(default="", max_length=80)
    quality: str = Field(default="", max_length=300)
    findings: list[str] = Field(default_factory=list, max_length=15)
    impression: str = Field(default="", max_length=800)
    possible_conditions: list[Condition] = Field(default_factory=list, max_length=6)
    urgent_flags: list[str] = Field(default_factory=list, max_length=6)
    recommendation: str = Field(default="", max_length=400)


def _lang(lang: str) -> str:
    return lang if lang in HEAD else "fr"


def prepare_image(data: bytes) -> bytes:
    """Decode, apply EXIF orientation, grey-scale, fit in MAX_SIDE, re-encode as a fresh PNG (no metadata)."""
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im).convert("L")
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        im.save(out, format="PNG")
    return out.getvalue()


def render(d: RadiographDraft, lang: str) -> str:
    h, lk = HEAD[_lang(lang)], LIKELY[_lang(lang)]
    tech = ", ".join(x for x in (d.region, d.projection, d.quality) if x)
    parts = [f"{h[0]} : {tech}" if lang == "fr" else f"{h[0]}: {tech}",
             f"{h[1]} :" if lang == "fr" else f"{h[1]}:", *[f"- {f}" for f in d.findings],
             f"{h[2]} : {d.impression}" if lang == "fr" else f"{h[2]}: {d.impression}"]
    if d.possible_conditions:
        parts.append(f"{h[3]} :" if lang == "fr" else f"{h[3]}:")
        parts += [f"- {c.name} ({lk[c.likelihood]}){' — ' + c.evidence if c.evidence else ''}"
                  for c in d.possible_conditions]
    if d.urgent_flags:
        parts.append((f"{h[4]} : " if lang == "fr" else f"{h[4]}: ") + "; ".join(d.urgent_flags))
    if d.recommendation:
        parts.append((f"{h[5]} : " if lang == "fr" else f"{h[5]}: ") + d.recommendation)
    return "\n".join(parts)


def template(lang: str, reason: str) -> dict:
    h = HEAD[_lang(lang)]
    sep = " :" if _lang(lang) == "fr" else ":"
    text = "\n\n".join(f"{x}{sep}" for x in (h[0], h[1], h[2], h[5]))
    return {"source": "rules", "reason": reason[:200], "draft_text": text, "disclaimer": DISCLAIMER}


def read(data: bytes, hint: str = "") -> tuple[str, dict]:
    """(status, ai_suggested): "ready" with a model draft, "unavailable" (no model / bad output) or "failed"
    (unreadable image), the last two with the blank template."""
    s = get_settings()
    lang = _lang(s.radiology_report_lang)
    try:
        png = prepare_image(data)
    except Exception:
        return "failed", template(lang, "unreadable image")
    try:
        d = llm.complete_vision_json("radiograph_report", png,
                                     f"Language: {LANG_NAME[lang]}. Requested exam: {hint or 'radiograph'}.",
                                     RadiographDraft)
    except llm.LLMUnavailable as e:
        return "unavailable", template(lang, str(e))
    return "ready", {"source": "llm", "model": s.llm_vision_model, **d.model_dump(),
                     "draft_text": render(d, lang), "disclaimer": DISCLAIMER}


if __name__ == "__main__":
    t0 = time.monotonic()
    status, ai = read(Path(sys.argv[1]).read_bytes(), " ".join(sys.argv[2:]))
    print(json.dumps({"status": status, "seconds": round(time.monotonic() - t0, 1), **ai}, ensure_ascii=False, indent=2))
```
Simplify `render` while implementing so French uses " : " and English ": " through one helper (keep the outputs the tests check). The `_prompt` helper in llm.py loads `prompts/{name}.v1.md`.

- [ ] **Step 4:** Tests → PASS; ruff check.
- [ ] **Step 5:** Commit `feat(ai): radiograph reading draft - local vision call, image prep, template fallback`.

---

### Task 5: Job service and worker thread

**Files:** `backend/app/services/radiology.py`, `backend/app/iot/worker.py`, tests appended to `backend/tests/test_radiology_service.py`

**Interfaces — Consumes:** `radiology.read`, `radiology.RULES` (Task 4), `RadiographReading` (Task 3), `storage.get`, `publisher.publish_ws_frame`, `new_id`. **Produces:** `is_radiograph(code: str, content_type: str) -> bool`, `enqueue(db, result: ExamResult, hint: str) -> RadiographReading`, `claim_next(db) -> RadiographReading | None`, `process(db, reading, get=storage.get) -> dict` (the WS frame), `recover(db) -> int`, `tick(db, publish=publisher.publish_ws_frame, get=storage.get) -> bool`, `run_forever(stop: threading.Event, poll_s: float = 3.0) -> None`, `to_out(db, r, viewer: User) -> dict`, `confirm(db, r, user: User, text: str, now: datetime) -> None`.

- [ ] **Step 1: Failing tests** (append; reuse `make_result` from Task 3)

```python
from datetime import UTC, datetime

from app.services import radiology as R
from tests.helpers import make_user

READY = ("ready", {"source": "llm", "model": "m", "draft_text": "Technique : thorax", "disclaimer": "d"})


def test_is_radiograph():
    assert R.is_radiograph("chest_xray", "image/png") and R.is_radiograph("xray_outside", "image/jpeg")
    assert not R.is_radiograph("chest_xray", "application/pdf") and not R.is_radiograph("ecg", "image/png")


def test_enqueue_claim_process(db, seeded, monkeypatch):
    _, res = make_result(db)
    r = R.enqueue(db, res, "Chest X-ray")
    assert r.id.startswith("rr-") and r.status == "queued"
    got = R.claim_next(db)
    assert got.id == r.id and got.status == "running" and got.started_at
    assert R.claim_next(db) is None
    monkeypatch.setattr(R.radiology, "read", lambda data, hint: READY)
    frame = R.process(db, got, get=lambda key: b"img")
    assert got.status == "ready" and got.ai_suggested["model"] == "m" and got.finished_at
    assert frame == {"type": "radiograph_reading", "reading_id": r.id, "exam_result_id": res.id,
                     "patient_id": "p-0001", "status": "ready"}


def test_missing_file_fails_softly(db, seeded):
    _, res = make_result(db)
    r = R.enqueue(db, res, "")
    R.claim_next(db)

    def gone(key):
        raise FileNotFoundError(key)

    R.process(db, r, get=gone)
    assert r.status == "failed" and r.ai_suggested["source"] == "rules" and r.ai_suggested["draft_text"]


def test_worker_never_overwrites_confirmed_text(db, seeded, monkeypatch):
    _, res = make_result(db)
    r = R.enqueue(db, res, "")
    R.claim_next(db)
    doctor = db.get(__import__("app.models", fromlist=["User"]).User, "u-0001")
    R.confirm(db, r, doctor, "Written by hand", datetime.now(UTC))
    monkeypatch.setattr(R.radiology, "read", lambda data, hint: READY)
    R.process(db, r, get=lambda key: b"img")
    assert r.final_text == "Written by hand" and r.status == "ready"
    assert db.get(type(res), res.id).report_text == "Written by hand"


def test_recover_requeues_running(db, seeded):
    _, res = make_result(db)
    r = R.enqueue(db, res, "")
    R.claim_next(db)
    assert R.recover(db) == 1 and r.status == "queued" and r.started_at is None


def test_tick(db, seeded, monkeypatch):
    sent = []
    assert R.tick(db, publish=sent.append, get=lambda k: b"") is False
    _, res = make_result(db)
    R.enqueue(db, res, "")
    monkeypatch.setattr(R.radiology, "read", lambda data, hint: READY)
    assert R.tick(db, publish=sent.append, get=lambda k: b"img") is True
    assert sent[0]["status"] == "ready"


def test_to_out_by_role(db, seeded):
    _, res = make_result(db)
    r = R.enqueue(db, res, "Chest X-ray")
    r.ai_suggested = READY[1]
    nurse = make_user(db, "img2@ward.tn", role="nurse", ward="Imaging")
    assert set(R.to_out(db, r, nurse)) == {"id", "exam_result_id", "status"}
    doctor = db.get(__import__("app.models", fromlist=["User"]).User, "u-0001")
    full = R.to_out(db, r, doctor)
    assert full["ai_suggested"]["draft_text"] and full["hint"] == "Chest X-ray" and "confirmed_by_name" in full
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** `backend/app/services/radiology.py`

```python
"""Radiograph reading jobs (spec 2026-10-10-radiograph-reading-design.md): uploads enqueue, the worker thread
drafts, a doctor confirms. The model call lives in app/ai/radiology.py; this module owns states and storage."""

import logging
import threading
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import radiology
from app.db import SessionLocal
from app.ids import new_id
from app.iot import publisher
from app.models import ExamResult, RadiographReading, User
from app.services import storage
from app.services.time import iso  # use whatever iso() helper app/services/exams.py imports

log = logging.getLogger("ward.radiology")


def is_radiograph(code: str, content_type: str) -> bool:
    return code in radiology.RULES["codes"] and content_type in radiology.RULES["image_types"]


def enqueue(db: Session, result: ExamResult, hint: str) -> RadiographReading:
    r = RadiographReading(id=new_id(db, "rr"), exam_result_id=result.id, patient_id=result.patient_id,
                          status="queued", hint=(hint or "")[:120])
    db.add(r)
    db.flush()
    return r


def claim_next(db: Session) -> RadiographReading | None:
    r = db.scalars(select(RadiographReading).where(RadiographReading.status == "queued")
                   .order_by(RadiographReading.created_at, RadiographReading.id)
                   .limit(1).with_for_update(skip_locked=True)).first()
    if r is not None:
        r.status, r.started_at = "running", datetime.now(UTC)
        db.commit()
    return r


def process(db: Session, r: RadiographReading, get=None) -> dict:
    get = get or storage.get
    result = db.get(ExamResult, r.exam_result_id)
    try:
        data = get(result.file_key)
    except Exception as e:
        log.warning("reading %s: file unavailable: %s", r.id, e)
        status, ai = "failed", radiology.template(radiology.get_settings().radiology_report_lang, "file unavailable")
    else:
        status, ai = radiology.read(data, r.hint)
    r.status, r.ai_suggested, r.finished_at = status, ai, datetime.now(UTC)
    db.commit()
    return {"type": "radiograph_reading", "reading_id": r.id, "exam_result_id": r.exam_result_id,
            "patient_id": r.patient_id, "status": r.status}


def recover(db: Session) -> int:
    rows = db.scalars(select(RadiographReading).where(RadiographReading.status == "running")).all()
    for r in rows:
        r.status, r.started_at = "queued", None
    db.commit()
    return len(rows)


def tick(db: Session, publish=None, get=None) -> bool:
    r = claim_next(db)
    if r is None:
        return False
    (publish or publisher.publish_ws_frame)(process(db, r, get=get))
    return True


def run_forever(stop: threading.Event, poll_s: float = 3.0) -> None:
    """Worker thread: one job at a time (one GPU). Never dies on a bad job."""
    with SessionLocal() as db:
        n = recover(db)
        if n:
            log.info("re-queued %d interrupted radiograph readings", n)
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                busy = tick(db)
        except Exception:
            log.exception("radiograph job loop error")
            busy = False
        if not busy:
            stop.wait(poll_s)


def _name(db: Session, user_id: str | None) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return u.name if u else None


def to_out(db: Session, r: RadiographReading, viewer: User) -> dict:
    if viewer.role != "doctor":
        return {"id": r.id, "exam_result_id": r.exam_result_id, "status": r.status}
    return {"id": r.id, "exam_result_id": r.exam_result_id, "patient_id": r.patient_id, "status": r.status,
            "hint": r.hint, "ai_suggested": r.ai_suggested, "final_text": r.final_text,
            "human_confirmed_by": r.human_confirmed_by, "confirmed_by_name": _name(db, r.human_confirmed_by),
            "confirmed_at": iso(r.confirmed_at), "created_at": iso(r.created_at), "finished_at": iso(r.finished_at)}


def confirm(db: Session, r: RadiographReading, user: User, text: str, now: datetime) -> None:
    r.final_text, r.human_confirmed_by, r.confirmed_at = text, user.id, now
    db.get(ExamResult, r.exam_result_id).report_text = text
    db.flush()
```
Fix the `iso` import to the helper `app/services/exams.py` actually uses, and `radiology.get_settings()` to a direct `from app.config import get_settings`.

`backend/app/iot/worker.py` `main()`: after `publisher.use(client)` add
```python
    from app.services import radiology as radiology_jobs  # noqa: PLC0415 (keeps MQTT-only imports light)

    threading.Thread(target=radiology_jobs.run_forever, args=(threading.Event(),), daemon=True,
                     name="radiograph-jobs").start()
```
(move the import to the top if there is no import cycle; add `import threading`).

- [ ] **Step 4:** Tests → PASS; full suite; ruff.
- [ ] **Step 5:** Commit `feat(backend): radiograph reading jobs in the worker (claim, draft, recover, confirm)`.

---

### Task 6: Endpoints, upload hook, catalogue

**Files:** `backend/app/routers/radiology.py`, `backend/app/main.py`, `backend/app/routers/exams.py`, `backend/app/services/exams.py`, `backend/app/ai/rules/exam_bundles.v1.json`, test `backend/tests/test_radiology_api.py`

**Interfaces — Consumes:** Task 5 service; `E.can_read_results`, `check_patient_access`, `storage.put` (tests monkeypatch it — check how `tests/test_exams_api.py` fakes storage and reuse that pattern).

- [ ] **Step 1: Failing tests** `backend/tests/test_radiology_api.py` — write them following `tests/test_exams_api.py` (its login helpers, ordering flow and storage fake). Cases:
  1. Imaging nurse uploads a PNG result for an ordered `chest_xray` → response `results[0].reading.status == "queued"`, one `RadiographReading` row with `hint == "Chest X-ray"`.
  2. Same flow with a PDF → `results[0].reading is None`, no row.
  3. Same flow for an `ecg` order (Cardiology nurse) with a PNG → no reading.
  4. `GET /exam-results/{id}/reading`: attending doctor → 200 with `ai_suggested` and an `audit_log` row (`read`, `radiograph_reading`); Imaging nurse → 200 with keys `{id, exam_result_id, status}` only; patient → 403; admin → 403; doctor without access (new doctor) → 403; result without reading → 404.
  5. `PUT …/reading {"final_text": "Conclusion : normal"}` by the attending doctor → 200, `final_text`, `confirmed_by_name`, exam result `report_text` updated; nurse → 403; empty text → 422.
  6. `POST /patients/p-0001/radiographs` (doctor, PNG, title "Outside X-ray — wrist") → 201 order with `code == "xray_outside"`, `department == "Imaging"`, `status == "done"`, a queued reading; PDF → 422 `bad_file`; nurse → 403; doctor without access → 403.
  7. `GET /exams/catalogue` includes `xray`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement.**
  - `app/routers/radiology.py` (`router = APIRouter(tags=["radiology"])`):
    - `GET /exam-results/{result_id}/reading` — `require_roles("doctor","nurse")`; load result (404 `result`), order; `if not E.can_read_results(db, user, order): raise forbidden("not your patient")`; reading by `exam_result_id` (404 `reading`); doctor → `audit(db, user, "read", "radiograph_reading", r.id, patient_id=r.patient_id, ip=…)`, commit; return `R.to_out`.
    - `PUT /exam-results/{result_id}/reading` — body `ConfirmIn(final_text: str = Field(min_length=1, max_length=20000))` (strip; empty after strip → 422 `invalid`); doctor only; same access checks; `R.confirm(..., datetime.now(UTC))`; `audit(..., "update", "radiograph_reading", ...)`; commit; return `R.to_out`.
    - `POST /patients/{patient_id}/radiographs` (201) — doctor; `check_patient_access(db, user, patient_id, write=True, resource="radiograph", ip=…)`; file must be JPEG/PNG ≤ `E.MAX_BYTES` else 422 `bad_file` ("upload a JPEG or PNG of at most 15 MB"); create done `ExamOrder` (`code="xray_outside"`, `label=(title.strip() or "Outside X-ray")[:120]`, `department="Imaging"`, `status="done"`, `human_confirmed_by=user.id`, `ordered_at=done_at=now`), `storage.put`, `ExamResult`, `R.enqueue(db, result, order.label)`, `audit(..., "create", "radiograph", rid, ...)`, flush, `out = E.to_out(db, o, user)`, commit, return out. Mirror `upload_report` in `routers/exams.py`.
  - `app/main.py`: include `radiology.router`.
  - `app/routers/exams.py` `upload_result`: right after `db.add(ExamResult(...))` keep a reference to the result and add `if R.is_radiograph(o.code, file.content_type): R.enqueue(db, result, o.label)` (import `from app.services import radiology as R`).
  - `app/services/exams.py` `to_out`: each result dict gains `"reading": {"id", "status", "confirmed": final_text is not None}` or `None` (one query per result by `exam_result_id`).
  - `exam_bundles.v1.json` catalogue: add `"xray": {"label": "X-ray (other region)", "department": "Imaging"}` in the same shape as `chest_xray`.
- [ ] **Step 4:** Tests → PASS; full suite; ruff.
- [ ] **Step 5:** Commit `feat(backend): radiograph reading API - read, confirm, outside X-ray upload; enqueue on imaging upload`.

---

### Task 7: Demo radiographs and seed step

**Files:** `backend/app/ai/assets/radiographs/*.jpg`, `backend/app/ai/assets/radiographs/CREDITS.md`, `backend/app/radiograph_seed.py`, `backend/app/seed.py` (`__main__`), test `backend/tests/test_radiograph_seed.py`

Images (all **CC0 1.0**, author **Mikael Häggström, M.D.**, Wikimedia Commons). Download each original, then downscale so the longest side is ≤ 1600 px and re-save as JPEG quality 88 with no metadata (Pillow) to keep the repo small:

| Save as | Commons file | Original URL |
|---|---|---|
| `chest_pa_normal.jpg` | File:Normal posteroanterior (PA) chest radiograph (X-ray).jpg | https://upload.wikimedia.org/wikipedia/commons/a/a1/Normal_posteroanterior_%28PA%29_chest_radiograph_%28X-ray%29.jpg |
| `chest_lobar_pneumonia.jpg` | File:X-ray of lobar pneumonia.jpg | https://upload.wikimedia.org/wikipedia/commons/5/51/X-ray_of_lobar_pneumonia.jpg |
| `foot_dp_normal.jpg` | File:X-ray of normal right foot by dorsoplantar projection.jpg | https://upload.wikimedia.org/wikipedia/commons/6/6f/X-ray_of_normal_right_foot_by_dorsoplantar_projection.jpg |
| `wrist_barton_fracture.jpg` | File:Radiograph of Barton's fracture.jpg | https://upload.wikimedia.org/wikipedia/commons/d/d6/Radiograph_of_Barton%27s_fracture.jpg |
| `hip_prosthesis_ap.jpg` | File:Postoperative radiograph of hip prosthesis - anteroposterior view.jpg | https://upload.wikimedia.org/wikipedia/commons/2/24/Postoperative_radiograph_of_hip_prosthesis_-_anteroposterior_view.jpg |
| `cervical_spine.jpg` | File:Projectional radiograph of cervical foraminal stenosis.jpg | https://upload.wikimedia.org/wikipedia/commons/5/5a/Projectional_radiograph_of_cervical_foraminal_stenosis.jpg |

Before saving, re-check each file's licence through `https://commons.wikimedia.org/w/api.php?action=query&prop=imageinfo&iiprop=extmetadata&format=json&titles=<title>` (`LicenseShortName` must be `CC0`); stop and report if not. Use a User-Agent header (Wikimedia requires one), e.g. `curl -A "WardPrototype/1.0 (hackathon demo)"`.

`CREDITS.md`: one row per file — saved name, Commons page URL (`https://commons.wikimedia.org/wiki/<title with underscores>`), author, licence CC0 1.0, "downscaled to ≤1600 px, metadata removed". Add a line: "Anonymized public-domain teaching images attached to *synthetic* demo patients; they are not those patients' images."

- [ ] **Step 1: Failing test** `backend/tests/test_radiograph_seed.py`

```python
from app.models import ExamOrder, ExamResult, RadiographReading
from app.radiograph_seed import ASSETS, DEMO, seed_radiographs


def test_assets_exist_and_are_credited():
    credits = (ASSETS / "CREDITS.md").read_text(encoding="utf-8")
    for row in DEMO:
        assert (ASSETS / row["file"]).stat().st_size < 1_500_000
        assert row["file"] in credits
    assert "CC0" in credits


def test_seed_radiographs_idempotent(db, seeded):
    put = []
    assert seed_radiographs(db, put=lambda key, data, ct: put.append((key, ct))) == len(DEMO)
    assert len(put) == len(DEMO) and all(ct == "image/jpeg" for _, ct in put)
    assert db.query(RadiographReading).filter(RadiographReading.status == "queued").count() == len(DEMO)
    assert seed_radiographs(db, put=lambda *a: put.append(a)) == 0 and len(put) == len(DEMO)
    o = db.get(ExamOrder, "ex-0901")
    assert o.department == "Imaging" and o.status == "done" and db.get(ExamResult, "er-0901").content_type == "image/jpeg"
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** `backend/app/radiograph_seed.py`

```python
"""Demo radiographs: CC0 teaching images (see ai/assets/radiographs/CREDITS.md) attached to synthetic patients,
each with a queued AI reading. Needs MinIO, so it runs from `python -m app.seed`, not from seed() (tests)."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.ids import reserve_upto
from app.models import ExamOrder, ExamResult, RadiographReading
from app.services import storage

ASSETS = Path(__file__).parent / "ai" / "assets" / "radiographs"
DEMO = [
    {"n": 1, "patient": "p-0001", "code": "chest_xray", "label": "Chest X-ray", "file": "chest_pa_normal.jpg"},
    {"n": 2, "patient": "p-0002", "code": "chest_xray", "label": "Chest X-ray", "file": "chest_lobar_pneumonia.jpg"},
    {"n": 3, "patient": "p-0003", "code": "xray", "label": "X-ray — right foot", "file": "foot_dp_normal.jpg"},
    {"n": 4, "patient": "p-0004", "code": "xray_outside", "label": "Outside X-ray — wrist", "file": "wrist_barton_fracture.jpg"},
    {"n": 5, "patient": "p-0005", "code": "xray", "label": "X-ray — hip", "file": "hip_prosthesis_ap.jpg"},
    {"n": 6, "patient": "p-0006", "code": "xray", "label": "X-ray — cervical spine", "file": "cervical_spine.jpg"},
]


def seed_radiographs(db: Session, put=None) -> int:
    put = put or storage.put
    now, added = datetime.now(UTC), 0
    for d in DEMO:
        oid, rid, rrid = f"ex-09{d['n']:02d}", f"er-09{d['n']:02d}", f"rr-09{d['n']:02d}"
        if db.get(ExamOrder, oid) is not None:
            continue
        outside = d["code"] == "xray_outside"
        db.add(ExamOrder(id=oid, patient_id=d["patient"], code=d["code"], label=d["label"], department="Imaging",
                         status="done", human_confirmed_by="u-0001", ordered_at=now, done_at=now))
        db.flush()
        key = f"exams/{oid}/{rid}/{d['file']}"
        data = (ASSETS / d["file"]).read_bytes()
        put(key, data, "image/jpeg")
        db.add(ExamResult(id=rid, exam_order_id=oid, patient_id=d["patient"],
                          uploaded_by="u-0001" if outside else "u-0006", file_key=key, file_name=d["file"],
                          content_type="image/jpeg", size_bytes=len(data)))
        db.flush()
        db.add(RadiographReading(id=rrid, exam_result_id=rid, patient_id=d["patient"], status="queued",
                                 hint=d["label"]))
        added += 1
    db.flush()
    for prefix in ("ex", "er", "rr"):
        reserve_upto(db, prefix, 900 + len(DEMO))
    return added
```
`backend/app/seed.py` `__main__`: after `seed(s)`, call `n = seed_radiographs(s)` then `s.commit()`, and print `f"demo radiographs: {n} added"`. Do not call it from `seed()`.

- [ ] **Step 4:** Tests → PASS; full suite.
- [ ] **Step 5:** Commit `feat(backend): six CC0 demo radiographs attached to synthetic patients, seeded with queued readings`.

---

### Task 8: Web data layer

**Files:** `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/mocks/exams.ts` (and `mocks/index.ts` if needed), `web/src/lib/labels.ts`, `web/src/i18n/messages/shared.ts`, `web/src/i18n/messages/radiology.ts`, `web/src/i18n/messages/index.ts`

**Produces:** types `ReadingStatus`, `RadiographCondition`, `RadiographAi`, `RadiographReading`, `ExamResultFile.reading?: {id: string; status: ReadingStatus; confirmed: boolean} | null`; api `getRadiographReading(resultId: string): Promise<RadiographReading>`, `confirmRadiographReading(resultId: string, finalText: string): Promise<RadiographReading>`, `uploadOutsideRadiograph(patientId: string, file: File, title: string): Promise<ExamOrder>`; i18n namespace `radiology`.

- [ ] **Step 1: Types** (append to `types.ts`, comment `// ── Radiograph reading (api.md 1.14) ──`):
```ts
export type ReadingStatus = "queued" | "running" | "ready" | "unavailable" | "failed";
export interface RadiographCondition { name: string; likelihood: "low" | "medium" | "high"; evidence: string; }
export interface RadiographAi {
  source: AiSource; model?: string; reason?: string; region?: string; projection?: string; quality?: string;
  findings?: string[]; impression?: string; possible_conditions?: RadiographCondition[]; urgent_flags?: string[];
  recommendation?: string; draft_text: string; disclaimer: string;
}
export interface RadiographReading {
  id: string; exam_result_id: string; status: ReadingStatus; patient_id?: string; hint?: string;
  ai_suggested?: RadiographAi | null; final_text?: string | null; human_confirmed_by?: string | null;
  confirmed_by_name?: string | null; confirmed_at?: string | null; created_at?: string; finished_at?: string | null;
}
```
and add `reading?: { id: string; status: ReadingStatus; confirmed: boolean } | null;` to `ExamResultFile`.
- [ ] **Step 2: API** (real: `http("GET", /exam-results/{id}/reading)`, `http("PUT", …, {final_text})`, `upload(/patients/{id}/radiographs, form{file,title})`). Mock mode: readings live in the mock store keyed by result id; `getRadiographReading` returns a deep copy; a reading in `queued` advances to `ready` (canned draft) after ~6 s of mock time so the polling UI can be seen; `confirmRadiographReading` sets `final_text`, `confirmed_by_name: "Dr Trabelsi"`, `confirmed_at`, and updates the result's `report_text`; `uploadOutsideRadiograph` rejects like `uploadReport` (`needs_backend`).
- [ ] **Step 3: Mocks** — in `mocks/exams.ts` add for the mock doctor's patient p-0001 a done `chest_xray` (Imaging) with one image result (`chest_pa_normal.jpg`, `image/jpeg`) whose `reading` is `{status:"ready"}` with a canned French draft (findings, impression, 1 condition `high`, no urgent flags, disclaimer exact), and a second done `xray_outside` "Outside X-ray — wrist" whose reading starts `queued` and becomes `ready` with an urgent flag ("Fracture déplacée du radius distal possible") and a `medium` condition. `examFileUrl` mock for these results may return a placeholder data URL (a small grey PNG) — no real image needed in mock mode.
- [ ] **Step 4: Labels** — add `xray` and `xray_outside` to `EXAM_CODES` in `labels.ts` with `shared.exam_xray` ("X-ray (other region)" / "Radiographie (autre région)" / "صورة بالأشعة (منطقة أخرى)") and `shared.exam_xray_outside` ("Outside X-ray" / "Radiographie externe" / "صورة أشعة من الخارج") in `shared.ts` (all three languages). If `examLabel` would hide the doctor's custom title for `xray_outside`, keep `exam.label` for that code instead.
- [ ] **Step 5: i18n `radiology`** (en/fr/ar, identical keys and placeholders): `title` "AI radiograph reading", `statusQueued` "AI reading queued", `statusRunning` "AI reading…", `statusReady` "AI draft ready", `statusUnavailable` "AI unavailable — write the report", `statusFailed` "Image unreadable — write the report", `statusConfirmed` "Report confirmed", `review` "Review report", `hide` "Hide", `disclaimer` "AI draft from a prototype, not a diagnosis and not clinically validated. Review every line.", `region` "Region", `projection` "Projection", `quality` "Image quality", `findings` "Findings", `impression` "Impression", `conditions` "Possible conditions", `likelihoodLow` "low", `likelihoodMedium` "medium", `likelihoodHigh` "high", `urgent` "Urgent signs", `recommendation` "Recommendation", `report` "Report (you sign this)", `confirm` "Confirm report", `confirmed` "Confirmed by {name} · {when}", `saveError` "Couldn’t save the report.", `loadError` "Couldn’t load the AI reading.", `model` "Model: {model}", `noModel` "No AI model available: write the report from the template.", `addOutside` "Add outside X-ray", `outsideTitle` "Title", `outsideTitleDefault` "Outside X-ray", `outsideFile` "Image (JPEG or PNG)", `upload` "Upload", `uploading` "Uploading…", `uploadError` "Couldn’t upload the image.", `cancel` "Cancel", `imageAlt` "Radiograph image". Register in `messages/index.ts`.
- [ ] **Step 6:** `npm run typecheck` → clean. Commit `feat(web): radiograph reading data layer - types, api (mock + real), mocks, en/fr/ar strings`.

---

### Task 9: Web UI — reading card, polling, outside upload

**Files:** `web/src/components/shared/RadiographReadingCard.tsx` + `.module.css`, `web/src/components/shared/ExamsPanel.tsx` (+ css), `web/src/components/doctor/PatientDetail.tsx`

- [ ] **Step 1: `ExamsPanel`** gets an optional prop `role?: Role` (doctor's `PatientDetail` passes `role="doctor"`; other callers unchanged). For each result with `r.reading`: a status chip (`radiology.status*`; `statusConfirmed` when `reading.confirmed`), and for doctors a `radiology.review` / `hide` toggle that renders `<RadiographReadingCard resultId={r.id} onConfirmed={reload} />` under the row. Doctors also get an `radiology.addOutside` button in the panel header that opens a small inline form (file input `accept="image/jpeg,image/png"`, title input defaulting to `outsideTitleDefault`, Upload/Cancel); on success reload the exams list; errors show `uploadError` (or the `needs_backend` message in mock mode). Extract the list fetch into a `reload()` used by the effect.
- [ ] **Step 2: `RadiographReadingCard`** ("use client"): loads `getRadiographReading(resultId)`; while status is `queued`/`running` re-fetches every 4 s (interval cleared on unmount and when finished; alive guard). Shows: image preview (`examFileUrl(resultId)` → `<img alt={t("radiology.imageAlt")}>`, max-height 280 px, revoke blob URLs on unmount); the disclaimer in a warning banner (always visible); when `ai_suggested.source === "llm"`: region/projection/quality line, `model` caption, urgent flags as danger chips (`--danger-*` tokens) at the top, findings list, possible conditions (name + likelihood chip: low `--news-low-*`, medium `--news-high-*`, high `--news-crit-*` + evidence in muted text), impression, recommendation; when `source === "rules"`: `noModel` (or `statusFailed`) note. Then the report textarea (`radiology.report`, ~12 rows, prefilled `final_text ?? ai_suggested.draft_text ?? ""`, `dir="auto"`), Confirm button (disabled while saving or empty) → `confirmRadiographReading` → shows `radiology.confirmed` with name and `tunisDay`/`tunisTime`, calls `onConfirmed`. Errors → `saveError` / `loadError`. Design tokens only, logical CSS properties (RTL), focus-visible outlines, matching `ExamsPanel.module.css` look.
- [ ] **Step 3: Verify** `npm run typecheck`, `npm run build`. Dev server in mock mode (`npx next dev -p 3100` from `web/`; delete any generated `web/AGENTS.md`/`web/CLAUDE.md`): `/doctor/patients/p-0001` (or wherever `PatientDetail` renders) → Exams card shows the two radiographs; "Review report" opens the ready draft; the outside wrist reading moves from "AI reading…" to "AI draft ready" by itself with the urgent flag on top; editing and confirming shows "Confirmed by Dr Trabelsi"; Arabic layout mirrors. Stop the dev server.
- [ ] **Step 4:** Commit `feat(web): AI radiograph reading card with live status, doctor confirmation, outside X-ray upload`.

---

### Task 10: Real-model smoke test, docs, push

- [ ] **Step 1:** `ollama pull qwen3-vl:4b` (≈3–4 GB; skip if present). From `backend/`, for each of the 6 demo images: `VISION_PROVIDER=local LLM_LOCAL_BASE_URL=http://localhost:11434 "D:/Projects 2026/smarty-hospital-/backend/.venv/Scripts/python" -m app.ai.radiology app/ai/assets/radiographs/<file> "<label>"`. Record status, seconds and a 1-line gist per image in the report. If outputs are malformed or the model ignores the language, tune `prompts/radiograph_report.v1.md` (it's versioned: edit v1 in place since it never shipped) and, if Ollama rejects a parameter, adjust `complete_vision_json` (keep the tests green). If `qwen3-vl:4b` is not available on this Ollama, try `qwen2.5vl:3b` and report.
- [ ] **Step 2:** README / `n8n`-free docs: add a short "AI radiograph reading" section to `README.md` only if the README has a features list (it is Faouzi's file — otherwise put the run instructions at the top of `backend/app/ai/radiology.py` docstring, already there): pull the model, set `VISION_PROVIDER=local`, `python -m app.seed` adds the 6 demo X-rays.
- [ ] **Step 3:** Full backend suite, `npm run typecheck`, `npm run build`.
- [ ] **Step 4:** `git push -u origin wali/radiograph-reading`. Prepare the PR text (base `main`; note it builds on the calendar PR; contract bumps api 1.14 / data-model 1.8 need 👍; tag @Faouzi-Blibech for `backend/app/ai/` and `web/`; test plan with the smoke timings; no AI attribution).
