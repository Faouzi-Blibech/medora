# REST + WebSocket contract — v1.0

> **Version:** 1.18 (2026-10-11) · **Owners:** Wali (core, IoT, alerts), Faouzi (appointments, AI, integrations, exams, notebook), Hedi (pharmacy)
> Any change: open a PR that bumps the version above, add a changelog line, and announce it in the team chat.

## Conventions

- Base URL: `http://localhost:8000` (backend container `api`). The web app reads it from `NEXT_PUBLIC_API_URL`.
- JSON everywhere.
- Auth: `Authorization: Bearer <jwt>`. JWT claims: `sub` (user id), `role` (`doctor|nurse|admin|patient|pharmacist`), `patient_id` (only for the patient role), `exp` (8 h).
- IDs are prefixed strings: `u-0001` user, `p-0001` patient, `a-0001` appointment, `rx-0001` prescription, `d-000001` dose, `al-0001` alert, `adm-0001` admission, `ex-0001` exam order, `er-0001` exam result, `nb-0001` notebook entry, `he-0001` health event, `bsu-001` device, `d-0001` drug (formulary; shares the counter with doses but has 4 digits), `pr-0001` prescription review, `lot-0001` stock lot, `sm-0001` stock movement, `disp-0001` dispensation, `dl-000001` dispensation line.
- Timestamps are ISO-8601 UTC strings (`2026-10-08T09:30:00Z`). (MQTT uses epoch seconds; the backend converts.)
- Errors: `{"detail": "human readable", "code": "snake_case_code"}` with the right HTTP status (400, 401, 403, 404, 409, 422, 423, 429).
- **Every read of a patient record** (`GET /patients/{id}` and every `GET /patients/{id}/*`) writes an `audit_log` row.
- Permissions per endpoint: see the role matrix in `data-model.md`. The column "Roles" below is the short version.

## Auth

| Method & path | Roles | Body → Response |
|---|---|---|
| `POST /auth/login` | public | `{"email","password"}` → `{"access_token","token_type":"bearer","user":{"id","name","role","patient_id"}}` |
| `GET /me` | any | → `{"id","name","email","role","patient_id"}` |

Seed accounts (password `ward1234` for all): `doctor@ward.tn`, `nurse@ward.tn`, `admin@ward.tn`, `patient@ward.tn` (linked to `p-0001`), `pharmacist@ward.tn`.

## Accounts and access

Added in 1.9 (spec `docs/superpowers/specs/2026-10-10-accounts-and-access-design.md`). Existing endpoints keep their shapes. Error envelope and status-code conventions are unchanged.

| Method and path | Who | Notes |
|---|---|---|
| `GET /hospital` | anyone | `{"name": "Ward Hospital"}`: this install's hospital (one install per hospital), from the setting `HOSPITAL_NAME`. Rate-limited like the directory (30/min per IP). Feeds the hospital select on the sign-up form. |
| `POST /auth/register` | anyone | `{name, email, password, role, requested_doctor_id?, note?}` with `role` in `patient`/`nurse`/`doctor`/`pharmacist` (required; anything else, including `admin`, is 422). `role: "doctor"` with a `requested_doctor_id` is 422. `role: "pharmacist"` with a `requested_doctor_id` is 422. Unknown extra fields (`ward`, `enrollment_code`...) are 422. An unknown or inactive `requested_doctor_id` is stored as null. → 202 `RECEIVED` (always the same answer). The account is `pending`; `role` is stored as `requested_role`, and the real role is set at approval. |
| `POST /auth/reset` | anyone | `{email, code, new_password}` → 204, or generic 400 `invalid_code` |
| `POST /auth/login` | anyone | `email` at most 254 and `password` at most 200 characters (422 above). Adds 403 `account_pending` / `account_disabled` / `account_rejected` and 423 `account_locked`, only after the password is correct |
| `POST /auth/change-password` | logged-in user | `{current_password, new_password}` → 204 |
| `POST /auth/logout` | logged-in user | 204; audit row. Device-only: the client deletes its token; tokens are not revoked server-side |
| `GET /doctors/directory` | anyone | doctor display names and ids only, for the sign-up "I work with" picker and the share panel. No emails. → `[{id, name}]`. Rate-limited: anonymous callers share a per-IP bucket; a logged-in caller (bearer token) has a bucket of their own. |
| `GET /users?status=pending` | admin (all), doctor (his requests) | `status` is `pending` (default) or `rejected` → list of `pending_out` |
| `POST /users/{id}/approve` | admin, doctor | `{role, ward?, patient_id?}`; `role` is patient, nurse, doctor, pharmacist or admin (the approver may change the requested role; 422 otherwise). **Only the admin approves a pharmacist**; a pharmacist has no ward and no team. **Admin:** any pending or rejected request. **Doctor:** only a request whose `requested_doctor_id` is himself, and only as `patient` or `nurse` (403 otherwise; his nurses join his team, `ward` is ignored). A doctor cannot approve a request an admin rejected (403). `role: "patient"` links the account to a record: with `patient_id` the existing record (404 if missing, 409 `conflict` if it already has an account, 403 for a doctor if he is not its attending doctor); without `patient_id` a new record is created from the request's name (first word = first name, the rest = last name; other fields empty) with the approving doctor as attending, or, for the admin, the requested doctor if still active, else none. `patient_id` with any other role is 422. → `admin_out` |
| `POST /users/{id}/reject` | admin (any request), doctor (requests naming him) | → `admin_out`; only a pending request, otherwise 409 `bad_status` |
| `POST /users/{id}/disable` · `/enable` | admin (anyone but himself), doctor (his team only) | → `admin_out`; wrong current status → 409 `bad_status`. Disabling closes the user's open WebSockets (code 4401). A doctor cannot enable an account an admin disabled (403). |
| `GET /doctors/me/team` | doctor | his team members and their status → list of `admin_out` |
| `PATCH /users/{id}` | admin | `{ward}`: add or clear a ward on an active doctor or nurse (e.g. a team nurse) → `admin_out`; 409 `bad_status` for other roles |
| `POST /patients/{id}/reset-code` | admin, attending doctor | reset code for the patient's account → `{code, expires_at}` |
| `POST /users/{id}/reset-code` | admin | → `{code, expires_at}`, shown once |
| `GET /patients/{id}/access` | attending doctor, admin | active grants → list of `_grant_out` |
| `POST /patients/{id}/access` | attending doctor, admin | `{doctor_id, expires_at?}` (default 30 days, at most 365; 422 otherwise) → `_grant_out`. A new grant replaces the doctor's live one. **Sharing is read-only:** a grant lets the doctor read the patient (detail, list, vitals, exams, appointments, alerts, notes, WebSocket frames) but every write on that patient returns 403 `forbidden`. |
| `DELETE /patients/{id}/access/{doctor_id}` | attending doctor, admin | → 204; 404 if no live grant |
| `GET /staff` | admin | gains `status` |

Codes are 10 characters shown as `XXXXX-XXXXX`, valid 48 h, single use; a new code for the same user revokes the previous unused one. Only password-reset codes exist (the first-admin bootstrap code is a reset code too): there are no enrollment codes.

A disabled or rejected account receives nothing more: its open WebSockets are closed on disable, it is left out of Telegram alert recipients, results-ready events and the daily digest, and appointment confirm rejects it as `doctor_id` (422).

### Error codes (additions)

| Status | `code` | When |
|---|---|---|
| 422 | `weak_password` | under 10 characters, over 72 UTF-8 bytes, in the common list, or equal to the email, its local part or the name |
| 400 | `invalid_code` | unknown, expired or used code (one generic answer) |
| 409 | `conflict` | approve: the chosen patient record already has an account |
| 429 | `rate_limited` | failed logins (10/min per IP), `/auth/register` and `/auth/reset` (5/min, 30/day per IP), `/doctors/directory` and `/hospital` (30/min per IP, or per user when logged in) |
| 403 | `account_pending` | login with the right password while waiting for approval |
| 403 | `account_disabled` | login with the right password on a disabled account |
| 403 | `account_rejected` | login with the right password after a rejected sign-up |
| 423 | `account_locked` | 5 failed logins lock the account for 15 min |
| 409 | `bad_status` | the account is not in a status that allows the action |

### Response shapes

`RECEIVED` (`POST /auth/register`, 202):
```json
{ "status": "received", "detail": "If the details are valid, your account was created or is waiting for approval." }
```

`admin_out` (approve, reject, disable, enable, `PATCH /users/{id}`, `/doctors/me/team`):
```json
{ "id": "u-0007", "name": "...", "email": "...", "role": "nurse", "status": "active", "ward": "Cardiology", "supervisor_id": "u-0001" }
```
`role` is null for pending and rejected accounts; `ward` and `supervisor_id` are null when unset.

`pending_out` (`GET /users`):
```json
{ "id": "u-0008", "name": "...", "email": "...", "note": "nurse, Cardiology", "requested_role": "nurse", "requested_doctor_id": "u-0001", "requested_doctor_name": "Dr Trabelsi", "status": "pending", "created_at": "2026-10-10T09:30:00Z" }
```
`note`, `requested_doctor_id` and `requested_doctor_name` are null when not given; `requested_role` is `patient`, `nurse` or `doctor` (null only for accounts created before 1.9).

Codes (`reset-code`):
```json
{ "code": "ABCDE-23456", "expires_at": "2026-10-12T09:30:00Z" }
```

`_grant_out` (sharing):
```json
{ "patient_id": "p-0001", "doctor_id": "u-0003", "doctor_name": "Dr ...", "expires_at": "2026-11-09T09:30:00Z" }
```

## Patients and records

| Method & path | Roles | Notes |
|---|---|---|
| `GET /patients?ward=&q=&unlinked=` | doctor (own), nurse (ward), admin (list only: name, bed, device) | → `[PatientSummary]`. `unlinked=true` keeps only records with no active account (the candidates when approving a patient). |
| `GET /patients/{id}` | doctor (own), nurse (ward), patient (self) | → `Patient` |
| `PATCH /patients/{id}` | doctor (own), nurse (ward; allergies + notes only) | partial `Patient` → `Patient` |
| `GET /patients/{id}/vitals?from=&to=` | doctor, nurse, patient (self) | → `[Vital]`, default last 24 h, max 5000 points |
| `POST /patients/{id}/vitals` | nurse, doctor (write access) | `{hr?, spo2?, temp?}` (at least one; hr 20–250, spo2 50–100, temp 30–45) → 201 `Vital` with `source: "manual"`, `nurse_id` = the author. Scored with NEWS2 and alerted exactly like a feed reading (same `vital`/`alert` WS frames). 409 if the same author saved one this second. |
| `GET /patients/{id}/prescriptions` | doctor, nurse, patient (self) | → `[Prescription]` |
| `GET /patients/{id}/notes` · `POST /patients/{id}/notes` | doctor, nurse | `{"text"}` → `Note` |

```jsonc
// PatientSummary
{ "id": "p-0001", "first_name": "Amira", "last_name": "Ben Salah", "age": 54, "ward": "Cardiology",
  "bed": "C-12", "device_id": "bsu-001", "latest_news2": 1, "open_alerts": 0 }
// Patient = PatientSummary + 
{ "sex": "F", "date_of_birth": "1972-03-14", "allergies": ["penicillin"], "history": "Hypertension",
  "attending_doctor_id": "u-0001", "admission_id": "adm-0001" }
// Vital
{ "ts": "2026-10-08T09:30:00Z", "hr": 88, "spo2": 97, "temp": 37.1, "nurse_id": "u-0002", "news2": 0, "source": "device" }
// Note
{ "id": "n-0001", "author_id": "u-0002", "author_role": "nurse", "text": "...", "created_at": "..." }
```

## Prescriptions → pharmacy review → schedule

Changed in 1.15 (spec `docs/superpowers/specs/2026-10-10-hospital-pharmacy-design.md`). A new prescription waits for the pharmacist: it has no dose until it is validated, unless the doctor ticks `urgent`.

| Method & path | Roles | Notes |
|---|---|---|
| `POST /prescriptions/check` | doctor (attending) | Dry run while typing: `{patient_id, items[], replaces_id?}` → `{"checks": [Check]}`. Writes only an audit row (`prescription_check`). 422 `unknown_drug`; 404 unknown patient or `replaces_id`; 409 `conflict` if `replaces_id` is another patient's. |
| `POST /prescriptions` | doctor (attending) | `{patient_id, items[], care_plan, urgent?: bool = false, override_reason?: str ≤ 500, replaces_id?: str}` → 201 `Prescription` + `schedule_version`, `published_to_device`. Always saved as `pending_pharmacy`. `urgent: true`: doses are created and the schedule published at once. |
| `PATCH /prescriptions/{id}` | doctor (attending) | `{"active": false}` only (`true` is 422): stops it at once (status `stopped`, future doses deleted, schedule re-published) → same shape as POST. Allowed from `pending_pharmacy`, `changes_requested`, `validated`; otherwise 409 `bad_status`. Other edits = a new version through `replaces_id`. |

Item: `{med, drug_id?, dose_mg?, units_per_intake?, times[], slot?, days?}`. `med` (1–80) is the display string. `drug_id` is null for a non-formulary drug. `dose_mg` (> 0) is mg **per intake**; when absent the dose check uses `units_per_intake` (integer 1–10, default 1) × the drug's `unit_mg`. `times` has 1–8 `HH:MM`, `slot` is 1–4 or null, and `days` is 1–60 (default 1).

Errors: 422 `override_required` (a `critical` check and no non-blank `override_reason`; nothing is saved), 422 `unknown_drug` (unknown or inactive `drug_id`), 409 `conflict` (`replaces_id` belongs to another patient, is not `pending_pharmacy`/`changes_requested`/`validated`, or any later version in its chain is still live: a replace is allowed only when no later version is live), 404 (`replaces_id` unknown).

Versions: the new row gets `version = old.version + 1` and `replaces_id = old.id`. A replaced version that never ran (`pending_pharmacy` without urgent, or `changes_requested`) becomes `superseded` at once. A running one keeps running until the new version is validated, then becomes `superseded`. **Exception:** an `urgent` new version supersedes the running one at once (no double dosing); if that urgent version is then rejected, the old one is not restored. A rejected non-urgent new version leaves the old one as it was.

`active` is derived: true for `validated`, and for `pending_pharmacy` with `urgent`. Doses of a non-urgent prescription start at its validation time; an urgent one's start when it was written.

```jsonc
// Prescription (doctor, nurse, pharmacist)
{ "id": "rx-0002", "patient_id": "p-0001", "doctor_id": "u-0001", "items": [ ... ], "care_plan": "",
  "active": false, "created_at": "...", "status": "pending_pharmacy",   // pending_pharmacy|validated|changes_requested|rejected|stopped|superseded
  "urgent": false, "version": 1, "replaces_id": null, "checks": [Check],  // the checks stored at the last save or decision
  "override_reason": "…", "review_comment": null, "reviewed_by_name": null, "reviewed_at": null }
// Prescription (patient, self): only id, patient_id, doctor_id, items, care_plan, active, created_at, status
// POST/PATCH response: Prescription + "schedule_version": 4 | null, "published_to_device": bool (false when no dose changed)

// Check (sorted: critical, major, moderate, info; then item_index; then code)
{ "code": "allergy", "severity": "critical", "item_index": 0, "drug_id": "d-0003",
  "params": { "med": "Amoxicillin 1 g", "allergy": "penicillin", "class": "penicillin" },
  "message": "Amoxicillin: the patient is allergic to penicillin (penicillin)" }   // English, for logs; the web translates by code + params
```

| `code` | severity | `params` |
|---|---|---|
| `allergy` | critical \| moderate | `med, allergy` (the patient's wording), `class`. Moderate (cross-reactivity, e.g. penicillin to cephalosporin/carbapenem) adds `cross_reactivity: true, cross_class`; direct hits stay critical |
| `interaction` | critical \| major \| moderate | `med, groups[2], note, with_med, with_drug_id, with_item_index` (null when the other drug is in another prescription), `with_prescription_id` (null inside the same prescription) |
| `max_daily_dose` | major; critical above 2× | `med, daily_mg, max_daily_mg` |
| `duplicate_therapy` | major | `med, reason` (`same_dci`\|`same_atc_class`), `with_med, with_drug_id, with_item_index, with_prescription_id` |
| `non_formulary` | moderate | `med` |
| `high_alert` | info | `med` |
| `elderly` | moderate | `med, age` |
| `dose_unverified` | info | `med` (the drug has a daily maximum but the daily dose cannot be computed: bad values, no times, or a free-text match without `dose_mg`) |

Free-text items are checked too when `med` resolves to a formulary drug (by DCI or brand). Any check, `info` included, needs `acknowledged` at validation.

`GET /patients/{id}/prescriptions` returns the role's Prescription shape. `GET /patients/{id}/doses` is unchanged in Phase A: the nurse view shows the "pending pharmacy review" badge by joining `prescription_id` to this list (`status == "pending_pharmacy" && urgent`). `POST /doses/{id}/given` returns 409 `bad_status` when the dose's prescription is not active.

## Drug catalogue (1.15)

| Method & path | Roles | Notes |
|---|---|---|
| `GET /drugs?q=&active=true` | doctor, nurse, pharmacist, admin | → `[Drug]`, at most 50, ordered by DCI then strength. `q` (≤ 80) matches the DCI or a brand (substring) or the ATC code (prefix), case-insensitive, taken literally (`%`, `_` are not wildcards). `active`: `true` (default, active only), `false` (inactive only), `all`. Not audited (no patient data). |
| `POST /drugs` | pharmacist, admin | `DrugIn` → 201 `Drug`. 409 `conflict` if the same DCI (case-insensitive) + strength + form exists. Audited (`drug`). |
| `PATCH /drugs/{id}` | pharmacist, admin | Any `DrugIn` field → `Drug`. `unit_mg`/`max_daily_mg` may be set to null; other nulls are 422. `{"active": false}` retires a drug; there is no DELETE (405). Audited. |

```jsonc
// Drug
{ "id": "d-0003", "dci": "Amoxicillin", "brand_names": ["Clamoxyl"], "form": "tablet", "strength": "1 g",
  "unit_mg": 1000.0, "max_daily_mg": 6000.0, "atc_code": "J01CA04", "allergy_classes": ["penicillin", "beta_lactam"],
  "interaction_groups": [], "high_alert": false, "min_stock": 100, "active": true, "created_at": "...", "updated_at": "..." }
// DrugIn: dci (1–120), brand_names (≤ 20 × 1–80), form (tablet|capsule|syrup|injection|inhaler|patch|drops|other),
// strength (≤ 40), unit_mg (> 0 | null), max_daily_mg (> 0 | null), atc_code ("" or e.g. J01CA04; upper-cased),
// allergy_classes / interaction_groups (≤ 20 tags, lower-cased, ^[a-z][a-z0-9_]{0,39}$), high_alert, min_stock (≥ 0), active
```

## Pharmacist (1.15)

Role `pharmacist` only (403 for everyone else). Every worklist row and every review read writes `audit_log` (resource `prescription`, with `patient_id`), and so does every decision. The patient part is a minimal projection, never the full record: `{id, name, age, sex, ward, bed, allergies}` (no weight column exists; age is null without a date of birth).

| Method & path | Notes |
|---|---|
| `GET /pharmacy/worklist?status=pending_pharmacy` | `status`: `pending_pharmacy` (default), `changes_requested`, `all` (every status, the newest 200); anything else 422 → `[WorklistItem]`, urgent first, then the highest severity, then the oldest |
| `GET /pharmacy/prescriptions/{id}` | → `ReviewDetail`; 404 unknown |
| `POST /pharmacy/prescriptions/{id}/validate` | `{acknowledged?: bool = false, comment?: str ≤ 500}` → `Prescription`. 409 `bad_status` unless `pending_pharmacy`; 422 `ack_required` if the checks recomputed now are not empty and `acknowledged` is false |
| `POST /pharmacy/prescriptions/{id}/request-changes` | `{comment}` (1–500 after trimming; required) → `Prescription`; 409 `bad_status` |
| `POST /pharmacy/prescriptions/{id}/reject` | `{comment}` (1–500; required) → `Prescription`; 409 `bad_status` |
| `GET /pharmacy/summary` | → `{pending, urgent_pending, critical_pending, changes_requested}`; Phase B adds `low_stock` (drugs under `min_stock`) and `expiring` (lots with stock expiring within 30 days) |

Two pharmacists deciding at once: the status is checked under `SELECT … FOR UPDATE`, so the second gets 409 `bad_status`.

Side effects of a decision: the checks are recomputed and stored. A `prescription_reviews` row is written. Doses are rebuilt and the device schedule is re-published when something starts or stops: on validation, and on rejecting or requesting changes on an urgent prescription (future doses deleted). On validation, the version it replaces is superseded. Then the `prescription_status` WS frame goes out, and the n8n event `prescription.review`.

```jsonc
// WorklistItem
{ "prescription": Prescription, "patient": { "id": "p-0001", "name": "Amira Ben Salah", "age": 54, "sex": "F",
  "ward": "Cardiology", "bed": "C-12", "allergies": ["penicillin"] }, "doctor_name": "Dr Trabelsi",
  "checks": [Check], "urgent": false, "waiting_since": "...", "max_severity": "critical" }   // null without checks
// ReviewDetail
{ "prescription": Prescription, "patient": {…}, "doctor_name": "…",
  "running": [Prescription],   // the patient's other running prescriptions, without this one and the versions it replaces
  "checks": [Check],           // recomputed now
  "history": [Review],         // decisions on this prescription and the versions it replaces, newest first
  "replaces": Prescription | null }
// Review
{ "id": "pr-0001", "prescription_id": "rx-0002", "pharmacist_id": "u-0010", "pharmacist_name": "Pharm. Salma",
  "decision": "changes_requested", "comment": "…", "checks_snapshot": [Check], "created_at": "..." }
```

## Dispensing and stock (1.15, Phase B)

| Method & path | Roles | Notes |
|---|---|---|
| `GET /pharmacy/dispensing?date=YYYY-MM-DD&round=HH:MM&ward=` | pharmacist | `round` required; `date` defaults to today (Africa/Tunis); `ward` optional → `[{ward, patients: [{id, name, bed, doses: [RoundDose]}]}]`. Only doses of active prescriptions (validated, or urgent pending). Audited per patient. |
| `POST /pharmacy/dispensations` | pharmacist | `{ward, date, round_time, lines: [{dose_id, lot_id?}]}` (1–200 lines) → 201 `Dispensation` (`sent`). One transaction: dispensation, lot decrements (FEFO when `lot_id` is missing), stock movements. 409 `insufficient_stock` (body adds `drug_id`), 409 `already_dispensed`, 409 `bad_status` (prescription no longer active), 422 `invalid` (dose not in that ward/date/round, a dose twice, a lot of another drug, an expired lot, a lot on a non-formulary dose), 404 unknown dose. A refused request writes nothing. |
| `GET /dispensations?ward=&date=` | nurse (own ward only; another ward is 403), pharmacist | `date` defaults to today → `[Dispensation]` |
| `POST /dispensations/{id}/receive` | nurse of that ward | → `Dispensation` (`received`); idempotent; another ward 403 |
| `GET /pharmacy/stock` | pharmacist, admin | → `[StockItem]` for every active drug |
| `POST /pharmacy/stock/receipts` | pharmacist | `{drug_id, lot_number (1–40), expiry_date, quantity (1–100000)}` → 201 `Lot`. Tops up the lot when `(drug_id, lot_number)` exists; 409 `conflict` if it exists with another expiry; 422 if already expired; 404 unknown drug |
| `POST /pharmacy/stock/adjustments` | pharmacist | `{lot_id, delta (≠ 0, ±100000), reason: adjustment\|expired\|return, comment (1–500)}` → `Lot`. `expired` needs a negative delta (422). Below zero: 409 `insufficient_stock` (+ `drug_id`) |
| `GET /pharmacy/stock/reorder` | pharmacist, admin | → `[{drug_id, dci, strength, form, on_hand, min_stock, suggested_quantity}]` for drugs with `on_hand < min_stock`; `suggested_quantity = 2 × min_stock − on_hand` |

```jsonc
// RoundDose
{ "dose_id": "d-000123", "prescription_id": "rx-0001", "med": "Paracetamol 500mg", "drug_id": "d-0001", "quantity": 1,
  "suggested_lot": { "id": "lot-0001", "lot_number": "L0001-A", "expiry_date": "2027-10-10" } | null,
  "on_hand": 200 | null,   // null for a non-formulary dose
  "dispensed": false }
// Dispensation
{ "id": "disp-0001", "ward": "Cardiology", "round_date": "2026-10-10", "round_time": "20:00", "status": "sent",
  "prepared_by": "u-0010", "prepared_by_name": "Pharm. Salma", "prepared_at": "...",
  "received_by": null, "received_by_name": null, "received_at": null,
  "lines": [{ "id": "dl-000001", "dose_id": "d-000123" | null, "patient_id": "p-0001", "patient_name": "Amira Ben Salah",
              "bed": "C-12", "drug_id": "d-0001" | null, "lot_id": "lot-0001" | null, "lot_number": "L0001-A" | null,
              "quantity": 1, "med": "Paracetamol 500mg" }] }   // dose_id becomes null if the dose was later cancelled
// StockItem
{ "drug_id": "d-0001", "dci": "Paracetamol", "strength": "500 mg", "form": "tablet", "on_hand": 200, "min_stock": 200,
  "lots": [Lot], "low": false, "expiring": false, "expired": false }
// Lot (lots[] lists lots with quantity > 0)
{ "id": "lot-0001", "drug_id": "d-0001", "lot_number": "L0001-A", "expiry_date": "2027-10-10", "quantity": 200,
  "received_at": "...", "expired": false, "expiring": false }
```

`on_hand` is the sum of the lots that are not expired. `low` means `on_hand < min_stock`. A lot is `expiring` when it has stock and expires within 30 days (today included), and `expired` when its expiry is before today. FEFO takes, among the lots that are not expired on the round date and hold the whole line, the one that expires first (ties: oldest receipt, then id). One line takes from one lot.

Nurse round: each `Dose` in `GET /patients/{id}/doses` (and `POST /doses/{id}/given`) adds `"pharmacy": "none"|"sent"|"received"`. A dose can still be given when it is not dispensed (ward stock).

## Admissions, beds, devices

| Method & path | Roles | Notes |
|---|---|---|
| `GET /devices` | admin, nurse | → `[{"id","online","fw_version","last_seen","patient_id","bed"}]` |
| `POST /devices/{id}/assign` | admin | `{"patient_id","bed"}` → creates/updates the admission and publishes the schedule |
| `POST /admissions/{id}/discharge` | admin, doctor | Clears the device schedule (`patient_id:null`), sets `discharged_at`, fires the n8n `patient.discharged` event (W6) |
| `POST /devices/{id}/command` | doctor, nurse, admin | `{"type","text?","dose_id?"}`, forwarded to MQTT `command` (demo helper). `dispense_now` returns 409 `bad_status` when the dose's prescription is not active or the dose is already taken (1.15) |

## Appointments and waitlist (Faouzi)

| Method & path | Roles | Notes |
|---|---|---|
| `POST /appointments` | patient (self), admin | Runs triage synchronously (rules + trained model, no LLM) → `Appointment` with `status:"requested"` |
| `GET /appointments/waitlist` | admin, doctor | Requested appointments sorted by `urgency_final ?? urgency_ai` desc, then `created_at` asc |
| `GET /appointments?patient_id=&status=` | admin, doctor, patient (self) | |
| `PATCH /appointments/{id}` | admin, doctor | `{"urgency_final": 1-5}`: human override of the AI urgency without booking a slot; sets `human_confirmed_by` |
| `POST /appointments/{id}/confirm` | admin, doctor | `{"slot_at","urgency_final"?,"doctor_id"}`; `urgency_final` set means a human override of the AI. Sets `confirmed_by` |
| `POST /appointments/{id}/cancel` | admin, patient (self) | `{"reason"?}`; fires the n8n `appointment.cancelled` event (W2 backfill) |
| `POST /appointments/{id}/reply` | patient (self) | `{"reply":"confirm\|cancel"}`: the patient's answer to the W1 reminder. `confirm` sets `patient_confirmed_at`; `cancel` = the cancel flow |

```jsonc
// POST /appointments request
{ "patient_id": "p-0003", "referral_text": "ألم في الصدر منذ يومين / douleur thoracique", "symptoms": ["chest pain"],
  "preferred_dates": ["2026-10-12"] }
// Appointment
{ "id": "a-0001", "patient_id": "p-0003", "status": "requested|confirmed|cancelled|done|no_show",
  "urgency_ai": 5, "urgency_final": null, "triage": { "urgency": 5, "reasons": ["..."], "red_flags": ["chest_pain"], "source": "model|rules" },
  "slot_at": null, "doctor_id": null, "confirmed_by": null, "patient_confirmed_at": null, "no_show_prob": 0.18, "created_at": "..." }
```

## Alerts

| Method & path | Roles | Notes |
|---|---|---|
| `GET /alerts?status=open` | doctor, nurse | → `[Alert]` newest first |
| `POST /alerts/{id}/ack` | doctor, nurse | sets `acked_by`, `acked_at` |

```jsonc
// Alert
{ "id": "al-0001", "patient_id": "p-0001", "device_id": "bsu-001",
  "kind": "news2|trend|call_nurse|dose_missed|device_offline",
  "severity": "low|medium|high|critical", "news2": 7, "message": "SpO2 89%, HR 128",
  "created_at": "...", "acked_by": null, "acked_at": null }
```

## AI (Faouzi; early warning is internal, owned by Wali)

| Method & path | Roles | Notes |
|---|---|---|
| `POST /ai/triage` | admin, doctor | `{"referral_text","symptoms[]","age"}` → `{"urgency":1-5,"reasons[]","red_flags[]","model_urgency","confidence","source"}`. `model_urgency` and `confidence` are null when no trained model is loaded. Preview only, nothing stored |
| `GET /ai/summary/{patient_id}` | doctor | → `{"summary","interactions":[{"drugs":[a,b],"severity","note"}],"source","generated_at","human_confirmed_by"}` (cached 10 min; `human_confirmed_by` is null until a doctor reviews it, and the UI shows "needs review" until then) |
| `POST /ai/summary/{patient_id}/review` | doctor | Marks the latest summary as reviewed (`human_confirmed_by`) |
| `POST /ai/chat` | doctor, nurse, patient | `{"question","patient_id?","history?":[{"role":"user"\|"assistant","text"}],"lang?":"en"\|"fr"\|"ar"}` → `{"id","answer","citations":[{"n?","source_id","kind","title","ts","text"}],"source":"llm"\|"rules","unverified?":[..],"urgent?"}`. Answers only from one patient's record (RAG), in the language of the question. Doctor and nurse: `patient_id` required, access-checked and audited (`ai_chat`); patient: own record. Stored as a `notebook_entries` row. |
| `GET /ai/conversations` · `POST /ai/conversations` · `GET /ai/conversations/{id}` · `DELETE /ai/conversations/{id}` | doctor, nurse (own conversations only; others 404) | The sidebar "AI assistant" page: `{"id","title","created_at","updated_at"}`; `GET {id}` adds `messages[]` (`{"id","role","text","patient":{"id","name"}\|null,"created_at","citations?","source?","unverified?"}`) and `patient` (the current one). Reading a conversation re-checks and audits each patient in it. |
| `POST /ai/conversations/{id}/messages` | doctor, nurse | `{"question","patient_id?","clear_patient?","lang?"}` → `{"message","conversation"}`. `patient_id` = the patient mentioned with @; omitted = the conversation's current patient; `clear_patient: true` = a general question (no record). With a patient: same rules as `POST /ai/chat`. |
| `POST /patients/{id}/reports` | doctor (write access) | multipart `file` (PDF, JPEG, PNG or text, ≤ 15 MB), `title?`, `report_text?` → the `ExamOrder` (department `"Report"`, status `done`). The chat reads the text of PDF and text reports. |
| `POST /ai/assistant` *(stretch)* | patient | `{"question"}` → `{"answer","sources[]","intent","source"}`, scoped to the caller's own record |

`source` is `"model"` (a trained model decided), `"rules"` (deterministic rules only) or `"llm"` (the optional open LLM wrote the text) on every AI response, so the UI can show a badge.

## Shift handover (1.17 — Faouzi)

| Method & path | Roles | Notes |
|---|---|---|
| `GET /handover?ward=&hours=12&lang=` | nurse (her ward, plus her supervisor doctor's patients; another `ward` is 403 like `GET /patients`), doctor (his patients) | `hours` is 8, 12 or 24 (anything else falls back to 12); `lang` (`en`\|`fr`\|`ar`, optional) only steers the optional LLM narrative. → `{"window_hours","generated_at","items":[Handover]}`, highest NEWS2 first. Items: patients with an active admission, plus patients in scope with vitals, notes, alerts or doses in the window. Each item is an audited read (`handover`). |
| `POST /handover/{patient_id}/confirm` | nurse (write access to the patient) | `{"hours"?: 12, "lang"?}` → `Handover` with `confirmation` set. The outgoing nurse read the draft: it is stored in `handovers` (`ai_suggested` = the draft, `human_confirmed_by` = the nurse). Audited (`handover`, `update`). |

`Handover`: `{"patient":{"id","first_name","last_name","ward","bed","age","sex"}, "window":{"hours","from","to"}, "situation":{"bed","ward","reason","admitted_at","latest_news2","news2_trend":"rising"|"falling"|"stable"|null,"latest_vital_at"}, "background":{"allergies[]","meds":[{"med","times[]"}],"care_plans[]"}, "assessment":{"vitals":{"count","hr","spo2","temp","news2"} (each `{"min","max","latest","trend"}` or null), "alerts":{"raised","acked","open":[{"id","kind","severity","message","created_at"}]}, "doses":{"given","missed":[Dose]}, "notes":[{"text","author_name","created_at"}] (last 5), "notes_count"}, "recommendations":[{"code","params"}], "upcoming_doses":[Dose], "narrative", "source":"rules"|"llm", "generated_at", "confirmation":null|{"id","human_confirmed_by","human_confirmed_by_name","confirmed_at","window_hours","source"}}` with `Dose` = `{"id","scheduled_at","time","meds[]","status"}` (`time` is HH:MM Africa/Tunis).

Recommendation `code`s (rules in `backend/app/ai/rules/handover.v1.json`; the UI translates them): `news2_high {score}`, `news2_rising {from,to}`, `open_alert {kind,severity,time,at}`, `missed_dose {time,meds}` (status `missed`, or still scheduled/dispensed 60 min after its time), `no_vitals {hours}`, `pending_exam {label}` (exam `ordered`), `next_dose {time,meds}` (next 4 h), `routine {}` (nothing else). The structured sections always come from rules; with an LLM configured only `narrative` may be rewritten (kept only if it adds or changes no number). `confirmation` is the latest confirmation within the window.

## Health watch (Faouzi)

| Method + path | Who | Body / response |
|---|---|---|
| `GET /health-watch` | doctor, nurse, admin | `{"city","available","demo","days":[{date,tmax,tmin,apparent_max,precip,gusts,uv,dust_max,pm10_max,aqi_max}],"alerts":[{id,date,severity,value,groups[],title,staff,patient,at_risk[],at_risk_count}],"news":[{title,link,source,published,lang}],"updated_at"}`. Texts are `{en,fr,ar}`. `at_risk`: the patients this user can access whose age or history puts them in a group (audited `health_watch`); admin gets counts only. |
| `GET /health-watch/me` | patient | Same forecast; alerts carry `patient` advice and `concerns_me`, no staff text, no news. |
| `GET /integrations/n8n/health-watch` | n8n (`X-N8N-Secret`) | `{"city","demo","alerts":[{..., "staff","patient","at_risk_count"}]}`: no names. |

## Integrations (n8n callbacks — Faouzi)

All are authenticated with the header `X-N8N-Secret: ${N8N_CALLBACK_SECRET}` (no JWT). See `n8n-webhooks.md`.

| Method & path | Body |
|---|---|
| `POST /integrations/n8n/appointment-reply` | `{"appointment_id","reply":"confirm\|cancel"}` |
| `POST /integrations/n8n/backfill-accept` | `{"appointment_id","slot_at"}` → `{"status":"confirmed"}` · 409 `slot_taken` / `not_waiting` |
| `GET /integrations/n8n/daily-digest[?doctor_id=]` | → `[{"doctor":{"id","name","email"},"patients":[{"name","bed","news2","summary"}]}]` |
| `POST /integrations/n8n/follow-up` | `{"patient_id","days"}` → `{"appointment_id","status":"requested"}` |
| `GET /integrations/n8n/health-events/due` | events with `announced_at IS NULL` and `starts_on - notify_days_before <= today <= ends_on` → list of the `health_event.upcoming` payloads (see `n8n-webhooks.md`) |
| `POST /integrations/n8n/health-events/{id}/announced` | sets `announced_at` (idempotent) → `{"status":"announced"}` |

## Health calendar (1.13 — Wali)

Dated public-health events in Tunisia (Octobre Rose, flu campaign, HPV vaccination, world health days). Everyone sees every event; push goes only to active users who match the event `audience` and follow its category. Categories: `screening`, `vaccination`, `chronic_disease`, `infectious_disease`, `lifestyle`, `mental_health`, `blood_donation`. Event ids are `he-0001`.

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

Unknown id → 404 `not_found`; non-admin writes → 403. No patient data is read by these endpoints except the caller's own sex/date of birth for `matches_me`, so no `audit_log` row (the rule covers reads of a patient record). The admin "Notify now" writes `audit_log` (`action: "notify"`, `resource: "health_event"`).

## Radiograph reading (1.14 — Wali)

An AI draft report per radiograph image (JPEG/PNG of exam codes `chest_xray`, `xray`, `xray_outside`). The model only drafts; a doctor edits and confirms. Images are read by a local vision model only (`VISION_PROVIDER=local`); with none, the status is `unavailable` and the doctor writes the report. Statuses: `queued`, `running`, `ready`, `unavailable`, `failed`. Reading ids are `rr-0001`.

`RadiographReading` (doctor view):
```json
{"id":"rr-0001","exam_result_id":"er-0901","patient_id":"p-0001","status":"ready","hint":"Chest X-ray",
 "ai_suggested":{"source":"llm","model":"qwen3-vl:4b","region":"chest","projection":"PA","quality":"adequate",
   "findings":["Clear lung fields"],"impression":"No acute abnormality seen.",
   "possible_conditions":[{"name":"No acute cardiopulmonary disease","likelihood":"high","evidence":"normal lungs, heart size"}],
   "urgent_flags":[],"recommendation":"","draft_text":"Technique : …","disclaimer":"AI draft from a prototype, not a diagnosis and not clinically validated. A doctor must review it."},
 "final_text":null,"human_confirmed_by":null,"confirmed_by_name":null,"confirmed_at":null,
 "created_at":"2026-10-10T09:00:00Z","finished_at":"2026-10-10T09:00:40Z"}
```

| Endpoint | Who | Notes |
|---|---|---|
| `GET /exam-results/{result_id}/reading` | doctor, nurse with result access | doctor: full reading (audit `read radiograph_reading`); nurse: `{id, exam_result_id, status}`; 404 when the result has no reading |
| `PUT /exam-results/{result_id}/reading` | doctor with result access (not a sharing grant) | `{"final_text": "1..20000 chars"}` → sets `final_text`, `human_confirmed_by`, `confirmed_at`; copies the text into `exam_results.report_text`; audit `update`; re-confirming edits it. Allowed in any status (a doctor may write before the AI finishes; the worker never overwrites `final_text`). A read-only sharing grant cannot confirm (403): write access is the attending doctor, the orderer or the appointment's booked doctor |
| `POST /patients/{patient_id}/radiographs` | doctor with write access | multipart `file` (JPEG/PNG ≤ 15 MB), `title` (default "Outside X-ray") → creates a done `Imaging` exam `xray_outside` + result + queued reading → `ExamOrder` (201) |

`ExamOrder.results[]` gains `reading: {"id","status","confirmed"} | null`. New exam codes `xray` and `xray_outside` (department `Imaging`); `chest_xray` is also read. Uploading a radiograph through `POST /exams/{id}/results` enqueues a reading.

## Pilot impact (1.18 — Faouzi; backend area: Wali)

`GET /admin/impact?days=30` · **admin** only (`days` 1–365; the UI offers 7, 30 and 90). Aggregates only: no patient names or ids, so no `audit_log` row. Measures the period `[now - days, now)` and the previous period of equal length.

```json
{"days":30,"period":{"from":"…Z","to":"…Z"},"previous_period":{"from":"…Z","to":"…Z"},
 "patient_days":12.5,"data":"synthetic",
 "indicators":[{"id":"ack_median_min","group":"alerts","unit":"minutes","better":"lower",
                "status":"ok","value":3.5,"previous":6.0,"breakdown":null}]}
```

- `group`: `alerts | medication | appointments | monitoring | workload`. `unit`: `count | pct | minutes | hours | days | rate`. `better`: `higher | lower | null` (null = context, not a target).
- `status`: `ok`, or `not_recorded` when the data model cannot measure it (`value`/`previous` null). `value: null` with `ok` = nothing to measure in that period (empty denominator).
- `breakdown` (current period only): `alerts_total` by severity, `vitals_automated_pct` by `source`, `news2_medium_high_pct` by band (`low` 0–4, `medium` 5–6, `high` 7+), `ai_reviewed_pct` `{reviewed, pending}`.
- Ids: `alerts_total`, `ack_median_min`, `ack_p90_min` (created → acked), `ack_within_5min_pct` (high/critical, an open alert counts as late); `doses_due` (doses whose 30-min window closed), `doses_taken_pct`, `doses_missed_pct`, `doses_on_time_pct` (taken, `updated_at` within 30 min of the dose time), `missed_per_patient_day`; `requests_received`, `request_to_booking_hours` (always `not_recorded`: no booking timestamp), `request_to_slot_days` (median request → appointment date), `cancellations` (of the period's requests), `backfill_refills` (booked by the system, `confirmed_by` empty), `no_show_rate_pct` (`not_recorded` until some appointment is `done`/`no_show`); `vitals_per_patient_day`, `vitals_automated_pct`, `news2_medium_high_pct`; `nurse_notes_per_shift` (3 shifts a day), `ai_reviewed_pct` (AI summaries, notebook answers and triaged requests with `human_confirmed_by`).
- Patient-days = admitted time overlapping the period (`admissions`).

## Health

`GET /health` → `{"status":"ok","db":true,"mqtt":true}` (public).

## WebSocket

`WS /ws?token=<jwt>`: the server pushes JSON frames; the client sends nothing (except optional `{"type":"ping"}`).

```jsonc
{ "type": "vital",         "data": { "patient_id": "p-0001", "device_id": "bsu-001", "ts": "...", "hr": 88, "spo2": 97, "temp": 37.1, "news2": 0 } }
{ "type": "alert",         "data": Alert }
{ "type": "call_nurse",    "data": { "patient_id": "p-0001", "device_id": "bsu-001", "bed": "C-12", "ts": "..." } }
{ "type": "dose_event",    "data": { "patient_id": "p-0001", "dose_id": "d-000123", "status": "dispensed|taken|missed", "method": "ir|button", "ts": "..." } }
{ "type": "device_status", "data": { "device_id": "bsu-001", "online": false, "ts": "..." } }
{ "type": "prescription_status", "data": { "prescription_id": "rx-0002", "patient_id": "p-0001", "status": "validated", "urgent": false } }
{ "type": "radiograph_reading", "reading_id": "rr-0001", "exam_result_id": "er-0901", "patient_id": "p-0001", "status": "ready" }
```

Filtering: a nurse receives frames for their ward, a doctor for their own patients, an admin only `device_status`, a pharmacist only `prescription_status` (every patient). `prescription_status` is sent on every status change (save, stop, decision, supersede) to the attending doctor, the patient's ward nurses and every pharmacist. Patients do not connect.

## Proposed in 1.5 (web UI needs)

Proposed by Faouzi from the web UI (`web/src/lib/api.ts`, `web/src/lib/types.ts`); **Wali to confirm** before the backend builds them. Nothing above changes. Until confirmed, the web app calls these paths in real mode but survives their absence (empty sections, not error pages).

**Endpoints**

| Method & path | Roles | Notes |
|---|---|---|
| `GET /patients/{id}/doses?date=YYYY-MM-DD` | doctor, nurse, patient (self) | → `[Dose]` oldest first (the `med_doses` rows). Without `date`: the last 24 h and the rest of today |
| `POST /doses/{id}/given` | nurse | Nurse gave the dose by hand → `Dose` with `status:"taken"`, `given_by`, `taken_at` |
| `GET /offers/{id}` | patient (self) | → `SlotOffer` (a freed slot offered by the W2 backfill) |
| `POST /offers/{id}/accept` | patient (self) | → the moved `Appointment` · 409 `slot_taken` / `not_waiting` |
| `GET /patients/{id}/home-care` | patient (self) | → `HomeCarePlan` (the "After discharge" screen) |
| `GET /staff` | admin | → `[StaffMember]` |
| `POST /staff` | admin | `{"name","email","role","ward"}`: invite a staff member → `StaffMember` |
| `DELETE /ai/summary/{id}/review` | doctor | Un-review (clears `human_confirmed_by`); the UI's "Undo" |
| A patient call-nurse request *(optional)* | patient (self) | e.g. `POST /patients/{id}/call-nurse` → raises a `call_nurse` alert. The bedside unit has no button, so this is the only way a patient could ask |
| Admin dashboard stats | admin | Admitted count, requests per day by urgency, reminders confirmed, slots refilled, open offers (one stats endpoint, e.g. `GET /stats/today`) |
| Admin read of alert counts | admin | Either `GET /alerts` for admin (counts only) or the stats endpoint above |

**Fields**

| Type | Added fields |
|---|---|
| `PatientSummary` | `last_vital_at`, `device_online`, `sex` |
| `Patient` | `admitted_at`, `allergy_notes`, `attending_doctor_name`, `nurse_name` |
| `Vital` | `rr`, `bp_sys`, `bp_dia`; `source` enum `device\|simulator\|manual` |
| `Note` | `author_name` |
| `Prescription` | `allergy_override` |
| `Dose` | full shape (`id`, `prescription_id`, `patient_id`, `scheduled_at`, `time_of_day`, `meds[]`, `slot`, `status`, `taken_method`, `updated_at`) plus `taken_at`, `given_by`, `given_by_name`, `instructions` |
| `AiSummary` | `human_confirmed_by_name`, `reviewed_at`, `based_on {vitals, doses, notes}` |
| `Appointment.triage` | `confidence`, `model_urgency` |
| `Appointment` | `ai_suggested`, `human_confirmed_by`, `human_confirmed_by_name`, `patient_name`, `patient_age`, `specialty`, `referral_text`, `lang` (`fr\|ar\|aeb-Latn\|en`), `doctor_name`, `room`, `confirmed_by_name` |
| `Alert` | `bed`, `patient_first_name`, `acked_by_name`; AI `source` on `trend` alerts |
| `Device` | `patient_name`, `admission_id` (the active admission, needed for `POST /admissions/{id}/discharge`) |

New types:

```jsonc
// StaffMember
{ "id": "u-0001", "name": "Dr Trabelsi", "email": "...", "role": "doctor|nurse|admin", "ward": "Cardiology", "scope": "Cardiology · Ward C", "last_login_at": "..." }
// SlotOffer
{ "id": "of-0001", "appointment_id": "a-0001", "slot_at": "...", "doctor_id": "u-0001", "doctor_name": "Dr Trabelsi", "room": "...", "status": "open|accepted|taken", "expires_at": "..." }
// HomeCarePlan
{ "patient_id": "p-0001", "discharged_at": "...", "ward_label": "...", "follow_up": { "title": "...", "steps": ["..."] }, "medicines": [...], "desk_phone": "...", "emergency_number": "190" }
```

**Patient role:** an appointment returned to the patient role (`GET /appointments?patient_id=`, `/appointments/{id}/reply`, `/offers/{id}/accept`) must omit `urgency_ai`, `triage` and `no_show_prob`. The patient never sees an AI urgency score.

## Confirmed in 1.6 (Wali: core, IoT, alerts)

Wali confirms and has built these 1.5 proposals (`wali/backend-core`). The others in the 1.5 list stay proposed.

| Method & path | Roles | Notes |
|---|---|---|
| `GET /patients/{id}/doses?date=YYYY-MM-DD` | doctor (own), nurse (ward), patient (self) | → `[Dose]` oldest first. `date` is a local (Africa/Tunis) day; without it, the last 24 h and the rest of today. Audited like every patient read |
| `POST /doses/{id}/given` | nurse (ward) | → `Dose` with `status:"taken"` plus `given_by`, `given_by_name`, `taken_at` **in this response only**: the confirming nurse is kept in `audit_log`, not on `med_doses` (no column in data-model 1.3). Also pushes a `dose_event` WS frame |
| `GET /staff` | admin | → `[StaffMember]`; `scope` is the ward, or `"All wards"` for staff without one; `last_login_at` from the latest `login` audit row (null if never) |

`Dose` = the `med_doses` row: `{id, prescription_id, patient_id, scheduled_at, time_of_day, meds[], slot, status, taken_method, updated_at}`.

Fields confirmed (additive; every 1.4 field is unchanged):

| Type | Fields now returned |
|---|---|
| `PatientSummary` | `sex`, `last_vital_at`, `device_online`, `admission_id` |
| `Patient` | `admitted_at`, `attending_doctor_name` |
| `Note` | `author_name` |
| `Alert` | `bed`, `patient_first_name`, `acked_by_name`, `source` (from `ai_suggested.source`; `"rules"` for `news2`/`trend`, null otherwise) |
| `Device` (`GET /devices`) | `patient_name`, `admission_id`, `schedule_version`, `schedule_acked_version` |

Not built yet (still proposed): `Vital.rr/bp_sys/bp_dia` (the simulator sends none), `Patient.allergy_notes/nurse_name`, `Prescription.allergy_override`, `POST /staff`, the patient call-nurse route, the stats endpoint, and Faouzi's offers / home-care / summary items.

Clarifications of 1.4 behaviour, as built:
- `GET /alerts?status=` accepts `open` or `all` (default all); anything else is a 422. An admin gets 403.
- `POST /alerts/{id}/ack` is idempotent: a second ack keeps the first `acked_by`. The acked alert is pushed again as an `alert` WS frame so other dashboards drop it.
- 422 validation errors use the same envelope: `{"detail": "<field>: <message>", "code": "invalid"}`.
- `WS /ws`: an invalid token (or a disabled account) is closed with code 4401, a patient token with 4403. Disabling a user closes their open sockets with 4401.
- `POST /devices/{id}/assign` → `{"admission_id","patient_id","device_id","bed","schedule_version","published_to_device"}`; 409 `device_busy` if the device has another active patient. Moving a patient to another device sends the old device an unassigned schedule.
- `POST /admissions/{id}/discharge` → `{"admission_id","patient_id","device_id","discharged_at"}`; 409 `already_discharged`.
- `POST /devices/{id}/command` → `{"published": bool}`.

## Built in 1.7 (Faouzi: appointments, integrations)

The appointments and n8n callback routes above are built as specified. Additions and clarifications, as built:
- `Appointment` also returns the 1.5 display fields `ai_suggested`, `human_confirmed_by`, `human_confirmed_by_name`, `patient_name`, `patient_age` (string), `specialty` (the patient's ward), `referral_text`, `doctor_name` and `confirmed_by_name`. `lang` and `room` are not returned yet.
- For the patient role, `urgency_ai`, `triage`, `no_show_prob` and `ai_suggested` are left out.
- `GET /appointments` for a patient always returns their own appointments; another `patient_id` is a 403. Rows come soonest slot first, then unbooked requests newest first.
- `POST /appointments/{id}/confirm`: 422 if `doctor_id` is not a doctor, 409 `slot_taken` if that doctor already has a confirmed appointment at `slot_at`, 409 `not_waiting` if the appointment is not `requested`.
- `POST /appointments/{id}/cancel`: 409 `not_cancellable` if it is already cancelled, done or no-show.
- `POST /integrations/n8n/appointment-reply` → `{"status":"confirmed|cancelled"}`; a cancel fires `appointment.cancelled` like the web cancel.
- `POST /integrations/n8n/backfill-accept`: the doctor comes from the cancelled appointment that had `slot_at`; 404 if no cancelled appointment had that slot. A backfill does not fire `appointment.confirmed` (W2 sends its own confirmation).
- `GET /integrations/n8n/daily-digest`: `summary` is the latest stored AI summary, or a fresh one built from the last 24 h (not stored).
- Callbacks without a valid `X-N8N-Secret` get 401 `unauthorized`.

Still proposed: `GET /offers/{id}`, `POST /offers/{id}/accept` and `GET /patients/{id}/home-care` (offers need somewhere to store an offer; see the 1.5 list).

## Proposed in 1.8 (Faouzi: single-visit exams, case notebook)

| Method & path | Roles | Notes |
|---|---|---|
| `GET /exams/catalogue` | doctor | → `[{"code","label","department"}]` |
| `GET /appointments/{id}/exams` | doctor, admin (no results), patient (self; ordered/done only) | → `[ExamOrder]` |
| `GET /patients/{id}/exams` | doctor (own), nurse (ward), patient (self; ordered/done only) | → `[ExamOrder]`, audited |
| `GET /exams?status=ordered` | nurse (own department), admin | Worklist → `[ExamOrder]` with `patient_name` |
| `POST /appointments/{id}/exams/order` | doctor | `{"exam_ids":[...]}`: listed `suggested` rows → `ordered`, the other suggestions → `cancelled`. 422 if an id is not a suggestion of this appointment. Emits `exam.ordered` |
| `POST /exams` | doctor | `{"patient_id","appointment_id"?,"code"}` → `ExamOrder` with `status:"ordered"`. Emits `exam.ordered` |
| `POST /exams/{id}/cancel` | doctor | → `ExamOrder`; 409 `bad_status` |
| `POST /exams/{id}/results` | nurse (own department) | multipart `file` (PDF/JPEG/PNG, ≤ 15 MB) + `report_text` → `ExamOrder` with `status:"done"`; 422 `bad_file`, 409 `bad_status`. Emits `exam.results_ready` when the appointment has no `ordered` exam left |
| `GET /exam-results/{id}/file` | doctor, nurse (as for reading the exam) | → the file bytes, audited |
| `POST /ai/notebook/{patient_id}` | doctor (own) | `{"question"}` → `NotebookEntry` |
| `GET /ai/notebook/{patient_id}` | doctor (own) | → `[NotebookEntry]` newest first |
| `GET /ai/notebook/{patient_id}/sources` | doctor (own) | → `[{"id","kind","title","ts"}]` |
| `POST /ai/notebook/entries/{id}/review` | doctor | → `NotebookEntry` with `human_confirmed_by` |

`Appointment` gains `exams_total` (ordered + done), `exams_done` and `exams_suggested`. `triage` gains `scale: {"name","level","confirmed"}`.

```jsonc
// ExamOrder
{ "id": "ex-0001", "patient_id": "p-0003", "appointment_id": "a-0001", "code": "ecg", "label": "ECG (12-lead)",
  "department": "Cardiology", "status": "suggested|ordered|done|cancelled", "ai_suggested": {"source": "rules", "bundles": ["chest_pain"], "reason": "..."},
  "human_confirmed_by": "u-0001", "ordered_at": "...", "done_at": null, "created_at": "...", "patient_name": "...",
  "results": [{ "id": "er-0001", "file_name": "ecg.pdf", "content_type": "application/pdf", "size_bytes": 81234, "report_text": "Sinus rhythm", "uploaded_by_name": "Nurse Rania", "created_at": "..." }] }
// NotebookEntry
{ "id": "nb-0001", "patient_id": "p-0001", "question": "...", "answer": "...", "source": "rules|llm",
  "citations": [{ "n": 1, "source_id": "note:n-0003", "kind": "note", "title": "Nurse note · 08 Oct 21:40", "snippet": "..." }],
  "human_confirmed_by": null, "created_at": "..." }
```

## Changelog

- **1.18** (2026-10-11): `GET /admin/impact?days=` pilot impact indicators (admin, aggregates only). Owner: Faouzi; router in the backend area (Wali).
- **1.17** (2026-10-11): nurse shift handover — `GET /handover` (rules-based SBAR draft per patient, optional LLM narrative) and `POST /handover/{patient_id}/confirm` (the outgoing nurse confirms; stored in `handovers`, data-model 1.10). Owner: Faouzi.
- **1.16** (2026-10-11): `POST /patients/{id}/vitals`: a reading taken by hand on a nurse round (source `manual`), so vitals have a real collection path besides the simulated bedside feed. Owner: Faouzi (route in Wali's `patients.py`).
- **1.15** (2026-10-11): hospital pharmacy. Role `pharmacist` (sign-up; only the admin approves). Drug catalogue (`/drugs`). Prescriptions gain a pharmacy status, `urgent`, versions (`replaces_id`, 409 `conflict` while a later version is live), `checks` (incl. `dose_unverified` and moderate cross-reactivity `allergy`), `override_reason` and review fields; `POST /prescriptions/check` dry run; 422 `override_required`/`unknown_drug`; `PATCH` only stops. Pharmacist worklist, review and decisions (`/pharmacy/*`), WS `prescription_status`; `POST /doses/{id}/given` and `dispense_now` refuse doses of inactive prescriptions. Dispensing, nurse receipt, stock and the dose `pharmacy` field. Owner: Hedi.
- **1.14** (2026-10-10): radiograph reading — `GET/PUT /exam-results/{id}/reading`, `POST /patients/{id}/radiographs`, `results[].reading`, exam codes `xray`/`xray_outside`, WS frame `radiograph_reading`.
- **1.13** (2026-10-10): health calendar — `GET/POST /health-events`, `PATCH/DELETE /health-events/{id}`, `POST /health-events/{id}/notify`, `GET/PUT /me/health-prefs`, n8n callbacks `GET /integrations/n8n/health-events/due` and `POST /integrations/n8n/health-events/{id}/announced`.
- **1.12** (2026-10-10): health watch (`/health-watch`, `/health-watch/me`, `/integrations/n8n/health-watch`). Owner: Faouzi.
- **1.11** (2026-10-10): staff AI assistant conversations (`/ai/conversations*`), stored server-side. Owner: Faouzi.
- **1.10** (2026-10-10): `POST /ai/chat` (role assistants over one patient's record, any language, cited) and `POST /patients/{id}/reports` (doctor attaches a report). Owner: Faouzi.
- **1.9** (2026-10-10): accounts — sign-up with a requested role and doctor (`role` required on register), `GET /hospital`, reset/change-password, doctor directory, account approval (/users*) that links or creates the patient record, `GET /patients?unlinked=`, doctor team, patient sharing; no enrollment codes (reset codes only); login error codes and length limits; JWT exp 8 h; logout; disabled accounts lose WebSockets and notifications

- **1.8** (2026-10-09): proposes the exam and notebook routes above and the new `Appointment`/`triage` fields (spec 2026-10-09). Nothing earlier changes. Needs a 👍 from Wali.

- **1.7** (2026-10-09): Faouzi builds the appointments and n8n callback routes; documents the additive `Appointment` fields, the patient-role omissions and the 401/404/409/422 cases listed in "Built in 1.7". Nothing earlier is removed. Needs a 👍 from Wali.
- **1.6** (2026-10-08): Wali confirms and builds, from the 1.5 proposals, `GET /patients/{id}/doses`, `POST /doses/{id}/given` (`given_by` in that response only) and `GET /staff`, plus the additive fields listed in "Confirmed in 1.6"; documents the alerts `status` values, the 422 envelope, the WS close codes and the assign/discharge/command responses as built. Nothing in 1.4/1.5 is removed. Needs a 👍 from Faouzi.

- **1.5** (2026-10-06): UI needs, proposed by Faouzi; Wali to confirm. Adds the section "Proposed in 1.5 (web UI needs)" (endpoints, fields and new types the web app uses) and the rule that patient-role appointment responses omit `urgency_ai`, `triage` and `no_show_prob`. Nothing in 1.4 changes.

- **1.4** (2026-10-06): AI layer reworked onto rules and trained models. `POST /ai/triage` drops `history` and adds `model_urgency` and `confidence`; `POST /ai/assistant` also returns `intent` and `source`; `source` is now `"model" | "rules" | "llm"` (was `"llm" | "fallback"`), including `Appointment.triage.source`. Owner: Faouzi.

- **1.3** (2026-10-05): removes `POST /ai/digitize` and `/ai/digitize/{id}/approve` (paper digitizer dropped) and the `doc-` ID. Owner: Faouzi; nothing else called them.

- **1.2** (2026-10-05): `GET /ai/summary/{patient_id}` also returns `human_confirmed_by`, so the doctor view can show "needs review" / "reviewed" (AI-output convention). Both sides: Faouzi.

- **1.1** (2026-10-05): integrations callbacks aligned with n8n-webhooks v1.2 (`backfill-accept` responses, `daily-digest` list shape with doctor email, new `follow-up`); the `n8n@ward.tn` service account is no longer needed.

- **1.0** (2026-10-05): initial freeze. Adds `PATCH /appointments/{id}` (urgency override), `/appointments/{id}/reply`, `/ai/summary/{id}/review`, `/me`, `/patients/{id}/prescriptions`, `/patients/{id}/notes`, discharge, digitize-approve, device command and `/integrations/n8n/*` to the brief's drafts.
