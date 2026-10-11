# Health calendar — design

> 2026-10-10 · Author: Wali · Lanes touched: backend (Wali), web + n8n (Faouzi, tagged on the PR) · Branch `wali/health-calendar`

## Goal

Every Medora user (patient, nurse, doctor, admin) sees a calendar of the important public-health events in Tunisia
(Octobre Rose, the seasonal flu campaign, HPV vaccination for girls, world health days…) and is told about the ones
that concern them: in the app (nav badge, home banner) and by push (WhatsApp + email through n8n). The admin curates
the list. Users choose which categories they follow.

Prototype honesty: national campaign dates are announced every year by the Ministry of Health / ONFP. The seed uses
the published or usual dates and every page says "Dates as announced — check with the Ministry of Health or ONFP".
No medical advice beyond the public campaign message.

## Decisions (agreed in brainstorming)

| Topic | Decision |
|---|---|
| Notification | In-app (badge + banner) **and** push via n8n W9 (WhatsApp + email) |
| Management | Admin creates, edits, deletes events and can press **Notify now** |
| Targeting | Each event has an **audience** (roles, sex, age range). Push goes to users who match the audience **and** follow the category. Everyone *sees* every event |
| Opt-in | Per-category preferences. Default = follow everything (opt-out rows only) |
| Patient | 5th tab **Calendar** in the phone app + banner on Home, and a full-width web page `/calendar` |
| Staff | New nav item **Health calendar** for doctor, nurse and admin, with a badge |
| Push trigger | n8n daily cron pulls `/integrations/n8n/health-events/due`; admin "Notify now" emits `health_event.upcoming` directly. Both converge on W9 |
| Delivery | One branch, commits per lane; contract bump first |

## Data (data-model 1.5 → 1.6, migration `0006_health_calendar`)

### `health_events`

| Column | Type | Notes |
|---|---|---|
| `id` | text PK | `he-0001` (`new_id(db, "he")`) |
| `title` | jsonb | `{"en","fr","ar"}`, all three required |
| `description` | jsonb | `{"en","fr","ar"}`, may be empty strings |
| `category` | text | `screening` \| `vaccination` \| `chronic_disease` \| `infectious_disease` \| `lifestyle` \| `mental_health` \| `blood_donation` |
| `starts_on`, `ends_on` | date | inclusive; `ends_on >= starts_on` (single-day event: equal) |
| `audience` | jsonb | `{"roles": ["patient","nurse","doctor","admin"], "sex": "F"\|"M"\|null, "min_age": int\|null, "max_age": int\|null}` |
| `notify_days_before` | int | default 3, 0–30 |
| `source_url` | text, null | public page of the organiser |
| `organizer` | text, null | e.g. "ONFP", "Ministère de la Santé", "WHO" |
| `announced_at` | timestamptz, null | set when the push went out (W9 callback or Notify now); never pushed twice by the cron |
| `created_by` | text FK users, null | null for seeded rows |
| `created_at` | timestamptz | default now() |

Index on `starts_on`.

### `health_event_prefs`

| Column | Type | Notes |
|---|---|---|
| `user_id` | text FK users | PK part |
| `category` | text | PK part |
| `following` | bool | only `false` rows matter; no row = following |

### Audience matching (`app/services/health_calendar.py`)

`matches(user, patient | None, event, on: date) -> bool`:
- `user.role` must be in `audience.roles`.
- `sex`, `min_age`, `max_age` apply to **patients only** (via `users.patient_id → patients.sex / date_of_birth`, age
  computed on the event's `starts_on`). A patient with an unknown sex or birth date does **not** match a sex/age-limited
  event (no guess). Staff ignore sex/age limits (they are the audience by role).
- `recipients(db, event)` = active users that match **and** follow the event's category.

## Seed (`app/health_seed.py`, idempotent upsert by fixed id, run from `seed()` on both branches)

Ids `he-0001` … `he-0017`, Oct 2026 → Sep 2027:

| id | Dates | Event | Category | Audience | Organizer |
|---|---|---|---|---|---|
| he-0001 | 2026-09-30 → 2026-10-30 | Octobre Rose: free breast screening (Mamo Life mobile clinic, 24 governorates) | screening | patients F, 40+ ; all staff | ONFP |
| he-0002 | 2026-10-10 | World Mental Health Day | mental_health | everyone | WHO |
| he-0003 | 2026-10-15 → 2027-02-28 | Seasonal flu vaccination (pharmacies, basic health centres) | vaccination | patients 65+ ; all staff | Ministère de la Santé |
| he-0004 | 2026-11-01 → 2026-11-30 | Movember: prostate cancer awareness | screening | patients M, 50+ ; doctors | Movember / associations |
| he-0005 | 2026-11-14 | World Diabetes Day | chronic_disease | everyone | IDF / WHO |
| he-0006 | 2026-12-01 | World AIDS Day | infectious_disease | patients 15+ ; all staff | UNAIDS / WHO |
| he-0007 | 2027-02-04 | World Cancer Day | screening | everyone | UICC |
| he-0008 | 2027-02-08 → 2027-03-09 | Ramadan: fasting safely with diabetes or hypertension (approximate dates) | chronic_disease | patients 18+ ; doctors, nurses | Ministère de la Santé |
| he-0009 | 2027-03-24 | World TB Day | infectious_disease | everyone | WHO |
| he-0010 | 2027-04-07 | World Health Day | lifestyle | everyone | WHO |
| he-0011 | 2027-04-24 → 2027-04-30 | World Immunization Week | vaccination | everyone | WHO / Ministère de la Santé |
| he-0012 | 2027-04-05 → 2027-04-30 | HPV vaccination for 12-year-old girls (schools, basic health centres) | vaccination | patients F, 11–13 ; doctors, nurses | Ministère de la Santé |
| he-0013 | 2027-05-17 | World Hypertension Day | chronic_disease | patients 18+ ; all staff | WHL |
| he-0014 | 2027-05-31 | World No Tobacco Day | lifestyle | patients 15+ ; all staff | WHO |
| he-0015 | 2027-06-14 | World Blood Donor Day | blood_donation | patients 18–65 ; all staff | CNTS / WHO |
| he-0016 | 2027-07-28 | World Hepatitis Day | infectious_disease | everyone | WHO |
| he-0017 | 2027-09-29 | World Heart Day | chronic_disease | patients 18+ ; all staff | World Heart Federation |

"everyone" = roles all four, no sex/age limit. "all staff" = doctor, nurse, admin. A seed row is only inserted if its
id is missing (an admin edit is never overwritten). Titles and short descriptions in en/fr/ar, written in the
implementation; descriptions state the campaign message only (where/when/who), no clinical claims.

## API (api 1.9 → 1.10)

`HealthEvent` (out):
```json
{"id":"he-0001","title":{"en":"…","fr":"…","ar":"…"},"description":{"en":"…","fr":"…","ar":"…"},
 "category":"screening","starts_on":"2026-09-30","ends_on":"2026-10-30",
 "audience":{"roles":["patient","doctor","nurse","admin"],"sex":"F","min_age":40,"max_age":null},
 "notify_days_before":3,"organizer":"ONFP","source_url":"https://…","announced_at":null,
 "matches_me":true,"following":true}
```

| Endpoint | Who | Notes |
|---|---|---|
| `GET /health-events?from=YYYY-MM-DD&to=YYYY-MM-DD` | any active user | events overlapping `[from,to]`, sorted by `starts_on`; default window today → today+365. `matches_me`/`following` for the caller |
| `POST /health-events` | admin | body = HealthEvent without `id`, `announced_at`, `matches_me`, `following` → 201 HealthEvent. 422 `bad_dates` if `ends_on < starts_on` |
| `PATCH /health-events/{id}` | admin | partial; changing `starts_on` clears `announced_at` |
| `DELETE /health-events/{id}` | admin | 204; prefs are per category so nothing cascades |
| `POST /health-events/{id}/notify` | admin | emits `health_event.upcoming` now (after commit), sets `announced_at`, → `{"recipients": n}` |
| `GET /me/health-prefs` | any active user | `{"following": {"screening":true, …all 7}}` |
| `PUT /me/health-prefs` | any active user | same body (partial allowed) → same shape |

No patient data is read by these endpoints except the caller's own sex/date of birth for `matches_me`, so no
`audit_log` row (the rule covers reads of a patient record). The admin "Notify now" writes `audit_log`
(`action: "notify"`, `resource: "health_event"`).

### n8n callbacks (header `X-N8N-Secret`)

| Endpoint | Body / result |
|---|---|
| `GET /integrations/n8n/health-events/due` | events with `announced_at IS NULL` and `starts_on - notify_days_before <= today <= ends_on` → list of the `health_event.upcoming` payloads |
| `POST /integrations/n8n/health-events/{id}/announced` | sets `announced_at` (idempotent) → `{"status":"announced"}` |

## n8n (1.3 → 1.4)

Event `health_event.upcoming` (from Notify now) and each item of `/due` share one payload:
```json
{"event_id":"he-0001","title":{"en","fr","ar"},"category":"screening","starts_on":"2026-09-30","ends_on":"2026-10-30",
 "organizer":"ONFP","source_url":"https://…","web_url":"http://<WEB_URL>/calendar",
 "recipients":[{"first_name":"Amira","role":"patient","email":"patient1@example.tn","lang":"fr"}],
 "recipient_count":1}
```
First names only (n8n rule). `lang` defaults to `fr` (no per-user language stored server-side yet).

W9 `W9-health-calendar.json` (id `wardHealthCalW9x`):
- Trigger A: called by the W0 router on `health_event.upcoming`.
- Trigger B: Cron 08:00 Africa/Tunis → `GET /due` → split items.
- Both → one WhatsApp text to `WARD_WHATSAPP_PATIENT` and `WARD_WHATSAPP_STAFF` ("📅 {title.fr} · {dates} · {organizer} — {web_url}") → one email per recipient (`ward-smtp`) → `POST /announced` (trigger B only; Notify now already set it).
- `onError: continueRegularOutput` on every send node. W0 gets one more Switch branch.

## Web (Faouzi's lane — tagged on the PR)

Shared:
- `lib/types.ts`: `HealthEvent`, `HealthCategory`, `HealthAudience`, `HealthPrefs`.
- `lib/api.ts`: `getHealthEvents(from?, to?)`, `createHealthEvent`, `updateHealthEvent`, `deleteHealthEvent`,
  `notifyHealthEvent`, `getHealthPrefs`, `setHealthPrefs` (mock + real, same as every other call).
- `mocks/healthEvents.ts`: the 17 seed events (same ids/dates) and matching for the mock user of each role.
- `lib/healthCalendar.ts` (pure): month grid builder, `upcoming(events, today, days)`, `badgeCount`, category colours.
- `i18n/messages/calendar.ts`: every UI string in en/fr/ar.
- `components/calendar/HealthCalendar.tsx` (+ module CSS): month grid with event bars, prev/next/today, upcoming list,
  detail panel (title, dates, organizer, source link, "For you" chip when `matches_me`), "Categories I follow"
  switches, honesty footnote. Props: `editable` (admin) → add/edit/delete form and Notify now.
- `components/calendar/UpcomingBanner.tsx`: "Octobre Rose · until 30 Oct" for the nearest matching + followed event
  active now or starting within 7 days; dismissible per session.

Routes:
- `/doctor/calendar`, `/nurse/calendar`, `/admin/calendar` inside `RoleShell`; nav item `calendar.nav` with a badge =
  matching + followed events active today or starting within 7 days (fetched once in the Sidebar).
- `/patient/calendar`: phone-frame screen, compact (upcoming list + small month), 5th tab `calendar`, link "Open full
  calendar" → `/calendar`.
- `/calendar`: full-width page for any signed-in user (its own minimal header with Medora brand, language switcher,
  back link to the user's home).
- Patient Home shows `UpcomingBanner`; staff home pages show it above their content.

## Error handling

- Push never blocks the API (existing `emit_after_commit`); n8n down → event logged, `announced_at` still set by Notify now; cron path retries next day because `announced_at` stays null.
- Bad payloads → 422 with the existing `ApiError` codes; unknown id → 404 `not_found`; non-admin writes → 403.
- Web: `ErrorCard` on load failure; the calendar still renders an empty grid.

## Testing

Backend (pytest, real Postgres schema per run): matching (role, sex, age bounds, unknown sex/DOB, staff ignore
limits); prefs default/opt-out; recipients = match ∧ follow ∧ active; list window + flags; admin-only writes; bad
dates; PATCH clears `announced_at`; notify emits once with first names only + audit row; `/due` window and
`announced` idempotency; seed idempotent and does not overwrite edits.

Web: `npm run typecheck`, `npm run build`; browser check of every route in mock mode (EN + AR/RTL) and in real mode
against the local stack.

## Out of scope

Per-user language stored on the server, recurring-rule engine (rows are dated instances), ICS export, device (ESP32)
display of events, SMS.
