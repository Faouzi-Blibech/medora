# n8n workflows (owner: Faouzi)

Self-hosted n8n runs in Docker at http://localhost:5678. The contract is `docs/contracts/n8n-webhooks.md`.

## Layout

- `workflows/W<n>-<slug>.json`: exported workflows (n8n → ⋯ → Download). Commit them after every change.
- Credentials are **never** exported. Recreate them on each machine:
  - **WhatsApp** (no n8n credential, read from `.env`): `WAHA_API_KEY`, `WARD_WHATSAPP_STAFF` (comma-separated
    staff numbers) and `WARD_WHATSAPP_PATIENT`. See "WhatsApp setup" below.
  - **SMTP**: e.g. a Gmail app password, credential name `ward-smtp`.
  - **Header Auth** for callbacks to the API: name `ward-callback`, header `X-N8N-Secret`, value = `N8N_CALLBACK_SECRET` from `.env`.

## Entry webhook

All backend events arrive at `POST /webhook/ward-events` with `{event, ts, data}` and header `X-Ward-Secret`.
The router workflow (`W0-router.json`) checks the secret, then fans out on `event` with a Switch node.

## Import (CLI, recommended)

The compose file mounts `n8n/workflows/` read-only at `/ward-workflows`. Workflow IDs are fixed (`wardRouterW00000`,
`wardCritAlertW04`, …) because the router calls each sub-workflow by ID.

```bash
# Git Bash on Windows: export MSYS_NO_PATHCONV=1 first, or the container paths get rewritten
C="docker compose -f infra/docker-compose.yml exec -T n8n"
for f in W4-critical-alert W3-missed-dose W1-appointment-reminder W2-slot-backfill W6-discharge-follow-up W5-doctor-daily-digest W9-health-calendar W0-router; do   # sub-workflows first
  $C n8n import:workflow --input=/ward-workflows/$f.json
done
for id in wardCritAlertW04 wardMissedDoseW3 wardApptRemindW1 wardBackfillW2xx wardFollowUpW6xx wardDigestW5xxxx wardHealthCalW9x wardRouterW00000; do
  $C n8n publish:workflow --id=$id
done
docker compose -f infra/docker-compose.yml restart n8n
```

Then in the UI → Credentials, create (or edit) **`ward-smtp`** (e.g. Gmail: `smtp.gmail.com`, port 465, SSL, an app password). All Email nodes point to it.
If an Email node shows the credential as missing (a credential created in the UI gets a new ID), open the workflow → the node → pick `ward-smtp` → save + publish. One click, once per laptop.

Every WhatsApp/Email node uses `onError: continueRegularOutput`: one bad recipient doesn't stop the others.

## WhatsApp setup (about 5 minutes)

Messages go out through **WAHA** (`waha` service in compose), a self-hosted gateway that links a WhatsApp account by
QR code, the same way WhatsApp Web does. No Meta or Twilio account is needed. It is unofficial: use a spare or
team number, not a personal one, and keep the volume low (a few demo messages).

1. In `.env`: `WAHA_API_KEY=<random>`, `WARD_WHATSAPP_STAFF=216xxxxxxxx,216yyyyyyyy`,
   `WARD_WHATSAPP_PATIENT=216zzzzzzzz` (digits only).
2. `docker compose -f infra/docker-compose.yml --env-file .env up -d waha n8n`
3. Open http://localhost:3010/dashboard (login `admin` / your `WAHA_API_KEY`). Start the session named **default**,
   then on the sender phone: WhatsApp → **Linked devices → Link a device** → scan the QR code.
4. When the session shows **WORKING**, send a test alert (see "Test" below).

The sender number should differ from the recipients: a message to yourself lands in "Message yourself" with no
notification. The link survives restarts (the `waha-sessions` volume).

In production the hospital would use the official WhatsApp Business API (Meta) instead; only the HTTP node's URL
and body change.

**Privacy:** staff alerts name the bed only ("Ward: critical alert, bed C-12. Open Ward now."): no patient name,
score, vitals or medication leaves the server. Patient messages carry the patient's own appointment details.
WhatsApp is still a third-party service outside Tunisia: a real deployment needs INPDP authorisation for it.

## Workflows

| File | ID | Status |
|---|---|---|
| `W0-router.json` | `wardRouterW00000` | ✅ checks `X-Ward-Secret`, drops unknown events, routes `alert.critical` → W4, `dose.missed` → W3, `appointment.confirmed` → W1, `appointment.cancelled` → W2, `patient.discharged` → W6, `health_event.upcoming` → W9 |
| `W4-critical-alert.json` | `wardCritAlertW04` | ✅ one WhatsApp message per staff number, bed only |
| `W3-missed-dose.json` | `wardMissedDoseW3` | ✅ WhatsApp to the staff numbers (bed and time only), email to the doctor (contract v1.1 field `doctor_email`) |
| `W1-appointment-reminder.json` | `wardApptRemindW1` | ✅ waits until `slot_at − 24h` (sends at once if the slot is sooner: demo trick), then WhatsApp + email to the patient with confirm/cancel links to `${WEB_URL}/patient/appointments/{id}?action=…` |
| `W2-slot-backfill.json` | `wardBackfillW2xx` | Offers a freed slot to the event's `candidate` (WhatsApp + email, link previews off) with an accept link valid 2 h (n8n resume URL under `N8N_PUBLIC_URL`). On click: `backfill-accept` → HTML result page + confirmation, or "slot already taken" on 409. A used link answers 409. |
| `W6-discharge-follow-up.json` | `wardFollowUpW6xx` | Calls `follow-up` (14 days) and, only if the backend created the appointment, tells the patient over WhatsApp + email that the follow-up is requested and the hospital will confirm the date. |
| `W5-doctor-daily-digest.json` | `wardDigestW5xxxx` | Every day at 07:30 Africa/Tunis (or on demand via its "Run now" trigger): `GET daily-digest`, then one email per doctor with an address and at least one admitted patient. Patients are listed by bed, highest NEWS2 first, with NEWS2 >= 5 flagged "review first" and summaries labelled as AI suggestions to review. Not called by the router. |
| `W9-health-calendar.json` | `wardHealthCalW9x` | W9 health calendar: daily 08:00 push of due health events + admin Notify now. Router event `health_event.upcoming` (Notify now) and the daily `GET health-events/due` both feed one Compose step, then WhatsApp (`WARD_WHATSAPP_PATIENT` + `WARD_WHATSAPP_STAFF`) and one email per opted-in recipient; cron runs then `POST .../announced`. |
| `W10-health-watch.json` | `wardHlthWatchW10` | Every day at 07:00 (or `POST /webhook/ward-health-watch` with `X-Ward-Secret`, the demo button): `GET health-watch`, then for today's and tomorrow's weather-health alerts one WhatsApp to the staff numbers (staff advice in French and Arabic, number of at-risk patients) and, when someone is at risk, one to the patient numbers (patient advice). No names. Not called by the router. |

## Test

W4 (critical alert):

```bash
curl -X POST localhost:5678/webhook/ward-events -H "X-Ward-Secret: change-me-event" -H "Content-Type: application/json"   -d '{"event":"alert.critical","ts":"2026-10-06T10:00:00Z","data":{"patient_first_name":"Amira","bed":"C-12","kind":"news2","news2":8,"message":"SpO2 88%, HR 130","nurse_chat_ids":["<your chat id>"],"doctor_chat_id":"<your chat id>"}}'
```

The webhook always answers 200 (`responseMode: onReceived`). A wrong secret is silently dropped; check Executions in the UI.

W3 (missed dose) and W1 (reminder, slot 2 h from now so it sends immediately):

```bash
curl -X POST localhost:5678/webhook/ward-events -H "X-Ward-Secret: change-me-event" -H "Content-Type: application/json" -d '{"event":"dose.missed","ts":"2026-10-06T08:31:00Z","data":{"dose_id":"d-000123","patient_first_name":"Amira","bed":"C-12","meds":["Paracetamol 500mg"],"scheduled_at":"2026-10-06T07:00:00Z","nurse_chat_ids":["<chat id>"],"doctor_chat_id":"<chat id>","doctor_email":"<you@mail>"}}'
curl -X POST localhost:5678/webhook/ward-events -H "X-Ward-Secret: change-me-event" -H "Content-Type: application/json" -d '{"event":"appointment.confirmed","ts":"x","data":{"appointment_id":"a-0001","patient_first_name":"Amira","patient_telegram_chat_id":"<chat id>","patient_email":"<you@mail>","slot_at":"<ISO time ~2h from now>","doctor_name":"Dr Trabelsi"}}'
```

A far-away `slot_at` parks the W1 execution in **Waiting** until 24 h before the slot (visible under Executions).

W2 (slot backfill): send the event, then open the `accept_url` (Executions → the waiting W2 run → "Plan offer" output, or the link in the WhatsApp message/email):

```bash
curl -X POST localhost:5678/webhook/ward-events -H "X-Ward-Secret: change-me-event" -H "Content-Type: application/json" -d '{"event":"appointment.cancelled","ts":"x","data":{"appointment_id":"a-0003","slot_at":"<ISO slot>","doctor_id":"u-0001","doctor_name":"Dr Trabelsi","candidate":{"appointment_id":"a-0007","patient_first_name":"Sami","patient_telegram_chat_id":"<chat id>","patient_email":"<you@mail>"}}}'
```

W6 (discharge follow-up):

```bash
curl -X POST localhost:5678/webhook/ward-events -H "X-Ward-Secret: change-me-event" -H "Content-Type: application/json" -d '{"event":"patient.discharged","ts":"x","data":{"patient_id":"p-0001","patient_first_name":"Amira","patient_email":"<you@mail>","patient_telegram_chat_id":"<chat id>","doctor_id":"u-0001","discharged_at":"2026-10-08T10:00:00Z"}}'
```

W5 (doctor digest) on demand, without waiting for 07:30:

```bash
# N8N_RUNNERS_BROKER_PORT avoids a port clash with the running n8n
docker compose -f infra/docker-compose.yml exec -e N8N_RUNNERS_BROKER_PORT=5690 n8n n8n execute --id=wardDigestW5xxxx
```

Or open W5 in the UI and click "Execute workflow". Note: in `n8n execute` (CLI) mode the Email node fails with "license provider has not been set", a CLI-only limitation. Use the UI to actually send the digest.

## Testing workflows without the backend

Point n8n at any stub that implements the `/integrations/n8n/*` callbacks:

```bash
WARD_API_URL=http://host.docker.internal:8099 docker compose -f infra/docker-compose.yml up -d --force-recreate n8n
```
