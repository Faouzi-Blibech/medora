# n8n contract — v1.0

> **Version:** 1.4 (2026-10-10) · **Owners:** Faouzi (workflows + callbacks), Wali (event emitter in the backend)
> Any change: open a PR that bumps the version above, add a changelog line, and announce it in the team chat.

## Rules (locked)

- n8n is **self-hosted** (container `n8n`, UI at `http://localhost:5678`). It is not the source of truth.
- The backend → n8n direction carries **events**. The n8n → backend direction carries **callbacks** to `/integrations/n8n/*` with the header `X-N8N-Secret`.
- On-device medication reminders never go through n8n.
- Event posting is fire-and-forget: 3 s timeout, failures are logged, and the API never fails because n8n is down.
- Demo channels: **Telegram** (bot token in n8n credentials), **WhatsApp** (self-hosted WAHA gateway, `waha` service; see `n8n/README.md`) and **email** (SMTP, e.g. a Gmail app password). SMS is out of scope.
- Payloads carry **first names only**, never national IDs or full records.
- Every workflow is exported as JSON to `n8n/workflows/W<n>-<slug>.json` (credentials are NOT exported; recreate them from `n8n/README.md`).

## Transport

The backend emits every event to **one** webhook URL with an envelope, and n8n routes on `event` with a Switch node:

```
POST ${N8N_WEBHOOK_URL}            # default http://n8n:5678/webhook/ward-events
Content-Type: application/json
X-Ward-Secret: ${N8N_EVENT_SECRET}
```

```json
{ "event": "alert.critical", "ts": "2026-10-08T09:30:00Z", "data": { } }
```

Backend helper (Wali implements it in `backend/app/integrations/n8n.py`; everyone calls it):

```python
def emit(event: str, data: dict) -> None:
    """Fire-and-forget: posts on a daemon thread with a 3 s timeout, logs failures, never raises."""
```

## Events (backend → n8n)

| Event | Fired when | `data` | Workflow |
|---|---|---|---|
| `appointment.confirmed` | `POST /appointments/{id}/confirm` | `{appointment_id, patient_first_name, patient_telegram_chat_id, patient_email, slot_at, doctor_name}` | W1 schedules the 24 h reminder |
| `appointment.cancelled` | `POST /appointments/{id}/cancel` or a W1 "cancel" reply | `{appointment_id, slot_at, doctor_id, doctor_name, candidate}`. `candidate` is the best waiting patient for the freed slot (ranked by `rank_backfill`: urgency desc, no-show probability asc, oldest first): `{appointment_id, patient_first_name, patient_telegram_chat_id, patient_email}`, or `null` when `slot_at` is null or nobody is waiting | W2 backfill |
| `dose.missed` | `events/dose_missed` ingested | `{dose_id, patient_id, patient_first_name, bed, meds[], scheduled_at, nurse_chat_ids[], doctor_chat_id, doctor_email}` | W3 |
| `alert.critical` | alert with severity `high` or `critical` | `{alert_id, patient_first_name, bed, kind, news2, message, nurse_chat_ids[], doctor_chat_id}` | W4 |
| `patient.discharged` | `POST /admissions/{id}/discharge` | `{patient_id, patient_first_name, patient_email, patient_telegram_chat_id, doctor_id, discharged_at}` | W6 |
| `exam.ordered` | `POST /appointments/{id}/exams/order` or `POST /exams` | `{appointment_id, patient_first_name, patient_telegram_chat_id, patient_email, exams:[{label, department}]}` | W7 tells the patient where to go |
| `exam.results_ready` | the last ordered exam of an appointment gets its result | `{appointment_id, patient_first_name, doctor_id, doctor_name, doctor_email, doctor_chat_id}` | W8 tells the ordering doctor |
| `health_event.upcoming` | `POST /health-events/{id}/notify` (Notify now), and each item returned by `GET /integrations/n8n/health-events/due` | `{event_id, title:{en,fr,ar}, category, starts_on, ends_on, organizer, source_url, web_url, recipients:[{first_name, role, email, lang}], recipient_count}`. `web_url` = `${WEB_URL}/calendar`; first names only; `lang` defaults to `fr` (no per-user language stored server-side yet) | W9 |

W5 (daily digest) is cron-driven inside n8n and pulls from `GET /integrations/n8n/daily-digest`.

n8n's public base URL (used in W2's accept links, which phones open) comes from `N8N_PUBLIC_URL` in `.env`. Set it to the laptop's LAN IP for the demo, e.g. `http://192.168.1.10:5678/`.

## Callbacks (n8n → backend)

| Callback | Used by | Body |
|---|---|---|
| `POST /integrations/n8n/appointment-reply` | W1 stretch (Telegram inline button via tunnel) | `{"appointment_id","reply":"confirm\|cancel"}` |
| `POST /integrations/n8n/backfill-accept` | W2 | `{"appointment_id","slot_at"}` → 200 `{"status":"confirmed"}`, or 409 `{"code":"slot_taken"}` if the slot was filled meanwhile, or 409 `{"code":"not_waiting"}` if the appointment is no longer `requested` |
| `GET /integrations/n8n/daily-digest[?doctor_id=]` | W5 | → `[{"doctor":{"id","name","email"},"patients":[{"name","bed","news2","summary"}]}]`: one entry per doctor with at least one admitted patient; `doctor_id` filters to that doctor (still a list) |
| `POST /integrations/n8n/follow-up` | W6 | `{"patient_id","days":14}` → `{"appointment_id","status":"requested"}`. Creates a `requested` appointment with `referral_text: "Post-discharge follow-up in {days} days"` that goes through normal triage; an admin confirms the date (which then triggers W1) |
| `GET /integrations/n8n/health-events/due` | W9 (trigger B) | → list of `health_event.upcoming` payloads for events with `announced_at IS NULL` and `starts_on - notify_days_before <= today <= ends_on` |
| `POST /integrations/n8n/health-events/{id}/announced` | W9 (trigger B only; Notify now already sets it) | → `{"status":"announced"}`, idempotent; sets `announced_at` |

The backend base URL from inside Docker is `http://api:8000`.

## Workflows

| ID | Name | Priority | Trigger → steps |
|---|---|---|---|
| W4 | Critical-alert fan-out | **core, Day 1** | event `alert.critical` → Telegram message to each `nurse_chat_ids` + `doctor_chat_id`: "🚨 Bed {bed} · {patient_first_name} · NEWS2 {news2}: {message}" |
| W3 | Missed-dose escalation | **core, Day 2** | event `dose.missed` → Telegram to the ward nurses ("💊 Missed dose · Bed {bed} · {meds}") + email to the attending doctor |
| W1 | Appointment reminder | **core, Day 2** | event `appointment.confirmed` → Wait until `slot_at − 24h` → Telegram + email with two links to the web app: `${WEB_URL}/patient/appointments/{appointment_id}?action=confirm\|cancel` (the patient view calls the API). *Demo trick:* if `slot_at` is < 24 h away, send immediately. *Stretch:* Telegram inline buttons → `appointment-reply` callback (needs a public HTTPS tunnel such as `cloudflared` because Telegram triggers are webhooks) |
| W2 | Slot backfill | stretch | event `appointment.cancelled` with a `candidate` → Telegram + email offer with an **accept link** (n8n Wait-node resume URL, valid 2 h) → on click, callback `backfill-accept` → confirmation message to the patient (or "slot already taken"). No click within 2 h: nothing happens; staff can still offer the slot by hand |
| W5 | Doctor daily digest | stretch | Cron 07:30 Africa/Tunis → GET daily-digest → one email per doctor listing each admitted patient (bed, latest NEWS2, AI summary marked as needing review) |
| W6 | Discharge follow-up | stretch | event `patient.discharged` → callback `follow-up` (14 days) → Telegram + email to the patient: "your follow-up visit has been requested; the hospital will confirm the date" |
| W7 | Exams ordered | core for the single-visit demo | event `exam.ordered` → Telegram + email to the patient: "Before your visit, please do: {label} ({department}) …" |
| W8 | Results ready | core for the single-visit demo | event `exam.results_ready` → Telegram + email to the doctor: "{patient_first_name}'s results are in; the visit can be booked" |
| W9 | Health calendar | core for the calendar demo | `W9-health-calendar.json` (id `wardHealthCalW9x`). Trigger A: called by the W0 router on `health_event.upcoming`. Trigger B: Cron 08:00 Africa/Tunis → `GET /due` → split items. Both → one WhatsApp text to `WARD_WHATSAPP_PATIENT` and `WARD_WHATSAPP_STAFF` ("📅 {title.fr} · {dates} · {organizer} — {web_url}") → one email per recipient (`ward-smtp`) → `POST /announced` (trigger B only). `onError: continueRegularOutput` on every send node; W0 gets one more Switch branch |

## Changelog

- **1.4** (2026-10-10): `health_event.upcoming` event, health-events due/announced callbacks, W9 health calendar (daily cron + Notify now).

- **1.3** (2026-10-09): adds `exam.ordered` and `exam.results_ready` with W7/W8. Emitter: the exams router (Faouzi's lane); the emit helper stays Wali's.

- **1.2** (2026-10-05): W2/W5/W6 made buildable. `appointment.cancelled` adds `doctor_name` + `candidate`; `backfill-accept` defines its responses; `daily-digest` returns a list with doctor email; W6 books through the new `follow-up` callback instead of a service JWT; `N8N_PUBLIC_URL`. Backend side of all of these: Faouzi (appointments + integrations routers).

- **1.1** (2026-10-05): `dose.missed` adds `doctor_chat_id` and `doctor_email` (attending doctor) so W3 can reach the doctor. Emitter side: Wali.

- **1.0** (2026-10-05): initial freeze. W1 replies go through web-app links (Telegram buttons need a public tunnel). Adds the single-webhook envelope, the secrets and the core/stretch split.
