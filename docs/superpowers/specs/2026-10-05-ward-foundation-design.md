# Medora — Foundation Design (HackCure @ ESEN)

> **Amendment (2026-10-05, later the same day): reduced hardware.** The bedside unit is now ESP32 + SSD1306 OLED +
> SG90 servo + DS1307 RTC, developed in Wokwi and built last. It has no vital-sign sensors, RFID, touch screen,
> stepper carousel or IR sensor; `simulator/` produces vitals, nurse taps, call-nurse and `dose_taken`. Where this
> spec mentions those parts, the current source of truth is `docs/contracts/mqtt-topics.md` v1.1,
> `docs/architecture.md` §5, `firmware/PINMAP.md` and `plans/HEDI.md`. The rest of this spec is unchanged.

- **Date:** 2026-10-05 (Day 0)
- **Status:** approved by the team lead in brainstorming; changes go through a PR
- **Source brief:** the HackCure project brief (sections 0–12), summarized below so this file stands alone

## 1. Intended outcome

A repo foundation that lets three people, each driving their own Claude Code session,
build a connected smart-hospital prototype **in parallel from Day 1** and converge on one
demo by Day 3 midday. Success means:

1. Every teammate can open their own `plans/<NAME>.md` and work without asking the others.
2. Integration contracts (MQTT, REST/WS, data model, n8n) are frozen at v1.0 on Day 0.
3. `docker compose up` runs the empty stack from `main` at all times.
4. The golden demo path (section 6) works end-to-end on Day 3.

## 2. Decisions taken in brainstorming

| Topic | Decision |
|---|---|
| Name | **Medora** (Arabic: ميدورا) |
| Team | Faouzi (lead, presenter), Hedi and Wali (hardware) |
| HW lanes | Hedi = HW-A (firmware + device UI, Patient owner), Wali = HW-B (wiring + mechanics + core backend + IoT, Nurse owner). They may swap; see `CLAUDE.md` ("Swapping lanes") |
| Dispenser | **Option A (full)**: rotating carousel on a 28BYJ-48 stepper + IR pickup sensor. Go/no-go at the end of Day 2; the fallback is the "Taken" button with the same MQTT events |
| Timeline | Day 0 = Mon 2026-10-05, Day 1 = Tue 10-06, Day 2 = Wed 10-07, Day 3 = Thu 10-08 (integration), Day 4 = Fri 10-09 (polish), 10-10 onward = buffer + pitch |
| Workload rebalance | Simulator → Hedi. Core backend + IoT + early warning → Wali. Appointments + LLM modules + web + n8n → Faouzi. Patient assistant and n8n W2/W5/W6 become stretch goals |
| Attribution | No AI co-author trailers or "generated with" footers on commits or PRs |

## 3. Locked product principles

- **Framing:** automate the patient process (no paper, fewer no-shows, urgency-aware booking, automatic follow-ups). Shorter waits are a *result*; never claim the system "solves the waitlist".
- **Human in the loop:** AI only suggests. A doctor, nurse or admin confirms every output that changes care or bookings.
- **Privacy:** self-hosted via Docker Compose; RBAC plus an audit log of every patient-record read; strip names and IDs before any cloud LLM call (or use a local model). Pitch mentions Tunisian Organic Law 2004-63 (INPDP).
- **Prototype honesty:** sensors are not medical-grade; the AI is not clinically validated.
- **Synthetic data only.**

## 4. Architecture

See `docs/architecture.md` for the diagrams. In short:

- **Devices:** ESP32 bedside unit ⇄ Mosquitto (MQTT). `simulator/` speaks the same contract.
- **Backend:** FastAPI (REST + WS, JWT + RBAC) and an MQTT ingestion worker built from the same image. AI modules live in `backend/app/ai/`.
- **Data:** PostgreSQL + TimescaleDB (vitals hypertable), MinIO (documents), `audit_log` table.
- **Automation:** self-hosted n8n. The backend posts events to n8n webhooks; n8n calls back `/integrations/n8n/*`. n8n is never the source of truth.
- **Web:** one Next.js PWA with role-based views (doctor, nurse, admin, patient).
- **Offline rule:** on-device dose reminders depend only on the ESP32's NVS schedule and DS3231 RTC.

## 5. Ownership

| Area | Owner |
|---|---|
| `firmware/` | Hedi (Wali co-owns `firmware/PINMAP.md` and `hardware/`) |
| `hardware/` (wiring, enclosure, carousel) | Wali |
| `simulator/` | Hedi |
| `backend/` (default) | Wali |
| `backend/app/routers/appointments.py`, `backend/app/routers/ai.py`, `backend/app/routers/integrations.py`, `backend/app/ai/` (except below) | Faouzi |
| `backend/app/ai/early_warning.py` | Wali |
| `backend/app/ai/no_show/` | Hedi |
| `web/`, `n8n/` | Faouzi |
| `infra/` | Wali |
| `docs/contracts/` | everyone (version bump + announcement) |

Role owners (each is responsible for their role's end-to-end demo flow): Patient → Hedi, Nurse → Wali, Doctor + Admin → Faouzi.

## 6. Golden demo path

1. A patient requests an appointment (web). Triage scores urgency (red-flag rules + LLM, with a deterministic fallback).
2. The admin sees the AI-ranked waitlist and confirms it, overriding where needed.
3. The doctor writes a prescription. The backend builds `med_doses` and publishes a retained `schedule` to the device.
4. The device shows the next dose. At dose time it rotates the carousel, buzzes, and the IR sensor detects pickup → `dose_taken`.
5. The nurse taps a badge; nurse mode measures vitals → `vitals` tagged with `nurse_rfid`.
6. A **simulated abnormal vital** → NEWS2 alert → dashboard (WS) + Telegram (n8n W4).
7. **Paper digitizer:** a photo of a handwritten record → structured fields with confidence → the nurse or doctor approves.
8. Discharge → follow-up booked automatically (W6, stretch; otherwise shown as a seeded state).

## 7. Contract refinements over the brief's drafts (frozen at v1.0)

- MQTT `ts` = epoch seconds (UTC) from the RTC. Every device→server message carries `msg_id` (device-unique, monotonically increasing `uint32` persisted in NVS) so offline replays can be deduplicated on `(device_id, msg_id)`.
- New event types: `nurse_tap {rfid_uid}` and `schedule_ack {schedule_version}`. New command: `rotate_home`.
- `schedule` carries `schedule_version` (int) so the device can ack it and ignore stale messages.
- API additions: `GET /me`, `GET /patients/{id}/prescriptions`, `POST /admissions/{id}/discharge`, `POST /ai/digitize/{document_id}/approve`, `/integrations/n8n/*` callbacks authenticated with the `X-N8N-Secret` header.
- WS envelope: `{"type": "vital|alert|call_nurse|dose_event|device_status", "data": {...}}`.
- Every AI output row carries `ai_suggested` (JSON) and `human_confirmed_by` (user id, nullable).
- Early warning uses NEWS2 partial bands for HR, SpO2 (scale 1) and temperature, flagged in code as "verify against the official RCP NEWS2 chart".

Full detail lives in `docs/contracts/`.

## 8. Error handling and resilience

- **Every AI module has a deterministic fallback:**
  - triage → red-flag rules + keyword score
  - summary → templated text from the latest vitals
  - digitizer → a pre-baked extraction for the demo image
  - no-show → base-rate probability
- The LLM wrapper times out after 15 s and then falls back.
- **The device works offline:**
  - a ring buffer of 128 messages (~30 KB RAM) with RTC timestamps, replayed on reconnect
  - a last-will `status {online:false}`
- The ingestion worker is idempotent on `(device_id, msg_id)`.
- n8n failures never block the API: event posts are fire-and-forget with a 3 s timeout and a log line.

## 9. Testing

- **Backend:** pytest. Unit tests for NEWS2 scoring, triage red-flag rules, schedule building, RBAC and ingestion dedupe; API tests with httpx `TestClient`.
- **Firmware:**
  - PlatformIO `native` env unit tests for pure logic (ring buffer, schedule parsing, dose state machine)
  - hardware smoke sketches per sensor
- **Web:** typecheck + build in CI-less mode (`npm run build`). Mock data comes from `web/src/mocks/` fixtures until the API is live.
- **Integration:** simulator scripts reproduce the golden path without hardware (`simulator/scenarios/`).

## 10. Out of scope (YAGNI for the hackathon)

- SMS
- Real EHR integration
- Multi-hospital tenancy
- Production hardening (TLS on MQTT, secrets manager)
- Clinical validation
- Arabic UI localization beyond the triage input
