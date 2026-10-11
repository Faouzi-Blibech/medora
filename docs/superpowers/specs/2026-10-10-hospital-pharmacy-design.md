# Hospital Pharmacy: Design Spec

**Date:** 2026-10-10 · **Status:** approved by the user (Hedi), who asked to skip the section-by-section review and
go straight to plans and implementation · **Branch:** `abdelhedimed05/pharmacy`

## 1. Goal and decisions

Bring the **hospital pharmacist** into Medora's medication chain, between the doctor's prescription and the nurse or
bedside device that gives the dose. A second pair of eyes catches prescription errors (allergy, interaction,
overdose, duplicate) before they reach the patient. The pharmacist then prepares each ward's doses and manages the
drug stock.

User decisions (2026-10-10):
- **Hospital pharmacy** only, inside the hospital's own install. Community pharmacies are out of scope.
- **All four jobs:** prescription validation, drug catalogue, dispensing to wards, stock.
- **Gate with urgent bypass:** a new prescription waits for the pharmacist before any dose is given. The doctor can
  tick "Urgent: start now"; doses then go out at once and the pharmacist reviews right after.
- **Approach 1:** a pharmacy module inside the existing backend and web app. No separate service.
- **Two phases:**
  - **Phase A, the safety loop:** the pharmacist role, the drug catalogue, the check engine and prescription
    validation.
  - **Phase B, logistics:** dispensing to wards and stock.
  - Phase A ships first and is complete on its own.

Constraints carried over from the project:
- Offline-first, with no LLM. The checks are deterministic, explainable rules.
- A human always decides. The engine only flags.
- Every patient-data read is audited.
- fr/ar/en with RTL.
- Synthetic data only.
- The rule files are labelled "illustrative, not a clinical reference; to be validated by the hospital's
  pharmacists".

## 2. Roles and workflow

**The `pharmacist` role.**
- It is a 4th staff role. It is picked on the sign-up form (role list: patient, nurse, doctor, pharmacist).
- **Only the hospital admin approves it.** A doctor can't approve a pharmacist.
- The pharmacist sees every prescription in the hospital and, per patient, only what the checks need: name, age, sex,
  ward/bed, allergies, weight if present, and the current prescriptions. **Not** notes, exams, vitals or AI
  summaries.
- Every read is audited.

**Prescription life cycle**
```
doctor saves ──► pending_pharmacy ──► validated ──► doses created → nurse round + bedside device
                    │     ├──► changes_requested (comment) ──► doctor edits = new version ──► pending_pharmacy
                    │     └──► rejected (reason) ──► nothing is given
 urgent=true ──► doses created at once + pending_pharmacy ("urgent: review now")
 validated ──► doctor stops it ──► stopped (immediate: stopping is always safe; future doses deleted)
 validated v1 ──► doctor edits ──► v2 pending; v1 keeps running ──► v2 validated ──► v1 superseded
```

Statuses: `pending_pharmacy | validated | changes_requested | rejected | stopped | superseded`.
- **The check engine runs on every save.** The doctor sees the same warnings the pharmacist will see, through a dry
  run while they type.
- **A `critical` check requires the doctor to give an `override_reason`** to send the prescription anyway.
- **Pharmacist worklist order:** urgent first, then the highest severity, then the oldest.
- **Validate** takes 1 click with no checks, or 2 with checks: tick "warnings reviewed", then Validate.
- **Request change and reject** require a comment.
- **The doctor is told** through an in-app status and comment, a live WebSocket frame and an n8n event (WhatsApp/email).
- **Urgent then rejected:** the remaining future doses are deleted and the device schedule is republished.
- **Editing creates a new version** (`replaces_id`). The old version keeps running until the new one is validated,
  so treatment never stops. If the new version is rejected, the old one stays as it was.

| Action | Doctor | Pharmacist | Nurse | Admin | Patient |
|---|---|---|---|---|---|
| Write, edit or stop a prescription | ✅ (attending doctor) | ❌ | ❌ | ❌ | ❌ |
| Validate, request change, reject | ❌ | ✅ | ❌ | ❌ | ❌ |
| Give doses | ❌ | ❌ | ✅ (validated, or urgent) | ❌ | ❌ |
| Read the catalogue | ✅ | ✅ | ✅ | ✅ | ❌ |
| Edit the catalogue | ❌ | ✅ | ❌ | ✅ | ❌ |
| Dispense, stock (Phase B) | ❌ | ✅ | receive delivery | read stock | ❌ |

A shared doctor (read-only sharing) can't prescribe, which matches the existing rule.

## 3. Data model (data-model 1.7)

### Phase A: migration `0007_pharmacy`
**`drugs`** is the hospital formulary (livret thérapeutique):

| Column | Type | Note |
|---|---|---|
| id | `d-0001` | |
| dci | text | Generic name, e.g. "Amoxicillin" |
| brand_names | jsonb text[] | Tunisian brands, for search |
| form | text | tablet, capsule, syrup, injection, inhaler, patch, drops, other |
| strength | text | Display only, e.g. "500 mg" |
| unit_mg | numeric, null | mg per unit (tablet or capsule), used for the dose check |
| max_daily_mg | numeric, null | Adult max per day; null means no dose check |
| atc_code | text | e.g. J01CA04 |
| allergy_classes | jsonb text[] | e.g. ["penicillin", "beta_lactam"] |
| interaction_groups | jsonb text[] | e.g. ["anticoagulant"], ["nsaid"] |
| high_alert | bool | Insulin, anticoagulants, opioids, potassium IV… |
| min_stock | int, default 0 | Used in Phase B |
| active | bool | |
| created_at, updated_at | | |

**`prescriptions`** gets these new columns (the existing ones stay):
- `status`;
- `urgent` bool;
- `version` int, default 1;
- `replaces_id` (FK prescriptions, null);
- `checks` jsonb (the last results);
- `override_reason` text, null;
- `reviewed_by` (FK users, null), `reviewed_at`, `review_comment`.

`active` stays for compatibility and is derived: it's true when the status is `validated`, or when it's
`pending_pharmacy` with `urgent` set.
- **Items** stay JSONB: `[{med, drug_id?, dose_mg?, units_per_intake (default 1), times[], slot, days}]`. `med`
  keeps the display string. `drug_id` is null for a non-formulary ("hors livret") drug.
- **Backfill:**
  - existing active prescriptions become `validated`, with `reviewed_by` set to the seed pharmacist (or null);
  - inactive ones become `stopped`;
  - `drug_id` is filled by a case-insensitive name match on the DCI or a brand (prefix before the strength).

**`prescription_reviews`** is the decision history:
- id `pr-0001`, prescription_id, pharmacist_id;
- decision `validated | changes_requested | rejected`;
- comment, checks_snapshot jsonb, created_at.

### Phase B: migration `0008_pharmacy_stock`
- **`stock_lots`:** id `lot-0001`, drug_id, lot_number, expiry_date, quantity int ≥ 0, received_at.
- **`stock_movements`:**
  - id `sm-0001`, drug_id, lot_id, delta int;
  - reason `receipt | dispense | adjustment | expired | return`;
  - ref_id (null), by_user_id, created_at.
  - It is append-only. Stock is the sum of the lot quantities, kept in sync inside the same transaction.
- **`dispensations`:** one per ward and round.
  - id `disp-0001`, ward, round_date, round_time "HH:MM";
  - status `sent | received`;
  - prepared_by, prepared_at, received_by (null), received_at (null).
- **`dispensation_lines`:**
  - id, dispensation_id, dose_id (FK med_doses), patient_id, drug_id (null for non-formulary), lot_id (null),
    quantity int, med text.

## 4. The check engine (`backend/app/services/pharmacy/checks.py`)

It is pure and deterministic. The input is the patient (age, allergies, weight), the candidate items, the patient's
other running prescriptions (status `validated`, or `pending_pharmacy` with `urgent`; it excludes the version being
replaced) and the formulary. The output is a list of `Check` objects, sorted by severity:
`{code, severity: critical|major|moderate|info, item_index, drug_id, params{}, message}`. `message` is English for
logs and the web translates by `code` and `params`.

| code | Rule | Severity |
|---|---|---|
| `allergy` | One of the drug's `allergy_classes` matches one of the patient's allergies, after normalising both through `rules/pharmacy/allergy_synonyms.v1.json` (fr/en/ar, e.g. "pénicilline", "بنسلين" → penicillin) | critical |
| `interaction` | A group pair, from this prescription's items or other running prescriptions, is listed in `rules/pharmacy/interactions.v1.json` | the table's severity: critical, major or moderate |
| `max_daily_dose` | `dose_mg` (or units_per_intake × unit_mg) × intakes per day > max_daily_mg | major; critical if > 2× |
| `duplicate_therapy` | The same DCI, or the same 5-character ATC prefix, already running or twice in the list | major |
| `non_formulary` | The item has no drug_id | moderate |
| `high_alert` | `drug.high_alert` | info ("double-check") |
| `elderly` | Age ≥ 75 and the drug is in the `rules/pharmacy/elderly_caution.v1.json` list (Beers-style, illustrative) | moderate |

- The rule files live in `backend/app/rules/pharmacy/`. The formulary seed is `backend/app/data/pharmacy/formulary.v1.json`, with about 50 drugs. It covers every drug in the seed prescriptions, plus the demo cases: amoxicillin, azithromycin, warfarin, ibuprofen, enoxaparin, insulin, morphine, KCl, metformin, furosemide, amlodipine, paracetamol and others.
- Speed: under 20 ms per check, with no I/O beyond one query per call.

## 5. API (api 1.12)

All routes are staff-authenticated and audited. Errors use the existing `{detail, code}` shape.

### Phase A

**Catalogue**
- `GET /drugs?q=&active=true` (doctor, nurse, pharmacist, admin): returns `Drug[]`. q matches the DCI, a brand or the ATC code; at most 50 results.
- `POST /drugs` (pharmacist, admin): creates a drug and returns `Drug`.
- `PATCH /drugs/{id}` (pharmacist, admin): updates fields and returns `Drug`. Deactivating is allowed; deleting isn't.

**Prescribing (doctor)**
- `POST /prescriptions/check` takes `{patient_id, items[], replaces_id?}`, a dry run, and returns `{checks: Check[]}`.
- `POST /prescriptions` takes `{patient_id, items[], care_plan, urgent?: bool, override_reason?: str, replaces_id?: str}`
  and returns `PrescriptionPublished`, now with `status`, `urgent`, `version`, `checks`.
  - 422 `override_required` when there is a critical check and no `override_reason`.
  - 409 `conflict` if `replaces_id` isn't the latest running version.
- `PATCH /prescriptions/{id}` takes `{active: false}` and stops it immediately (status `stopped`). Other edits go through `replaces_id`.
- `GET /patients/{id}/prescriptions` adds `status, urgent, version, replaces_id, checks, override_reason, review_comment,
  reviewed_by_name, reviewed_at` to each item. Patients see only `status`.

**Pharmacist**
- `GET /pharmacy/worklist?status=pending_pharmacy` returns `WorklistItem[]`, each with:
  - `prescription`;
  - `patient: {id, name, age, sex, ward, bed, allergies}`;
  - `doctor_name`, `checks`, `urgent`, `waiting_since`, `max_severity`.
  - Sort order: urgent, then severity, then age. `status=changes_requested|all` is also allowed.
- `GET /pharmacy/prescriptions/{id}` returns `{prescription, patient, doctor_name, running: Prescription[], checks (recomputed now), history: Review[], replaces?: Prescription}`.
- `POST /pharmacy/prescriptions/{id}/validate` takes `{acknowledged: bool, comment?}`.
  - 409 `bad_status` if it isn't pending.
  - 422 `ack_required` if there are checks and `acknowledged` is false.
- `POST /pharmacy/prescriptions/{id}/request-changes` takes `{comment}`; the comment is required (1–500 characters).
- `POST /pharmacy/prescriptions/{id}/reject` takes `{comment}`; the comment is required.
- `GET /pharmacy/summary` returns `{pending, urgent_pending, critical_pending, changes_requested}`, for the sidebar badge and the dashboard.

**Side effects of a decision**
- Doses are rebuilt through `services/schedule.rebuild_doses` and published to the device:
  - on validation;
  - on an urgent save;
  - on rejecting an urgent prescription, which deletes its future doses;
  - on superseding.
- A WebSocket frame `prescription_status {prescription_id, patient_id, status, urgent}` goes to the attending doctor, every pharmacist and the patient's ward nurses.
- The n8n event `prescription.review` carries `{prescription_id, patient_id, decision, comment, doctor_email, doctor_chat_id}`. The workflow is optional, and Faouzi owns n8n.

### Phase B

**Dispensing**
- `GET /pharmacy/dispensing?date=YYYY-MM-DD&round=HH:MM&ward=` returns, per ward, its patients and their doses due in that round. Only validated or urgent prescriptions count. Each dose has its med, drug_id, quantity, a FEFO suggested lot, stock on hand and an already-dispensed flag.
- `POST /pharmacy/dispensations` takes `{ward, date, round_time, lines: [{dose_id, lot_id?}]}` and returns `Dispensation`. In one transaction it:
  1. creates the dispensation as `sent`;
  2. decrements the lots (FEFO when lot_id is missing);
  3. writes the stock movements.
  - 409 `insufficient_stock` (with the drug) when stock is short; nothing is written.
  - 409 `already_dispensed` when a dose is already dispensed.
- `GET /dispensations?ward=&date=` (nurse, pharmacist) lists them. `POST /dispensations/{id}/receive` (a nurse of that ward) moves it to `received`.

**Stock**
- `GET /pharmacy/stock` returns, per drug, `on_hand`, `min_stock`, `lots[]` and the flags `low` (on_hand < min_stock), `expiring` (a lot ≤ 30 days) and `expired`.
- `POST /pharmacy/stock/receipts` takes `{drug_id, lot_number, expiry_date, quantity}` and creates or tops up a lot.
- `POST /pharmacy/stock/adjustments` takes `{lot_id, delta, reason: adjustment|expired|return, comment}`. Stock can't go negative (409).
- `GET /pharmacy/stock/reorder` lists the drugs below min_stock, with the suggested quantity (2 × min_stock − on_hand).

**Stock alerts:** after any stock change, a pharmacist-only notice appears in `GET /pharmacy/summary`
(`low_stock`, `expiring`). It is **not** sent to the nurses' ward alerts.

**Nurse round (Phase B):** each dose in `GET /patients/{id}/doses` adds `pharmacy: none|sent|received`. The nurse can
still give a dose that isn't dispensed yet, because ward stock exists. The UI shows a small "not from pharmacy" note.

## 6. Web (Next.js, fr/ar/en, RTL, mock mode)

**`/pharmacist` space** (RoleShell with a sidebar):
- the **Worklist**, with a count badge and the critical items in red;
- the **Catalogue**;
- **Dispensing** and **Stock** (Phase B);
- Change password and Log out.

**Worklist and review**
- Each row shows the patient, the ward and bed, the doctor, the waiting time, an urgent badge and severity chips.
- Opening a row shows the review panel:
  - the allergies, prominent;
  - the prescription items: drug, dose, times, days;
  - the patient's other running prescriptions;
  - the check list (severity, a plain-language explanation, the item it concerns);
  - the doctor's override reason;
  - the history.
- **Actions:**
  - Validate: with any checks, the "I reviewed the warnings" box must be ticked first;
  - Request changes and Reject open a comment dialog.
- Every action takes 3 steps at most.
- The list updates live through the `prescription_status` frame.

**Catalogue:** search, a table, and an add/edit drug form for pharmacists and admins. A form covers allergy classes and interaction groups as tags.

**Doctor:** the prescription form (`Prescriptions.tsx`) changes like this.
- **A drug picker** searches the catalogue, with a "Non-formulary drug" option that keeps free text.
- **New fields:** dose (mg) and units per intake.
- **Live check panel:** a 400 ms debounced call to `/prescriptions/check`.
- **When a check is critical,** an override reason is required.
- **An "Urgent: start now" checkbox.**
- **Prescription list:** a status badge on each, plus the pharmacist's comment. "Changes requested" shows "Edit and resubmit", which opens the form pre-filled as a new version.

**Nurse:**
- Doses of a pending urgent prescription show a "pending pharmacy review" badge.
- In Phase B, a "Pharmacy deliveries" panel lists the round's sent dispensations with a Confirm receipt button.

**Admin:** pharmacist sign-ups appear in the pending list; the role selects include pharmacist. The admin can edit the catalogue.

**Sign-up:** the role list adds Pharmacist; pharmacists pick no doctor.

**Mocks:** every new API function has a mock (`web/src/mocks/pharmacy.ts`) so the screens work with `NEXT_PUBLIC_USE_MOCKS=1`.

## 7. Seed and demo
- **A pharmacist account:** `pharmacist@medora.tn`, "Pharm. Salma", active, password `SEED_PASSWORD`.
- **A formulary** of about 50 drugs.
- **Existing seed prescriptions** are mapped to drugs and validated by the seed pharmacist.
- **A pending demo prescription:** Amoxicillin 1 g × 3/day for a penicillin-allergic seed patient (give one seed
  patient a "penicillin" allergy if none has it), with a doctor override reason, so it shows as critical.
- **Phase B:**
  - lots for every formulary drug;
  - one drug below min_stock;
  - one lot expiring in 10 days;
  - one expired lot.

**Demo path**
1. The doctor prescribes amoxicillin and gets the allergy warning live.
2. They send it with a reason.
3. The pharmacist's worklist shows it in red. The pharmacist requests a change: "allergie pénicilline → azithromycine".
4. The doctor resubmits with azithromycin. The pharmacist validates.
5. The doses appear on the nurse round and the device schedule updates.
6. **Phase B:** the pharmacist prepares the 20:00 Cardiology round, the nurse confirms receipt, the stock goes down,
   and a low-stock alert shows on the pharmacy dashboard.

## 8. Security, privacy and audit
- **Role checks** go through `require_roles`.
- **The pharmacist's patient view** is a minimal projection and is never the full record.
- **Audit:** every worklist or review read writes `audit_log` (resource `prescription`, with patient_id), and so does every decision and every stock movement.
- **The rule and formulary files are versioned** and carry the "illustrative, not a clinical reference" note.
- **Concurrency:** two pharmacists validating at once means the second gets 409 `bad_status`. The status is checked under `SELECT … FOR UPDATE`.
- **Stock** can't go negative, also checked under a row lock.

## 9. Testing
- **Backend:**
  - each check rule, including fr/ar allergy synonyms and the ×2 dose threshold;
  - the status machine: validate, changes, reject, urgent then reject cancels doses, supersede keeps v1 until v2 is validated, stop;
  - the permission matrix;
  - 409/422 paths;
  - FEFO and no negative stock;
  - dispensation idempotence;
  - audit rows;
  - the contract shapes.
- **Web:** typecheck, a mock-mode build, and i18n keys present in fr, ar and en.
- **Live smoke script:** the demo path through the API.

## 10. Contracts and ownership
- **Contract bumps:** api 1.11 → 1.12, data-model 1.6 → 1.7, n8n-webhooks 1.3 → 1.4 (`prescription.review`). mqtt-topics stays the same.
- **Lanes:**
  - the backend and infra are ours;
  - `web/` and `n8n/` are Faouzi's folders: the user drives this feature, and Faouzi gets a handoff note;
  - `routers/appointments.py` is untouched.
- **Branches:** `abdelhedimed05/pharmacy-backend` and `abdelhedimed05/pharmacy-web` (worktrees), merged into
  `abdelhedimed05/pharmacy`. Local commits, no AI attribution, no push until the user asks.

## 11. Out of scope
- community pharmacies;
- CNAM/insurance billing;
- barcode or NFC scanning of drugs;
- a real national drug database;
- automatic supplier orders;
- pediatric weight-based dosing (the weight is shown but not checked);
- renal dose adjustment.
