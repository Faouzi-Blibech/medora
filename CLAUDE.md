# CLAUDE.md — Medora (HackCure @ ESEN)

Shared conventions for every teammate's Claude Code session. Read this file, then your own `plans/<NAME>.md`.

## Project in one paragraph

**Medora** is a connected smart-hospital prototype. Patient, nurse,
doctor and admin share one patient record. A bedside unit (ESP32 + OLED + servo + RTC, developed in Wokwi)
listens over MQTT, fires dose reminders offline and turns a servo to the pill slot; a simulator sends the vitals. A FastAPI backend stores everything in PostgreSQL/TimescaleDB,
scores urgency and early warnings with AI (a human always confirms), and drives n8n for Telegram/email follow-ups.
The goal we pitch is **automating the patient process**; shorter waits are the result, not the promise.

## Team and lanes

| Person | Lane | Role owner (end-to-end demo flow) | Plan |
|---|---|---|---|
| **Faouzi** (lead, presenter) | Web PWA, n8n, LLM AI modules, appointments API, pitch | Doctor + Admin | `plans/FAOUZI.md` |
| **Hedi** (HW-A) | Simulator (all patient-side traffic), no-show model, ESP32 listener firmware (OLED + servo, Wokwi, built last) | Patient | `plans/HEDI.md` |
| **Wali** (HW-B) | Core backend, real-board wiring + servo pill holder (if built), IoT ingestion, early warning, infra | Nurse | `plans/WALI.md` |

**Swapping lanes:** Hedi and Wali are both hardware people and may swap HW-A/HW-B. If they do, swap the two plan files' names,
update the ownership table below and the table above in one PR titled `chore: swap HW lanes`, and tell Faouzi.

## Repo layout and ownership

**Only edit folders you own.** If you need a change in someone else's folder, ask them (or open a PR and tag them).

| Path | Owner | What |
|---|---|---|
| `firmware/` | Hedi | PlatformIO project (Arduino framework, SSD1306 OLED, servo, DS1307) + Wokwi `diagram.json` |
| `firmware/PINMAP.md`, `hardware/` | Wali (Hedi co-signs PINMAP) | Pin map, wiring, power, servo pill holder |
| `simulator/` | Hedi | Python fake devices speaking the MQTT contract |
| `backend/` (default) | Wali | FastAPI app, models, migrations, auth, IoT, alerts |
| `backend/app/routers/appointments.py`, `backend/app/routers/ai.py`, `backend/app/routers/integrations.py` | Faouzi | |
| `backend/app/ai/` (default) | Faouzi | Triage, copilot, assistant, trained models + training scripts, optional LLM wrapper, prompts, rules |
| `backend/app/ai/early_warning.py` | Wali | NEWS2 + trend |
| `backend/app/ai/no_show/` | Hedi | No-show model + backfill ranking |
| `web/` | Faouzi | Next.js PWA |
| `n8n/` | Faouzi | Exported workflows |
| `infra/` | Wali | docker-compose, mosquitto config |
| `docs/contracts/` | **everyone** | See the contract-change rule |
| `docs/`, `TEAM_PLAN.md`, `README.md` | Faouzi | |

## Contract-change rule

`docs/contracts/*.md` are frozen at **v1.0** (2026-10-05). They are what lets us work in parallel. To change one:
1. Open a PR that edits the contract, **bumps the version** in its header (1.0 → 1.1) and adds a changelog line.
2. Announce it in the team chat with a one-line summary, and wait for a 👍 from the other side of that contract.
3. Update your mocks/fixtures in the same PR if you own any.

Never change a payload shape silently in code. If the code and the contract disagree, the contract wins until it is bumped.

## Locked rules (do not relitigate)

- **Human in the loop:** AI only suggests. Every AI output is stored with `ai_suggested` (JSON incl. `source: model|rules|llm`) and `human_confirmed_by`.
- **Every AI module works with no LLM.** The demo must work with the Wi-Fi off and `LLM_PROVIDER=none`.
- **Models are trained only on synthetic data in `backend/app/ai/data/`;** the training scripts live in `backend/app/ai/training/`.
- **Any optional LLM call goes through `backend/app/ai/llm.py`** (open models only), which strips names, phone numbers and IDs first. Prompts and rule lists live in versioned files under `backend/app/ai/prompts/` and `backend/app/ai/rules/`, never inline.
- **Privacy:** self-hosted only (n8n too). Every read of a patient record writes `audit_log`. Synthetic data only, never real patients.
- **On-device reminders never depend on the server or n8n** (NVS schedule + DS1307 RTC).
- **n8n is not the source of truth.** The backend emits events; n8n calls back `/integrations/n8n/*`.
- **Prototype honesty:** vitals are simulated (the device has no sensors); never claim medical-grade sensing or clinically validated AI in UI copy or the pitch.
- **Demo first:** if a feature isn't on the golden demo path (`TEAM_PLAN.md`), it waits until the path works.
- **Mocks first:** never block on a teammate. Build against the contract and mock the rest (`simulator/`, `web/src/mocks/`, `backend/tests/fixtures/`).

## Git

- **No AI attribution.** Never add `Co-Authored-By: Claude …` trailers or "Generated with Claude Code" footers to commits or PRs.
- Branch per member and feature: `<name>/<feature>` (e.g. `wali/ingestion`, `hedi/simulator`, `faouzi/doctor-view`).
- Small PRs into `main`. Squash merge. `main` must always start with `docker compose up`.
- Commit messages: Conventional Commits (`feat(backend): …`, `fix(firmware): …`, `docs(contracts): …`).
- Secrets only in `.env` (never committed). Keep `.env.example` up to date whenever you add a variable.

## Running the stack

```bash
cp .env.example .env                       # fill in LLM key / Telegram later; defaults work offline
docker compose -f infra/docker-compose.yml --env-file .env up --build
```

| Service | URL |
|---|---|
| API (FastAPI) | http://localhost:8000 · docs at `/docs` · `GET /health` |
| Web (Next.js) | http://localhost:3000 |
| n8n | http://localhost:5678 |
| MinIO console | http://localhost:9001 |
| MQTT | `mqtt://localhost:1883` |
| Postgres | `localhost:5432` (db `ward`) |

Port 8000 or 3000 already taken on your laptop? Set `API_PORT` / `WEB_PORT` in `.env`.

Lane-specific dev loops:
- **Backend:** `cd backend && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements-dev.txt && uvicorn app.main:app --reload`, tests with `pytest`.
- **Web:** `cd web && npm install && npm run dev` (uses mocks when `NEXT_PUBLIC_USE_MOCKS=1`).
- **Simulator:** `cd simulator && pip install -r requirements.txt && python sim.py --device bsu-001`.
- **Firmware:** `cd firmware && pio run -e wokwi`, then start the Wokwi simulator in VS Code (`wokwi.toml`); real board: `pio run -t upload && pio device monitor`. Logic tests with `pio test -e native`.

## Coding conventions

- **Python 3.12:**
  - FastAPI + SQLAlchemy 2.0 (typed `Mapped[...]`) + Alembic + Pydantic v2.
  - One router per resource in `backend/app/routers/`.
  - Business logic in `backend/app/services/`, not in routers.
  - `pytest` for tests. Format with `ruff format`; lint with `ruff check`.
- **TypeScript:**
  - Next.js App Router, strict TS, CSS Modules + design tokens in `globals.css`.
  - API types in `web/src/lib/types.ts` mirror `docs/contracts/api.md`.
- **C++ (firmware):**
  - One module per peripheral in `firmware/src/` (`net.cpp`, `schedule.cpp`, `ui.cpp`, `servo.cpp`, `clock.cpp`).
  - Pure logic goes in `firmware/lib/` so `pio test -e native` can run it.
  - Secrets go in `firmware/include/secrets.h` (git-ignored; copy `secrets.h.example`).
- Times:
  - MQTT uses epoch seconds UTC.
  - REST uses ISO-8601 UTC.
  - The device shows Africa/Tunis (UTC+1).
- IDs are prefixed strings (`p-0001`, `bsu-001`). See `docs/contracts/api.md`.

## Where things are

- Product + architecture + diagrams: `docs/architecture.md`
- Design decisions (spec): `docs/superpowers/specs/2026-10-05-ward-foundation-design.md`
- Contracts: `docs/contracts/{mqtt-topics,api,data-model,n8n-webhooks}.md`
- Day-by-day plan, demo script, risks: `TEAM_PLAN.md`
- Your own brief: `plans/<NAME>.md`
