# Medora — Architecture

> Medora is a connected smart-hospital ecosystem
> in which patient, nurse, doctor and administration share one patient record and the patient process is automated.

## 1. Problem and framing

Tunisian hospitals today:
- Patients who need care fast often get appointments 6–12 months away.
- A patient usually sees the doctor twice: a first visit to be told which exams to do, a second one with the results for the diagnosis and treatment.
- Doctors and nurses log, search and re-read paper records every day.
- Patient, nurse, doctor and administration have no shared system.

**Medora automates the patient process**:
- no paper
- exams done before the visit, so one consultation is enough
- fewer no-shows
- urgency-aware booking
- automatic follow-ups

Shorter waits are the *result*. We do not claim to "solve the waitlist".

**Where Medora fits.** Doctors we showed the demo to (2026-10-09) already use a doctor-only system, and the national
programme is rolling out:
- electronic records and PACS imaging in public hospitals
- Sahetna.tn for citizens, keyed on the national health identifier (INS)

Medora does not replace these. It connects the four roles around one patient and automates the steps between them; in
production it would use the INS as the patient identifier and exchange records with these systems.

**Locked principles:**
- **Human in the loop:** AI suggests and a human confirms.
- **Privacy:** self-hosted, RBAC, an audit log of every read, and no patient data leaves the server unless an optional open LLM is switched on, and then it is anonymized (Tunisian Organic Law 2004-63 / INPDP).
- **Prototype honesty:** vitals are simulated (the bedside unit has no sensors) and the AI is not clinically validated.
- **Data:** synthetic only.

## 2. System architecture

```mermaid
flowchart TB
  subgraph USERS["Users & devices"]
    BSU["Bedside Unit<br/>ESP32 + OLED + servo + RTC<br/>(listener)"]
    SIM["simulator/<br/>(vitals, nurse taps, call-nurse)"]
    PWA["Next.js PWA<br/>doctor · nurse · admin · patient"]
    TG["WhatsApp / email"]
  end

  subgraph CONN["Connectivity"]
    MQ["Mosquitto<br/>MQTT :1883"]
    API["FastAPI gateway<br/>REST + WS · JWT + RBAC :8000"]
  end

  subgraph SVC["Backend services (one codebase: backend/)"]
    WRK["MQTT ingestion worker"]
    VIT["Vitals & Alerts"]
    APT["Appointments & Waitlist"]
    EXM["Exams (single visit)<br/>suggest · order · upload · read"]
    REC["Patient records"]
    RX["Prescriptions & Med schedule"]
    AI["AI engine<br/>triage · exam suggestions · early warning<br/>copilot · no-show · assistant<br/>(rules + trained models)"]
    LLM["ai/llm.py<br/>optional open LLM (off by default)<br/>Groq gpt-oss-120b or Ollama · PII stripped"]
  end

  subgraph DATA["Data (hospital's own server)"]
    PG[("PostgreSQL<br/>+ TimescaleDB")]
    MINIO[("MinIO<br/>exam result files")]
    AUD[("audit_log")]
  end

  N8N["n8n (self-hosted) :5678"]

  BSU <-->|MQTT| MQ
  SIM <-->|MQTT| MQ
  MQ --> WRK
  WRK --> VIT
  RX -->|retained schedule| MQ
  PWA <-->|HTTPS + WS| API
  API --- VIT & APT & EXM & REC & RX & AI
  AI --> LLM
  VIT & APT & EXM & REC & RX & WRK --> PG
  EXM --> MINIO
  API --> AUD
  API -->|events| N8N
  N8N -->|callbacks| API
  N8N --> TG
```

**Containers** (`infra/docker-compose.yml`): `db` (timescale/timescaledb, pg16), `mqtt` (eclipse-mosquitto 2), `minio`, `n8n`, `api` (FastAPI), `worker` (same image, runs `python -m app.iot.worker`), `web` (Next.js).

**Languages.** The web app speaks Arabic, French and English. Each user picks one from the sign-in page, the staff sidebar or the patient app header. How it works:
- The choice is saved in a `ward_lang` cookie. The server reads the cookie, so `<html lang dir>` is correct on the first paint, and Arabic switches the whole layout to right-to-left.
- Messages live in typed files under `web/src/i18n/messages/` (one per area). The build fails if French or Arabic is missing a key.
- Dates follow the language; clock times stay 24 h with Latin digits.
- Data typed by people or produced by the backend (names, notes, alert texts, AI reasons) is shown as written.
- Charts keep time running left to right.

## 3. Users and use cases

```mermaid
flowchart LR
  P(("Patient"))
  N(("Nurse"))
  D(("Doctor"))
  A(("Admin"))

  subgraph Medora
    UC1["Request appointment"]
    UC2["Med reminders on bedside screen"]
    UC3["See prescriptions & next visit"]
    UC4["Call nurse (simulated)"]
    UC5["Home care via app after discharge"]
    UC6["Ask patient assistant (stretch)"]
    UC7["Log vitals via badge tap (simulated)"]
    UC8["Update patient record / notes"]
    UC9["Receive abnormal-vitals alerts"]
    UC10["Med-round checklist"]
    UC11["Patient list + AI daily summary"]
    UC12["Prescribe & plan care"]
    UC13["Vitals history & trends"]
    UC14["Set / confirm urgency"]
    UC16["Bookings & AI-ranked waitlist"]
    UC17["Assign beds & devices"]
    UC18["Staff accounts & roles"]
    UC19["Hospital dashboard"]
    UC20["Do exams before the visit"]
    UC21["Order or drop suggested exams"]
    UC22["Upload exam results (own department)"]
    UC23["Read results at the visit"]
    UC24["Ask the case notebook (planned)"]
  end

  P --- UC1 & UC2 & UC3 & UC4 & UC5 & UC6 & UC20
  N --- UC7 & UC8 & UC9 & UC10 & UC22
  D --- UC11 & UC12 & UC13 & UC14 & UC9 & UC21 & UC23 & UC24
  A --- UC16 & UC17 & UC18 & UC19 & UC14
```

All four roles share **one patient record** and see only what their permissions allow (matrix in `contracts/data-model.md`).

**Role owners** (each is responsible for their role's flow end-to-end in the demo): Patient → Hedi · Nurse → Wali · Doctor + Admin → Faouzi.

## 4. Patient journey (swimlane)

```mermaid
sequenceDiagram
  autonumber
  actor P as Patient
  actor A as Admin
  actor D as Doctor
  actor N as Nurse
  actor X as Department nurse
  participant S as System + AI
  participant B as Bedside Unit

  P->>S: Request appointment (app / reception)
  S->>S: Triage: red-flag rules + trained classifier → urgency 1–5
  S->>S: Exam rules → suggested exams (e.g. ECG, troponin, chest X-ray)
  S-->>D: Request with suggested exams
  D->>S: Order the exams to keep (the rest are dropped)
  S-->>P: "Before your visit" checklist (n8n W7)
  P->>X: Does the exams (Imaging / Laboratory / Cardiology)
  X->>S: Uploads the result file + short report
  S-->>D: Results ready (n8n W8)
  S-->>A: AI-ranked waitlist with exam progress
  A->>S: Confirm booking (may override urgency)
  S-->>P: Confirmation + 24h reminder (n8n W1)
  D->>S: Single consultation with the results → prescription + care plan
  S->>B: Retained MQTT schedule (med_doses)
  B-->>S: schedule_ack
  Note over B: Dose time (RTC, works offline)
  B->>B: Turn servo to slot · show "TAKE NOW"
  B-->>S: dose_dispensed
  P->>S: Takes pill (dose_taken, simulated)
  Note over B: or 30 min → dose_missed → n8n W3
  N->>S: Badge tap → vitals {nurse_rfid} (simulated)
  S->>S: Early warning (NEWS2 partial + trend)
  alt abnormal
    S-->>N: WS alert + WhatsApp (n8n W4)
    S-->>D: WS alert + WhatsApp
  end
  D->>S: Daily review with AI summary
  A->>S: Discharge
  S-->>P: Follow-up booked (n8n W6) · home care in app
```

**Golden demo path:** the journey above, plus a **simulated abnormal vital** that fires an alert on the dashboard and on WhatsApp.

## 5. Single-visit pathway (exams before the visit)

Built from the doctors' feedback of 2026-10-09.

```mermaid
stateDiagram-v2
  [*] --> suggested: exam rules on a new request
  suggested --> ordered: doctor orders it
  suggested --> cancelled: doctor drops it
  ordered --> done: department nurse uploads the result
  ordered --> cancelled: doctor cancels
  done --> [*]
```

- **Suggestions are rules, not a model.**
  - `backend/app/ai/rules/exam_bundles.v1.json` maps red flags and keywords (French, English, Arabic) to exam sets, at most 4 per request. Example: chest pain gives ECG, troponin and a chest X-ray.
  - Rows are stored with `ai_suggested.source = "rules"`.
  - The sets are illustrative, for the hospital's doctors to review.
- **A doctor orders.** Only a doctor moves an exam from `suggested` to `ordered` (`human_confirmed_by`). Unticked suggestions are dropped. Any other transition is a 409 `bad_status`.
- **The performing department uploads.**
  - A nurse whose ward is the exam's `department` (Imaging, Laboratory or Cardiology) sees it in the **Exams** worklist.
  - The nurse uploads a PDF, JPEG or PNG of at most 15 MB, plus a short report line.
  - The file goes to MinIO under `exams/{exam}/{result}/{name}`.
- **Who sees what:**
  - **Doctor and nurse:** they read results and open files through `GET /exam-results/{id}/file`, which is audited and sent with `nosniff`.
  - **Admin:** status only.
  - **Patient:** ordered and done exams only. Never suggestions, AI fields or files.
- **Events:** `exam.ordered` (n8n W7, tells the patient where to go) and `exam.results_ready` (W8, tells the ordering doctor, once, when the last exam is done).
- **Booking:** staff still pick the slot. The waitlist shows "Exams 2/3" so they can book once the results are in.
- **Triage scale label:** our urgency 1–5 is shown with the hospital's triage-scale level from `rules/triage_scale.v1.json`, e.g. "Tri 1 · FRENCH". It is marked "(to confirm)" until the doctors confirm which scale they use.
- **Out of scope:** AI reading lab values, and a DICOM viewer. PACS integration is the production path. Radiographs (JPEG/PNG) are the one exception: since api.md 1.14 a local vision model drafts a report that a doctor edits and confirms (owner: Wali).

## 6. Hardware: Smart Bedside Unit (listener: OLED + servo + RTC)

The bedside unit is a **listener**. It receives the schedule and commands, shows them, turns a servo to the dose's
pill slot and acknowledges. It has **no vital-sign sensors**: vitals, nurse taps and call-nurse come from
`simulator/`, which can run next to the device on the same `device_id` (`--companion`). The firmware is developed in
**Wokwi** (virtual ESP32, `firmware/diagram.json`) and is the last piece built; the same code flashes to a real board.

```mermaid
flowchart LR
  PWR["5V USB"] --> ESP
  subgraph ESP["ESP32 DevKit"]
    direction TB
    WIFI["Wi-Fi + MQTT"]
    NVS["NVS: schedule"]
    Q["Small event queue (offline)"]
  end
  ESP ---|"I2C 0x3C"| OLED["0.96in SSD1306 OLED<br/>128x64"]
  ESP ---|"I2C 0x68"| RTC["DS1307 RTC<br/>(UTC)"]
  ESP ---|"GPIO 13 PWM"| SERVO["SG90 servo<br/>4-slot pill holder"]
  SIM["simulator --companion<br/>vitals · nurse_tap · call_nurse · dose_taken"] -.->|"same device_id"| MQ[Mosquitto]
  ESP <-->|MQTT| MQ
```

- OLED and RTC share I2C (distinct addresses). The final pin assignment lives in `firmware/PINMAP.md`.
- **Servo dispenser:** slot 0 = 0° (home), slots 1–4 = 45°, 90°, 135°, 180°. A dose with `slot: null` is reminder-only.

**Device screens (OLED):**
- **Home:** first name, clock, next dose, online/offline icon.
- **Dose reminder:** "TAKE NOW" + meds, blinking.
- **Alert banner** (inverted screen, 5 s) and **message toast**, from `command`.
- **Status:** "Syncing time…", "Not assigned".

**Dose flow:**
1. At dose time (or on `dispense_now`), turn the servo to the dose's `slot` → `dose_dispensed`, and show the reminder.
2. The simulator (`--companion`) answers with `dose_taken {method:"button"}`; the device sees it on its own `events` topic, homes the servo and returns to the home screen.
3. After 30 min with no `dose_taken` → `dose_missed` → the backend sends it to n8n W3.

**Offline:**
- The schedule lives in NVS, and reminders fire from the DS1307 RTC, so a reboot with no Wi-Fi still knows the time. NTP only sets the RTC when Wi-Fi is up.
- Up to 8 pending events are queued in RAM and sent on reconnect; the server deduplicates on `msg_id`.
- An MQTT last-will reports offline status.

## 7. AI layer (human in the loop)

```mermaid
flowchart LR
  subgraph In["Inputs"]
    REF["Referral + symptoms<br/>(AR / FR / Darija)"]
    VS["Vitals stream"]
    H24["24h vitals + notes + meds"]
    HIST["Booking history"]
    Q["Patient question"]
  end
  subgraph Mods["backend/app/ai/"]
    T["1 · Triage<br/>red-flag rules + trained char n-gram classifier<br/>+ hospital scale label"]
    EX["4 · Exam suggestions<br/>rules: red flags + keywords → exam set"]
    EW["2 · Early warning<br/>NEWS2 partial + z-score"]
    CP["3 · Doctor copilot<br/>templated summary + rule interactions<br/>(optional open LLM rewrite)"]
    NS["5 · No-show model<br/>LogReg on Kaggle dataset"]
    PA["6 · Patient assistant<br/>keyword rules + trained classifier → intent<br/>templated answers"]
  end
  W["llm.py wrapper (optional)<br/>strip PII · LLM_PROVIDER · open models only"]
  subgraph Human["Human confirms"]
    HA["Admin / doctor<br/>confirms waitlist order"]
    HX["Doctor orders<br/>or drops exams"]
    HN["Nurse + doctor<br/>ack alert"]
    HD["Doctor reviews summary"]
    HO["Admin can override booking"]
  end
  REF --> T --> HA
  REF --> EX --> HX
  VS --> EW --> HN
  H24 --> CP --> HD
  HIST --> NS --> HO
  Q --> PA
  CP -.-> W
```

| # | Module | Owner | Without the model or LLM |
|---|---|---|---|
| 1 | Triage | Faouzi | Red-flag rules alone (`source: "rules"`); with the trained model, `source: "model"` |
| 2 | Early warning | Wali | Pure rules, so it is its own fallback |
| 3 | Doctor copilot | Faouzi | Templated summary from min/max/latest vitals + the curated interaction list (this is the default; an open LLM only rewrites it when `LLM_PROVIDER` is set) |
| 4 | Exam suggestions | Faouzi | Pure rules (`source: "rules"`), so it is its own fallback |
| 5 | No-show model | Hedi | Base rate (≈0.20) |
| 6 | Patient assistant | Faouzi | Keyword intent rules, then the same templated answers from the DB; otherwise "Please ask your nurse" |

**How the modules decide:**
- **Triage:** urgency = max(red-flag floor, trained classifier, 2 if age ≥ 75). The model can raise urgency above the floor, never lower it.
- **Assistant:** a red-flag question gets the URGENT message with no model call. A question that names exactly one topic (dose, appointment, vitals) is answered by keyword rules; otherwise a small trained char n-gram classifier picks the intent. Low confidence means "ask staff". The answer is a template filled from the caller's own record.
- **Copilot:** the summary and the interaction list come from templates and a curated rule file.
  - The summary is cached 10 minutes and stored in `ai_summaries`. The doctor marks it reviewed, or undoes that.
  - An optional open LLM may rewrite the text. Our setup is Groq with `openai/gpt-oss-120b`, an open-weight model; Ollama works for fully local use. If the call fails, the template text is served (`source: "rules"`).
- **Exam suggestions:** red-flag ids from triage plus keywords in three languages pick exam bundles, at most 4 exams. The doctor orders or drops each one (section 5).
- **Early warning and no-show:** unchanged (Wali and Hedi).
- **Case notebook (planned):** questions about one patient, answered only from that patient's record, with citations.
  - The doctor asks questions about one patient. Answers come only from that patient's record (notes, exam reports, prescriptions, vitals summary, referral) and cite their sources.
  - Without an LLM it returns the best-matching passages (BM25). With an LLM it writes a short answer that may cite only those passages; anything else falls back.

**Measured on hand-written sets (synthetic, small):**

| Model | Eval set | Result |
|---|---|---|
| Triage classifier alone | 29 referrals | exact 0.897, within one 1.0, under-triaged 2, urgent missed 1 |
| Triage rules + model | same 29 | exact 0.897, within one 1.0, under-triaged 2, urgent missed 1 |
| Intent: classifier argmax | 36 questions | accuracy 0.722 (26/36) |
| Intent: classifier + 0.4 confidence threshold, red flags first (the shipped behaviour) | same 36 | accuracy 0.611 (22/36) |

The shipped behaviour is the classifier row with the 0.4 threshold (0.611): about four questions in ten fall to "ask your nurse" or the wrong template. On 2026-10-06 the evaluation sets were rewritten to remove leakage into the training data (a test now guards this), which is why these numbers are lower than earlier ones. The one urgent-missed triage case is a Darija chest/faint complaint scored 4 instead of 5, and no keyword rule covers it. Sources: `backend/app/ai/models/*metrics.json`. These sets are tiny; read them as a sanity check, not a validation.

**Rules for every module:**
- Every module works with no LLM. A trained model is optional too: without its file the module drops to rules.
- Models are trained only on synthetic data (`backend/app/ai/data/`, scripts in `backend/app/ai/training/`).
- Any optional LLM call goes through `backend/app/ai/llm.py` (open models only).
- Every output is stored with `ai_suggested` + `human_confirmed_by`.
- Prompts and red-flag lists are versioned files in `backend/app/ai/prompts/` and `backend/app/ai/rules/`.

**Early-warning thresholds** (NEWS2 partial, single-parameter bands; **verify against the official RCP NEWS2 chart before the demo**):

| Parameter | 3 | 2 | 1 | 0 | 1 | 2 | 3 |
|---|---|---|---|---|---|---|---|
| Heart rate (bpm) | ≤40 | | 41–50 | 51–90 | 91–110 | 111–130 | ≥131 |
| SpO2 scale 1 (%) | ≤91 | 92–93 | 94–95 | ≥96 | | | |
| Temperature (°C) | ≤35.0 | | 35.1–36.0 | 36.1–38.0 | 38.1–39.0 | ≥39.1 | |

Partial score → severity:
- 0 → none
- 1–2 → low
- 3–4 → medium
- any single parameter = 3 → high
- ≥5 → high
- ≥7 → critical

**Trend:** a rolling z-score over the patient's last 30 readings; |z| ≥ 3 on HR or SpO2 raises a `trend` alert (medium).

## 8. Data and privacy

- Everything runs from one `docker compose` on the hospital's server.
- RBAC is enforced in FastAPI dependencies.
  - Every read of a patient record appends an `audit_log` row: records, vitals, doses, exams, result files, AI summaries and assistant questions.
  - Postgres RLS is the Day 4 stretch / production plan.
- Exam result files live in MinIO and are never exposed by a public link. The API checks the role and the department or ward, logs the read, then streams the file.
- Two things send data off the server:
  - **Notifications (n8n).** WhatsApp (through the self-hosted WAHA gateway; the official Business API in production) and email (SMTP) are third-party services outside Tunisia.
    Staff alerts name the bed only, with no patient name, score, vitals or medication. Patient messages carry the
    patient's own appointment details. The doctor's digest email lists first names and summaries a doctor has
    already reviewed. A real deployment needs INPDP authorisation for these transfers (Law 2004-63).
  - **The optional LLM**, off by default (`LLM_PROVIDER=none`).
  - When it is set, `llm.py` first replaces names, phone numbers and IDs with placeholders.
  - `LLM_PROVIDER=local` sends nothing off the machine (Ollama).
  - `groq` calls the Groq API with an open-weight model (`openai/gpt-oss-120b`).
  - Only the doctor's summary text uses it today. Tests always run with `LLM_PROVIDER=none`.
- Seed data is synthetic (`backend/app/seed.py`).
  - Staff: one doctor, a Cardiology nurse, an Internal Medicine nurse, an Imaging nurse and a Laboratory nurse, plus one admin.
  - 12 patients, of whom one is admitted with 48 h of vitals and one prescription.
  - 10 appointment requests with their suggested exams.
  - `python -m app.seed` is safe to re-run: on an existing database it only adds missing staff accounts.
