# Faouzi (lead) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Next.js PWA (doctor → nurse → admin → patient views), the AI layer (triage, doctor copilot, patient assistant), the appointments/waitlist API and the n8n workflows. Then lead the demo and the pitch.

**Architecture:**
- **Web:**
  - One Next.js App Router app in `web/` with role-based route groups.
  - A typed API client that switches between fixtures (`NEXT_PUBLIC_USE_MOCKS=1`) and the real FastAPI.
  - One WebSocket hook for live frames.
- **AI:**
  - Reworked 2026-10-06 (spec: `docs/superpowers/specs/2026-10-06-ai-rework-design.md`). Hand-coded rules plus small trained models decide; no LLM is needed.
  - Triage = red-flag rules + a trained char n-gram classifier. Assistant = keyword rules + the same kind of classifier, templated answers. Copilot = templates + rule interactions.
  - An optional open LLM (`LLM_PROVIDER=groq|local`) may rewrite the copilot summary through `llm.py`. It strips PII, times out at 15 s and raises `LLMUnavailable`; the template text is kept then.
  - `source` is `"model"`, `"rules"` or `"llm"`.
- **n8n:** one router workflow on `/webhook/ward-events` that fans out on `event`.

**Tech stack:** Next.js 16 + React 19 + TypeScript (strict) + Tailwind v4 + Recharts · Python 3.12, FastAPI, Pydantic v2, scikit-learn (training only), httpx (Groq or Ollama, optional), MinIO · n8n self-hosted, Telegram Bot API, SMTP.

**Spec:** `docs/superpowers/specs/2026-10-05-ward-foundation-design.md` · read also `CLAUDE.md`, `docs/architecture.md`, `TEAM_PLAN.md` and all of `docs/contracts/` (you own `api.md` → Appointments/AI/Integrations and all of `n8n-webhooks.md`).

**Now: core first (`TEAM_PLAN.md` §0).** Extras are frozen until the medication loop runs end to end. Your part of it:
1. **Doctor view: prescribe + see adherence** (core step 4). UI from Claude Design, wired to `api.md` (`POST /patients/{id}/prescriptions`, doses taken / missed per day) on mocks until Wali's API lands.
2. **Missed dose → nurse** (core step 6): n8n W3 is built; wire it to Wali's `dose.missed` emitter and show the alert in the nurse view.
3. Then the extras, in the order of `TEAM_PLAN.md` §0 step 7.

**You are:** Faouzi, team lead and presenter, **Doctor + Admin role owner**. You own `web/`, `n8n/`, `docs/`, `backend/app/ai/` (except `early_warning.py` (Wali) and `no_show/` (Hedi)), and `backend/app/routers/{appointments,ai,integrations}.py`.

## Global Constraints

- Contracts v1.0 are frozen; changes need a version bump, an announcement and a 👍.
- **Human in the loop:** every AI output is stored with `ai_suggested` (including `source`) plus a confirmer, and the UI shows the badge "AI suggestion · needs confirmation" until a human confirms it.
- **Every AI module works with no LLM.** The full demo must run with `LLM_PROVIDER=none` and no internet.
- Models are trained only on synthetic data in `backend/app/ai/data/`; training scripts live in `backend/app/ai/training/`.
- Any optional LLM call goes through `backend/app/ai/llm.py` (open models only). Prompts live in `backend/app/ai/prompts/<name>.v1.md`, rules in `backend/app/ai/rules/*.v1.json`; never inline them.
- PII stripping before any optional LLM call: patient names, phone numbers, emails, `p-\d{4}`-style IDs, 8-digit Tunisian CIN numbers.
- UI copy never claims medical-grade sensing or clinically validated AI; vitals are simulated (the bedside unit has no sensors since PR #13). Pitch framing: "automates the patient process; shorter waits are a result".
- Optional LLM model: `LLM_MODEL` in `.env.example` (open models only: Groq or Ollama). Anthropic is removed.
- No AI attribution in commits/PRs. Branches: `faouzi/<feature>`. Conventional Commits.
- Your lane is the widest. **Cut order if you fall behind:** patient assistant → W6 → W5 → W2 → patient view polish. Then hand the patient view to Hedi and `routers/integrations.py` to Wali (`TEAM_PLAN.md` §7).

## Review Focus

1. **No LLM, or a broken one** (`LLM_PROVIDER=none`, no key, timeout, invalid JSON): every AI endpoint still returns 200 with `source` `"model"` or `"rules"` (the tests in `test_triage.py`, `test_copilot.py`, `test_assistant.py`).
2. **Red flag + a low model score:** "douleur thoracique" must come out ≥ 5 whatever the trained model says. The rules set a floor the model cannot lower.
3. **Arabic / Darija / mixed-script referral text** (`ألم في الصدر`, `waja3 fi sadri`): red-flag matching must work across scripts and accents (Task 5 test `test_red_flag_arabic_and_darija`).
4. **The admin overrides the AI urgency,** and the waitlist re-sorts using `urgency_final` first (Task 6 test `test_waitlist_uses_final_over_ai`).
5. **WebSocket drops mid-demo:** the nurse dashboard must auto-reconnect (backoff 1 s → 10 s) and show a "reconnecting" pill, never a blank page (Task 3, manual check: restart the `api` container).

---

## Interfaces you PROVIDE

```python
# backend/app/ai/llm.py
class LLMUnavailable(Exception): ...
def strip_pii(text: str, names: Iterable[str] = ()) -> str
def complete_json(prompt_name: str, user_text: str, schema: type[T], *, names: Iterable[str] = ()) -> T
    # raises LLMUnavailable on any failure (provider none, network, bad JSON)

# backend/app/ai/triage.py
class TriageResult(BaseModel):
    urgency: int; reasons: list[str]; red_flags: list[str]; source: str  # "model" | "rules"
    model_urgency: int | None; confidence: float | None
def triage(referral_text: str, symptoms: list[str], age: int | None) -> TriageResult

# backend/app/ai/copilot.py (DB-free; the router loads the rows)
def summarize(vitals: list[dict], notes: list[str], meds: list[str], names: list[str]) -> dict
    # {"summary", "interactions", "source", "generated_at"}: "rules" by default, "llm" if an open LLM rewrote the text
def check_interactions(med_names: list[str]) -> list[dict]

# backend/app/ai/assistant.py (DB-free; the router loads only the caller's own rows)
def assistant_context(patient, doses_today, next_visit, latest_vital, *, now) -> dict
def answer(question: str, ctx: dict) -> dict   # {"answer", "sources", "intent", "source": "model"|"rules"}
```

REST: `api.md` → Appointments, AI and Integrations sections (you implement those routers on Wali's models and deps).

## Interfaces you CONSUME

| From | What | Until it exists, use |
|---|---|---|
| Wali | `app.models.*`, `app.auth.deps.{get_current_user, require_roles, check_patient_access}`, `app.services.audit.audit`, `app.ids.new_id`, `app.integrations.n8n.emit` | Day 1: build `ai/` modules as pure functions with unit tests; mount routers once Wali's Task 3 merges |
| Wali | REST `/auth`, `/patients…`, `/alerts`, `/prescriptions`, `/devices`, `WS /ws` | `web/src/mocks/*.json` + the mock WS in `web/src/lib/ws.ts` |
| Hedi | Device/simulator traffic | `python simulator/sim.py --scenario abnormal` (Day 0+) |
| Hedi | `predict_no_show`, `rank_backfill` (Day 3) | `no_show_prob = 0.20`, waitlist sort only |

---

## Day 0 — Mon 10-05

### Task 1: Web foundation + mocks + n8n/Telegram setup

**Files:**
- Create:
  - `web/src/lib/{types,api,ws,auth}.ts`
  - `web/src/mocks/{patients,patient-p-0001,vitals-p-0001,alerts,waitlist,devices,prescriptions-p-0001,me-doctor,me-nurse,me-admin,me-patient}.json`
  - `web/src/app/login/page.tsx`
  - `web/src/app/globals.css`
  - `web/public/manifest.webmanifest`
- Modify: `web/package.json` (add `tailwindcss@4`, `@tailwindcss/postcss`, `recharts`), `web/src/app/layout.tsx`

- [ ] **Step 1:** `types.ts` mirrors `api.md` exactly: `PatientSummary`, `Patient`, `Vital`, `Note`, `Prescription`, `Appointment`, `Alert`, `Device`, `Me` and `WsFrame` (a discriminated union on `type`). Every mock JSON must type-check against these.
- [ ] **Step 2:** `api.ts` (a single place for HTTP):

```ts
// web/src/lib/api.ts
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

const mockRoutes: Record<string, () => Promise<unknown>> = {
  "GET /patients": () => import("@/mocks/patients.json").then((m) => m.default),
  "GET /patients/p-0001": () => import("@/mocks/patient-p-0001.json").then((m) => m.default),
  "GET /patients/p-0001/vitals": () => import("@/mocks/vitals-p-0001.json").then((m) => m.default),
  "GET /alerts": () => import("@/mocks/alerts.json").then((m) => m.default),
  "GET /appointments/waitlist": () => import("@/mocks/waitlist.json").then((m) => m.default),
  "GET /devices": () => import("@/mocks/devices.json").then((m) => m.default),
};

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const key = `${method} ${path.split("?")[0]}`;
  if (MOCKS && mockRoutes[key]) return (await mockRoutes[key]()) as T;
  const token = typeof window !== "undefined" ? localStorage.getItem("ward_token") : null;
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${(await res.json().catch(() => ({}))).detail ?? res.statusText}`);
  return (await res.json()) as T;
}
```

- [ ] **Step 3:** `ws.ts` exports `useWard(onFrame)`. In mock mode it emits a `vital` frame every 3 s and an `alert` every 30 s. In real mode it connects to `ws://…/ws?token=` and reconnects with backoff from 1 s up to 10 s, exposing `status: "live" | "reconnecting"`.
- [ ] **Step 4:** Login page: email + password → `/auth/login` → store the token and the `me` object → redirect by role (`/doctor`, `/nurse`, `/admin`, `/patient`). In mock mode, four "log in as…" buttons.
- [ ] **Step 5:** Install and configure Tailwind v4. Add a minimal `manifest.webmanifest` (name "Medora", theme colour, icons 192/512) linked from `layout.tsx` so the app installs on phones.
- [ ] **Step 6:** Create the Telegram bot via @BotFather. Get your chat ID (message the bot, then `https://api.telegram.org/bot<token>/getUpdates`). Create the n8n credentials per `n8n/README.md`.
- [ ] **Step 7:** `npm run build` passes. Commit `feat(web): api client, mocks, ws hook, login`.

**Day 0 done when:** `npm run dev` with mocks lets you "log in as" each role and reach an (empty) page, and the Telegram bot replies to you.

---

## Day 1 — Tue 10-06

### Task 2: Doctor view (patient list + patient detail)

**Files:** Create `web/src/app/doctor/page.tsx`, `web/src/app/doctor/patients/[id]/page.tsx`, `web/src/components/{VitalsChart,News2Badge,AiBadge,PatientHeader}.tsx`

- [ ] `/doctor`: a table of the doctor's patients (`GET /patients`), with name, age, bed, the latest NEWS2 badge (0 green · 1–4 amber · ≥5 red) and an open-alerts count. Rows link to the detail page.
- [ ] `/doctor/patients/[id]`:
  - header (name, age, allergies in red, bed/device)
  - **VitalsChart** (Recharts, 24 h, three lines with the NEWS2 band shading), live-updated from WS `vital` frames for this patient
  - prescriptions list + a "New prescription" form (meds, times, slot 1–8, days, care plan) → `POST /prescriptions`, with a toast saying "Sent to bedside unit ✓" or "No device assigned"
  - notes timeline
  - an **AI daily summary card** (Task 7) with `AiBadge`
- [ ] `AiBadge` shows `source` (`AI` or `Fallback`) and "Needs review", which switches to "Reviewed by Dr …" after a click.
- [ ] Commit `feat(web): doctor views`.

### Task 3: Nurse view (ward board + alerts)

**Files:** Create `web/src/app/nurse/page.tsx`, `web/src/components/{AlertsPanel,BedCard,ConnectionPill}.tsx`

- [ ] A ward board: one `BedCard` per patient (bed, first name, live HR/SpO2/temp, NEWS2 colour, device online dot). Frames update it live.
- [ ] `AlertsPanel`: open alerts newest first, with critical ones flashing red. An **Ack** button calls `POST /alerts/{id}/ack`. `call_nurse` frames pop a toast with the bed number, plus a sound (`new Audio('/ding.mp3')`).
- [ ] A med-round checklist per patient: today's doses with their status (scheduled/dispensed/taken/missed), from `GET /patients/{id}/prescriptions` plus `dose_event` frames.
- [ ] `ConnectionPill` shows `live` / `reconnecting`.
- [ ] **CP1 (end of day, with Wali):** switch to `NEXT_PUBLIC_USE_MOCKS=0`; simulator vitals move the nurse board in under 2 s.
- [ ] Commit `feat(web): nurse ward board and alerts`.

### Task 4: n8n W4 (critical-alert fan-out)

**Files:** Create `n8n/workflows/W0-router.json`, `n8n/workflows/W4-critical-alert.json`

- [ ] **W0 router:**
  1. Webhook node `POST /webhook/ward-events`.
  2. IF `{{$json.headers["x-ward-secret"]}} == {{$env.N8N_EVENT_SECRET}}`, otherwise respond 401.
  3. Switch on `{{$json.body.event}}`, with an "Execute Workflow" call for each W*n*.
- [ ] **W4:** for each `nurse_chat_ids[]` plus `doctor_chat_id`, send a Telegram message: `🚨 Bed {{bed}} · {{patient_first_name}} · NEWS2 {{news2}}: {{message}}`.
- [ ] Test: `curl -X POST localhost:5678/webhook/ward-events -H "X-Ward-Secret: change-me-event" -H "Content-Type: application/json" -d '{"event":"alert.critical","ts":"2026-10-06T10:00:00Z","data":{"patient_first_name":"Amira","bed":"C-12","kind":"news2","news2":8,"message":"SpO2 88%, HR 130","nurse_chat_ids":["<yours>"],"doctor_chat_id":"<yours>"}}'` → a Telegram message arrives.
- [ ] Export both workflows to `n8n/workflows/` and commit `feat(n8n): router + W4 critical alert`.

**Day 1 done when:** CP1 passes (live simulator vitals on the nurse board via the real API), and the W4 curl test delivers a Telegram message.

---

## Day 2 — Wed 10-07

### Task 5: LLM wrapper + triage

> **Historical (superseded 2026-10-06).** The steps and code below describe the original LLM-first design. The shipped design is in the AI rework spec; triage no longer calls an LLM and takes no `history`.

**Files:**
- Create:
  - `backend/app/ai/{llm,triage}.py`
  - `backend/app/ai/prompts/triage.v1.md`
  - `backend/app/ai/rules/red_flags.v1.json`
- Test: `backend/tests/test_llm.py`, `backend/tests/test_triage.py`

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_llm.py
from app.ai.llm import strip_pii

def test_strip_pii():
    t = "Amira Ben Salah (p-0007), tel 98 123 456, CIN 01234567, amira@mail.tn"
    out = strip_pii(t, names=["Amira", "Ben Salah"])
    for leak in ["Amira", "Ben Salah", "p-0007", "98 123 456", "01234567", "amira@mail.tn"]:
        assert leak not in out
```

```python
# backend/tests/test_triage.py
import pytest
from app.ai import triage as T
from app.ai.llm import LLMUnavailable

def fake_llm(urgency):
    def _f(prompt_name, user_text, schema, **kw):
        return schema(urgency=urgency, reasons=["llm"], red_flags=[])
    return _f

def test_red_flag_floor_beats_llm(monkeypatch):
    monkeypatch.setattr(T, "complete_json", fake_llm(2))
    r = T.triage("Douleur thoracique depuis 2 jours", [], 55)
    assert r.urgency == 5 and "chest_pain" in r.red_flags and r.source == "llm"

@pytest.mark.parametrize("text", ["ألم في الصدر منذ يومين", "3andi waja3 fi sadri", "chest pain at rest"])
def test_red_flag_arabic_and_darija(monkeypatch, text):
    monkeypatch.setattr(T, "complete_json", fake_llm(1))
    assert T.triage(text, [], 40).urgency == 5

def test_triage_fallback_when_llm_unavailable(monkeypatch):
    def boom(*a, **k): raise LLMUnavailable("down")
    monkeypatch.setattr(T, "complete_json", boom)
    r = T.triage("Contrôle de routine, pas de plainte", [], 30)
    assert r.source == "fallback" and 1 <= r.urgency <= 2

def test_no_flag_keeps_llm_score(monkeypatch):
    monkeypatch.setattr(T, "complete_json", fake_llm(4))
    assert T.triage("toux légère", [], 30).urgency == 4
```

Run: `pytest tests/test_llm.py tests/test_triage.py -v`, expected FAIL (modules missing).

- [ ] **Step 2: Implement `llm.py`**

```python
# backend/app/ai/llm.py
"""Single gateway for every LLM call. Strips PII, routes on LLM_PROVIDER, never hangs the demo."""
import base64, json, re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TypeVar

import anthropic
import httpx
from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)
PROMPTS = Path(__file__).parent / "prompts"

class LLMUnavailable(Exception):
    pass

_PATTERNS = [
    (re.compile(r"\b[pu]-\d{4}\b"), "[ID]"),
    (re.compile(r"\b\d{8}\b"), "[CIN]"),
    (re.compile(r"(\+216\s?)?\b\d{2}\s?\d{3}\s?\d{3}\b"), "[PHONE]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
]

def strip_pii(text: str, names: Iterable[str] = ()) -> str:
    for rx, rep in _PATTERNS:          # structured identifiers first (emails contain names)
        text = rx.sub(rep, text)
    for n in sorted((n for n in names if n), key=len, reverse=True):
        text = re.sub(re.escape(n), "[NAME]", text, flags=re.IGNORECASE)
    return text

def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.v1.md").read_text(encoding="utf-8")

def complete_json(prompt_name: str, user_text: str, schema: type[T], *,
                  names: Iterable[str] = (), images: Sequence[tuple[bytes, str]] = ()) -> T:
    s = get_settings()
    text = strip_pii(user_text, names)
    try:
        if s.llm_provider == "anthropic":
            return _anthropic(s, _prompt(prompt_name), text, schema, images)
        if s.llm_provider == "local":
            return _ollama(s, _prompt(prompt_name), text, schema, images)
    except LLMUnavailable:
        raise
    except Exception as e:  # timeout, network, validation, rate limit...
        raise LLMUnavailable(str(e)) from e
    raise LLMUnavailable(f"provider={s.llm_provider}")

def _anthropic(s, system: str, text: str, schema: type[T], images) -> T:
    client = anthropic.Anthropic(api_key=s.anthropic_api_key or None, timeout=s.llm_timeout_s, max_retries=0)
    content: list[dict] = [
        {"type": "image", "source": {"type": "base64", "media_type": mt, "data": base64.b64encode(b).decode()}}
        for b, mt in images
    ]
    content.append({"type": "text", "text": text})
    resp = client.messages.parse(
        model=s.llm_model, max_tokens=4000, system=system,
        messages=[{"role": "user", "content": content}], output_format=schema,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise LLMUnavailable(f"stop_reason={resp.stop_reason}")
    return resp.parsed_output

def _ollama(s, system: str, text: str, schema: type[T], images) -> T:
    msg = {"role": "user", "content": text}
    if images:
        msg["images"] = [base64.b64encode(b).decode() for b, _ in images]
    r = httpx.post(f"{s.llm_local_base_url}/api/chat", timeout=s.llm_timeout_s, json={
        "model": s.llm_local_model, "stream": False, "format": schema.model_json_schema(),
        "messages": [{"role": "system", "content": system}, msg]})
    r.raise_for_status()
    return schema.model_validate(json.loads(r.json()["message"]["content"]))
```

The structured-output call (`client.messages.parse(..., output_format=PydanticModel)` → `resp.parsed_output`) follows the Anthropic Python SDK docs. If you upgrade the SDK and a name changes, check `anthropic`'s README rather than guessing.

- [ ] **Step 3: `rules/red_flags.v1.json`.** Each entry is `{id, min_urgency, keywords[]}`, with keywords in FR, EN, Arabic and Darija (Latin script with digits). Required entries:
  - `chest_pain` (5): `douleur thoracique`, `chest pain`, `ألم في الصدر`, `وجع في صدري`, `waja3 fi sadri`, `sadri yoja3ni`
  - `stroke_signs` (5): `avc`, `paralysie`, `bouche déviée`, `stroke`, `شلل`, `جلطة`, `fama chalal`
  - `severe_bleeding` (5): `hémorragie`, `saignement abondant`, `severe bleeding`, `نزيف`, `dam barcha`
  - `breathing` (5): `dyspnée`, `essoufflement`, `difficulty breathing`, `ضيق في التنفس`, `ma najjamch nitnaffes`
  - `loss_of_consciousness` (5): `perte de connaissance`, `syncope`, `fainted`, `إغماء`, `ghabt`
  - `pregnancy_bleeding` (5): `enceinte saignement`, `pregnant bleeding`, `حامل نزيف`
  - `high_fever_child` (4): `fièvre nourrisson`, `bébé fièvre`, `baby fever`, `سخانة رضيع`

  Matching: lowercase, strip Latin accents (`unicodedata` NFKD), collapse whitespace, then substring match on the referral text plus the symptoms joined together.
- [ ] **Step 4: `prompts/triage.v1.md`.** The prompt:
  - asks for urgency 1–5 as JSON `{urgency, reasons[], red_flags[]}`, given a referral in Arabic/French/Darija, the age and the history
  - **forbids diagnosis**, and asks for a conservative score when unsure
  - includes a 1–5 anchor scale (5 = possible life threat today, 1 = routine follow-up)
- [ ] **Step 5: `triage.py`.** `triage()` builds the user text, calls `complete_json("triage", …, schema=_LlmTriage)`, clamps the score to 1–5, and applies the floor: `urgency = max(llm, max(min_urgency of matched flags))`. On `LLMUnavailable`, it falls back to `max(rule floor, 2 if age ≥ 75 else 1)` with `source="fallback"` and reasons from the matched flags (or "No red flag found; routine priority").
- [ ] **Step 6:** `pytest -v` passes. Commit `feat(ai): llm wrapper with pii stripping + triage with red-flag floor`.

### Task 6: Appointments & waitlist API + admin view

**Files:**
- Create: `backend/app/routers/appointments.py`, `backend/app/services/appointments.py`, `web/src/app/admin/{page,waitlist/page,devices/page}.tsx`
- Test: `backend/tests/test_appointments.py`

- [ ] **Step 1: Failing tests** (use Wali's `client` fixture from `tests/conftest.py` and the `login` helper from `tests/helpers.py`)

```python
# backend/tests/test_appointments.py
from tests.helpers import login

def test_request_runs_triage(client, monkeypatch):
    from app.ai import triage as T
    monkeypatch.setattr(T, "complete_json", lambda *a, **k: (_ for _ in ()).throw(T.LLMUnavailable("x")))
    h = login(client, "patient@medora.tn")
    r = client.post("/appointments", headers=h, json={"patient_id": "p-0001",
                    "referral_text": "douleur thoracique", "symptoms": [], "preferred_dates": []})
    assert r.status_code == 200 and r.json()["urgency_ai"] == 5 and r.json()["status"] == "requested"

def test_waitlist_uses_final_over_ai(client):
    h = login(client, "admin@medora.tn")
    wl = client.get("/appointments/waitlist", headers=h).json()
    last = wl[-1]["id"]
    r = client.patch(f"/appointments/{last}", headers=h, json={"urgency_final": 5})
    assert r.status_code == 200 and r.json()["human_confirmed_by"] == "u-0004"
    assert client.get("/appointments/waitlist", headers=h).json()[0]["id"] == last

def test_patient_cannot_confirm(client):
    h = login(client, "patient@medora.tn")
    assert client.post("/appointments/a-0001/confirm", headers=h, json={}).status_code == 403
```

- [ ] **Step 2: Implement:**
  - `POST /appointments` → `triage()` → store `urgency_ai` and `ai_suggested` (the full triage result) → `no_show_prob` = `predict_no_show(...)` if Hedi's module is importable, otherwise `0.20`.
  - `GET /appointments/waitlist`: sort by `coalesce(urgency_final, urgency_ai) DESC, created_at ASC`.
  - `PATCH /appointments/{id}` `{urgency_final}`: a human override without booking; sets `human_confirmed_by`.
  - `confirm`: sets `confirmed_by`, `human_confirmed_by`, `slot_at`, `doctor_id`, plus the optional `urgency_final`, then `emit("appointment.confirmed", …)`.
  - `cancel` and `reply`: per `api.md`, emitting `appointment.cancelled`.
- [ ] **Step 3: Admin web:**
  - `/admin/waitlist`: a ranked table showing urgency with the AI badge, the red flags as chips, the reasons in a tooltip, an "Override" dropdown, and a "Confirm + pick slot" datetime picker. Override changes are highlighted ("Human override").
  - `/admin/devices`: device list with online status, plus assign to patient/bed (`POST /devices/{id}/assign`) and discharge.
  - `/admin`: KPI tiles (patients admitted, open alerts, waitlist length, devices online, no-shows avoided = confirmed reminders).
- [ ] Commit `feat(appointments): triage-ranked waitlist, confirm/override; admin views`.

### Task 7: Doctor copilot summary

> **Historical (superseded 2026-10-06).** The summary is now a template; an LLM only rewrites it when `LLM_PROVIDER` is set.

**Files:**
- Create: `backend/app/ai/copilot.py`, `backend/app/ai/prompts/summary.v1.md`, `backend/app/ai/rules/interactions.v1.json`, `backend/app/routers/ai.py`
- Test: `backend/tests/test_copilot.py`

- [ ] `interactions.v1.json` (demo scope, curated) has entries `{"drugs":["warfarin","aspirin"],"severity":"high","note":"bleeding risk"}` for: warfarin+aspirin, warfarin+ibuprofen, lisinopril+spironolactone (hyperkalaemia), clarithromycin+simvastatin (myopathy), metformin+iodinated contrast (lactic acidosis), sertraline+tramadol (serotonin syndrome). Matching is case-insensitive substring on the active prescription item names.
- [ ] `daily_summary(db, patient_id)`:
  1. Load the last 24 h of vitals (min/max/latest, NEWS2 max), notes and active meds.
  2. Compute the interactions with the **rules, never the LLM**.
  3. Call `complete_json("summary", …, names=[first, last])` for a ≤ 120-word summary.
  4. The fallback is a template: "Last 24h: HR {min}–{max} (latest {x}), SpO2 …, Temp …, max NEWS2 {n}. {k} nurse notes. Active meds: …".
  5. Store it in `ai_summaries`.
- [ ] Tests:
  - `test_summary_fallback_mentions_vitals` (LLM down → contains "HR" and the max NEWS2)
  - `test_interaction_detected` (warfarin + aspirin → one `high` interaction)
- [ ] `GET /ai/summary/{patient_id}` (doctor) with a 10-minute cache (latest row younger than 10 min). Add `POST /ai/summary/{patient_id}/review` to set `human_confirmed_by` on the latest summary.
- [ ] Commit `feat(ai): doctor copilot daily summary + interaction rules`.

### Task 8: Paper digitizer (dropped 2026-10-05)

Removed from scope: code, routes (`api.md` v1.3) and the `documents` table (`data-model.md` v1.2). The doctor's paper records stay out of the demo.

### Task 9: Patient view + n8n W3 and W1

**Files:**
- Create: `web/src/app/patient/{page,appointments/[id]/page}.tsx`, `n8n/workflows/{W3-missed-dose,W1-appointment-reminder}.json`

- [ ] `/patient`: my meds today (with status), next visit, "Request appointment" form (free text + symptom chips) → shows "Request received. Urgency is reviewed by staff" (**never** show the AI score to the patient), and my vitals (read-only, last 24 h).
- [ ] `/patient/appointments/[id]?action=confirm|cancel` → `POST /appointments/{id}/reply` → "Thanks, see you on …".
- [ ] **W3:** `dose.missed` → Telegram to `nurse_chat_ids` (`💊 Missed dose · Bed {{bed}} · {{meds}}`) and email to the doctor.
- [ ] **W1:** `appointment.confirmed`:
  1. If `slot_at − now < 24h`, send now; otherwise Wait until `slot_at − 24h`.
  2. Telegram + email: "Reminder: appointment on {{date}} with {{doctor_name}}. Confirm: {{WEB_URL}}/patient/appointments/{{id}}?action=confirm · Cancel: …?action=cancel".
- [ ] Export the workflows. **CP2** (with Hedi): the prescription you write reaches the real device.
- [ ] Commit `feat(web,n8n): patient view, W1 reminder, W3 missed dose`.

**Day 2 done when:** CP2 passes. Triage, waitlist and summary all work with `LLM_PROVIDER=none` (and with `groq` or `local` if you want to try the optional rewrite); W1, W3 and W4 deliver to Telegram.

---

## Day 3 — Thu 10-08 (integration)

### Task 10: Golden path (Doctor + Admin owner) + integrations router

- [ ] Flip every view to the real API (`NEXT_PUBLIC_USE_MOCKS=0`) and run the full golden path from `TEAM_PLAN.md` §5 twice by 13:00 (**CP3**). Keep the shared bug list and assign each bug to its owner.
- [x] `routers/integrations.py`:
  - `X-N8N-Secret` check
  - `appointment-reply`
  - `backfill-accept` (409 `slot_taken` / `not_waiting`, per n8n-webhooks v1.2)
  - `daily-digest` (list of doctors with email; re-uses `daily_summary`)
  - `follow-up` (creates a `requested` post-discharge appointment through normal triage)
  - In `POST /appointments/{id}/cancel`: compute `candidate` with Hedi's `rank_backfill` and put it in the `appointment.cancelled` event
- [ ] Afternoon stretch, in order:
  1. W2 backfill (uses Hedi's `rank_backfill`)
  2. W6 discharge follow-up (books via the `follow-up` callback)
  3. W5 digest

### Link checklist: when Wali's backend lands

Built ahead against the contracts (all DB-free and tested): `app/services/appointments.py`, `app/services/integrations.py`, `app/ai/{llm,triage,copilot,assistant}.py`, n8n W0-W6. When Wali's `app.models`, `app.auth.deps` (`get_current_user`, `require_roles`, `check_patient_access`), `app.services.audit.audit`, `app.ids.new_id` and `app.integrations.n8n.emit` are on `main`:

- [x] `routers/appointments.py`: `POST /appointments` (`new_appointment_fields` → row via `new_id(db, "a")`), `GET /appointments/waitlist` (`waitlist`), `GET /appointments`, `PATCH /appointments/{id}` (`apply_override`), `POST .../confirm` (`apply_confirm` → `emit("appointment.confirmed", confirmed_event(...))`), `POST .../cancel` (`apply_cancel` → `emit("appointment.cancelled", cancelled_event(..., waiting=requested appointments + patients))`), `POST .../reply` (`apply_reply`). `Conflict` → 409 `{"detail","code"}`; `ValueError` → 422.
- [x] `routers/integrations.py`: dependency that 401s unless `callback_secret_ok(request.headers.get("X-N8N-Secret"))`; `appointment-reply` (`apply_reply`), `backfill-accept` (`slot_taken` = another confirmed appointment with the same `doctor_id` + `slot_at`, `doctor_id` from the cancelled appointment; `apply_backfill_accept`), `daily-digest` (`digest_entries` over active admissions, latest `news2`, `copilot` summary), `follow-up` (`follow_up_fields`).
- [ ] `routers/ai.py`:
  - `POST /ai/triage` (`triage`, preview only)
  - `GET /ai/summary/{patient_id}`: `summary_inputs` over the last 24 h, `is_fresh` cache, else `summarize` + new `ai_summaries` row, `summary_payload`
  - `POST /ai/summary/{patient_id}/review` (`apply_review`)
  - `POST /ai/assistant` (patient): the caller's own today's doses, next appointment, latest vital → `assistant.answer(q, assistant_context(...))`; the response carries `intent` and `source` too
  - `summary_inputs` takes notes and vitals oldest-first, so the router loads them oldest-first
- [ ] Mount the three routers in `app/main.py` (one-line PR to Wali, he owns `main.py`).
- [ ] API tests with Wali's `client` fixture and `tests/helpers.login` for each route above, including the 403s from the role matrix and the 409s.
- [ ] Run W2/W5/W6 against the real API (no stub): `WARD_API_URL` back to the default.

### Task 11 (stretch): Patient assistant

- [ ] `POST /ai/assistant`: built (rework 2026-10-06). It classifies the question into an intent (`next_dose`, `next_visit`, `my_vitals`, `ask_staff`, `urgent`) with keyword rules plus a trained classifier, then fills a template from the caller's own record. A red-flag question gets the URGENT message with no model call. No LLM, no diagnosis; otherwise "Please ask your nurse".

### Single-visit exams (doctor feedback 2026-10-09)

Spec: `docs/superpowers/specs/2026-10-09-single-visit-and-case-notebook-design.md` · plan: `docs/superpowers/plans/2026-10-09-single-visit-exams.md`.

- [x] Contracts: data-model 1.4, api 1.8, n8n-webhooks 1.3 (needs Wali's 👍)
- [x] Tables `exam_orders`, `exam_results`, `notebook_entries` (migration 0003); Imaging and Laboratory nurses in the seed (also added to already-seeded databases)
- [x] Rules-based exam suggestions on every new request (`rules/exam_bundles.v1.json`, illustrative, for the doctors to review)
- [x] Doctor orders or drops suggestions; department nurse uploads results to MinIO; doctor opens them on the patient page (audited, doctor/nurse only)
- [x] Patient "Before your visit" checklist; waitlist exam progress; hospital triage-scale label (FRENCH, to confirm)
- [ ] n8n W7 (exams ordered → patient) and W8 (results ready → doctor)
- [ ] Ask the doctors which triage scale they use; set `confirmed: true` in `rules/triage_scale.v1.json`

### Interface languages (2026-10-10)

Plan: `docs/superpowers/plans/2026-10-10-i18n.md`.

- [x] i18n core: typed messages per area, `useT()` / `getT()`, `ward_lang` cookie, `<html lang dir>` from the server, Noto Sans Arabic
- [x] Language switcher on the sign-in page, the staff sidebar and the patient app header
- [x] Every role's screens in English, French and Arabic; RTL layout for Arabic
- [ ] Backend texts in the user's language (alert messages, AI reasons, exam labels, assistant replies)

## Day 4 — Fri 10-09 (polish + pitch)

- [ ] Verify the whole demo with `LLM_PROVIDER=none` and the Wi-Fi off (local stack only).
- [ ] Record the **backup demo video** of the full golden path.
- [ ] Pitch deck (≤ 10 slides): problem → Medora (one line) → the live demo → architecture → AI with a human in the loop → privacy (self-hosted, audit, no data leaves the server by default, optional LLM anonymised, INPDP Law 2004-63) → honesty slide (vitals simulated, AI not clinically validated, production path) → impact metrics we'd track (no-show rate, time-to-appointment for urgency ≥ 4, paper hours saved) → team.
- [ ] Rehearse ×3 with a timer. Q&A prep: cost per bed, scaling to a hospital, data residency, what if the AI is wrong (rules floor + human confirm), and offline behaviour.

**Day 4 done when:** the backup video is recorded, the deck is done, and the team has rehearsed three times.

## Self-review checklist (run before each PR)

- [ ] `web`: `npm run typecheck && npm run build` are green; mocks still type-check against `types.ts`.
- [ ] `backend`: `pytest -v` and `ruff check` are green; every AI response carries `source`.
- [ ] No prompt or rule text is inline in Python.
- [ ] No secrets committed; `.env.example` updated.
