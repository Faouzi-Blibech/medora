# AI radiograph reading — design

> 2026-10-10 · Author: Wali · Lanes touched: backend core (Wali), `backend/app/ai/` + `web/` (Faouzi, tagged on the PR)
> Branch `wali/radiograph-reading`, built on top of `wali/health-calendar` (so contract versions don't collide).

## Goal

When a radiograph image reaches a patient's record, a local open vision model drafts a structured reading
(region, quality, findings, impression, possible conditions with likelihood and visual evidence, urgent flags).
A doctor reviews, edits and confirms it; the confirmed text becomes the exam result's report. The AI only
suggests (CLAUDE.md "human in the loop"); nothing reaches the patient that a doctor has not confirmed.

Prototype honesty: every draft carries "AI draft from a prototype, not a diagnosis and not clinically validated.
A doctor must review it." The pitch never claims diagnostic accuracy.

## Decisions (agreed in brainstorming)

| Topic | Decision |
|---|---|
| Entry points | (1) Imaging nurse uploads a JPEG/PNG for an ordered radiograph exam (`chest_xray`, new `xray` "X-ray (other region)"); (2) doctor uploads an **outside X-ray** on the patient page (code `xray_outside`). DICOM out of scope |
| Scope | All radiographs (chest, limbs, spine, pelvis, abdomen…) |
| Engine | Local Ollama vision model, default **Qwen3-VL 4B** (`qwen3-vl:4b`, fits the RTX 3050 6 GB); configurable `LLM_VISION_MODEL`; `qwen2.5vl:3b` as a fallback choice |
| Privacy | Images never go to Groq or any hosted API (names burned into an image can't be stripped). Image re-encoded before inference: EXIF/metadata dropped, grey-scale, longest side 1024 px |
| No model | `VISION_PROVIDER=none` (default), Ollama down, timeout or invalid output → status `unavailable`, the doctor gets a blank structured report (Technique / Findings / Impression / Recommendation), `source: "rules"` |
| When | Automatically after upload, in the background (worker thread). No re-draft button |
| Live update | Web polls the reading every 4 s while `queued`/`running` (the web app has no WebSocket client in real mode yet). The worker still publishes a `radiograph_reading` WS frame for later clients |
| Language | Draft written in `RADIOLOGY_REPORT_LANG` (default `fr`; `en` supported) |
| Who sees what | Doctor with result access: full draft, edit, confirm. Nurse with result access: status only. Patient and admin: nothing new |
| Demo images | 6 CC0 teaching radiographs by Mikael Häggström (Wikimedia Commons), attached to synthetic patients p-0001…p-0006 by an idempotent seed step, credited in `CREDITS.md` |

## Data (data-model → 1.8, migration `0008_radiograph_readings`)

`radiograph_readings`

| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `rr-0001` |
| `exam_result_id` | text FK exam_results, **unique** | one reading per image |
| `patient_id` | text FK patients, index | |
| `status` | text, index | `queued` → `running` → `ready` \| `unavailable` \| `failed` |
| `hint` | text | the exam label or the doctor's title ("Chest X-ray", "Outside X-ray — wrist"); never patient identity |
| `ai_suggested` | jsonb, null | see below |
| `final_text` | text, null | doctor-confirmed report |
| `human_confirmed_by` | text FK users, null | |
| `confirmed_at`, `started_at`, `finished_at` | timestamptz, null | |
| `created_at` | timestamptz | default now() |

`ai_suggested` (model draft): `{"source":"llm","model":"qwen3-vl:4b","region","projection","quality","findings":[...],
"impression","possible_conditions":[{"name","likelihood":"low|medium|high","evidence"}],"urgent_flags":[...],
"recommendation","draft_text","disclaimer"}`. Template: `{"source":"rules","reason","draft_text","disclaimer"}`.
`failed` (unreadable image or file missing): `{"source":"rules","reason","draft_text","disclaimer"}` too, so the
doctor can always write the report.

## Backend units

- `app/ai/llm.py` — new `complete_vision_json(prompt_name, image_png, user_text, schema)`: only when
  `VISION_PROVIDER=local`; Ollama `/api/chat` with `images:[base64]`, `format` = JSON schema, temperature 0,
  `LLM_VISION_TIMEOUT_S` (default 180). Any failure → `LLMUnavailable`. `user_text` goes through `strip_pii`.
- `app/ai/radiology.py` — `prepare_image(bytes) -> png bytes`, `RadiographDraft` schema, `render(draft, lang)`,
  `template(lang)`, `read(image_bytes, hint) -> (status, ai_suggested)`; `python -m app.ai.radiology <file>` smoke CLI.
- `app/ai/prompts/radiograph_report.v1.md` — versioned prompt (describe, don't diagnose with certainty; say when
  the image is not a radiograph or is unreadable; likelihoods; urgent flags; requested language).
- `app/ai/rules/radiograph.v1.json` — `{"codes": ["chest_xray","xray","xray_outside"], "image_types": ["image/jpeg","image/png"]}`.
- `app/models/radiology.py` — `RadiographReading`.
- `app/services/radiology.py` — `is_radiograph`, `enqueue`, `claim_next` (`FOR UPDATE SKIP LOCKED`), `process`,
  `recover` (running → queued at worker start), `tick`, `run_forever`, `to_out`, `confirm`.
- `app/iot/worker.py` — starts the radiology job thread (daemon) next to the MQTT loop.
- `app/routers/radiology.py` — endpoints below. `app/routers/exams.py` — enqueue on radiograph upload.
  `app/services/exams.py` — each result in `to_out` gains `reading: {id, status, confirmed} | null`.
- `app/radiograph_seed.py` + `app/ai/assets/radiographs/` — demo images and seed step (run by `python -m app.seed`).

## API (api → 1.14)

| Endpoint | Who | Notes |
|---|---|---|
| `GET /exam-results/{result_id}/reading` | doctor, nurse with result access | doctor: full reading (audit `read radiograph_reading`); nurse: `{id, exam_result_id, status}`; 404 when the result has no reading |
| `PUT /exam-results/{result_id}/reading` | doctor with result access | `{"final_text": "1..20000 chars"}` → sets final_text, human_confirmed_by, confirmed_at; copies the text into `exam_results.report_text`; audit `update`; re-confirming edits it. Allowed in any status (a doctor may write before the AI finishes; the worker never overwrites `final_text`) |
| `POST /patients/{patient_id}/radiographs` | doctor with write access | multipart `file` (JPEG/PNG ≤ 15 MB), `title` (default "Outside X-ray") → creates a done `Imaging` exam `xray_outside` + result + queued reading → `ExamOrder` (201) |

`ExamOrder.results[].reading` added. WS frame `{"type":"radiograph_reading","reading_id","exam_result_id","patient_id","status"}`.

## Infra

- `backend/requirements.txt`: `pillow==11.*`.
- Settings / `.env.example`: `VISION_PROVIDER=none`, `LLM_VISION_MODEL=qwen3-vl:4b`, `LLM_VISION_TIMEOUT_S=180`,
  `RADIOLOGY_REPORT_LANG=fr`, `DOCKER_OLLAMA_URL=http://host.docker.internal:11434`.
- Compose `worker`: MinIO env (it now reads files), `LLM_LOCAL_BASE_URL: ${DOCKER_OLLAMA_URL:-http://host.docker.internal:11434}`,
  `extra_hosts: ["host.docker.internal:host-gateway"]`.
- Demo laptop: `ollama pull qwen3-vl:4b`, set `VISION_PROVIDER=local`.

## Web (Faouzi's lane)

- Types + api (mock and real): `getRadiographReading`, `confirmRadiographReading`, `uploadOutsideRadiograph`.
- `ExamsPanel` (doctor patient page): reading chip per radiograph result (AI reading… / AI draft ready / AI
  unavailable / Confirmed) and a "Review report" toggle opening `RadiographReadingCard`: image preview,
  disclaimer, region/projection/quality, urgent flags, findings, possible conditions with likelihood chips,
  impression, editable report textarea (prefilled with `final_text ?? draft_text`), Confirm. Polls while queued/running.
- "Add outside X-ray" (doctor) in the same panel: file (JPEG/PNG) + title.
- i18n namespace `radiology` (en/fr/ar).

## Error handling

Upload never waits for the model. Worker failures are contained per job (status `failed`, template text) and
logged; a crash mid-job is recovered at the next worker start. Ollama errors, timeouts and invalid JSON become
`unavailable`. Nothing in the API depends on Ollama being up.

## Testing

pytest with Ollama mocked: valid draft → `ready`; invalid JSON / timeout / provider none → `unavailable`;
unreadable bytes → `failed`; EXIF removed and size capped; payload has the image and the configured model; job
claim / recover / tick; permissions (doctor vs nurse vs patient/admin); confirm copies the text; outside upload;
enqueue only for radiograph codes and image types; seed idempotent with fake storage. Manual smoke: real
`qwen3-vl:4b` on the 6 demo images (time per image recorded). Web: typecheck, build, browser check in mock mode.

## Out of scope

DICOM, CT/MRI volumes, comparison with prior images, patient-facing wording, re-draft button, model fine-tuning.
