# Hospital Pharmacy: Web Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the web side of the hospital pharmacy: Phase A (the pharmacist role and space, worklist and review with decisions in 3 steps at most, the drug catalogue, the doctor's checked prescription form, the nurse badge, sign-up and approval) and then Phase B (dispensing, stock, nurse deliveries). Every screen must work in mock mode and against the spec §5 API unchanged.

**Architecture:** Every call goes through `web/src/lib/api.ts`: the real branch uses `http()`, and the mock branch uses `mock()` over `MockStore`, with fixtures and a mock check engine in `web/src/mocks/pharmacy.ts`. Pure pharmacy logic lives in `web/src/lib/pharmacy.ts`, so the screens and the mocks share one implementation: severity order, worklist order, "running", the doctor's list, check texts, decision validation, FEFO and stock flags.

**Live updates:** today there is **no WebSocket client in `web/src`**. There is only the `WsFrame` type in `types.ts`, and the sidebar "Live" pill is mock-only. Task 2 adds the first one, `web/src/lib/live.ts`: one ref-counted `WS /ws?token=` per tab, which publishes frames to an in-tab bus, `web/src/lib/frames.ts`. The `useLiveRefresh()` hook refreshes a screen on `prescription_status` frames, and polls every 15 s while no socket is open. Mock mode has no socket: its mutations publish the frames the server would send.

**File layout:** new UI goes in `web/src/components/pharmacist/`. Shared pieces (`CheckList`, `RxStatusBadge`) go in `web/src/components/shared/`. Every new string goes in a new `pharmacy` i18n namespace.

**Tech Stack:** Next.js 16 App Router, React 19, strict TypeScript 5, CSS Modules plus the design tokens in `web/src/app/globals.css`, and typed i18n (`messages()` in `web/src/i18n/define.ts`: `fr` and `ar` must carry exactly the keys of `en`, or `tsc` fails). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-10-hospital-pharmacy-design.md`. The binding sections are §2 (roles and workflow), §5 (API, binding field names) and §6 (web). §3 and §4 give the meaning of the fields and checks.

## Global Constraints

- **Field names.** Spec §5 field names, paths and error codes are used verbatim (`status`, `urgent`, `version`, `replaces_id`, `checks`, `override_reason`, `review_comment`, `reviewed_by_name`, `reviewed_at`, `acknowledged`, `waiting_since`, `max_severity`, `on_hand`, `min_stock`, `lots`, `low`, `expiring`, `expired`, `round_time`…). A backend plan is written in parallel from the same spec. Where the spec is silent, follow the "Contract decisions" section at the end of this plan, and never invent a shape inline.
- **API types.** `web/src/lib/types.ts` mirrors the API (CLAUDE.md). This plan does not edit `docs/contracts/*`; the backend plan owns the api 1.11 → 1.12 bump.
- **Mocks.** Components never import `@/mocks`; only `api.ts` does (existing rule). Every new API function has a mock branch, and the mocks throw the same `{status, code}` errors the server does: `override_required`, `ack_required`, `bad_status`, `conflict`, `insufficient_stock`, `already_dispensed`, `negative_stock`.
- **i18n.** Every user-visible string goes through `t()`, with `en`, `fr` and `ar` values. New keys go only in `web/src/i18n/messages/pharmacy.ts` (namespace `pharmacy`). There are no string literals in JSX, apart from symbols (`×`, `−`, `+`, `—`, `–`).
- **RTL.** CSS uses logical properties only (`margin-inline-*`, `padding-inline-*`, `inset-inline-*`, `border-inline-start`, `text-align: start`). Codes, ids, ATC codes, lot numbers, doses, dates and times are `dir="ltr"`. Names, drug names and free text are `dir="auto"`.
- **Pharmacist privacy (spec §2, §8).** Pharmacist screens call only the pharmacy functions: `getWorklist`, `getReview`, the decision functions, `getPharmacySummary`, the catalogue, and the Phase B stock and dispensing functions. They never call `getPatient`, `getNotes`, `getVitals`, `getPatientExams`, `getSummary` or `getDoses`. They never render `NotesPanel`, `ExamsPanel`, `PatientAiCard`, `VitalsChart`, `VitalsCard` or `DosesTimeline`, and they never link to `/doctor/patients/*` or `/nurse/patients/*`.
- **Decisions.** Every pharmacist decision takes 3 steps at most:
  - Validate takes 1 click with no checks, or a tick plus 1 click with checks.
  - Request changes and Reject take 3 steps: open the dialog, type the comment, Send.
- **Prototype honesty.** The catalogue says the data is illustrative, not a clinical reference (spec §1). No UI copy claims clinical validation.
- **Times.** REST uses ISO-8601 UTC. The UI shows Africa/Tunis through `web/src/lib/time.ts` (`tunisDate`, `tunisTime`, `ago`, `now()`; `now()` is frozen at Mon 5 Oct 2026 09:12 in mock mode). Dispensing dates are `YYYY-MM-DD` Tunis dates.
- **Verification.** There is no test runner and no lint script in `web/` (scripts: `dev`, `build`, `start`, `typecheck`), and none is added. Each task is verified with `npx tsc --noEmit`, then `NEXT_PUBLIC_USE_MOCKS=1 npm run build`, then the manual mock-mode steps listed. All commands run from the `web/` folder of the worktree you execute in (spec §10 lane branch: `abdelhedimed05/pharmacy-web`). If `web/node_modules` is missing, run `npm ci` once.
- **Shell.** The commands below are for Git Bash. In PowerShell, set the variable first: `$env:NEXT_PUBLIC_USE_MOCKS='1'; npm run build`.
- **Commits.** Conventional Commits (`feat(web): …`). No AI attribution lines, no `Co-Authored-By` and no trailers (CLAUDE.md).
- **Scope.** Do not touch `backend/`, `n8n/`, `infra/` or `docs/contracts/`.

## Review Focus

1. **Arabic (RTL) on the new screens.** This covers the worklist row's red critical edge, the review panel, the comment dialog, the doctor's drug picker and check panel, catalogue tags, and dispensing lot selects. In `ar`, the critical edge must sit on the right (inline-start). Drug names, ATC codes, doses, `08:00` times and lot numbers must not reorder. An Arabic comma (`،`) must add a tag like `,` does. *Pinned by:* Task 8, Steps 3 and 5 (physical-property grep, manual `ar` walk-through); Task 4, Step 6 (Arabic comma); Task 12, Step 7.
2. **Decisions under races.**
   - Two pharmacists on one row: the second gets 409 `bad_status`. Expected: a localized message, the list refreshes, and nothing crashes.
   - Checks appear between opening and clicking Validate: 422 `ack_required`. Expected: the tick is cleared and must be given again; the prescription is never silently validated.
   - Double-clicking Validate or Send must send one request.
   - *Pinned by:* Task 3, Step 9 (mock scenarios with two tabs and a `?` race).
3. **The pharmacist never sees notes, exams or vitals.** The mock patient projection must pick fields explicitly; a `...patient` spread would leak `history`. No pharmacist file imports a clinical-record component or call. *Pinned by:* Task 1, Step 9 (explicit `pharmacyPatient` pick); Task 8, Step 4 (privacy grep, run again in Task 12).
4. **Mock-mode parity.** Every flow and error code of spec §5 is reachable with `NEXT_PUBLIC_USE_MOCKS=1`: override required, ack required, bad status, version conflict, insufficient stock, already dispensed, negative stock. The mock build passes. *Pinned by:* the mock scenarios in Tasks 3, 5, 10 and 11, and the build gate in every task.
5. **Stale or unexpected check data.** A slow `/prescriptions/check` reply must never overwrite a newer one (last request wins). A check `code` the web doesn't know, or a missing `params` value, must fall back to the server's English `message`, never `{allergy}` or a crash. A pre-1.12 prescription with no `status` is treated through `active`. *Pinned by:* Task 5, Step 8 (fast typing and a slow-reply check); Task 3, Step 9 (unknown-code check); Task 1 (`statusOf`, `checkText` fallbacks).

---

## File Structure

**Create**
- `web/src/lib/pharmacy.ts`: pure rules (severity, sorting, running, doctor rows, check text, decision validation; Phase B: FEFO, stock flags, shortages, rounds).
- `web/src/lib/pharmacyUi.ts`: pharmacy error codes mapped to message keys.
- `web/src/lib/frames.ts`: the in-tab live-frame bus.
- `web/src/lib/live.ts`: the shared WebSocket and `useLiveRefresh()`.
- `web/src/lib/useDebounced.ts`.
- `web/src/i18n/messages/pharmacy.ts`: namespace `pharmacy`.
- `web/src/mocks/pharmacy.ts`: formulary, mock check engine, reviews, lots, the seeded dispensation.
- `web/src/components/shared/CheckList.tsx`, `web/src/components/shared/RxStatusBadge.tsx`, `web/src/components/shared/Pharmacy.module.css`.
- `web/src/components/pharmacist/` (all with `Pharmacist.module.css`):
  - `usePharmacySummary.ts`, `SummaryStrip.tsx`, `PharmacistHome.tsx`;
  - `WorklistView.tsx`, `ReviewPanel.tsx`, `CommentDialog.tsx`;
  - `CatalogueView.tsx`, `DrugForm.tsx`, `TagInput.tsx`;
  - Phase B: `DispensingView.tsx`, `StockView.tsx`, `ReceiptForm.tsx`, `AdjustDialog.tsx`.
- `web/src/components/doctor/DrugPicker.tsx`, `web/src/components/doctor/usePrescriptionCheck.ts`.
- `web/src/components/nurse/PharmacyBadge.tsx`, `web/src/components/nurse/PharmacyBadge.module.css`, and in Phase B `web/src/components/nurse/PharmacyDeliveries.tsx` and `PharmacyDeliveries.module.css`.
- Pages:
  - `web/src/app/pharmacist/layout.tsx`, `page.tsx`, `password/page.tsx`, `catalogue/page.tsx`;
  - Phase B: `dispensing/page.tsx`, `stock/page.tsx`;
  - `web/src/app/admin/catalogue/page.tsx`.

**Modify**
- Data layer:
  - `web/src/lib/types.ts`;
  - `web/src/lib/api.ts`;
  - `web/src/i18n/messages/index.ts`;
  - `web/src/mocks/index.ts`, `web/src/mocks/people.ts`, `web/src/mocks/clinical.ts`, `web/src/mocks/accounts.ts`.
- Shell and sign-in:
  - `web/src/components/Sidebar.tsx`, `web/src/components/Sidebar.module.css`;
  - `web/src/app/page.tsx`;
  - `web/src/components/LoginForm.tsx`.
- Shared and admin:
  - `web/src/components/shared/NotesPanel.tsx`;
  - `web/src/components/admin/StaffView.tsx`, `web/src/components/admin/PendingList.tsx`;
  - `web/src/components/auth/RegisterForm.tsx`.
- Doctor:
  - `web/src/components/doctor/Prescriptions.tsx`, `web/src/components/doctor/Prescriptions.module.css`;
  - `web/src/components/doctor/PatientDetail.tsx`.
- Nurse:
  - `web/src/components/nurse/nurse.ts`;
  - `web/src/components/nurse/MedRound.tsx`;
  - `web/src/components/nurse/NursePatientDetail.tsx`.

---

# Phase A: the safety loop

## Task 1: Types, pure rules, i18n base, mocks and API (Phase A data layer)

**Files:**
- Modify:
  - `web/src/lib/types.ts`;
  - `web/src/lib/api.ts`;
  - `web/src/i18n/messages/index.ts`;
  - `web/src/mocks/index.ts`, `web/src/mocks/people.ts`, `web/src/mocks/clinical.ts`;
  - `web/src/components/LoginForm.tsx`;
  - `web/src/components/shared/NotesPanel.tsx`;
  - `web/src/components/admin/StaffView.tsx`.
- Create:
  - `web/src/i18n/messages/pharmacy.ts`;
  - `web/src/lib/pharmacy.ts`, `web/src/lib/pharmacyUi.ts`, `web/src/lib/frames.ts`;
  - `web/src/mocks/pharmacy.ts`.

**Interfaces:**
- Consumes: the existing `http()`, `mock()`, `notFound()`, `iso`, `enc`, `ApiError`, `ActorOpts`, `USERS`, `userName`, and `now`/`tunisDate`.
- Produces, as types in `@/lib/types`:
  - `Role` now includes `"pharmacist"`;
  - `PrescriptionStatus`, `CheckSeverity`, `CheckCode`, `Check`, `DrugForm`, `Drug`, `DrugInput`, `DrugPatch`;
  - `CheckRequest`, `CheckResponse`, `PharmacyPatient`, `WorklistItem`, `WorklistStatus`, `ReviewDecision`, `PrescriptionReview`, `ReviewDetail`, `ValidateRequest`, `PharmacySummary`;
  - extended `PrescriptionItem`, `Prescription`, `CreatePrescriptionRequest` and `WsFrame`.
- Produces in `@/lib/api`:
  ```ts
  liveSocketUrl(): string | null
  listDrugs(opts?: { q?: string; active?: boolean }): Promise<Drug[]>
  createDrug(req: DrugInput): Promise<Drug>
  updateDrug(id: string, patch: DrugPatch): Promise<Drug>
  checkPrescription(req: CheckRequest): Promise<CheckResponse>
  createPrescription(req: CreatePrescriptionRequest, opts?: ActorOpts): Promise<Prescription>   // now 1.12
  getPrescriptions(patientId: string): Promise<Prescription[]>                                   // all versions, newest first
  getWorklist(status?: WorklistStatus): Promise<WorklistItem[]>                                   // sorted
  getReview(id: string): Promise<ReviewDetail>
  validatePrescription(id: string, req: ValidateRequest, opts?: ActorOpts): Promise<Prescription>
  requestPrescriptionChanges(id: string, comment: string, opts?: ActorOpts): Promise<Prescription>
  rejectPrescription(id: string, comment: string, opts?: ActorOpts): Promise<Prescription>
  getPharmacySummary(): Promise<PharmacySummary>
  ```
- Produces in `@/lib/pharmacy`:
  - constants: `SEVERITY_RANK`, `SEVERITY_KEY`, `STATUS_KEY`, `DECISION_KEY`, `COMMENT_MAX` (500), `OVERRIDE_MAX` (500);
  - functions: `maxSeverity`, `sortChecks`, `hasCritical`, `sortWorklist`, `statusOf`, `isRunning`, `isPendingUrgent`, `doctorRows`, `pendingSuccessor`, `drugLabel`, `checkText`, `decisionProblem`;
  - types: `Decision`, `DecisionProblem`.
- Produces in `@/lib/pharmacyUi`: `pharmacyErrorKey(err): Key | null` and `describePharmacyError(err): Key`.
- Produces in `@/lib/frames`: `subscribeFrames(fn): () => void` and `publishFrame(frame): void`.
- Produces in `@/mocks`: `chainOf`, `checksFor`, `drugMatches`, `USERS.pharmacist` (`u-0012`, "Pharm. Salma").

- [ ] **Step 1: Baseline**

Run (from `web/`): `npm ci` (only if `node_modules` is missing), then `npx tsc --noEmit`.
Expected: exit 0, no output.

- [ ] **Step 2: Add the types (`web/src/lib/types.ts`)**

Change the role union at the top:

```ts
export type Role = "doctor" | "nurse" | "admin" | "patient" | "pharmacist";
```

Replace `PrescriptionItem`, `Prescription` and `CreatePrescriptionRequest` (the `// ── Prescriptions and doses` block, lines 96–121) with:

```ts
export interface PrescriptionItem {
  med: string; // display string, "Paracetamol 500 mg"
  /** api 1.12: formulary drug id ("d-0001"); null or absent = non-formulary ("hors livret"). */
  drug_id?: string | null;
  /** api 1.12: mg per intake; null = use units_per_intake × unit_mg. */
  dose_mg?: number | null;
  /** api 1.12: tablets/capsules per intake, default 1. */
  units_per_intake?: number;
  times: string[]; // ["08:00","20:00"], Africa/Tunis wall-clock
  slot: number | null; // carousel slot 1–4, null = reminder only
  days: number;
}

export interface Prescription {
  id: string; // rx-0001
  patient_id: string;
  doctor_id: string;
  items: PrescriptionItem[];
  care_plan: string;
  /** Derived (spec §3): validated, or pending_pharmacy with urgent. */
  active: boolean;
  created_at: string;
  schedule_version: number;
  published_to_device: boolean;
  /** UI extension: saved despite an allergy rule conflict (override logged). */
  allergy_override?: boolean;
  /** api 1.12 */
  status: PrescriptionStatus;
  urgent: boolean;
  version: number;
  replaces_id?: string | null;
  /** The last check results (doctor and pharmacist roles; absent for patients). */
  checks?: Check[];
  override_reason?: string | null;
  review_comment?: string | null;
  reviewed_by_name?: string | null;
  reviewed_at?: string | null;
}

export interface CreatePrescriptionRequest {
  patient_id: string;
  items: PrescriptionItem[];
  care_plan: string;
  /** api 1.12: doses start at once; the pharmacist reviews right after. */
  urgent?: boolean;
  /** Required (422 `override_required`) when a check is critical. */
  override_reason?: string;
  /** Edit = a new version of this prescription (409 `conflict` if it already has a successor). */
  replaces_id?: string;
}
```

Add this block just before `// ── Composed views`:

```ts
// ── Pharmacy (api 1.12, spec 2026-10-10-hospital-pharmacy-design.md §5) ─────

export type PrescriptionStatus = "pending_pharmacy" | "validated" | "changes_requested" | "rejected" | "stopped" | "superseded";
export type CheckSeverity = "critical" | "major" | "moderate" | "info";
export type CheckCode = "allergy" | "interaction" | "max_daily_dose" | "duplicate_therapy" | "non_formulary" | "high_alert" | "elderly";

/** One check-engine finding (spec §4). `message` is English (logs); the UI translates by `code` + `params`. */
export interface Check {
  code: CheckCode;
  severity: CheckSeverity;
  /** Index in the prescription's `items`; null when the finding is not tied to one item. */
  item_index: number | null;
  drug_id: string | null;
  params: Record<string, string | number | null>;
  message: string;
}

export type DrugForm = "tablet" | "capsule" | "syrup" | "injection" | "inhaler" | "patch" | "drops" | "other";

/** One formulary row (`drugs`, data-model 1.7). */
export interface Drug {
  id: string; // d-0001
  dci: string;
  brand_names: string[];
  form: DrugForm;
  strength: string; // display only, "500 mg"
  unit_mg: number | null;
  max_daily_mg: number | null; // null = no dose check
  atc_code: string;
  allergy_classes: string[];
  interaction_groups: string[];
  high_alert: boolean;
  min_stock: number;
  active: boolean;
  created_at: string;
  updated_at: string;
}
export type DrugInput = Omit<Drug, "id" | "created_at" | "updated_at">;
export type DrugPatch = Partial<DrugInput>;

/** POST /prescriptions/check (dry run). */
export interface CheckRequest {
  patient_id: string;
  items: PrescriptionItem[];
  replaces_id?: string;
}
export interface CheckResponse {
  checks: Check[];
}

/** The pharmacist's minimal patient projection (spec §2): never notes, exams, vitals or AI summaries. */
export interface PharmacyPatient {
  id: string;
  name: string;
  age: number;
  sex: "F" | "M";
  ward: string | null;
  bed: string | null;
  allergies: string[];
  /** Shown when present (spec §2 "weight if present"); not checked. */
  weight_kg?: number | null;
}

export type WorklistStatus = "pending_pharmacy" | "changes_requested" | "all";

export interface WorklistItem {
  prescription: Prescription;
  patient: PharmacyPatient;
  doctor_name: string;
  checks: Check[];
  urgent: boolean;
  waiting_since: string;
  max_severity: CheckSeverity | null;
}

export type ReviewDecision = "validated" | "changes_requested" | "rejected";

/** One `prescription_reviews` row. */
export interface PrescriptionReview {
  id: string; // pr-0001
  prescription_id: string;
  pharmacist_id: string;
  decision: ReviewDecision;
  comment: string | null;
  checks_snapshot: Check[];
  created_at: string;
  /** UI extension: "Pharm. Salma". */
  pharmacist_name?: string | null;
}

/** GET /pharmacy/prescriptions/{id} */
export interface ReviewDetail {
  prescription: Prescription;
  patient: PharmacyPatient;
  doctor_name: string;
  /** The patient's other running prescriptions. */
  running: Prescription[];
  /** Recomputed now. */
  checks: Check[];
  history: PrescriptionReview[];
  replaces?: Prescription | null;
}

export interface ValidateRequest {
  acknowledged: boolean;
  comment?: string;
}

/** GET /pharmacy/summary (sidebar badge and dashboard). Phase B adds the stock counts. */
export interface PharmacySummary {
  pending: number;
  urgent_pending: number;
  critical_pending: number;
  changes_requested: number;
  low_stock?: number;
  expiring?: number;
}
```

Add one member to the `WsFrame` union, after `device_status`:

```ts
  | { type: "device_status"; data: { device_id: string; online: boolean; ts: string } }
  | {
      type: "prescription_status";
      data: { prescription_id: string; patient_id: string; status: PrescriptionStatus; urgent: boolean };
    };
```

- [ ] **Step 3: Run the type check to see what the new role and fields break**

Run: `npx tsc --noEmit`
Expected: FAIL. The errors include:
- `src/mocks/people.ts` (`USERS` misses `pharmacist`);
- `src/components/LoginForm.tsx` (`HOME`);
- `src/components/shared/NotesPanel.tsx` (`ROLE_WORD`);
- `src/components/admin/StaffView.tsx` (`ROLE_LABEL`, `ROLE_COLORS`);
- `src/mocks/clinical.ts` and `src/lib/api.ts` (`status`, `urgent`, `version` missing).

Steps 4–11 fix them all.

- [ ] **Step 4: Create the `pharmacy` i18n namespace (`web/src/i18n/messages/pharmacy.ts`)**

```ts
import { messages } from "../define";

// Hospital pharmacy: pharmacist space, checks, statuses, catalogue, doctor form additions,
// nurse badges, and Phase B dispensing and stock. Later tasks append keys to all three blocks.
export const pharmacy = messages({
  en: {
    rolePharmacist: "Pharmacist",
    sevCritical: "Critical",
    sevMajor: "Major",
    sevModerate: "Moderate",
    sevInfo: "Info",
    statusPending: "Awaiting pharmacist",
    statusPendingUrgent: "Urgent · started, awaiting pharmacist",
    statusValidated: "Validated",
    statusChanges: "Changes requested",
    statusRejected: "Rejected",
    statusStopped: "Stopped",
    statusSuperseded: "Replaced",
    chkAllergy: "Allergy: the patient is allergic to {allergy} ({class}).",
    chkInteraction: "Interaction with {other} ({group_a} + {group_b}).",
    chkMaxDailyDose: "{daily_mg} mg a day is above the maximum of {max_mg} mg.",
    chkDuplicate: "Duplicate therapy with {other}.",
    chkNonFormulary: "Not in the hospital formulary.",
    chkHighAlert: "High-alert drug: double-check.",
    chkElderly: "Patient aged {age}: use with caution in the elderly.",
    checkItem: "Item {n}: {med}",
    errOverrideRequired: "A critical warning needs a reason before it can be sent.",
    errAckRequired: "The warnings changed. Tick “I reviewed the warnings” again, then validate.",
    errBadStatus: "Someone already decided on this prescription. The list was refreshed.",
    errRxConflict: "A newer version of this prescription already exists. Reload the page and edit the latest one.",
  },
  fr: {
    rolePharmacist: "Pharmacien(ne)",
    sevCritical: "Critique",
    sevMajor: "Majeur",
    sevModerate: "Modéré",
    sevInfo: "Info",
    statusPending: "En attente du pharmacien",
    statusPendingUrgent: "Urgent · commencé, en attente du pharmacien",
    statusValidated: "Validée",
    statusChanges: "Modification demandée",
    statusRejected: "Refusée",
    statusStopped: "Arrêtée",
    statusSuperseded: "Remplacée",
    chkAllergy: "Allergie : le patient est allergique à {allergy} ({class}).",
    chkInteraction: "Interaction avec {other} ({group_a} + {group_b}).",
    chkMaxDailyDose: "{daily_mg} mg par jour dépasse le maximum de {max_mg} mg.",
    chkDuplicate: "Doublon thérapeutique avec {other}.",
    chkNonFormulary: "Hors livret thérapeutique de l'hôpital.",
    chkHighAlert: "Médicament à haut risque : double contrôle.",
    chkElderly: "Patient de {age} ans : prudence chez le sujet âgé.",
    checkItem: "Ligne {n} : {med}",
    errOverrideRequired: "Un avertissement critique exige une justification avant l'envoi.",
    errAckRequired: "Les avertissements ont changé. Cochez à nouveau « J'ai examiné les avertissements », puis validez.",
    errBadStatus: "Quelqu'un a déjà statué sur cette ordonnance. La liste a été actualisée.",
    errRxConflict: "Une version plus récente de cette ordonnance existe déjà. Rechargez la page et modifiez la dernière.",
  },
  ar: {
    rolePharmacist: "صيدلي",
    sevCritical: "حرج",
    sevMajor: "كبير",
    sevModerate: "متوسط",
    sevInfo: "معلومة",
    statusPending: "بانتظار الصيدلي",
    statusPendingUrgent: "عاجل · بدأ، بانتظار الصيدلي",
    statusValidated: "معتمدة",
    statusChanges: "طُلب تعديلها",
    statusRejected: "مرفوضة",
    statusStopped: "موقوفة",
    statusSuperseded: "استُبدلت",
    chkAllergy: "حساسية: المريض لديه حساسية من {allergy} ({class}).",
    chkInteraction: "تداخل دوائي مع {other} ({group_a} + {group_b}).",
    chkMaxDailyDose: "{daily_mg} ملغ في اليوم تتجاوز الحد الأقصى البالغ {max_mg} ملغ.",
    chkDuplicate: "علاج مكرر مع {other}.",
    chkNonFormulary: "خارج دليل أدوية المستشفى.",
    chkHighAlert: "دواء عالي الخطورة: تحقق مزدوج.",
    chkElderly: "عمر المريض {age} سنة: يُستعمل بحذر لدى المسنين.",
    checkItem: "البند {n}: {med}",
    errOverrideRequired: "يتطلب التحذير الحرج ذكر مبرر قبل الإرسال.",
    errAckRequired: "تغيّرت التحذيرات. ضع علامة على «راجعتُ التحذيرات» من جديد ثم اعتمد.",
    errBadStatus: "سبق أن اتخذ أحدهم قراراً بشأن هذه الوصفة. تم تحديث القائمة.",
    errRxConflict: "توجد نسخة أحدث من هذه الوصفة. أعد تحميل الصفحة وعدّل الأحدث.",
  },
});
```

Register the namespace in `web/src/i18n/messages/index.ts`:

```ts
import { pharmacy } from "./pharmacy";
// …
export const ALL = { common, shared, doctor, nurse, admin, patient, auth, accounts, pharmacy };
```

- [ ] **Step 5: Create the pure rules (`web/src/lib/pharmacy.ts`)**

```ts
// Pure pharmacy rules shared by the screens and the mocks (no React, no I/O): severity order, the
// worklist order, what "running" means, the doctor's list, check texts and decision validation.
import type { Key, TFn } from "@/i18n/messages";
import type {
  Check,
  CheckCode,
  CheckSeverity,
  Drug,
  Prescription,
  PrescriptionStatus,
  ReviewDecision,
  WorklistItem,
} from "./types";

export const SEVERITY_RANK: Record<CheckSeverity, number> = { critical: 3, major: 2, moderate: 1, info: 0 };
const rank = (s: CheckSeverity | null | undefined): number => (s ? SEVERITY_RANK[s] : -1);

export const SEVERITY_KEY: Record<CheckSeverity, Key> = {
  critical: "pharmacy.sevCritical",
  major: "pharmacy.sevMajor",
  moderate: "pharmacy.sevModerate",
  info: "pharmacy.sevInfo",
};

export const STATUS_KEY: Record<PrescriptionStatus, Key> = {
  pending_pharmacy: "pharmacy.statusPending",
  validated: "pharmacy.statusValidated",
  changes_requested: "pharmacy.statusChanges",
  rejected: "pharmacy.statusRejected",
  stopped: "pharmacy.statusStopped",
  superseded: "pharmacy.statusSuperseded",
};

export const DECISION_KEY: Record<ReviewDecision, Key> = {
  validated: "pharmacy.statusValidated",
  changes_requested: "pharmacy.statusChanges",
  rejected: "pharmacy.statusRejected",
};

/** Request-changes and reject comments: 1–500 characters (spec §5), counted in code points like the server. */
export const COMMENT_MAX = 500;
/** The doctor's override reason (Contract decisions §15). */
export const OVERRIDE_MAX = 500;

export function maxSeverity(checks: readonly Check[]): CheckSeverity | null {
  return checks.reduce<CheckSeverity | null>((m, c) => (rank(c.severity) > rank(m) ? c.severity : m), null);
}

/** Most severe first, then by item. */
export function sortChecks(checks: readonly Check[]): Check[] {
  return [...checks].sort(
    (a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity] || (a.item_index ?? -1) - (b.item_index ?? -1),
  );
}

export function hasCritical(checks: readonly Check[] | null | undefined): boolean {
  return !!checks?.some((c) => c.severity === "critical");
}

/** Spec §2: urgent first, then the highest severity, then the oldest. Stable for equal rows. */
export function sortWorklist(items: readonly WorklistItem[]): WorklistItem[] {
  return items
    .map((it, i) => ({ it, i }))
    .sort(
      (a, b) =>
        Number(b.it.urgent) - Number(a.it.urgent) ||
        rank(b.it.max_severity) - rank(a.it.max_severity) ||
        Date.parse(a.it.waiting_since) - Date.parse(b.it.waiting_since) ||
        a.i - b.i,
    )
    .map(({ it }) => it);
}

/** The status, falling back to the pre-1.12 `active` flag when a server sends none. */
export function statusOf(rx: Pick<Prescription, "status" | "active">): PrescriptionStatus {
  return rx.status ?? (rx.active ? "validated" : "stopped");
}

/** Doses go out (spec §3 `active`): validated, or pending with the urgent bypass. */
export function isRunning(rx: Pick<Prescription, "status" | "active" | "urgent">): boolean {
  const s = statusOf(rx);
  return s === "validated" || (s === "pending_pharmacy" && !!rx.urgent);
}

/** Doses are already going out but the pharmacist hasn't reviewed it yet. */
export function isPendingUrgent(rx: Pick<Prescription, "status" | "active" | "urgent"> | null | undefined): boolean {
  return !!rx && statusOf(rx) === "pending_pharmacy" && !!rx.urgent;
}

const DOCTOR_ORDER: Partial<Record<PrescriptionStatus, number>> = {
  changes_requested: 0,
  pending_pharmacy: 1,
  validated: 2,
  rejected: 3,
};

/**
 * The doctor's list: no stopped or superseded rows; a version that was sent back and then resubmitted
 * hides behind its successor. Needs-action first (changes requested, pending), then running, then rejected.
 */
export function doctorRows(list: readonly Prescription[]): Prescription[] {
  const replaced = new Set(list.map((r) => r.replaces_id).filter((x): x is string => !!x));
  return list
    .filter((r) => DOCTOR_ORDER[statusOf(r)] !== undefined && (isRunning(r) || !replaced.has(r.id)))
    .sort(
      (a, b) =>
        (DOCTOR_ORDER[statusOf(a)] ?? 9) - (DOCTOR_ORDER[statusOf(b)] ?? 9) ||
        Date.parse(b.created_at) - Date.parse(a.created_at),
    );
}

/** A pending version that will replace `rx` once validated (the doctor can't edit `rx` meanwhile). */
export function pendingSuccessor(rx: Prescription, list: readonly Prescription[]): Prescription | undefined {
  return list.find((r) => r.replaces_id === rx.id && statusOf(r) === "pending_pharmacy");
}

/** "Amoxicillin 1 g": the `med` display string written for a formulary pick. */
export const drugLabel = (d: Pick<Drug, "dci" | "strength">): string => `${d.dci} ${d.strength}`;

const CHECK_TEXT: Record<CheckCode, { key: Key; params: readonly string[] }> = {
  allergy: { key: "pharmacy.chkAllergy", params: ["allergy", "class"] },
  interaction: { key: "pharmacy.chkInteraction", params: ["other", "group_a", "group_b"] },
  max_daily_dose: { key: "pharmacy.chkMaxDailyDose", params: ["daily_mg", "max_mg"] },
  duplicate_therapy: { key: "pharmacy.chkDuplicate", params: ["other"] },
  non_formulary: { key: "pharmacy.chkNonFormulary", params: [] },
  high_alert: { key: "pharmacy.chkHighAlert", params: [] },
  elderly: { key: "pharmacy.chkElderly", params: ["age"] },
};

/** Plain-language text in the UI language; the server's English `message` when the code or a param is unknown. */
export function checkText(c: Check, t: TFn): string {
  const spec = (CHECK_TEXT as Partial<Record<string, { key: Key; params: readonly string[] }>>)[c.code];
  if (!spec) return c.message;
  const vars: Record<string, string | number> = {};
  for (const p of spec.params) {
    const v = c.params?.[p];
    if (v === undefined || v === null || v === "") return c.message;
    vars[p] = v;
  }
  return t(spec.key, vars);
}

export type Decision = "validate" | "request_changes" | "reject";
export type DecisionProblem = "ack_required" | "comment_required" | "comment_too_long";

/**
 * Client-side mirror of the decision rules (spec §2, §5): Validate needs the "warnings reviewed" tick when
 * there are checks; Request changes and Reject need a 1–500 character comment. null = the action may go.
 */
export function decisionProblem(
  d: { decision: Decision; acknowledged: boolean; comment: string },
  hasChecks: boolean,
): DecisionProblem | null {
  const length = [...d.comment.trim()].length;
  if (d.decision === "validate") {
    if (hasChecks && !d.acknowledged) return "ack_required";
    return length > COMMENT_MAX ? "comment_too_long" : null;
  }
  if (length === 0) return "comment_required";
  return length > COMMENT_MAX ? "comment_too_long" : null;
}
```

- [ ] **Step 6: Create the frame bus (`web/src/lib/frames.ts`) and the error mapping (`web/src/lib/pharmacyUi.ts`)**

```ts
// In-tab bus for live frames. The WebSocket client (lib/live.ts) publishes server frames here; mock mode
// publishes the frames the server would send, so every screen refreshes the same way in both modes.
import type { WsFrame } from "./types";

type Listener = (frame: WsFrame) => void;
const listeners = new Set<Listener>();

export function subscribeFrames(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function publishFrame(frame: WsFrame): void {
  for (const fn of [...listeners]) {
    try {
      fn(frame);
    } catch {
      /* one failing listener must not stop the others */
    }
  }
}
```

```ts
// Pharmacy error codes (spec §5) → localized message keys. Only for pharmacy calls: `conflict` and
// `bad_status` mean other things on the accounts screens, which keep lib/accountsUi.ts.
import type { Key } from "@/i18n/messages";
import { describeError } from "./accountsUi";
import { ApiError } from "./api";

const BY_CODE: Partial<Record<string, Key>> = {
  override_required: "pharmacy.errOverrideRequired",
  ack_required: "pharmacy.errAckRequired",
  bad_status: "pharmacy.errBadStatus",
  conflict: "pharmacy.errRxConflict",
};

/** The key for a pharmacy error code, or null when `err` is not one. */
export function pharmacyErrorKey(err: unknown): Key | null {
  return err instanceof ApiError ? (BY_CODE[err.code] ?? null) : null;
}

/** pharmacyErrorKey, else the shared mapping (server unreachable, 403, 404, 422…). */
export function describePharmacyError(err: unknown): Key {
  return pharmacyErrorKey(err) ?? describeError(err).key;
}
```

- [ ] **Step 7: Create the mock formulary and check engine (`web/src/mocks/pharmacy.ts`)**

```ts
// Pharmacy fixtures and the mock check engine. Synthetic and illustrative, not a clinical reference.
// The engine follows spec §4 closely enough for the demo; the backend's rule files are the authority.
import { isRunning, SEVERITY_RANK } from "@/lib/pharmacy";
import type { Check, CheckRequest, CheckSeverity, Drug, Patient, Prescription, PrescriptionItem, PrescriptionReview } from "@/lib/types";
import { USERS } from "./people";
import { at, TODAY } from "./time";

const CREATED = at("2026-09-01", "09:00");

function drug(
  n: number,
  dci: string,
  strength: string,
  form: Drug["form"],
  unit_mg: number | null,
  max_daily_mg: number | null,
  atc_code: string,
  brand_names: string[],
  allergy_classes: string[] = [],
  interaction_groups: string[] = [],
  high_alert = false,
): Drug {
  return {
    id: `d-${String(n).padStart(4, "0")}`,
    dci, brand_names, form, strength, unit_mg, max_daily_mg, atc_code, allergy_classes, interaction_groups, high_alert,
    min_stock: 20, active: true, created_at: CREATED, updated_at: CREATED,
  };
}

/** Every drug of the seed prescriptions plus the demo cases (spec §7). */
export const FORMULARY: Drug[] = [
  drug(1, "Paracetamol", "500 mg", "tablet", 500, 4000, "N02BE01", ["Doliprane", "Efferalgan"]),
  drug(2, "Paracetamol", "1 g", "tablet", 1000, 4000, "N02BE01", ["Doliprane"]),
  drug(3, "Amoxicillin", "1 g", "tablet", 1000, 6000, "J01CA04", ["Amoxil", "Hiconcil"], ["penicillin", "beta_lactam"]),
  drug(4, "Amoxicillin", "500 mg", "capsule", 500, 6000, "J01CA04", ["Amoxil"], ["penicillin", "beta_lactam"]),
  drug(5, "Azithromycin", "250 mg", "tablet", 250, 500, "J01FA10", ["Zithromax"], ["macrolide"]),
  drug(6, "Warfarin", "5 mg", "tablet", 5, 15, "B01AA03", ["Coumadine"], [], ["anticoagulant"], true),
  drug(7, "Aspirin", "100 mg", "tablet", 100, 300, "B01AC06", ["Kardegic", "Aspegic"], ["nsaid"], ["antiplatelet"]),
  drug(8, "Ibuprofen", "400 mg", "tablet", 400, 1200, "M01AE01", ["Brufen", "Advil"], ["nsaid"], ["nsaid"]),
  drug(9, "Enoxaparin", "40 mg", "injection", null, null, "B01AB05", ["Lovenox"], [], ["anticoagulant"], true),
  drug(10, "Bisoprolol", "2.5 mg", "tablet", 2.5, 20, "C07AB07", ["Concor"], [], ["beta_blocker"]),
  drug(11, "Furosemide", "40 mg", "tablet", 40, 600, "C03CA01", ["Lasilix"], [], ["loop_diuretic"]),
  drug(12, "Furosemide", "20 mg", "tablet", 20, 600, "C03CA01", ["Lasilix"], [], ["loop_diuretic"]),
  drug(13, "Ramipril", "5 mg", "capsule", 5, 10, "C09AA05", ["Triatec"], [], ["ace_inhibitor"]),
  drug(14, "Metformin", "500 mg", "tablet", 500, 3000, "A10BA02", ["Glucophage"]),
  drug(15, "Metformin", "1000 mg", "tablet", 1000, 3000, "A10BA02", ["Glucophage"]),
  drug(16, "Salbutamol", "100 µg/dose", "inhaler", null, null, "R03AC02", ["Ventoline"]),
  drug(17, "Insulin glargine", "100 U/mL", "injection", null, null, "A10AE04", ["Lantus"], [], [], true),
  drug(18, "Morphine", "10 mg", "tablet", 10, null, "N02AA01", ["Skenan"], [], ["opioid"], true),
  drug(19, "Potassium chloride", "1 g/10 mL", "injection", null, null, "B05XA01", [], [], ["potassium"], true),
  drug(20, "Amlodipine", "5 mg", "tablet", 5, 10, "C08CA01", ["Amlor"], [], ["ccb"]),
  drug(21, "Diazepam", "5 mg", "tablet", 5, 40, "N05BA01", ["Valium"], [], ["benzodiazepine"]),
];

const squash = (s: string) => s.toLowerCase().replace(/\s+/g, "");

/** Backfill rule (spec §3): exact "DCI + strength", else the first drug whose DCI starts the name. */
export function drugIdFor(med: string): string | null {
  const m = squash(med);
  return (FORMULARY.find((d) => squash(`${d.dci}${d.strength}`) === m) ?? FORMULARY.find((d) => m.startsWith(squash(d.dci))))?.id ?? null;
}

/** GET /drugs?q= match: DCI or brand (substring), ATC (prefix), case-insensitive. */
export function drugMatches(d: Drug, q: string): boolean {
  const n = q.trim().toLowerCase();
  if (!n) return true;
  return d.dci.toLowerCase().includes(n) || d.brand_names.some((b) => b.toLowerCase().includes(n)) || d.atc_code.toLowerCase().startsWith(n);
}

// Illustrative rule tables (the backend's rules/pharmacy/*.v1.json are the reference).
const INTERACTIONS: [string, string, CheckSeverity][] = [
  ["anticoagulant", "nsaid", "major"],
  ["anticoagulant", "antiplatelet", "major"],
  ["opioid", "benzodiazepine", "critical"],
  ["ace_inhibitor", "potassium", "moderate"],
  ["nsaid", "loop_diuretic", "moderate"],
];
const ALLERGY_SYNONYMS: Record<string, string> = {
  penicillin: "penicillin", "pénicilline": "penicillin", "بنسلين": "penicillin", amoxicillin: "penicillin",
  ibuprofen: "nsaid", "ibuprofène": "nsaid", aspirin: "nsaid", aspirine: "nsaid", nsaid: "nsaid", ains: "nsaid",
  macrolide: "macrolide",
};
const ELDERLY_CAUTION = new Set(["diazepam", "ibuprofen"]);

const norm = (s: string) => s.trim().toLowerCase();
const allergyClass = (a: string) => ALLERGY_SYNONYMS[norm(a)] ?? norm(a);

/** Spec §4, simplified. Pairs are reported only when at least one side is a candidate item. */
export function mockChecks(
  patient: { age: number; allergies: string[] },
  items: PrescriptionItem[],
  running: Prescription[],
  drugs: Drug[],
): Check[] {
  const byId = new Map(drugs.map((d) => [d.id, d]));
  const drugOf = (it: PrescriptionItem) => (it.drug_id ? byId.get(it.drug_id) : undefined);
  const classes = new Map(patient.allergies.map((a) => [allergyClass(a), a]));
  const runningItems = running.flatMap((rx) => rx.items.map((it) => ({ it, drug: drugOf(it) })));
  const out: Check[] = [];
  const add = (c: Omit<Check, "message">, message: string) => out.push({ ...c, message });

  items.forEach((it, i) => {
    const d = drugOf(it);
    if (!d) {
      add({ code: "non_formulary", severity: "moderate", item_index: i, drug_id: null, params: { med: it.med } }, `${it.med} is not in the formulary`);
      return;
    }
    for (const cls of d.allergy_classes) {
      const hit = classes.get(cls);
      if (hit) add({ code: "allergy", severity: "critical", item_index: i, drug_id: d.id, params: { allergy: hit, class: cls } }, `Allergy: ${hit} (${cls})`);
    }
    const perIntake = it.dose_mg ?? (d.unit_mg != null ? (it.units_per_intake ?? 1) * d.unit_mg : null);
    if (perIntake != null && d.max_daily_mg != null) {
      const daily = perIntake * it.times.length;
      if (daily > d.max_daily_mg)
        add(
          { code: "max_daily_dose", severity: daily > 2 * d.max_daily_mg ? "critical" : "major", item_index: i, drug_id: d.id, params: { daily_mg: daily, max_mg: d.max_daily_mg } },
          `Daily dose ${daily} mg > max ${d.max_daily_mg} mg`,
        );
    }
    const others = [...runningItems, ...items.slice(i + 1).map((x) => ({ it: x, drug: drugOf(x) }))];
    for (const o of others) {
      if (!o.drug) continue;
      if (o.drug.dci === d.dci || o.drug.atc_code.slice(0, 5) === d.atc_code.slice(0, 5))
        add({ code: "duplicate_therapy", severity: "major", item_index: i, drug_id: d.id, params: { other: o.it.med } }, `Duplicate therapy with ${o.it.med}`);
      for (const [a, b, severity] of INTERACTIONS) {
        const hit =
          (d.interaction_groups.includes(a) && o.drug.interaction_groups.includes(b)) ||
          (d.interaction_groups.includes(b) && o.drug.interaction_groups.includes(a));
        if (hit) add({ code: "interaction", severity, item_index: i, drug_id: d.id, params: { other: o.it.med, group_a: a, group_b: b } }, `Interaction with ${o.it.med} (${a} + ${b})`);
      }
    }
    if (d.high_alert) add({ code: "high_alert", severity: "info", item_index: i, drug_id: d.id, params: {} }, `${d.dci} is a high-alert drug`);
    if (patient.age >= 75 && ELDERLY_CAUTION.has(norm(d.dci)))
      add({ code: "elderly", severity: "moderate", item_index: i, drug_id: d.id, params: { age: patient.age } }, `Elderly caution (${patient.age})`);
  });
  return out.sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity]);
}

/** `id` and every version it replaces (Contract decisions §5: the check excludes the whole chain). */
export function chainOf(list: Prescription[], id: string | null | undefined): Set<string> {
  const ids = new Set<string>();
  let cur = id ? list.find((r) => r.id === id) : undefined;
  while (cur && !ids.has(cur.id)) {
    ids.add(cur.id);
    const prev: string | null | undefined = cur.replaces_id;
    cur = prev ? list.find((r) => r.id === prev) : undefined;
  }
  return ids;
}

/** The checks for `req` against the patient's other running prescriptions (spec §4 inputs). `selfId` = the saved version itself. */
export function checksFor(patients: Patient[], prescriptions: Prescription[], drugs: Drug[], req: CheckRequest, selfId?: string): Check[] {
  const p = patients.find((x) => x.id === req.patient_id);
  if (!p) return [];
  const chain = chainOf(prescriptions, req.replaces_id);
  const running = prescriptions.filter((r) => r.patient_id === p.id && r.id !== selfId && !chain.has(r.id) && isRunning(r));
  return mockChecks({ age: p.age, allergies: p.allergies }, req.items, running, drugs);
}

/** Decision history. `checks_snapshot` is filled in createStore from the computed checks. */
export const REVIEWS: PrescriptionReview[] = [
  {
    id: "pr-0001",
    prescription_id: "rx-0015",
    pharmacist_id: USERS.pharmacist.id,
    decision: "changes_requested",
    comment: "Max 3 g/day, and Metformin 500 mg is already running: stop it or lower this dose.",
    checks_snapshot: [],
    created_at: at(TODAY, "08:50"),
    pharmacist_name: USERS.pharmacist.name,
  },
];
```

- [ ] **Step 8: Update the people, clinical and store mocks**

`web/src/mocks/people.ts`: add the pharmacist to `USERS`, and a row to `STAFF_ROWS`, after the admin row:

```ts
export const USERS = {
  doctor: { id: "u-0001", name: "Dr Trabelsi", email: "m.trabelsi@hr-ward.tn", role: "doctor", patient_id: null },
  nurse: { id: "u-0002", name: "Nurse Ines", email: "i.mejri@hr-ward.tn", role: "nurse", patient_id: null },
  admin: { id: "u-0003", name: "Mme Gharbi", email: "n.gharbi@hr-ward.tn", role: "admin", patient_id: null },
  patient: { id: "u-0007", name: "Amira Ben Salah", email: "patient@ward.tn", role: "patient", patient_id: "p-0001" },
  pharmacist: { id: "u-0012", name: "Pharm. Salma", email: "pharmacist@ward.tn", role: "pharmacist", patient_id: null },
} satisfies Record<Me["role"], Me>;
```

```ts
  { id: "u-0012", name: "Pharm. Salma", email: "pharmacist@ward.tn", role: "pharmacist", ward: null, scope: "Pharmacy", last_login_at: at(TODAY, "07:40") },
```

`web/src/mocks/clinical.ts`:
- Import `drugIdFor` from `./pharmacy`, and `Prescription` is already imported.
- Replace the `rx()` helper with the version below.
- Give `rx-0002` its historical override reason.
- Append four fixtures, and append one dose at the **end** of `DOSES`, so the existing dose ids keep their numbers.

```ts
import { drugIdFor } from "./pharmacy";

const RX_CREATED = at("2026-10-02", "11:00");
const RX_REVIEWED = at("2026-10-02", "11:30");

function rx(
  id: string,
  patient_id: string,
  med: string,
  times: string[],
  slot: number | null,
  days: number,
  care_plan: string,
  version: number,
  allergy_override = false,
  extra: Partial<Prescription> = {},
): Prescription {
  return {
    id,
    patient_id,
    doctor_id: "u-0001",
    items: [{ med, drug_id: drugIdFor(med), dose_mg: null, units_per_intake: 1, times, slot, days }],
    care_plan,
    active: true,
    created_at: RX_CREATED,
    schedule_version: version,
    published_to_device: true,
    status: "validated",
    urgent: false,
    version: 1,
    replaces_id: null,
    checks: [],
    override_reason: null,
    review_comment: null,
    reviewed_by_name: "Pharm. Salma",
    reviewed_at: RX_REVIEWED,
    ...(allergy_override ? { allergy_override: true } : {}),
    ...extra,
  };
}

/** Not yet reviewed (or sent back): no reviewer, no device publish until validated (unless urgent). */
const awaiting = (created: string, extra: Partial<Prescription> = {}): Partial<Prescription> => ({
  status: "pending_pharmacy",
  active: false,
  published_to_device: false,
  created_at: created,
  reviewed_by_name: null,
  reviewed_at: null,
  ...extra,
});

// `days` is the course length from 2 Oct; days left on Mon 5 Oct = days − 3 (design: 3, 4, 12, 30).
export const PRESCRIPTIONS: Prescription[] = [
  rx("rx-0001", "p-0001", "Paracetamol 500mg", ["08:00", "20:00"], 1, 6, "For fever above 38 °C", 1),
  rx("rx-0002", "p-0001", "Amoxicillin 1g", ["14:00"], 2, 7, "", 2, true, { override_reason: "Mild rash in 2019; no tolerated oral alternative." }),
  rx("rx-0003", "p-0001", "Warfarin 5mg", ["20:00"], 3, 15, "Recheck INR Wednesday", 3),
  rx("rx-0004", "p-0001", "Aspirin 100mg", ["08:00"], null, 33, "Nurse gives at round", 4),
  rx("rx-0005", "p-0002", "Bisoprolol 2.5mg", ["08:00"], 1, 10, "", 1),
  rx("rx-0006", "p-0002", "Furosemide 40mg", ["10:00"], null, 10, "", 2),
  rx("rx-0007", "p-0002", "Enoxaparin 40mg", ["20:00"], null, 10, "", 3),
  rx("rx-0008", "p-0003", "Ramipril 5mg", ["08:00"], 1, 10, "", 1),
  rx("rx-0009", "p-0003", "Furosemide 20mg", ["10:00"], 2, 10, "", 2),
  rx("rx-0010", "p-0004", "Metformin 500mg", ["09:00"], 1, 10, "", 1),
  rx("rx-0011", "p-0004", "Salbutamol inhaler", ["10:00"], null, 10, "", 2),
  // Pharmacy demo (spec §7): critical allergy with an override, urgent with an interaction, a clean one, one sent back.
  rx("rx-0012", "p-0001", "Amoxicillin 1 g", ["06:00", "14:00", "22:00"], null, 7, "Chest infection", 5, false,
    awaiting(at(TODAY, "08:40"), { override_reason: "Rash in 2019 was mild; benefit outweighs risk. Watch for rash." })),
  rx("rx-0013", "p-0002", "Ibuprofen 400 mg", ["08:00", "20:00"], null, 5, "Pain relief, short course", 4, false,
    awaiting(at(TODAY, "09:00"), { urgent: true, active: true })),
  rx("rx-0014", "p-0003", "Paracetamol 1 g", ["08:00", "14:00", "20:00"], null, 3, "", 3, false, awaiting(at(TODAY, "07:30"))),
  rx("rx-0015", "p-0004", "Metformin 1000 mg", ["08:00", "12:00", "18:00", "22:00"], null, 10, "", 3, false,
    awaiting(at(TODAY, "07:50"), {
      status: "changes_requested",
      review_comment: "Max 3 g/day, and Metformin 500 mg is already running: stop it or lower this dose.",
      reviewed_by_name: "Pharm. Salma",
      reviewed_at: at(TODAY, "08:50"),
    })),
];
```

At the end of the `DOSES` array, after the Salbutamol line:

```ts
  // Omar — urgent ibuprofen (rx-0013), started before the pharmacist's review
  dose("rx-0013", "p-0002", TODAY, "20:00", "Ibuprofen 400 mg", null, "scheduled", { instructions: "Give by hand" }),
```

`web/src/mocks/index.ts`:
- Re-export the helpers.
- Add the store fields.
- Compute the fixture checks in `createStore`.

```ts
import type { Alert, AiSummary, Appointment, Device, Dose, Drug, ExamOrder, HomeCarePlan, Note, Patient, Prescription, PrescriptionReview, SlotOffer, StaffMember, Vital, DoctorRef, PatientAccessGrant, PendingUser, UserAdmin } from "@/lib/types";
import { checksFor, FORMULARY, REVIEWS } from "./pharmacy";
export { chainOf, checksFor, drugMatches } from "./pharmacy";
```

In `MockStore`, add:

```ts
  drugs: Drug[];
  reviews: PrescriptionReview[];
  seq: { rx: number; dose: number; note: number; user: number; drug: number; review: number };
```

Replace `createStore()` with:

```ts
/** A fresh, deep-copied, mutable store. Mutations in api.ts write here. */
export function createStore(): MockStore {
  const s: MockStore = structuredClone({
    patients: PATIENTS,
    vitals: VITALS,
    prescriptions: PRESCRIPTIONS,
    doses: DOSES,
    notes: NOTES,
    summaries: SUMMARIES,
    appointments: [...WAITLIST, ...PATIENT_APPOINTMENTS],
    alerts: ALERTS,
    devices: DEVICES,
    staff: STAFF,
    boardBedOrder: BOARD_BED_ORDER,
    offers: OFFERS,
    exams: examFixtures(WAITLIST[0].id, WAITLIST[0].patient_id, WAITLIST[0].patient_name ?? ""),
    homeCare: HOME_CARE,
    directory: DOCTOR_DIRECTORY,
    pending: PENDING,
    team: TEAM,
    grants: GRANTS,
    linkedPatients: [USERS.patient.patient_id],
    drugs: FORMULARY,
    reviews: REVIEWS,
    seq: {
      rx: PRESCRIPTIONS.length,
      dose: DOSES.length,
      note: Object.values(NOTES).flat().length,
      user: 100,
      drug: FORMULARY.length,
      review: REVIEWS.length,
    },
  });
  // Checks are computed, never typed into fixtures: the same engine the mock POST /prescriptions runs.
  for (const rx of s.prescriptions)
    if (rx.status === "pending_pharmacy" || rx.status === "changes_requested")
      rx.checks = checksFor(s.patients, s.prescriptions, s.drugs, { patient_id: rx.patient_id, items: rx.items, ...(rx.replaces_id ? { replaces_id: rx.replaces_id } : {}) }, rx.id);
  for (const r of s.reviews) r.checks_snapshot = s.prescriptions.find((x) => x.id === r.prescription_id)?.checks ?? [];
  return s;
}
```

- [ ] **Step 9: Update the API client (`web/src/lib/api.ts`)**

Imports (top of the file):

```ts
import { chainOf, checksFor, createStore, drugMatches, generateCode, MOCK_CODES, EXAM_CATALOGUE, mockAssistant, USERS, userName, type AssistantContext, type MockStore } from "@/mocks";
import { publishFrame } from "./frames";
import { COMMENT_MAX, hasCritical, isRunning, maxSeverity, sortWorklist } from "./pharmacy";
```

Add these to the `import type { … } from "./types"` list:
- `Check`, `CheckRequest`, `CheckResponse`;
- `Drug`, `DrugInput`, `DrugPatch`;
- `PharmacyPatient`, `PharmacySummary`;
- `ReviewDecision`, `ReviewDetail`, `ValidateRequest`;
- `WorklistItem`, `WorklistStatus`.

Delete the old `PENICILLIN_FAMILY` constant. Then replace `getPrescriptions` and `createPrescription` (lines 546–608) with:

```ts
/** GET /patients/{id}/prescriptions: every version and status, newest first (screens filter with lib/pharmacy.ts). */
export function getPrescriptions(patientId: string): Promise<Prescription[]> {
  if (USE_MOCKS)
    return mock((s) =>
      s.prescriptions.filter((r) => r.patient_id === patientId).sort((a, b) => b.created_at.localeCompare(a.created_at)),
    );
  return http<Prescription[]>("GET", `/patients/${encodeURIComponent(patientId)}/prescriptions`);
}

/** Future doses of `rx` after `from`, one per (day × time), like the backend's rebuild_doses. Mock only. */
function scheduleDoses(s: MockStore, rx: Prescription, from: Date): void {
  const today = tunisDate(iso(from));
  for (const item of rx.items) {
    for (let d = 0; d < item.days + 1; d++) {
      const date = new Date(Date.parse(`${today}T12:00:00Z`) + d * 86_400_000).toISOString().slice(0, 10);
      for (const t of item.times) {
        const at = new Date(Date.parse(`${date}T${t}:00+01:00`));
        if (at <= from) continue;
        s.seq.dose += 1;
        s.doses.push({
          id: `d-${String(s.seq.dose).padStart(6, "0")}`,
          prescription_id: rx.id,
          patient_id: rx.patient_id,
          scheduled_at: iso(at),
          time_of_day: t,
          meds: [item.med],
          slot: item.slot,
          status: "scheduled",
          taken_method: null,
          updated_at: iso(from),
          taken_at: null,
          given_by: null,
          given_by_name: null,
          instructions: item.slot == null ? "Give by hand" : null,
        });
      }
    }
  }
  s.doses.sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
}

/** Deletes the future, not-yet-given doses of a prescription (reject, supersede). Mock only. */
function dropFutureDoses(s: MockStore, rxId: string): void {
  const t = now().getTime();
  s.doses = s.doses.filter((d) => !(d.prescription_id === rxId && d.status === "scheduled" && Date.parse(d.scheduled_at) > t));
}

/** The check engine on a saved prescription, as it stands now (the server's recompute). */
function rxChecks(s: MockStore, rx: Prescription): Check[] {
  return checksFor(s.patients, s.prescriptions, s.drugs, { patient_id: rx.patient_id, items: rx.items, ...(rx.replaces_id ? { replaces_id: rx.replaces_id } : {}) }, rx.id);
}

const statusFrame = (rx: Prescription) =>
  publishFrame({ type: "prescription_status", data: { prescription_id: rx.id, patient_id: rx.patient_id, status: rx.status, urgent: rx.urgent } });

/**
 * POST /prescriptions → Prescription with status/urgent/version/checks (api 1.12). The check engine runs on every save.
 * 422 `override_required`: a critical check and no `override_reason`. 409 `conflict`: `replaces_id` already has a successor.
 * Doses are created now only when `urgent`; otherwise on validation.
 */
export function createPrescription(req: CreatePrescriptionRequest, opts: ActorOpts = {}): Promise<Prescription> {
  if (USE_MOCKS)
    return mock((s) => {
      const patient = s.patients.find((p) => p.id === req.patient_id) ?? notFound(`Patient ${req.patient_id}`);
      const replaced = req.replaces_id
        ? (s.prescriptions.find((r) => r.id === req.replaces_id && r.patient_id === patient.id) ?? notFound(`Prescription ${req.replaces_id}`))
        : null;
      if (replaced && s.prescriptions.some((r) => r.replaces_id === replaced.id && r.status !== "rejected"))
        throw new ApiError(409, "conflict", "A newer version already replaces this prescription.");
      const checks = checksFor(s.patients, s.prescriptions, s.drugs, { patient_id: patient.id, items: req.items, ...(replaced ? { replaces_id: replaced.id } : {}) });
      const reason = req.override_reason?.trim() || null;
      if (hasCritical(checks) && !reason) throw new ApiError(422, "override_required", "A critical check needs an override_reason.");
      const urgent = !!req.urgent;
      const scheduleVersion = Math.max(0, ...s.prescriptions.filter((r) => r.patient_id === patient.id).map((r) => r.schedule_version)) + 1;
      s.seq.rx += 1;
      const created = now();
      const rx: Prescription = {
        id: `rx-${String(s.seq.rx).padStart(4, "0")}`,
        patient_id: patient.id,
        doctor_id: opts.by ?? USERS.doctor.id,
        items: req.items.map((i) => ({ ...i, units_per_intake: i.units_per_intake ?? 1 })),
        care_plan: req.care_plan,
        active: urgent,
        created_at: iso(created),
        schedule_version: scheduleVersion,
        published_to_device: urgent && !!patient.device_id,
        status: "pending_pharmacy",
        urgent,
        version: (replaced?.version ?? 0) + 1,
        replaces_id: replaced?.id ?? null,
        checks,
        override_reason: reason,
        review_comment: null,
        reviewed_by_name: null,
        reviewed_at: null,
        ...(reason && checks.some((c) => c.code === "allergy") ? { allergy_override: true } : {}),
      };
      s.prescriptions.push(rx);
      if (urgent) scheduleDoses(s, rx, created);
      statusFrame(rx);
      return rx;
    });
  return http<Prescription>("POST", "/prescriptions", req);
}
```

Append a new section after `markDoseGiven` (before `// ── AI summary and assistant`):

```ts
// ── Pharmacy (api 1.12, spec 2026-10-10 §5) ─────────────────────────────────

/** WS /ws?token=<jwt> for this tab's session; null in mock mode or when signed out (used by lib/live.ts). */
export function liveSocketUrl(): string | null {
  if (USE_MOCKS) return null;
  const token = getToken();
  return token ? `${BASE.replace(/^http/, "ws")}/ws?token=${encodeURIComponent(token)}` : null;
}

/** GET /drugs?q=&active=: DCI or brand (substring) or ATC code (prefix); at most 50. Omit `active` for both. */
export function listDrugs(opts: { q?: string; active?: boolean } = {}): Promise<Drug[]> {
  const q = (opts.q ?? "").trim();
  if (USE_MOCKS)
    return mock((s) => s.drugs.filter((d) => (opts.active === undefined || d.active === opts.active) && drugMatches(d, q)).slice(0, 50));
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (opts.active !== undefined) p.set("active", String(opts.active));
  const qs = p.toString();
  return http<Drug[]>("GET", `/drugs${qs ? `?${qs}` : ""}`);
}

const sortDrugs = (s: MockStore) => s.drugs.sort((a, b) => a.dci.localeCompare(b.dci) || a.strength.localeCompare(b.strength));

/** POST /drugs (pharmacist, admin). */
export function createDrug(req: DrugInput): Promise<Drug> {
  if (USE_MOCKS)
    return mock((s) => {
      if (!req.dci.trim() || !req.strength.trim() || !req.atc_code.trim()) throw new ApiError(422, "validation_error", "dci, strength and atc_code are required");
      s.seq.drug += 1;
      const t = iso(now());
      const drug: Drug = { ...req, id: `d-${String(s.seq.drug).padStart(4, "0")}`, created_at: t, updated_at: t };
      s.drugs.push(drug);
      sortDrugs(s);
      return drug;
    });
  return http<Drug>("POST", "/drugs", req);
}

/** PATCH /drugs/{id} (pharmacist, admin). Deactivate with `{active: false}`; there is no delete. */
export function updateDrug(id: string, patch: DrugPatch): Promise<Drug> {
  if (USE_MOCKS)
    return mock((s) => {
      const drug = s.drugs.find((d) => d.id === id) ?? notFound(`Drug ${id}`);
      for (const k of ["dci", "strength", "atc_code"] as const)
        if (patch[k] !== undefined && !patch[k]?.trim()) throw new ApiError(422, "validation_error", `${k} is required`);
      Object.assign(drug, patch, { updated_at: iso(now()) });
      sortDrugs(s);
      return drug;
    });
  return http<Drug>("PATCH", `/drugs/${enc(id)}`, patch);
}

/** POST /prescriptions/check: a dry run of the check engine while the doctor types. */
export function checkPrescription(req: CheckRequest): Promise<CheckResponse> {
  if (USE_MOCKS)
    return mock((s) => {
      s.patients.find((p) => p.id === req.patient_id) ?? notFound(`Patient ${req.patient_id}`);
      return { checks: checksFor(s.patients, s.prescriptions, s.drugs, req) };
    });
  return http<CheckResponse>("POST", "/prescriptions/check", req);
}

/** The pharmacist's minimal projection (spec §2). Explicit pick: never spread a Patient (history, notes…). */
function pharmacyPatient(p: Patient): PharmacyPatient {
  return { id: p.id, name: `${p.first_name} ${p.last_name}`, age: p.age, sex: p.sex, ward: p.ward, bed: p.bed, allergies: p.allergies };
}

function worklistItem(s: MockStore, rx: Prescription): WorklistItem {
  const p = s.patients.find((x) => x.id === rx.patient_id) ?? notFound(`Patient ${rx.patient_id}`);
  const checks = rx.checks ?? [];
  return {
    prescription: rx,
    patient: pharmacyPatient(p),
    doctor_name: userName(rx.doctor_id) ?? rx.doctor_id,
    checks,
    urgent: rx.urgent,
    waiting_since: rx.created_at,
    max_severity: maxSeverity(checks),
  };
}

/** GET /pharmacy/worklist?status=: urgent, then severity, then oldest (sorted here too, so both modes match). */
export async function getWorklist(status: WorklistStatus = "pending_pharmacy"): Promise<WorklistItem[]> {
  const list = USE_MOCKS
    ? await mock((s) =>
        s.prescriptions
          .filter((r) => (status === "all" ? r.status !== "stopped" && r.status !== "superseded" : r.status === status))
          .map((rx) => worklistItem(s, rx)),
      )
    : await http<WorklistItem[]>("GET", `/pharmacy/worklist?status=${status}`);
  return sortWorklist(list);
}

/** GET /pharmacy/prescriptions/{id}: the review panel, with `checks` recomputed now. */
export function getReview(id: string): Promise<ReviewDetail> {
  if (USE_MOCKS)
    return mock((s) => {
      const rx = s.prescriptions.find((r) => r.id === id) ?? notFound(`Prescription ${id}`);
      const p = s.patients.find((x) => x.id === rx.patient_id) ?? notFound(`Patient ${rx.patient_id}`);
      const chain = chainOf(s.prescriptions, rx.replaces_id);
      return {
        prescription: rx,
        patient: pharmacyPatient(p),
        doctor_name: userName(rx.doctor_id) ?? rx.doctor_id,
        running: s.prescriptions.filter((r) => r.patient_id === p.id && r.id !== rx.id && !chain.has(r.id) && isRunning(r)),
        checks: rxChecks(s, rx),
        history: s.reviews.filter((r) => r.prescription_id === rx.id),
        replaces: rx.replaces_id ? (s.prescriptions.find((r) => r.id === rx.replaces_id) ?? null) : null,
      };
    });
  return http<ReviewDetail>("GET", `/pharmacy/prescriptions/${enc(id)}`);
}

/** The prescription, if it is still pending; 409 `bad_status` otherwise (a second pharmacist was faster). */
function pendingRx(s: MockStore, id: string): Prescription {
  const rx = s.prescriptions.find((r) => r.id === id) ?? notFound(`Prescription ${id}`);
  if (rx.status !== "pending_pharmacy") throw new ApiError(409, "bad_status", `prescription is ${rx.status}`);
  return rx;
}

function requireComment(comment: string): string {
  const c = comment.trim();
  if (!c || [...c].length > COMMENT_MAX) throw new ApiError(422, "validation_error", "comment must be 1-500 characters");
  return c;
}

/** Writes the prescription_reviews row, the status and the reviewer, then sends the frame. */
function recordDecision(s: MockStore, rx: Prescription, decision: ReviewDecision, comment: string | null, by: string, checks: Check[]): Prescription {
  const at = iso(now());
  const name = userName(by) ?? by;
  s.seq.review += 1;
  s.reviews.unshift({
    id: `pr-${String(s.seq.review).padStart(4, "0")}`,
    prescription_id: rx.id,
    pharmacist_id: by,
    decision,
    comment,
    checks_snapshot: checks,
    created_at: at,
    pharmacist_name: name,
  });
  Object.assign(rx, { status: decision, checks, review_comment: comment, reviewed_by_name: name, reviewed_at: at });
  statusFrame(rx);
  return rx;
}

/** POST /pharmacy/prescriptions/{id}/validate `{acknowledged, comment?}`. 409 `bad_status`; 422 `ack_required`. */
export function validatePrescription(id: string, req: ValidateRequest, opts: ActorOpts = {}): Promise<Prescription> {
  if (USE_MOCKS)
    return mock((s) => {
      const rx = pendingRx(s, id);
      const checks = rxChecks(s, rx);
      if (checks.length && !req.acknowledged) throw new ApiError(422, "ack_required", "Acknowledge the checks first.");
      if (req.comment && [...req.comment.trim()].length > COMMENT_MAX) throw new ApiError(422, "validation_error", "comment is too long");
      // The running ancestor of this version is superseded only now: treatment never stops (spec §2).
      const ancestor = [...chainOf(s.prescriptions, rx.replaces_id)]
        .map((cid) => s.prescriptions.find((r) => r.id === cid))
        .find((r): r is Prescription => !!r && isRunning(r));
      if (ancestor) {
        Object.assign(ancestor, { status: "superseded", active: false });
        dropFutureDoses(s, ancestor.id);
      }
      rx.active = true;
      if (!rx.urgent) scheduleDoses(s, rx, now());
      return recordDecision(s, rx, "validated", req.comment?.trim() || null, opts.by ?? USERS.pharmacist.id, checks);
    });
  return http<Prescription>("POST", `/pharmacy/prescriptions/${enc(id)}/validate`, req);
}

/** POST /pharmacy/prescriptions/{id}/request-changes `{comment}` (1–500). An urgent one stops its future doses. */
export function requestPrescriptionChanges(id: string, comment: string, opts: ActorOpts = {}): Promise<Prescription> {
  if (USE_MOCKS)
    return mock((s) => {
      const rx = pendingRx(s, id);
      const text = requireComment(comment);
      rx.active = false;
      if (rx.urgent) dropFutureDoses(s, rx.id);
      return recordDecision(s, rx, "changes_requested", text, opts.by ?? USERS.pharmacist.id, rxChecks(s, rx));
    });
  return http<Prescription>("POST", `/pharmacy/prescriptions/${enc(id)}/request-changes`, { comment });
}

/** POST /pharmacy/prescriptions/{id}/reject `{comment}`. Urgent then rejected: its future doses are deleted (spec §2). */
export function rejectPrescription(id: string, comment: string, opts: ActorOpts = {}): Promise<Prescription> {
  if (USE_MOCKS)
    return mock((s) => {
      const rx = pendingRx(s, id);
      const text = requireComment(comment);
      rx.active = false;
      if (rx.urgent) dropFutureDoses(s, rx.id);
      return recordDecision(s, rx, "rejected", text, opts.by ?? USERS.pharmacist.id, rxChecks(s, rx));
    });
  return http<Prescription>("POST", `/pharmacy/prescriptions/${enc(id)}/reject`, { comment });
}

/** GET /pharmacy/summary: sidebar badge and dashboard tiles. */
export function getPharmacySummary(): Promise<PharmacySummary> {
  if (USE_MOCKS)
    return mock((s) => {
      const pending = s.prescriptions.filter((r) => r.status === "pending_pharmacy");
      return {
        pending: pending.length,
        urgent_pending: pending.filter((r) => r.urgent).length,
        critical_pending: pending.filter((r) => hasCritical(r.checks)).length,
        changes_requested: s.prescriptions.filter((r) => r.status === "changes_requested").length,
      };
    });
  return http<PharmacySummary>("GET", "/pharmacy/summary");
}
```

(The existing `getToken` and `BASE` are module-private and already defined above, so `liveSocketUrl` can use them.)

- [ ] **Step 10: Fix the remaining exhaustive role maps**

`web/src/components/LoginForm.tsx`:

```ts
const HOME: Record<Role, string> = { doctor: "/doctor", nurse: "/nurse", admin: "/admin", patient: "/patient", pharmacist: "/pharmacist" };
```

`web/src/components/shared/NotesPanel.tsx`, in `ROLE_WORD`:

```ts
const ROLE_WORD: Record<Role, Key> = {
  nurse: "shared.roleNurse",
  doctor: "shared.roleDoctor",
  admin: "shared.roleAdmin",
  patient: "shared.rolePatient",
  pharmacist: "pharmacy.rolePharmacist",
};
```

`web/src/components/admin/StaffView.tsx`:

```ts
const ROLE_LABEL: Record<StaffRole, Key> = { doctor: "admin.roleDoctor", nurse: "admin.roleNurse", admin: "admin.roleAdmin", pharmacist: "pharmacy.rolePharmacist" };
const ROLE_COLORS: Record<StaffRole, [string, string]> = {
  doctor: ["var(--doctor-bg)", "var(--doctor-fg)"],
  nurse: ["var(--ai-bg)", "var(--news-normal-fg)"],
  admin: ["var(--segment)", "var(--text)"],
  pharmacist: ["var(--warn-bg)", "var(--warn-ink)"],
};
```

If `tsc` reports any other `Record<Role, …>`, or a `satisfies` on roles, add the `pharmacist` entry with the same pattern. Do not widen anything to `Partial`.

- [ ] **Step 11: Run the type check and the mock build**

Run: `npx tsc --noEmit`
Expected: exit 0.

Run: `NEXT_PUBLIC_USE_MOCKS=1 npm run build`
Expected: "Compiled successfully". The route list is unchanged, since there are no new pages yet.

- [ ] **Step 12: Exercise the pure rules with a throwaway Node script (nothing is committed)**

Node 22.18+/24 strips types natively, and `lib/pharmacy.ts` has only `import type` lines, so it runs as is. Run this from `web/`:

```bash
node --input-type=module-typescript - <<'EOF'
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
const r = await import(pathToFileURL(`${process.cwd()}/src/lib/pharmacy.ts`).href);
const t = (key: string, vars?: Record<string, string | number>) => `${key}|${JSON.stringify(vars ?? {})}`;
const rx = (id: string, extra = {}) => ({ id, patient_id: "p", doctor_id: "u", items: [], care_plan: "", active: false, created_at: "2026-10-05T08:00:00Z", schedule_version: 1, published_to_device: false, status: "pending_pharmacy", urgent: false, version: 1, ...extra });
const wl = (id: string, urgent: boolean, sev: string | null, since: string) => ({ prescription: rx(id), patient: {}, doctor_name: "", checks: [], urgent, waiting_since: since, max_severity: sev });

// Worklist: urgent, then severity, then oldest. "…00.500Z" is later than "…00Z" (a string sort gets this wrong).
const order = r.sortWorklist([
  wl("old-info", false, "info", "2026-10-05T07:00:00Z"),
  wl("crit-b", false, "critical", "2026-10-05T08:00:00.500Z"),
  wl("urgent-none", true, null, "2026-10-05T09:00:00Z"),
  wl("crit-a", false, "critical", "2026-10-05T08:00:00Z"),
  wl("none", false, null, "2026-10-05T06:00:00Z"),
]).map((x: { prescription: { id: string } }) => x.prescription.id);
assert.deepEqual(order, ["urgent-none", "crit-a", "crit-b", "old-info", "none"]);

// Check text: translated when complete; the server's English message when a param or the code is unknown.
const allergy = { code: "allergy", severity: "critical", item_index: 0, drug_id: "d-0003", params: { allergy: "penicillin", class: "penicillin" }, message: "EN" };
assert.match(r.checkText(allergy, t), /^pharmacy\.chkAllergy\|/);
assert.equal(r.checkText({ ...allergy, params: { allergy: "penicillin" } }, t), "EN");
assert.equal(r.checkText({ ...allergy, code: "renal_dose" }, t), "EN");

// Decisions: the tick is needed only with checks; comments are 1–500 code points.
assert.equal(r.decisionProblem({ decision: "validate", acknowledged: false, comment: "" }, false), null);
assert.equal(r.decisionProblem({ decision: "validate", acknowledged: false, comment: "" }, true), "ack_required");
assert.equal(r.decisionProblem({ decision: "reject", acknowledged: false, comment: "   " }, false), "comment_required");
assert.equal(r.decisionProblem({ decision: "request_changes", acknowledged: false, comment: "ب".repeat(500) }, false), null);
assert.equal(r.decisionProblem({ decision: "request_changes", acknowledged: false, comment: "x".repeat(501) }, false), "comment_too_long");

// Running, the pre-1.12 fallback, and the doctor's list (resubmitted v2 hides; superseded and stopped never show).
assert.equal(r.isRunning(rx("a", { urgent: true })), true);
assert.equal(r.isRunning(rx("b")), false);
assert.equal(r.isRunning({ active: true, urgent: false }), true);
const rows = r.doctorRows([
  rx("v1", { status: "validated", active: true }),
  rx("v2", { status: "changes_requested", replaces_id: "v1" }),
  rx("v3", { replaces_id: "v2" }),
  rx("old", { status: "superseded" }),
  rx("stop", { status: "stopped" }),
]).map((x: { id: string }) => x.id);
assert.deepEqual(rows, ["v3", "v1"]);
console.log("pharmacy rules: ok");
EOF
```

Expected: `pharmacy rules: ok`. If you run it before Step 5 exists, it fails with `ERR_MODULE_NOT_FOUND`; a wrong rule fails with an `AssertionError` that shows the actual value.

- [ ] **Step 13: Run a quick regression on the existing screens in mock mode**

Run `npm run dev` and open the following pages.
- `http://localhost:3000/doctor/patients/p-0001`: the prescription card still lists the running items. It now also lists the pending Amoxicillin 1 g row; the old form is unchanged until Task 5.
- `http://localhost:3000/nurse/meds`: Omar's 20:00 "Ibuprofen 400 mg" dose appears.
- `http://localhost:3000/admin/staff`: "Pharm. Salma" appears with the "Pharmacist" chip.

- [ ] **Step 14: Commit**

```bash
git add web/src/lib web/src/mocks web/src/i18n/messages web/src/components/LoginForm.tsx web/src/components/shared/NotesPanel.tsx web/src/components/admin/StaffView.tsx
git commit -m "feat(web): pharmacy data layer (types, check rules, mocks, api 1.12 client)"
```

---

## Task 2: Live frames hook and the pharmacist role shell

**Files:**
- Create:
  - `web/src/lib/live.ts`;
  - `web/src/components/pharmacist/usePharmacySummary.ts`, `SummaryStrip.tsx`, `PharmacistHome.tsx`, `Pharmacist.module.css`;
  - `web/src/app/pharmacist/layout.tsx`, `web/src/app/pharmacist/page.tsx`, `web/src/app/pharmacist/password/page.tsx`.
- Modify:
  - `web/src/components/Sidebar.tsx`, `web/src/components/Sidebar.module.css`;
  - `web/src/app/page.tsx`;
  - `web/src/i18n/messages/pharmacy.ts`.

**Interfaces:**
- Consumes: from Task 1, `liveSocketUrl()`, `getPharmacySummary()`, `publishFrame`/`subscribeFrames`, and the `WsFrame` member `prescription_status`.
- Produces:
  ```ts
  // web/src/lib/live.ts
  export const POLL_MS = 15_000;
  export function acquireSocket(): () => void;
  export function isSocketOpen(): boolean;
  export interface LiveRefreshOptions { enabled?: boolean; pollMs?: number; poll?: "fallback" | "always" }
  export function useLiveRefresh(refresh: (frame?: WsFrame) => void, types: readonly WsFrame["type"][], opts?: LiveRefreshOptions): void;
  // web/src/components/pharmacist/usePharmacySummary.ts
  export function usePharmacySummary(enabled: boolean): PharmacySummary | null;
  // web/src/components/pharmacist/SummaryStrip.tsx, PharmacistHome.tsx
  export function SummaryStrip(): JSX.Element;
  export function PharmacistHome(): JSX.Element;   // Task 3 adds <WorklistView /> to it
  // Sidebar
  export type StaffRole = "doctor" | "nurse" | "admin" | "pharmacist";
  ```
  The `NAV.pharmacist` keys are `worklist` and `password` (Task 4 adds `catalogue`; Phase B adds `dispensing` and `stock`).

- [ ] **Step 1: Add the i18n keys (`pharmacy.ts`, append to each block)**

`en`:
```ts
    navWorklist: "Worklist",
    subPharmacist: "Hospital pharmacy · all wards",
    userSub: "Pharmacy · all wards",
    worklistTitle: "Prescriptions to review",
    worklistSub: "Urgent first, then the most serious warning, then the oldest.",
    tilePending: "To review",
    tileUrgent: "Urgent, already started",
    tileCritical: "With a critical warning",
    tileChanges: "Sent back to the doctor",
    criticalWaiting: "{n} with a critical warning",
```
`fr`:
```ts
    navWorklist: "À valider",
    subPharmacist: "Pharmacie hospitalière · tous les services",
    userSub: "Pharmacie · tous les services",
    worklistTitle: "Ordonnances à valider",
    worklistSub: "Urgentes d'abord, puis l'avertissement le plus grave, puis les plus anciennes.",
    tilePending: "À valider",
    tileUrgent: "Urgentes, déjà commencées",
    tileCritical: "Avec un avertissement critique",
    tileChanges: "Renvoyées au médecin",
    criticalWaiting: "{n} avec un avertissement critique",
```
`ar`:
```ts
    navWorklist: "للمراجعة",
    subPharmacist: "صيدلية المستشفى · كل الأقسام",
    userSub: "الصيدلية · كل الأقسام",
    worklistTitle: "وصفات للمراجعة",
    worklistSub: "العاجلة أولاً، ثم الأخطر تحذيراً، ثم الأقدم.",
    tilePending: "للمراجعة",
    tileUrgent: "عاجلة بدأت بالفعل",
    tileCritical: "بتحذير حرج",
    tileChanges: "أُعيدت إلى الطبيب",
    criticalWaiting: "{n} بتحذير حرج",
```

- [ ] **Step 2: Create the live hook (`web/src/lib/live.ts`)**

```ts
"use client";

// Live frames. Real mode: one WebSocket per tab (WS /ws?token=<jwt>, api.md), opened while at least one
// screen listens and reconnecting with backoff; every frame goes to the in-tab bus (lib/frames.ts).
// Mock mode has no socket: api.ts publishes the frames the server would send.
// `useLiveRefresh` reruns a screen's load on matching frames, and polls every 15 s while no socket is open.
import { useEffect, useRef } from "react";
import { liveSocketUrl } from "./api";
import { publishFrame, subscribeFrames } from "./frames";
import type { WsFrame } from "./types";

export const POLL_MS = 15_000;
const MAX_BACKOFF_MS = 30_000;

let socket: WebSocket | null = null;
let open = false;
let users = 0;
let attempt = 0;
let retry: ReturnType<typeof setTimeout> | null = null;

function isFrame(v: unknown): v is WsFrame {
  return typeof v === "object" && v !== null && typeof (v as { type?: unknown }).type === "string" && "data" in v;
}

function connect(): void {
  if (socket || users === 0) return;
  const url = liveSocketUrl();
  if (!url) return; // mock mode or signed out: polling only
  let ws: WebSocket;
  try {
    ws = new WebSocket(url);
  } catch {
    return;
  }
  socket = ws;
  ws.onopen = () => {
    if (socket !== ws) return;
    attempt = 0;
    open = true;
  };
  ws.onmessage = (e: MessageEvent) => {
    if (socket !== ws) return;
    try {
      const frame: unknown = JSON.parse(String(e.data));
      if (isFrame(frame)) publishFrame(frame);
    } catch {
      /* not JSON (e.g. a pong): ignore */
    }
  };
  ws.onclose = (e: CloseEvent) => {
    if (socket !== ws) return; // a socket we already let go of
    socket = null;
    open = false;
    // 4401 = dead token or disabled account, 4403 = role not allowed: the next REST call handles the session.
    if (users === 0 || e.code === 4401 || e.code === 4403) return;
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** attempt);
    attempt += 1;
    retry = setTimeout(() => {
      retry = null;
      connect();
    }, delay);
  };
}

/** Keeps the shared socket open while the caller needs it; the returned function lets go (idempotent). */
export function acquireSocket(): () => void {
  users += 1;
  connect();
  let released = false;
  return () => {
    if (released) return;
    released = true;
    users -= 1;
    if (users > 0) return;
    if (retry) clearTimeout(retry);
    retry = null;
    const ws = socket;
    socket = null;
    open = false;
    ws?.close(1000);
  };
}

export const isSocketOpen = (): boolean => open;

export interface LiveRefreshOptions {
  enabled?: boolean;
  pollMs?: number;
  /** "fallback" (default): poll only while no socket is open. "always": for data no frame announces (stock). */
  poll?: "fallback" | "always";
}

/**
 * Calls `refresh(frame)` on every frame whose type is in `types`, and `refresh()` every `pollMs` while the tab
 * is visible and no socket is open (or always). The latest `refresh` is used, so it needn't be memoized.
 */
export function useLiveRefresh(
  refresh: (frame?: WsFrame) => void,
  types: readonly WsFrame["type"][],
  opts: LiveRefreshOptions = {},
): void {
  const { enabled = true, pollMs = POLL_MS, poll = "fallback" } = opts;
  const latest = useRef(refresh);
  useEffect(() => {
    latest.current = refresh;
  });
  const typesKey = types.join(",");
  useEffect(() => {
    if (!enabled) return;
    const wanted = new Set(typesKey ? typesKey.split(",") : []);
    const release = acquireSocket();
    const off = subscribeFrames((f) => {
      if (wanted.has(f.type)) latest.current(f);
    });
    const timer = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      if (poll === "always" || !isSocketOpen()) latest.current();
    }, pollMs);
    return () => {
      off();
      clearInterval(timer);
      release();
    };
  }, [enabled, pollMs, poll, typesKey]);
}
```

- [ ] **Step 3: Create the summary hook, the tiles and the home page**

`web/src/components/pharmacist/usePharmacySummary.ts`:

```ts
"use client";

// GET /pharmacy/summary for the sidebar badge and the dashboard tiles. It is refreshed on every
// prescription_status frame, or every 15 s while no socket is open. A failed refresh keeps the last value.
import { useCallback, useEffect, useState } from "react";
import { getPharmacySummary } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live";
import type { PharmacySummary } from "@/lib/types";

export function usePharmacySummary(enabled: boolean): PharmacySummary | null {
  const [summary, setSummary] = useState<PharmacySummary | null>(null);
  const load = useCallback(() => {
    getPharmacySummary().then(setSummary, () => undefined);
  }, []);
  useEffect(() => {
    if (enabled) load();
  }, [enabled, load]);
  useLiveRefresh(load, ["prescription_status"], { enabled });
  return enabled ? summary : null;
}
```

`web/src/components/pharmacist/SummaryStrip.tsx`:

```tsx
"use client";

// The pharmacist dashboard tiles (GET /pharmacy/summary). The critical tile turns red when non-zero.
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import { usePharmacySummary } from "./usePharmacySummary";
import styles from "./Pharmacist.module.css";

interface Tile {
  key: string;
  label: Key;
  n: number | undefined;
  danger?: boolean;
}

export function SummaryStrip() {
  const { t } = useT();
  const s = usePharmacySummary(true);
  const tiles: Tile[] = [
    { key: "pending", label: "pharmacy.tilePending", n: s?.pending },
    { key: "urgent", label: "pharmacy.tileUrgent", n: s?.urgent_pending },
    { key: "critical", label: "pharmacy.tileCritical", n: s?.critical_pending, danger: true },
    { key: "changes", label: "pharmacy.tileChanges", n: s?.changes_requested },
  ];
  return (
    <dl className={styles.tiles} aria-busy={!s || undefined}>
      {tiles.map((x) => (
        <div key={x.key} className={`${styles.tile} ${x.danger && (x.n ?? 0) > 0 ? styles.tileDanger : ""}`}>
          <dt className={styles.tileLabel}>{t(x.label)}</dt>
          <dd className={styles.tileNum}>{x.n ?? "–"}</dd>
        </div>
      ))}
    </dl>
  );
}

export default SummaryStrip;
```

`web/src/components/pharmacist/PharmacistHome.tsx`:

```tsx
"use client";

// Pharmacist home (/pharmacist): the title, the summary tiles and (Task 3) the worklist.
import { useT } from "@/i18n/I18nProvider";
import page from "@/components/admin/AdminPage.module.css";
import { SummaryStrip } from "./SummaryStrip";

export function PharmacistHome() {
  const { t } = useT();
  return (
    <div className={page.page}>
      <div className={page.head}>
        <div className={page.titles}>
          <h2 className={page.h2}>{t("pharmacy.worklistTitle")}</h2>
          <span className={page.sub}>{t("pharmacy.worklistSub")}</span>
        </div>
      </div>
      <SummaryStrip />
    </div>
  );
}

export default PharmacistHome;
```

`web/src/components/pharmacist/Pharmacist.module.css` (new file; later tasks append):

```css
/* Pharmacist space. Logical properties only (the app runs RTL in Arabic). */

/* ── Summary tiles (Task 2) ─────────────────────────────────────────────── */
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin: 0;
}

.tile {
  display: flex;
  flex-direction: column-reverse;
  gap: 4px;
  padding: 16px 18px;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 12px;
}

.tileDanger {
  border-color: var(--danger);
  background: var(--danger-bg);
}

.tileLabel {
  font-size: 14px;
  color: var(--muted);
}

.tileNum {
  margin: 0;
  font: 600 32px/1 var(--serif);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}

.tileDanger .tileNum {
  color: var(--danger);
}
```

- [ ] **Step 4: Add the pages**

`web/src/app/pharmacist/layout.tsx`:

```tsx
import type { ReactNode } from "react";
import { RoleShell } from "@/components/RoleShell";

export default function PharmacistLayout({ children }: { children: ReactNode }) {
  return <RoleShell role="pharmacist">{children}</RoleShell>;
}
```

`web/src/app/pharmacist/page.tsx` (Suspense, because Task 3's worklist reads `?rx=`):

```tsx
import { Suspense } from "react";
import { PharmacistHome } from "@/components/pharmacist/PharmacistHome";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("pharmacy.navWorklist")} · Ward` };
}

export default function PharmacistPage() {
  return (
    <Suspense fallback={null}>
      <PharmacistHome />
    </Suspense>
  );
}
```

`web/src/app/pharmacist/password/page.tsx`:

```tsx
import { ChangePasswordPage } from "@/components/auth/ChangePasswordPage";

export default function PasswordPage() {
  return <ChangePasswordPage />;
}
```

- [ ] **Step 5: Add the pharmacist to the sidebar (`web/src/components/Sidebar.tsx`)**

Import the hook, and widen the role:

```ts
import { usePharmacySummary } from "./pharmacist/usePharmacySummary";

export type StaffRole = "doctor" | "nurse" | "admin" | "pharmacist";
```

In `USERS`, add:

```ts
  pharmacist: { name: "Pharm. Salma", sub: "pharmacy.userSub", ini: "PS" },
```

In `ROLE_SUB`, add `pharmacist: "pharmacy.rolePharmacist",`. In `NAV`, add:

```ts
  pharmacist: [
    { key: "worklist", label: "pharmacy.navWorklist", href: "/pharmacist" },
    { key: "password", label: "auth.navPassword", href: "/pharmacist/password" },
  ],
```

In `Sidebar()`, right after `const me = useMe(role);`:

```ts
  // Pharmacist: the worklist badge comes from GET /pharmacy/summary in both modes; red when a critical item waits.
  const summary = usePharmacySummary(role === "pharmacist");
  const merged: Partial<Record<string, string | number>> = { ...(summary ? { worklist: summary.pending } : {}), ...counts };
  const critical = new Set<string>(summary && summary.critical_pending > 0 ? ["worklist"] : []);
```

Replace the count computation and the pill inside `items.map`:

```tsx
          const count = USE_MOCKS ? String(merged[n.key] ?? n.count ?? "") : String(merged[n.key] ?? "");
          const crit = critical.has(n.key);
```

```tsx
              {count && count !== "0" ? (
                <span
                  className={`${styles.count} ${crit ? styles.countCritical : n.hot ? styles.countHot : ""}`}
                  title={crit && summary ? t("pharmacy.criticalWaiting", { n: summary.critical_pending }) : undefined}
                >
                  {count}
                </span>
              ) : null}
```

Append to `web/src/components/Sidebar.module.css`:

```css
.countCritical {
  background: var(--danger);
  color: var(--paper);
}
```

- [ ] **Step 6: Add the landing card (mock-mode role picker, `web/src/app/page.tsx`)**

Insert before the patient entry in `ROLES`:

```ts
  { href: "/pharmacist", role: "pharmacy.rolePharmacist", name: "Pharm. Salma", sub: "pharmacy.subPharmacist", ini: "PS" },
```

- [ ] **Step 7: Run the type check and the mock build**

Run: `npx tsc --noEmit`, then `NEXT_PUBLIC_USE_MOCKS=1 npm run build`.
Expected: both pass. The route list now includes `/pharmacist` and `/pharmacist/password`.

- [ ] **Step 8: Check it by hand in mock mode (`npm run dev`)**

- `/`: five role cards, including "Pharmacist · Pharm. Salma".
- `/pharmacist`: the sidebar shows "Worklist" with a **red** pill reading `3` (rx-0012, rx-0013, rx-0014 are pending, and rx-0012 is critical). Hovering it shows "1 with a critical warning".
  - The tiles read: To review 3, Urgent 1, With a critical warning 1 (red), Sent back 1.
- `/pharmacist/password`: the change-password form; Log out works.
- Switch the language to العربية: the sidebar moves to the right, the tiles read right-to-left, and the numbers stay Latin.
- DevTools → Network → WS: no socket in mock mode (`liveSocketUrl()` is null).

- [ ] **Step 9: Commit**

```bash
git add web/src/lib/live.ts web/src/components/pharmacist web/src/app/pharmacist web/src/components/Sidebar.tsx web/src/components/Sidebar.module.css web/src/app/page.tsx web/src/i18n/messages/pharmacy.ts
git commit -m "feat(web): pharmacist role shell, live frames hook and worklist badge"
```

---

## Task 3: Worklist, review panel and decision dialogs

**Files:**
- Create:
  - `web/src/components/shared/CheckList.tsx`, `web/src/components/shared/RxStatusBadge.tsx`, `web/src/components/shared/Pharmacy.module.css`;
  - `web/src/components/pharmacist/WorklistView.tsx`, `ReviewPanel.tsx`, `CommentDialog.tsx`.
- Modify:
  - `web/src/components/pharmacist/PharmacistHome.tsx`, `Pharmacist.module.css`;
  - `web/src/i18n/messages/pharmacy.ts`.

**Interfaces:**
- Consumes:
  - from Task 1: `getWorklist`, `getReview`, `validatePrescription`, `requestPrescriptionChanges`, `rejectPrescription`; `sortChecks`, `checkText`, `SEVERITY_KEY`, `STATUS_KEY`, `DECISION_KEY`, `decisionProblem`, `COMMENT_MAX`; `describePharmacyError`;
  - from Task 2: `useLiveRefresh`.
- Produces (Task 5 reuses `CheckList` and `RxStatusBadge`):
  ```ts
  export function SeverityChip(props: { severity: CheckSeverity }): JSX.Element;                    // shared/CheckList.tsx
  export interface CheckListProps { checks: readonly Check[]; items: readonly PrescriptionItem[]; emptyText?: string }
  export function CheckList(props: CheckListProps): JSX.Element | null;
  export function RxStatusBadge(props: { status: PrescriptionStatus; urgent?: boolean }): JSX.Element; // shared/RxStatusBadge.tsx
  export function WorklistView(): JSX.Element;
  export interface ReviewPanelProps { id: string; onDecided: (rx: Prescription, decision: ReviewDecision) => void; onStale: () => void }
  export function ReviewPanel(props: ReviewPanelProps): JSX.Element;
  export type CommentKind = "request_changes" | "reject";
  export interface CommentDialogProps { kind: CommentKind; busy: boolean; error: string | null; onSubmit: (comment: string) => void; onClose: () => void }
  export function CommentDialog(props: CommentDialogProps): JSX.Element;
  ```

- [ ] **Step 1: Add the i18n keys (append)**

`en`:
```ts
    filterAria: "Show",
    filterPending: "To review",
    filterChanges: "Changes requested",
    filterAll: "All",
    worklistEmpty: "Nothing to review. New prescriptions appear here.",
    worklistLoadError: "Couldn’t load the worklist.",
    urgentBadge: "Urgent · started",
    bedWard: "{ward} · bed {bed}",
    byDoctor: "by {name}",
    sentAgo: "sent {ago}",
    noWarnings: "No warnings",
    chipCount: "×{n}",
    pickRow: "Pick a prescription to review it.",
    reviewLoadError: "Couldn’t load this prescription.",
    allergiesTitle: "Allergies",
    noAllergies: "No known allergies",
    patientLine: "{age} y · {sex}",
    sexF: "F",
    sexM: "M",
    weight: "{kg} kg",
    itemsTitle: "This prescription",
    versionLine: "version {n}",
    replacesLine: "Replaces: {meds}",
    itemDoseMg: "{mg} mg per intake",
    itemUnits: "{n} units per intake",
    itemDays: "{n} days",
    nonFormularyTag: "non-formulary",
    runningTitle: "Other running prescriptions",
    runningNone: "None",
    checksTitle: "Warnings",
    overrideTitle: "Doctor’s reason for sending anyway",
    historyTitle: "History",
    historyNone: "No decision yet.",
    historyLine: "{decision} by {name} · {when}",
    reviewComment: "Comment: {comment}",
    ackLabel: "I reviewed the warnings",
    validate: "Validate",
    requestChanges: "Request changes",
    reject: "Reject",
    commentLabelChanges: "What should the doctor change?",
    commentLabelReject: "Why is it rejected?",
    commentCount: "{n}/{max}",
    commentTooLong: "500 characters at most.",
    send: "Send",
    cancel: "Cancel",
    toastValidated: "Validated. The doses are scheduled.",
    toastChanges: "Sent back to {name}.",
    toastRejected: "Rejected. {name} is told.",
```
`fr`:
```ts
    filterAria: "Afficher",
    filterPending: "À valider",
    filterChanges: "Modification demandée",
    filterAll: "Toutes",
    worklistEmpty: "Rien à valider. Les nouvelles ordonnances apparaissent ici.",
    worklistLoadError: "Impossible de charger la liste.",
    urgentBadge: "Urgent · commencé",
    bedWard: "{ward} · lit {bed}",
    byDoctor: "par {name}",
    sentAgo: "envoyée {ago}",
    noWarnings: "Aucun avertissement",
    chipCount: "×{n}",
    pickRow: "Choisissez une ordonnance à examiner.",
    reviewLoadError: "Impossible de charger cette ordonnance.",
    allergiesTitle: "Allergies",
    noAllergies: "Aucune allergie connue",
    patientLine: "{age} ans · {sex}",
    sexF: "F",
    sexM: "M",
    weight: "{kg} kg",
    itemsTitle: "Cette ordonnance",
    versionLine: "version {n}",
    replacesLine: "Remplace : {meds}",
    itemDoseMg: "{mg} mg par prise",
    itemUnits: "{n} unités par prise",
    itemDays: "{n} jours",
    nonFormularyTag: "hors livret",
    runningTitle: "Autres traitements en cours",
    runningNone: "Aucun",
    checksTitle: "Avertissements",
    overrideTitle: "Justification du médecin pour l'envoyer quand même",
    historyTitle: "Historique",
    historyNone: "Aucune décision pour l'instant.",
    historyLine: "{decision} par {name} · {when}",
    reviewComment: "Commentaire : {comment}",
    ackLabel: "J'ai examiné les avertissements",
    validate: "Valider",
    requestChanges: "Demander une modification",
    reject: "Refuser",
    commentLabelChanges: "Que doit modifier le médecin ?",
    commentLabelReject: "Pourquoi la refuser ?",
    commentCount: "{n}/{max}",
    commentTooLong: "500 caractères au maximum.",
    send: "Envoyer",
    cancel: "Annuler",
    toastValidated: "Validée. Les prises sont planifiées.",
    toastChanges: "Renvoyée à {name}.",
    toastRejected: "Refusée. {name} est prévenu(e).",
```
`ar`:
```ts
    filterAria: "عرض",
    filterPending: "للمراجعة",
    filterChanges: "طُلب تعديلها",
    filterAll: "الكل",
    worklistEmpty: "لا شيء للمراجعة. تظهر الوصفات الجديدة هنا.",
    worklistLoadError: "تعذّر تحميل القائمة.",
    urgentBadge: "عاجل · بدأ",
    bedWard: "{ward} · سرير {bed}",
    byDoctor: "من {name}",
    sentAgo: "أُرسلت {ago}",
    noWarnings: "لا تحذيرات",
    chipCount: "×{n}",
    pickRow: "اختر وصفة لمراجعتها.",
    reviewLoadError: "تعذّر تحميل هذه الوصفة.",
    allergiesTitle: "الحساسية",
    noAllergies: "لا حساسية معروفة",
    patientLine: "{age} سنة · {sex}",
    sexF: "أنثى",
    sexM: "ذكر",
    weight: "{kg} كغ",
    itemsTitle: "هذه الوصفة",
    versionLine: "النسخة {n}",
    replacesLine: "تحل محل: {meds}",
    itemDoseMg: "{mg} ملغ في كل جرعة",
    itemUnits: "{n} وحدات في كل جرعة",
    itemDays: "{n} أيام",
    nonFormularyTag: "خارج الدليل",
    runningTitle: "علاجات أخرى جارية",
    runningNone: "لا شيء",
    checksTitle: "التحذيرات",
    overrideTitle: "مبرر الطبيب للإرسال رغم التحذير",
    historyTitle: "السجل",
    historyNone: "لا قرار بعد.",
    historyLine: "{decision} من {name} · {when}",
    reviewComment: "تعليق: {comment}",
    ackLabel: "راجعتُ التحذيرات",
    validate: "اعتماد",
    requestChanges: "طلب تعديل",
    reject: "رفض",
    commentLabelChanges: "ما الذي يجب على الطبيب تعديله؟",
    commentLabelReject: "لماذا تُرفض؟",
    commentCount: "{n}/{max}",
    commentTooLong: "500 حرف كحد أقصى.",
    send: "إرسال",
    cancel: "إلغاء",
    toastValidated: "تم الاعتماد. جُدولت الجرعات.",
    toastChanges: "أُعيدت إلى {name}.",
    toastRejected: "رُفضت. تم إبلاغ {name}.",
```

- [ ] **Step 2: Create the shared styles (`web/src/components/shared/Pharmacy.module.css`)**

```css
/* Severity chips, prescription status pills and the check list (pharmacist review + doctor form). */
.sev,
.status {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 999px;
  font: 600 12px/1.2 var(--sans);
  white-space: nowrap;
}

.sevCritical { background: var(--news-crit-edge); color: var(--paper); }
.sevMajor { background: var(--news-high-bg); color: var(--news-high-fg); }
.sevModerate { background: var(--news-low-bg); color: var(--news-low-fg); }
.sevInfo { background: var(--ai-bg); color: var(--ai); }

.stPending { background: var(--warn-bg); color: var(--warn-ink); border: 1px solid var(--warn-line); }
.stUrgent { background: var(--danger); color: var(--paper); }
.stValidated { background: var(--news-normal-bg); color: var(--news-normal-fg); }
.stChanges { background: var(--news-high-bg); color: var(--news-high-fg); }
.stRejected { background: var(--news-crit-bg); color: var(--news-crit-fg); }
.stClosed { background: var(--chip); color: var(--muted); }

.checks {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.check {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--paper);
  font-size: 15px;
  line-height: 1.4;
  color: var(--text);
}

.checkCritical {
  border-color: var(--danger-line);
  border-inline-start: 4px solid var(--danger);
  background: var(--danger-bg);
  color: var(--danger-ink);
}

.checkBody {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.checkItem {
  font-size: 13px;
  color: var(--muted);
}

.noChecks {
  margin: 0;
  font-size: 15px;
  color: var(--news-normal-fg);
}
```

- [ ] **Step 3: Create `CheckList` and `RxStatusBadge`**

`web/src/components/shared/CheckList.tsx`:

```tsx
"use client";

// The check engine's findings: severity chip, plain-language text, and the item each one concerns.
// Shared by the pharmacist review panel and the doctor's live check panel (the same warnings, spec §2).
import { useT } from "@/i18n/I18nProvider";
import { checkText, SEVERITY_KEY, sortChecks } from "@/lib/pharmacy";
import type { Check, CheckSeverity, PrescriptionItem } from "@/lib/types";
import styles from "./Pharmacy.module.css";

const SEV_CLASS: Record<CheckSeverity, string> = {
  critical: styles.sevCritical,
  major: styles.sevMajor,
  moderate: styles.sevModerate,
  info: styles.sevInfo,
};

export function SeverityChip({ severity }: { severity: CheckSeverity }) {
  const { t } = useT();
  return <span className={`${styles.sev} ${SEV_CLASS[severity] ?? styles.sevInfo}`}>{t(SEVERITY_KEY[severity] ?? "pharmacy.sevInfo")}</span>;
}

export interface CheckListProps {
  checks: readonly Check[];
  /** The prescription's items, to name the item each check concerns. */
  items: readonly PrescriptionItem[];
  /** Shown when there is no check; omit to render nothing. */
  emptyText?: string;
}

export function CheckList({ checks, items, emptyText }: CheckListProps) {
  const { t } = useT();
  if (!checks.length) return emptyText ? <p className={styles.noChecks}>{emptyText}</p> : null;
  return (
    <ul className={styles.checks}>
      {sortChecks(checks).map((c, i) => {
        const item = c.item_index != null ? items[c.item_index] : undefined;
        return (
          <li key={`${c.code}-${c.item_index ?? "x"}-${i}`} className={`${styles.check} ${c.severity === "critical" ? styles.checkCritical : ""}`}>
            <SeverityChip severity={c.severity} />
            <span className={styles.checkBody}>
              <span dir="auto">{checkText(c, t)}</span>
              {item ? (
                <span dir="auto" className={styles.checkItem}>
                  {t("pharmacy.checkItem", { n: (c.item_index ?? 0) + 1, med: item.med })}
                </span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export default CheckList;
```

`web/src/components/shared/RxStatusBadge.tsx`:

```tsx
"use client";

// A prescription's pharmacy status as a coloured pill (doctor list, pharmacist panel).
import { useT } from "@/i18n/I18nProvider";
import { STATUS_KEY } from "@/lib/pharmacy";
import type { PrescriptionStatus } from "@/lib/types";
import styles from "./Pharmacy.module.css";

const TONE: Record<PrescriptionStatus, string> = {
  pending_pharmacy: styles.stPending,
  validated: styles.stValidated,
  changes_requested: styles.stChanges,
  rejected: styles.stRejected,
  stopped: styles.stClosed,
  superseded: styles.stClosed,
};

export function RxStatusBadge({ status, urgent = false }: { status: PrescriptionStatus; urgent?: boolean }) {
  const { t } = useT();
  const pendingUrgent = status === "pending_pharmacy" && urgent;
  return (
    <span className={`${styles.status} ${pendingUrgent ? styles.stUrgent : (TONE[status] ?? styles.stClosed)}`}>
      {t(pendingUrgent ? "pharmacy.statusPendingUrgent" : (STATUS_KEY[status] ?? "pharmacy.statusPending"))}
    </span>
  );
}

export default RxStatusBadge;
```

- [ ] **Step 4: Create the comment dialog (`web/src/components/pharmacist/CommentDialog.tsx`)**

```tsx
"use client";

// Comment dialog for "Request changes" and "Reject": the comment is required (1–500 characters).
// It opens with the text box focused; Escape or Cancel closes it; Send stays disabled until the comment is valid.
// Steps: open (1), type, Send (2): within the spec's 3-step limit.
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import page from "@/components/admin/AdminPage.module.css";
import { COMMENT_MAX, decisionProblem } from "@/lib/pharmacy";
import styles from "./Pharmacist.module.css";

export type CommentKind = "request_changes" | "reject";

export interface CommentDialogProps {
  kind: CommentKind;
  busy: boolean;
  /** A failed send (already localized). */
  error: string | null;
  onSubmit: (comment: string) => void;
  onClose: () => void;
}

export function CommentDialog({ kind, busy, error, onSubmit, onClose }: CommentDialogProps) {
  const { t } = useT();
  const [comment, setComment] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  const close = useRef(onClose);
  const id = useId();
  const problem = decisionProblem({ decision: kind, acknowledged: false, comment }, false);
  const length = [...comment.trim()].length;

  useEffect(() => {
    close.current = onClose;
  });
  useEffect(() => {
    box.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (problem || busy) return;
    onSubmit(comment.trim());
  }

  return (
    <div className={styles.overlay}>
      <form role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} className={styles.dialog} onSubmit={submit}>
        <h2 id={`${id}-title`} className={styles.dialogTitle}>
          {t(kind === "reject" ? "pharmacy.reject" : "pharmacy.requestChanges")}
        </h2>
        <label className={page.field}>
          <span className={page.fieldLabel}>{t(kind === "reject" ? "pharmacy.commentLabelReject" : "pharmacy.commentLabelChanges")}</span>
          <textarea
            ref={box}
            dir="auto"
            rows={4}
            maxLength={COMMENT_MAX}
            className={styles.textarea}
            value={comment}
            aria-describedby={`${id}-count`}
            onChange={(e) => setComment(e.target.value)}
          />
        </label>
        <span id={`${id}-count`} className={styles.count}>
          {t("pharmacy.commentCount", { n: length, max: COMMENT_MAX })}
        </span>
        {problem === "comment_too_long" ? (
          <span role="alert" className={styles.error}>
            {t("pharmacy.commentTooLong")}
          </span>
        ) : null}
        {error ? (
          <span role="alert" className={styles.error}>
            {error}
          </span>
        ) : null}
        <div className={styles.dialogActions}>
          <button type="button" className={page.btn} disabled={busy} onClick={onClose}>
            {t("pharmacy.cancel")}
          </button>
          <button type="submit" className={`${page.btnPrimary} ${kind === "reject" ? styles.dangerPrimary : ""}`} disabled={busy || problem !== null}>
            {t("pharmacy.send")}
          </button>
        </div>
      </form>
    </div>
  );
}

export default CommentDialog;
```

- [ ] **Step 5: Create the review panel (`web/src/components/pharmacist/ReviewPanel.tsx`)**

```tsx
"use client";

// One prescription under review, using only the minimal patient projection (spec §2: never notes, exams
// or vitals). Allergies come first, then the items, the checks (recomputed now), the doctor's override
// reason, the patient's other running prescriptions, and the history.
// Validate is 1 click with no checks, or tick + click with checks. Request changes and Reject go through
// CommentDialog (open, type, Send).
import { useCallback, useEffect, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import page from "@/components/admin/AdminPage.module.css";
import { CheckList } from "@/components/shared/CheckList";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { RxStatusBadge } from "@/components/shared/RxStatusBadge";
import { fmtWhen } from "@/lib/accountsUi";
import { ApiError, getReview, rejectPrescription, requestPrescriptionChanges, validatePrescription } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live";
import { DECISION_KEY, decisionProblem } from "@/lib/pharmacy";
import { describePharmacyError } from "@/lib/pharmacyUi";
import type { Prescription, PrescriptionItem, ReviewDecision, ReviewDetail } from "@/lib/types";
import { CommentDialog, type CommentKind } from "./CommentDialog";
import styles from "./Pharmacist.module.css";

export interface ReviewPanelProps {
  id: string;
  /** After a successful decision, with the updated prescription. */
  onDecided: (rx: Prescription, decision: ReviewDecision) => void;
  /** Someone else decided first (409 `bad_status`): the list should reload. */
  onStale: () => void;
}

function ItemLine({ item }: { item: PrescriptionItem }) {
  const { t } = useT();
  const units = item.units_per_intake ?? 1;
  const parts = [
    item.dose_mg != null ? t("pharmacy.itemDoseMg", { mg: item.dose_mg }) : null,
    units !== 1 ? t("pharmacy.itemUnits", { n: units }) : null,
    item.times.join(" · "),
    t("pharmacy.itemDays", { n: item.days }),
  ].filter((x): x is string => !!x);
  return (
    <div className={styles.item}>
      <span dir="auto" className={styles.itemMed}>
        {item.med}
        {item.drug_id ? null : <span className={styles.nf}> · {t("pharmacy.nonFormularyTag")}</span>}
      </span>
      <span className={styles.itemMeta}>{parts.join(" · ")}</span>
    </div>
  );
}

export function ReviewPanel({ id, onDecided, onStale }: ReviewPanelProps) {
  const { t, lang } = useT();
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [ack, setAck] = useState(false);
  const [dialog, setDialog] = useState<CommentKind | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getReview(id).then(
      (d) => {
        setDetail(d);
        setFailed(false);
      },
      () => setFailed(true),
    );
  }, [id]);
  useEffect(load, [load]);
  useLiveRefresh(load, ["prescription_status"]);

  async function run(decision: ReviewDecision, call: () => Promise<Prescription>) {
    if (busy) return; // a double click sends one request
    setBusy(true);
    setError(null);
    try {
      const rx = await call();
      setDialog(null);
      onDecided(rx, decision);
    } catch (err) {
      setError(t(describePharmacyError(err)));
      if (err instanceof ApiError && err.code === "ack_required") setAck(false); // the warnings changed: tick again
      if (err instanceof ApiError && (err.code === "bad_status" || err.code === "ack_required")) {
        setDialog(null);
        load();
        if (err.code === "bad_status") onStale();
      }
    } finally {
      setBusy(false);
    }
  }

  if (failed && !detail) return <ErrorCard title={t("pharmacy.reviewLoadError")} onRetry={load} secondaryLabel={null} />;
  if (!detail) return <div className="ward-skeleton" style={{ height: 360 }} aria-busy="true" />;

  const { prescription: rx, patient, checks } = detail;
  const hasChecks = checks.length > 0;
  const pending = rx.status === "pending_pharmacy";
  const blocked = decisionProblem({ decision: "validate", acknowledged: ack, comment: "" }, hasChecks) !== null;
  const where = patient.ward && patient.bed ? t("pharmacy.bedWard", { ward: patient.ward, bed: patient.bed }) : (patient.ward ?? patient.bed);
  const meta = [
    t("pharmacy.patientLine", { age: patient.age, sex: t(patient.sex === "F" ? "pharmacy.sexF" : "pharmacy.sexM") }),
    patient.weight_kg != null ? t("pharmacy.weight", { kg: patient.weight_kg }) : null,
    where,
    t("pharmacy.byDoctor", { name: detail.doctor_name }),
  ].filter((x): x is string => !!x);

  return (
    <article className={styles.panel} aria-labelledby={`rv-${rx.id}`}>
      <header className={styles.panelHead}>
        <h2 id={`rv-${rx.id}`} dir="auto" className={styles.panelName}>
          {patient.name}
        </h2>
        <RxStatusBadge status={rx.status} urgent={rx.urgent} />
        <span className={styles.panelMeta}>{meta.join(" · ")}</span>
      </header>

      <div className={`${styles.allergy} ${patient.allergies.length ? styles.allergyOn : ""}`}>
        <span className={styles.allergyLabel}>{t("pharmacy.allergiesTitle")}</span>
        <span dir="auto" className={styles.allergyList}>
          {patient.allergies.length ? patient.allergies.join(", ") : t("pharmacy.noAllergies")}
        </span>
      </div>

      <section className={styles.block}>
        <h3 className={styles.blockTitle}>
          {t("pharmacy.itemsTitle")}
          {rx.version > 1 ? <span className={styles.blockSub}> · {t("pharmacy.versionLine", { n: rx.version })}</span> : null}
        </h3>
        {rx.items.map((it, i) => (
          <ItemLine key={i} item={it} />
        ))}
        {rx.care_plan ? (
          <p dir="auto" className={styles.muted}>
            {rx.care_plan}
          </p>
        ) : null}
        {detail.replaces ? (
          <p dir="auto" className={styles.muted}>
            {t("pharmacy.replacesLine", { meds: detail.replaces.items.map((i) => i.med).join(", ") })}
          </p>
        ) : null}
      </section>

      <section className={styles.block}>
        <h3 className={styles.blockTitle}>{t("pharmacy.checksTitle")}</h3>
        <CheckList checks={checks} items={rx.items} emptyText={t("pharmacy.noWarnings")} />
        {rx.override_reason ? (
          <div className={styles.override}>
            <span className={styles.overrideLabel}>{t("pharmacy.overrideTitle")}</span>
            <span dir="auto">{rx.override_reason}</span>
          </div>
        ) : null}
      </section>

      <section className={styles.block}>
        <h3 className={styles.blockTitle}>{t("pharmacy.runningTitle")}</h3>
        {detail.running.length === 0 ? (
          <p className={styles.muted}>{t("pharmacy.runningNone")}</p>
        ) : (
          detail.running.flatMap((r) => r.items.map((it, i) => <ItemLine key={`${r.id}-${i}`} item={it} />))
        )}
      </section>

      <section className={styles.block}>
        <h3 className={styles.blockTitle}>{t("pharmacy.historyTitle")}</h3>
        {detail.history.length === 0 ? (
          <p className={styles.muted}>{t("pharmacy.historyNone")}</p>
        ) : (
          <ul className={styles.history}>
            {detail.history.map((h) => (
              <li key={h.id}>
                <span>
                  {t("pharmacy.historyLine", {
                    decision: t(DECISION_KEY[h.decision]),
                    name: h.pharmacist_name ?? h.pharmacist_id,
                    when: fmtWhen(h.created_at, lang),
                  })}
                </span>
                {h.comment ? (
                  <span dir="auto" className={styles.muted}>
                    {h.comment}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {pending ? (
        <footer className={styles.actions}>
          {hasChecks ? (
            <label className={styles.ack}>
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              {t("pharmacy.ackLabel")}
            </label>
          ) : null}
          {error && !dialog ? (
            <span role="alert" className={styles.error}>
              {error}
            </span>
          ) : null}
          <div className={styles.actionRow}>
            <button
              type="button"
              className={page.btnPrimary}
              disabled={busy || blocked}
              onClick={() => void run("validated", () => validatePrescription(rx.id, { acknowledged: ack }))}
            >
              {t("pharmacy.validate")}
            </button>
            <button type="button" className={page.btn} disabled={busy} onClick={() => setDialog("request_changes")}>
              {t("pharmacy.requestChanges")}
            </button>
            <button type="button" className={`${page.btn} ${styles.danger}`} disabled={busy} onClick={() => setDialog("reject")}>
              {t("pharmacy.reject")}
            </button>
          </div>
        </footer>
      ) : rx.review_comment ? (
        <p dir="auto" className={styles.muted}>
          {t("pharmacy.reviewComment", { comment: rx.review_comment })}
        </p>
      ) : null}

      {dialog ? (
        <CommentDialog
          kind={dialog}
          busy={busy}
          error={error}
          onClose={() => {
            setDialog(null);
            setError(null);
          }}
          onSubmit={(comment) =>
            void run(dialog === "reject" ? "rejected" : "changes_requested", () =>
              dialog === "reject" ? rejectPrescription(rx.id, comment) : requestPrescriptionChanges(rx.id, comment),
            )
          }
        />
      ) : null}
    </article>
  );
}

export default ReviewPanel;
```

- [ ] **Step 6: Create the worklist (`web/src/components/pharmacist/WorklistView.tsx`)**

```tsx
"use client";

// Pharmacist / Worklist (/pharmacist): the list (urgent, then severity, then oldest) and the review panel
// of the selected row (?rx=). Refreshes on every prescription_status frame, or every 15 s without a socket.
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import { SeverityChip } from "@/components/shared/CheckList";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { Toast, useToast } from "@/components/Toast";
import { getWorklist } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live";
import { ago, now } from "@/lib/time";
import type { CheckSeverity, Prescription, ReviewDecision, WorklistItem, WorklistStatus } from "@/lib/types";
import { ReviewPanel } from "./ReviewPanel";
import styles from "./Pharmacist.module.css";

const FILTERS: [WorklistStatus, Key][] = [
  ["pending_pharmacy", "pharmacy.filterPending"],
  ["changes_requested", "pharmacy.filterChanges"],
  ["all", "pharmacy.filterAll"],
];
const SEVERITIES: CheckSeverity[] = ["critical", "major", "moderate", "info"];
const TOAST: Record<ReviewDecision, Key> = {
  validated: "pharmacy.toastValidated",
  changes_requested: "pharmacy.toastChanges",
  rejected: "pharmacy.toastRejected",
};

/** [severity, count] for the row chips, most severe first. */
function chipsOf(it: WorklistItem): [CheckSeverity, number][] {
  return SEVERITIES.map((s): [CheckSeverity, number] => [s, it.checks.filter((c) => c.severity === s).length]).filter(([, n]) => n > 0);
}

export function WorklistView() {
  const { t, lang } = useT();
  const router = useRouter();
  const pathname = usePathname();
  const selected = useSearchParams().get("rx");
  const [filter, setFilter] = useState<WorklistStatus>("pending_pharmacy");
  const [items, setItems] = useState<WorklistItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [toast, showToast] = useToast<string>(4500);

  const load = useCallback(() => {
    getWorklist(filter).then(
      (list) => {
        setItems(list);
        setFailed(false);
      },
      () => setFailed(true), // a failed refresh keeps the rows on screen
    );
  }, [filter]);
  useEffect(() => {
    setItems(null);
    load();
  }, [load]);
  useLiveRefresh(load, ["prescription_status"]);

  const select = useCallback(
    (id: string | null) => router.replace(id ? `${pathname}?rx=${encodeURIComponent(id)}` : pathname, { scroll: false }),
    [router, pathname],
  );

  // After a decision, open the next row, so a run of reviews stays at 3 steps or fewer each.
  const onDecided = useCallback(
    (rx: Prescription, decision: ReviewDecision) => {
      const list = items ?? [];
      const i = list.findIndex((x) => x.prescription.id === rx.id);
      const next = i >= 0 ? (list[i + 1] ?? list[i - 1] ?? null) : null;
      showToast(t(TOAST[decision], { name: i >= 0 ? list[i].doctor_name : "" }));
      select(next ? next.prescription.id : null);
      load();
    },
    [items, load, select, showToast, t],
  );

  const ref = now();
  return (
    <div className={styles.split}>
      <section className={styles.listCol} aria-label={t("pharmacy.worklistTitle")}>
        <div className={styles.segment} role="group" aria-label={t("pharmacy.filterAria")}>
          {FILTERS.map(([k, label]) => (
            <button
              key={k}
              type="button"
              aria-pressed={filter === k}
              className={`${styles.segBtn} ${filter === k ? styles.segOn : ""}`}
              onClick={() => setFilter(k)}
            >
              {t(label)}
            </button>
          ))}
        </div>
        {failed && !items ? (
          <ErrorCard title={t("pharmacy.worklistLoadError")} onRetry={load} secondaryLabel={null} />
        ) : !items ? (
          <div className="ward-skeleton" style={{ height: 180 }} aria-busy="true" />
        ) : items.length === 0 ? (
          <p className={styles.empty}>{t("pharmacy.worklistEmpty")}</p>
        ) : (
          <ul className={styles.rows}>
            {items.map((it) => {
              const on = it.prescription.id === selected;
              const chips = chipsOf(it);
              const where = it.patient.ward && it.patient.bed ? t("pharmacy.bedWard", { ward: it.patient.ward, bed: it.patient.bed }) : (it.patient.ward ?? it.patient.bed);
              const meta = [where, t("pharmacy.byDoctor", { name: it.doctor_name }), t("pharmacy.sentAgo", { ago: ago(it.waiting_since, ref, lang) })].filter(
                (x): x is string => !!x,
              );
              return (
                <li key={it.prescription.id}>
                  <button
                    type="button"
                    aria-current={on ? "true" : undefined}
                    className={`${styles.row} ${on ? styles.rowOn : ""} ${it.max_severity === "critical" ? styles.rowCrit : ""}`}
                    onClick={() => select(it.prescription.id)}
                  >
                    <span className={styles.rowTop}>
                      <span dir="auto" className={styles.rowName}>
                        {it.patient.name}
                      </span>
                      {it.urgent ? <span className={styles.urgent}>{t("pharmacy.urgentBadge")}</span> : null}
                    </span>
                    <span className={styles.rowMeta}>{meta.join(" · ")}</span>
                    <span className={styles.rowChips}>
                      {chips.length ? (
                        chips.map(([s, n]) => (
                          <span key={s} className={styles.chipWrap}>
                            <SeverityChip severity={s} />
                            {n > 1 ? <span className={styles.chipN}>{t("pharmacy.chipCount", { n })}</span> : null}
                          </span>
                        ))
                      ) : (
                        <span className={styles.noWarn}>{t("pharmacy.noWarnings")}</span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
      <section className={styles.panelCol}>
        {selected ? (
          <ReviewPanel key={selected} id={selected} onDecided={onDecided} onStale={load} />
        ) : (
          <p className={styles.pick}>{t("pharmacy.pickRow")}</p>
        )}
      </section>
      {toast ? <Toast>{toast}</Toast> : null}
    </div>
  );
}

export default WorklistView;
```

`PharmacistHome.tsx`: import `WorklistView` from `./WorklistView`, and render `<WorklistView />` right after `<SummaryStrip />`.

- [ ] **Step 7: Append the worklist styles to `Pharmacist.module.css`**

```css
/* ── Worklist and review (Task 3) ───────────────────────────────────────── */
.split {
  display: grid;
  grid-template-columns: minmax(300px, 420px) minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

@media (max-width: 1100px) {
  .split {
    grid-template-columns: 1fr;
  }
}

.listCol { display: flex; flex-direction: column; gap: 12px; }
.panelCol { min-width: 0; }

.segment { display: flex; padding: 4px; gap: 4px; background: var(--segment); border-radius: 10px; }
.segBtn { flex: 1; min-height: 40px; padding: 0 12px; border: none; border-radius: 7px; background: transparent; color: var(--text); font: 600 14px/1 var(--sans); cursor: pointer; }
.segOn { background: var(--paper); color: var(--ink); box-shadow: var(--shadow-segment); }

.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }

.row {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  text-align: start;
  font: inherit;
  color: var(--text);
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 12px;
  cursor: pointer;
}

.row:hover { border-color: var(--line-strong); }
.rowOn { border-color: var(--teal); box-shadow: 0 0 0 2px var(--teal-tint); }
.rowCrit { border-inline-start: 5px solid var(--danger); }
.rowTop { display: flex; align-items: center; gap: 10px; }
.rowName { flex: 1; font-size: 17px; font-weight: 600; color: var(--ink); }
.rowMeta { font-size: 14px; color: var(--muted); }
.rowChips { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.chipWrap { display: inline-flex; align-items: center; gap: 3px; }
.chipN { font-size: 12px; font-weight: 600; color: var(--muted); }
.noWarn { font-size: 13px; color: var(--news-normal-fg); }
.urgent { padding: 3px 8px; border-radius: 999px; background: var(--danger); color: var(--paper); font: 600 12px/1.2 var(--sans); white-space: nowrap; }

.empty,
.pick {
  margin: 0;
  padding: 32px;
  text-align: center;
  font-size: 16px;
  color: var(--muted);
  background: var(--paper);
  border: 1px dashed var(--line-strong);
  border-radius: 12px;
}

.panel { display: flex; flex-direction: column; gap: 18px; padding: 24px; background: var(--paper); border: 1px solid var(--line); border-radius: 14px; }
.panelHead { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
.panelName { margin: 0; font: 600 28px/1.15 var(--serif); color: var(--ink); }
.panelMeta { flex: 1 1 100%; font-size: 15px; color: var(--muted); }

.allergy { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 12px; padding: 12px 14px; border-radius: 10px; background: var(--chip); color: var(--text); }
.allergyOn { background: var(--danger-bg); border: 2px solid var(--danger); color: var(--danger-ink); }
.allergyLabel { font: 600 13px/1.2 var(--sans); letter-spacing: 0.06em; text-transform: uppercase; }
.allergyList { font-size: 18px; font-weight: 700; }

.block { display: flex; flex-direction: column; gap: 8px; }
.blockTitle { margin: 0; font: 600 13px/1.2 var(--sans); letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
.blockSub { font-weight: 500; letter-spacing: 0; text-transform: none; }
.item { display: flex; flex-direction: column; gap: 2px; padding: 8px 0; border-bottom: 1px solid var(--line-soft); }
.itemMed { font-size: 16px; font-weight: 600; color: var(--ink); }
.itemMeta { font-size: 14px; color: var(--text); font-variant-numeric: tabular-nums; }
.nf { font-size: 12px; font-weight: 600; color: var(--warn-ink); }
.muted { margin: 0; font-size: 14px; color: var(--muted); }
.override { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border-radius: 10px; background: var(--warn-bg); border: 1px solid var(--warn-line); color: var(--warn-ink); font-size: 15px; }
.overrideLabel { font-size: 13px; font-weight: 700; }
.history { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: 14px; }
.history li { display: flex; flex-direction: column; gap: 2px; }

.actions { position: sticky; bottom: 0; display: flex; flex-direction: column; gap: 10px; padding-top: 14px; border-top: 1px solid var(--line); background: var(--paper); }
.ack { display: flex; align-items: center; gap: 10px; font-size: 16px; font-weight: 600; color: var(--ink); cursor: pointer; }
.ack input { width: 22px; height: 22px; }
.actionRow { display: flex; flex-wrap: wrap; gap: 10px; }
.danger { color: var(--danger-ink); border-color: var(--danger-line); }
.dialog .dangerPrimary { background: var(--danger); }
.dialog .dangerPrimary:hover { background: var(--danger-ink); }
.error { font-size: 14px; color: var(--danger-ink); }

.overlay { position: fixed; inset: 0; z-index: 50; display: grid; place-items: center; padding: 24px; background: rgba(15, 45, 68, 0.55); }
.dialog { width: min(520px, 100%); display: flex; flex-direction: column; gap: 14px; padding: 26px; background: var(--paper); border-radius: 14px; box-shadow: var(--shadow-frame); }
.dialogTitle { margin: 0; font: 600 22px/1.2 var(--serif); color: var(--ink); }
.textarea { width: 100%; padding: 12px 14px; border: 1px solid var(--line-strong); border-radius: 8px; font: 400 16px/1.4 var(--sans); color: var(--ink); background: var(--paper); resize: vertical; }
.count { align-self: flex-end; font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums; }
.dialogActions { display: flex; justify-content: flex-end; gap: 10px; }
```

- [ ] **Step 8: Run the type check and the mock build**

Run: `npx tsc --noEmit`, then `NEXT_PUBLIC_USE_MOCKS=1 npm run build`.
Expected: both pass.

- [ ] **Step 9: Run the mock-mode scenarios (`npm run dev`, `/pharmacist`)**

1. **Order.** The rows are rx-0013 Omar Jaziri (urgent badge; Major ×1, Moderate ×1), then rx-0012 Amira Ben Salah (red inline-start edge; Critical, Major), then rx-0014 Hédi Mansour ("No warnings").
2. **1-click Validate.** Open Hédi. Validate is enabled with no tick box. Click it:
   - the toast reads "Validated. The doses are scheduled.";
   - the panel moves to the next row;
   - the sidebar pill drops to `2` within the same second (mock frame).
3. **Tick + Validate.** Open Amira:
   - the allergy box is red, reading "penicillin";
   - the warnings read "Allergy: the patient is allergic to penicillin (penicillin)." and "Duplicate therapy with Amoxicillin 1g.";
   - the doctor's reason is shown;
   - the running list shows Paracetamol, Amoxicillin, Warfarin and Aspirin;
   - Validate is disabled until "I reviewed the warnings" is ticked.
4. **Request changes.** Still on Amira, open Request changes:
   - the text box has focus and Send is disabled;
   - type `allergie pénicilline → azithromycine` and Send;
   - the toast reads "Sent back to Dr Trabelsi.";
   - the "Changes requested" filter now lists her, and her history shows "Changes requested by Pharm. Salma · Today 09:12".
5. **Reject an urgent one.** Open Omar, then Reject and type a reason. Afterwards `/nurse/meds` no longer shows his 20:00 Ibuprofen dose (spec §2: urgent then rejected deletes the future doses). The mock store lives in the tab, so use the in-app links rather than a reload.
6. **Double click.** Reload (F5) to reset the store. Open Hédi and double-click Validate fast. Expected: one toast, no "Someone already decided" error.
7. **Escape.** Escape closes the comment dialog and keeps the panel.
8. **Unknown check code (Review Focus 5).** Temporarily change the `code: "allergy"` literal in `mockChecks` (`web/src/mocks/pharmacy.ts`) to `"renal_dose"`. Reload Amira's row: the English `message` "Allergy: penicillin (penicillin)" shows, the chip is still red, and nothing crashes. **Revert the edit.**
9. **Real mode (only if the backend branch is running):** two browsers signed in as two pharmacists, both on the same row.
   - Validate in A, then in B. B shows "Someone already decided on this prescription. The list was refreshed." and the row leaves B's list.

- [ ] **Step 10: Commit**

```bash
git add web/src/components/shared/CheckList.tsx web/src/components/shared/RxStatusBadge.tsx web/src/components/shared/Pharmacy.module.css web/src/components/pharmacist web/src/i18n/messages/pharmacy.ts
git commit -m "feat(web): pharmacist worklist, review panel and decision dialogs"
```

---

## Task 4: Drug catalogue (pharmacist and admin)

**Files:**
- Create:
  - `web/src/lib/useDebounced.ts`;
  - `web/src/components/pharmacist/TagInput.tsx`, `DrugForm.tsx`, `CatalogueView.tsx`;
  - `web/src/app/pharmacist/catalogue/page.tsx`, `web/src/app/admin/catalogue/page.tsx`.
- Modify:
  - `web/src/lib/pharmacy.ts` (`DRUG_FORMS`, `FORM_KEY`);
  - `web/src/components/Sidebar.tsx` (nav entries);
  - `web/src/components/pharmacist/Pharmacist.module.css`;
  - `web/src/i18n/messages/pharmacy.ts`.

**Interfaces:**
- Consumes: `listDrugs`, `createDrug`, `updateDrug` and `drugLabel` (Task 1), and `describePharmacyError`.
- Produces:
  ```ts
  export function useDebounced<T>(value: T, ms: number): T;                         // lib/useDebounced.ts (Task 5 reuses)
  export const DRUG_FORMS: DrugForm[];                                               // lib/pharmacy.ts
  export const FORM_KEY: Record<DrugForm, Key>;                                      // lib/pharmacy.ts (Task 5 reuses)
  export interface TagInputProps { label: string; values: string[]; onChange: (v: string[]) => void; normalize?: (raw: string) => string }
  export function TagInput(props: TagInputProps): JSX.Element;
  export const codeTag: (raw: string) => string;                                     // "Beta Lactam" → "beta_lactam"
  export interface DrugFormProps { drug: Drug | null; onSaved: (drug: Drug) => void; onClose: () => void }
  export function DrugForm(props: DrugFormProps): JSX.Element;
  export function CatalogueView(): JSX.Element;
  ```

- [ ] **Step 1: Add the i18n keys (append)**

`en`:
```ts
    navCatalogue: "Drug catalogue",
    catalogueTitle: "Drug catalogue",
    catalogueSub: "The hospital formulary. Illustrative data, not a clinical reference; to be validated by the hospital’s pharmacists.",
    searchLabel: "Search by name, brand or ATC code",
    showInactive: "Show inactive drugs",
    addDrug: "Add a drug",
    editDrug: "Edit drug",
    edit: "Edit",
    colDci: "Generic name",
    colForm: "Form · strength",
    colAtc: "ATC",
    colMaxDaily: "Max / day",
    colTags: "Allergy classes · interaction groups",
    colStatus: "Status",
    noMaxDaily: "No limit set",
    highAlert: "High alert",
    active: "Active",
    inactive: "Inactive",
    catalogueEmpty: "No drug matches.",
    catalogueLoadError: "Couldn’t load the catalogue.",
    fDci: "Generic name (DCI)",
    fBrands: "Brand names",
    fForm: "Form",
    fStrength: "Strength (display)",
    fUnitMg: "mg per unit",
    fMaxDaily: "Adult max per day (mg)",
    fMaxDailyHint: "Leave empty for no dose check.",
    fAtc: "ATC code",
    fAllergy: "Allergy classes",
    fInteraction: "Interaction groups",
    fHighAlert: "High-alert drug (double-check)",
    fMinStock: "Minimum stock",
    fActive: "Active (can be prescribed)",
    tagHint: "Press Enter or a comma to add; × removes.",
    tagRemove: "Remove {tag}",
    formTablet: "Tablet",
    formCapsule: "Capsule",
    formSyrup: "Syrup",
    formInjection: "Injection",
    formInhaler: "Inhaler",
    formPatch: "Patch",
    formDrops: "Drops",
    formOther: "Other",
    save: "Save",
    close: "Close",
    drugSaved: "{name} saved.",
    errDrugRequired: "Generic name, strength and ATC code are required.",
    errNumber: "Use positive numbers (and a whole number for the minimum stock).",
```
`fr`:
```ts
    navCatalogue: "Livret thérapeutique",
    catalogueTitle: "Livret thérapeutique",
    catalogueSub: "Le livret de l'hôpital. Données illustratives, pas une référence clinique ; à valider par les pharmaciens de l'hôpital.",
    searchLabel: "Rechercher par DCI, marque ou code ATC",
    showInactive: "Afficher les médicaments inactifs",
    addDrug: "Ajouter un médicament",
    editDrug: "Modifier le médicament",
    edit: "Modifier",
    colDci: "DCI",
    colForm: "Forme · dosage",
    colAtc: "ATC",
    colMaxDaily: "Max / jour",
    colTags: "Classes allergiques · groupes d'interaction",
    colStatus: "Statut",
    noMaxDaily: "Pas de limite",
    highAlert: "Haut risque",
    active: "Actif",
    inactive: "Inactif",
    catalogueEmpty: "Aucun médicament ne correspond.",
    catalogueLoadError: "Impossible de charger le livret.",
    fDci: "DCI",
    fBrands: "Noms commerciaux",
    fForm: "Forme",
    fStrength: "Dosage (affichage)",
    fUnitMg: "mg par unité",
    fMaxDaily: "Dose max adulte par jour (mg)",
    fMaxDailyHint: "Vide = pas de contrôle de dose.",
    fAtc: "Code ATC",
    fAllergy: "Classes allergiques",
    fInteraction: "Groupes d'interaction",
    fHighAlert: "Médicament à haut risque (double contrôle)",
    fMinStock: "Stock minimum",
    fActive: "Actif (prescriptible)",
    tagHint: "Entrée ou virgule pour ajouter ; × pour retirer.",
    tagRemove: "Retirer {tag}",
    formTablet: "Comprimé",
    formCapsule: "Gélule",
    formSyrup: "Sirop",
    formInjection: "Injectable",
    formInhaler: "Inhalateur",
    formPatch: "Patch",
    formDrops: "Gouttes",
    formOther: "Autre",
    save: "Enregistrer",
    close: "Fermer",
    drugSaved: "{name} enregistré.",
    errDrugRequired: "DCI, dosage et code ATC sont obligatoires.",
    errNumber: "Utilisez des nombres positifs (et un nombre entier pour le stock minimum).",
```
`ar`:
```ts
    navCatalogue: "دليل الأدوية",
    catalogueTitle: "دليل الأدوية",
    catalogueSub: "دليل أدوية المستشفى. بيانات توضيحية وليست مرجعاً سريرياً؛ يجب أن يعتمدها صيادلة المستشفى.",
    searchLabel: "ابحث بالاسم أو العلامة التجارية أو رمز ATC",
    showInactive: "إظهار الأدوية غير النشطة",
    addDrug: "إضافة دواء",
    editDrug: "تعديل الدواء",
    edit: "تعديل",
    colDci: "الاسم العلمي",
    colForm: "الشكل · التركيز",
    colAtc: "ATC",
    colMaxDaily: "الحد / اليوم",
    colTags: "فئات الحساسية · مجموعات التداخل",
    colStatus: "الحالة",
    noMaxDaily: "بلا حد",
    highAlert: "عالي الخطورة",
    active: "نشط",
    inactive: "غير نشط",
    catalogueEmpty: "لا يوجد دواء مطابق.",
    catalogueLoadError: "تعذّر تحميل الدليل.",
    fDci: "الاسم العلمي (DCI)",
    fBrands: "الأسماء التجارية",
    fForm: "الشكل",
    fStrength: "التركيز (للعرض)",
    fUnitMg: "ملغ لكل وحدة",
    fMaxDaily: "الحد الأقصى اليومي للبالغ (ملغ)",
    fMaxDailyHint: "اتركه فارغاً لعدم فحص الجرعة.",
    fAtc: "رمز ATC",
    fAllergy: "فئات الحساسية",
    fInteraction: "مجموعات التداخل",
    fHighAlert: "دواء عالي الخطورة (تحقق مزدوج)",
    fMinStock: "الحد الأدنى للمخزون",
    fActive: "نشط (يمكن وصفه)",
    tagHint: "اضغط Enter أو فاصلة للإضافة، و× للحذف.",
    tagRemove: "إزالة {tag}",
    formTablet: "قرص",
    formCapsule: "كبسولة",
    formSyrup: "شراب",
    formInjection: "حقن",
    formInhaler: "بخاخ",
    formPatch: "لصقة",
    formDrops: "قطرات",
    formOther: "أخرى",
    save: "حفظ",
    close: "إغلاق",
    drugSaved: "تم حفظ {name}.",
    errDrugRequired: "الاسم العلمي والتركيز ورمز ATC مطلوبة.",
    errNumber: "استعمل أرقاماً موجبة (وعدداً صحيحاً للحد الأدنى للمخزون).",
```

- [ ] **Step 2: Add the form list to `web/src/lib/pharmacy.ts`**

Add `DrugForm` to the type import list, then append:

```ts
export const DRUG_FORMS: DrugForm[] = ["tablet", "capsule", "syrup", "injection", "inhaler", "patch", "drops", "other"];

export const FORM_KEY: Record<DrugForm, Key> = {
  tablet: "pharmacy.formTablet",
  capsule: "pharmacy.formCapsule",
  syrup: "pharmacy.formSyrup",
  injection: "pharmacy.formInjection",
  inhaler: "pharmacy.formInhaler",
  patch: "pharmacy.formPatch",
  drops: "pharmacy.formDrops",
  other: "pharmacy.formOther",
};
```

- [ ] **Step 3: Create `web/src/lib/useDebounced.ts`**

```ts
"use client";

import { useEffect, useState } from "react";

/** `value`, updated only once it has stayed the same for `ms` (search boxes). */
export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}
```

- [ ] **Step 4: Create `web/src/components/pharmacist/TagInput.tsx`**

```tsx
"use client";

// Tag list editor (brand names, allergy classes, interaction groups). Enter, a comma or an Arabic comma (،)
// adds the tag; × removes it; Backspace in an empty box removes the last one. Leaving the box keeps what was typed.
import { useState, type KeyboardEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import page from "@/components/admin/AdminPage.module.css";
import styles from "./Pharmacist.module.css";

export interface TagInputProps {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  /** Applied to each new tag; an empty result is dropped. Default: trim. */
  normalize?: (raw: string) => string;
}

/** Lower-case snake_case codes the check engine matches ("Beta Lactam" → "beta_lactam"). */
export const codeTag = (raw: string): string => raw.trim().toLowerCase().replace(/[\s-]+/g, "_");

const ADD_KEYS = new Set(["Enter", ",", "،"]);

export function TagInput({ label, values, onChange, normalize = (s) => s.trim() }: TagInputProps) {
  const { t } = useT();
  const [draft, setDraft] = useState("");

  function commit() {
    const v = normalize(draft);
    if (v && !values.includes(v)) onChange([...values, v]);
    setDraft("");
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (ADD_KEYS.has(e.key)) {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  }

  return (
    <div className={page.field}>
      <span className={page.fieldLabel}>{label}</span>
      <div className={styles.tagBox}>
        {values.map((v) => (
          <span key={v} className={styles.tag}>
            <span dir="auto">{v}</span>
            <button type="button" className={styles.tagX} aria-label={t("pharmacy.tagRemove", { tag: v })} onClick={() => onChange(values.filter((x) => x !== v))}>
              ×
            </button>
          </span>
        ))}
        <input dir="auto" aria-label={label} className={styles.tagEntry} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} onBlur={commit} />
      </div>
      <span className={page.help}>{t("pharmacy.tagHint")}</span>
    </div>
  );
}

export default TagInput;
```

- [ ] **Step 5: Create `web/src/components/pharmacist/DrugForm.tsx`**

```tsx
"use client";

// Add or edit one formulary drug (pharmacist, admin): a side panel. Allergy classes and interaction groups
// are tags (lower-case codes the check engine matches). Deactivating is allowed; deleting isn't (spec §5).
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import page from "@/components/admin/AdminPage.module.css";
import { createDrug, updateDrug } from "@/lib/api";
import { DRUG_FORMS, FORM_KEY } from "@/lib/pharmacy";
import { describePharmacyError } from "@/lib/pharmacyUi";
import type { Drug, DrugForm as DosageForm, DrugInput } from "@/lib/types";
import { codeTag, TagInput } from "./TagInput";
import styles from "./Pharmacist.module.css";

interface Draft {
  dci: string;
  brands: string[];
  form: DosageForm;
  strength: string;
  unitMg: string;
  maxDaily: string;
  atc: string;
  allergy: string[];
  groups: string[];
  highAlert: boolean;
  minStock: string;
  active: boolean;
}

function toDraft(d: Drug | null): Draft {
  if (!d)
    return { dci: "", brands: [], form: "tablet", strength: "", unitMg: "", maxDaily: "", atc: "", allergy: [], groups: [], highAlert: false, minStock: "0", active: true };
  return {
    dci: d.dci,
    brands: d.brand_names,
    form: d.form,
    strength: d.strength,
    unitMg: d.unit_mg != null ? String(d.unit_mg) : "",
    maxDaily: d.max_daily_mg != null ? String(d.max_daily_mg) : "",
    atc: d.atc_code,
    allergy: d.allergy_classes,
    groups: d.interaction_groups,
    highAlert: d.high_alert,
    minStock: String(d.min_stock),
    active: d.active,
  };
}

/** "" → null; a positive number (decimal comma accepted) → the number; anything else → undefined (invalid). */
function optionalPositive(raw: string): number | null | undefined {
  const v = raw.trim().replace(",", ".");
  if (!v) return null;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

/** The request body, or the message key of the first problem. */
function toInput(d: Draft): DrugInput | Key {
  if (!d.dci.trim() || !d.strength.trim() || !d.atc.trim()) return "pharmacy.errDrugRequired";
  const unit = optionalPositive(d.unitMg);
  const max = optionalPositive(d.maxDaily);
  const min = d.minStock.trim() === "" ? 0 : Number(d.minStock);
  if (unit === undefined || max === undefined || !Number.isInteger(min) || min < 0) return "pharmacy.errNumber";
  return {
    dci: d.dci.trim(),
    brand_names: d.brands,
    form: d.form,
    strength: d.strength.trim(),
    unit_mg: unit,
    max_daily_mg: max,
    atc_code: d.atc.trim().toUpperCase(),
    allergy_classes: d.allergy,
    interaction_groups: d.groups,
    high_alert: d.highAlert,
    min_stock: min,
    active: d.active,
  };
}

export interface DrugFormProps {
  /** null = a new drug. */
  drug: Drug | null;
  onSaved: (drug: Drug) => void;
  onClose: () => void;
}

export function DrugForm({ drug, onSaved, onClose }: DrugFormProps) {
  const { t } = useT();
  const [d, setD] = useState<Draft>(() => toDraft(drug));
  const [error, setError] = useState<Key | null>(null);
  const [busy, setBusy] = useState(false);
  const first = useRef<HTMLInputElement>(null);
  const close = useRef(onClose);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));

  useEffect(() => {
    close.current = onClose;
  });
  useEffect(() => {
    first.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const input = toInput(d);
    if (typeof input === "string") {
      setError(input);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSaved(drug ? await updateDrug(drug.id, input) : await createDrug(input));
    } catch (err) {
      setError(describePharmacyError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className={styles.drawer} aria-labelledby="drug-form-title">
      <form className={styles.drawerForm} onSubmit={submit} noValidate>
        <div className={styles.drawerHead}>
          <h2 id="drug-form-title" className={styles.drawerTitle}>
            {drug ? t("pharmacy.editDrug") : t("pharmacy.addDrug")}
          </h2>
          <button type="button" className={page.btn} onClick={onClose}>
            {t("pharmacy.close")}
          </button>
        </div>
        <label className={page.field}>
          <span className={page.fieldLabel}>{t("pharmacy.fDci")}</span>
          <input ref={first} dir="auto" className={page.input} value={d.dci} onChange={(e) => set("dci", e.target.value)} />
        </label>
        <TagInput label={t("pharmacy.fBrands")} values={d.brands} onChange={(v) => set("brands", v)} />
        <div className={styles.pair}>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("pharmacy.fForm")}</span>
            <span className={page.selectWrap}>
              <select className={page.select} value={d.form} onChange={(e) => set("form", e.target.value as DosageForm)}>
                {DRUG_FORMS.map((f) => (
                  <option key={f} value={f}>
                    {t(FORM_KEY[f])}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("pharmacy.fStrength")}</span>
            <input dir="ltr" className={page.input} value={d.strength} onChange={(e) => set("strength", e.target.value)} />
          </label>
        </div>
        <div className={styles.pair}>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("pharmacy.fUnitMg")}</span>
            <input dir="ltr" inputMode="decimal" className={page.input} value={d.unitMg} onChange={(e) => set("unitMg", e.target.value)} />
          </label>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("pharmacy.fMaxDaily")}</span>
            <input dir="ltr" inputMode="decimal" className={page.input} value={d.maxDaily} onChange={(e) => set("maxDaily", e.target.value)} />
            <span className={page.help}>{t("pharmacy.fMaxDailyHint")}</span>
          </label>
        </div>
        <div className={styles.pair}>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("pharmacy.fAtc")}</span>
            <input dir="ltr" className={`${page.input} ${styles.mono}`} value={d.atc} onChange={(e) => set("atc", e.target.value)} />
          </label>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("pharmacy.fMinStock")}</span>
            <input dir="ltr" inputMode="numeric" className={page.input} value={d.minStock} onChange={(e) => set("minStock", e.target.value)} />
          </label>
        </div>
        <TagInput label={t("pharmacy.fAllergy")} values={d.allergy} normalize={codeTag} onChange={(v) => set("allergy", v)} />
        <TagInput label={t("pharmacy.fInteraction")} values={d.groups} normalize={codeTag} onChange={(v) => set("groups", v)} />
        <label className={styles.checkRow}>
          <input type="checkbox" checked={d.highAlert} onChange={(e) => set("highAlert", e.target.checked)} />
          {t("pharmacy.fHighAlert")}
        </label>
        <label className={styles.checkRow}>
          <input type="checkbox" checked={d.active} onChange={(e) => set("active", e.target.checked)} />
          {t("pharmacy.fActive")}
        </label>
        {error ? (
          <span role="alert" className={styles.error}>
            {t(error)}
          </span>
        ) : null}
        <button type="submit" className={page.btnPrimary} disabled={busy}>
          {t("pharmacy.save")}
        </button>
      </form>
    </aside>
  );
}

export default DrugForm;
```

- [ ] **Step 6: Create `web/src/components/pharmacist/CatalogueView.tsx`**

```tsx
"use client";

// Drug catalogue (/pharmacist/catalogue and /admin/catalogue): search by DCI, brand or ATC code, the
// formulary table, and the add/edit side panel (pharmacists and admins; spec §2). Illustrative data.
import { useEffect, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import page from "@/components/admin/AdminPage.module.css";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { Toast, useToast } from "@/components/Toast";
import { listDrugs } from "@/lib/api";
import { drugLabel, FORM_KEY } from "@/lib/pharmacy";
import type { Drug } from "@/lib/types";
import { useDebounced } from "@/lib/useDebounced";
import { DrugForm } from "./DrugForm";
import styles from "./Pharmacist.module.css";

export function CatalogueView() {
  const { t } = useT();
  const [q, setQ] = useState("");
  const query = useDebounced(q.trim(), 250);
  const [showInactive, setShowInactive] = useState(false);
  const [drugs, setDrugs] = useState<Drug[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [editing, setEditing] = useState<Drug | "new" | null>(null);
  const [toast, showToast] = useToast<string>(4500);

  useEffect(() => {
    let alive = true; // the last query wins
    setFailed(false);
    listDrugs({ q: query, ...(showInactive ? {} : { active: true }) }).then(
      (list) => {
        if (alive) setDrugs(list);
      },
      () => {
        if (alive) setFailed(true);
      },
    );
    return () => {
      alive = false;
    };
  }, [query, showInactive, reload]);

  return (
    <div className={page.page}>
      <div className={page.head}>
        <div className={page.titles}>
          <h2 className={page.h2}>{t("pharmacy.catalogueTitle")}</h2>
          <span className={page.sub}>{t("pharmacy.catalogueSub")}</span>
        </div>
        <button type="button" className={page.btnPrimary} onClick={() => setEditing("new")}>
          {t("pharmacy.addDrug")}
        </button>
      </div>

      <div className={styles.toolbar}>
        <input
          type="search"
          dir="auto"
          aria-label={t("pharmacy.searchLabel")}
          placeholder={t("pharmacy.searchLabel")}
          className={`${page.input} ${styles.search}`}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <label className={styles.checkRow}>
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
          {t("pharmacy.showInactive")}
        </label>
      </div>

      {failed && !drugs ? (
        <ErrorCard title={t("pharmacy.catalogueLoadError")} onRetry={() => setReload((n) => n + 1)} secondaryLabel={null} />
      ) : !drugs ? (
        <div className="ward-skeleton" style={{ height: 240 }} aria-busy="true" />
      ) : (
        <div className={styles.table} role="table" aria-label={t("pharmacy.catalogueTitle")}>
          <div role="row" className={`${styles.drugGrid} ${page.th}`}>
            <span role="columnheader">{t("pharmacy.colDci")}</span>
            <span role="columnheader">{t("pharmacy.colForm")}</span>
            <span role="columnheader">{t("pharmacy.colAtc")}</span>
            <span role="columnheader">{t("pharmacy.colMaxDaily")}</span>
            <span role="columnheader">{t("pharmacy.colTags")}</span>
            <span role="columnheader">{t("pharmacy.colStatus")}</span>
            <span role="columnheader" />
          </div>
          {drugs.length === 0 ? <p className={styles.empty}>{t("pharmacy.catalogueEmpty")}</p> : null}
          {drugs.map((d) => (
            <div key={d.id} role="row" className={`${styles.drugGrid} ${page.tr}`}>
              <span role="cell">
                <span dir="auto" className={styles.cellMain}>
                  {d.dci}
                </span>
                {d.brand_names.length ? (
                  <span dir="auto" className={styles.cellSub}>
                    {d.brand_names.join(", ")}
                  </span>
                ) : null}
              </span>
              <span role="cell">
                {t(FORM_KEY[d.form] ?? "pharmacy.formOther")} · <span dir="ltr">{d.strength}</span>
              </span>
              <span role="cell" dir="ltr" className={styles.mono}>
                {d.atc_code}
              </span>
              <span role="cell" dir="ltr">
                {d.max_daily_mg != null ? `${d.max_daily_mg} mg` : <span className={styles.cellSub}>{t("pharmacy.noMaxDaily")}</span>}
              </span>
              <span role="cell" className={styles.tags}>
                {d.allergy_classes.map((c) => (
                  <span key={`a-${c}`} className={styles.tag}>
                    {c}
                  </span>
                ))}
                {d.interaction_groups.map((g) => (
                  <span key={`g-${g}`} className={`${styles.tag} ${styles.tagGroup}`}>
                    {g}
                  </span>
                ))}
              </span>
              <span role="cell" className={styles.tags}>
                {d.high_alert ? <span className={styles.flag}>{t("pharmacy.highAlert")}</span> : null}
                <span className={`${styles.flag} ${d.active ? styles.flagOk : styles.flagOff}`}>{t(d.active ? "pharmacy.active" : "pharmacy.inactive")}</span>
              </span>
              <span role="cell">
                <button type="button" className={styles.linkBtn} onClick={() => setEditing(d)}>
                  {t("pharmacy.edit")}
                </button>
              </span>
            </div>
          ))}
        </div>
      )}

      {editing ? (
        <DrugForm
          key={editing === "new" ? "new" : editing.id}
          drug={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setEditing(null);
            showToast(t("pharmacy.drugSaved", { name: drugLabel(saved) }));
            setReload((n) => n + 1);
          }}
        />
      ) : null}
      {toast ? <Toast>{toast}</Toast> : null}
    </div>
  );
}

export default CatalogueView;
```

`"mg"` in `${d.max_daily_mg} mg` is a unit symbol (it is used the same way in every language). Leave it as is.

- [ ] **Step 7: Add the pages, nav entries and styles**

`web/src/app/pharmacist/catalogue/page.tsx`, and the same file at `web/src/app/admin/catalogue/page.tsx` with the function renamed `AdminCataloguePage`:

```tsx
import { CatalogueView } from "@/components/pharmacist/CatalogueView";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("pharmacy.catalogueTitle")} · Ward` };
}

export default function PharmacistCataloguePage() {
  return <CatalogueView />;
}
```

`Sidebar.tsx` `NAV`:
- pharmacist: insert `{ key: "catalogue", label: "pharmacy.navCatalogue", href: "/pharmacist/catalogue" },` between `worklist` and `password`;
- admin: insert the same entry with `href: "/admin/catalogue"` before `password`.

Append to `Pharmacist.module.css`:

```css
/* ── Catalogue (Task 4) ─────────────────────────────────────────────────── */
.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 20px; }
.search { flex: 1 1 280px; width: auto; }
.checkRow { display: inline-flex; align-items: center; gap: 10px; font-size: 15px; color: var(--ink); cursor: pointer; }
.checkRow input { width: 20px; height: 20px; }
.table { background: var(--paper); border: 1px solid var(--line); border-radius: 14px; overflow-x: auto; }
.drugGrid { display: grid; grid-template-columns: minmax(180px, 2fr) minmax(140px, 1.2fr) 100px 110px minmax(200px, 2fr) 150px 80px; gap: 12px; min-width: 1000px; }
.cellMain { font-size: 15px; font-weight: 600; color: var(--ink); }
.cellSub { display: block; font-size: 13px; color: var(--muted); }
.mono { font-family: var(--mono); font-size: 14px; }
.tags { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.tag { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 999px; background: var(--chip); color: var(--text); font-size: 12px; }
.tagGroup { background: var(--doctor-bg); color: var(--doctor-fg); }
.flag { padding: 3px 8px; border-radius: 999px; font: 600 12px/1.2 var(--sans); background: var(--warn-bg); color: var(--warn-ink); }
.flagOk { background: var(--news-normal-bg); color: var(--news-normal-fg); }
.flagOff { background: var(--chip); color: var(--muted); }
.flagDanger { background: var(--danger-bg); color: var(--danger-ink); }
.linkBtn { padding: 6px 0; border: none; background: none; color: var(--teal); font: 600 14px/1 var(--sans); cursor: pointer; }
.drawer { position: fixed; inset-block: 0; inset-inline-end: 0; z-index: 40; width: min(460px, 100%); overflow-y: auto; background: var(--paper); box-shadow: var(--drawer-shadow); }
.drawerForm { display: flex; flex-direction: column; gap: 14px; padding: 28px; }
.drawerHead { display: flex; align-items: center; gap: 12px; }
.drawerTitle { flex: 1; margin: 0; font: 600 24px/1.2 var(--serif); color: var(--ink); }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.tagBox { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 8px 10px; border: 1px solid var(--line-strong); border-radius: 8px; background: var(--paper); }
.tagBox:focus-within { border-color: var(--teal); box-shadow: 0 0 0 3px #cbeaee; }
.tagX { padding: 0 2px; border: none; background: none; color: var(--muted); font-size: 14px; line-height: 1; cursor: pointer; }
.tagEntry { flex: 1 1 120px; min-width: 80px; padding: 4px 2px; border: none; outline: none; background: transparent; color: var(--ink); font: 400 16px/1.4 var(--sans); }
```

- [ ] **Step 8: Run the type check and the mock build**

Run: `npx tsc --noEmit`, then `NEXT_PUBLIC_USE_MOCKS=1 npm run build`.
Expected: both pass, and the routes include `/pharmacist/catalogue` and `/admin/catalogue`.

- [ ] **Step 9: Check it by hand in mock mode**

- `/pharmacist/catalogue`: 21 drugs. Typing `amox` shows 2 rows; `J01` shows Amoxicillin and Azithromycin; `Lasilix` shows both Furosemide rows.
- **Add a drug.** Add "Ceftriaxone", 1 g, injection, ATC `j01dd04` (it is saved as `J01DD04`), allergy classes `Beta Lactam` (saved as `beta_lactam`). Then:
  - an empty DCI shows "Generic name, strength and ATC code are required.";
  - "abc" in mg per unit shows the number error.
- **Edit.** Edit Diazepam and untick Active: the row disappears. With "Show inactive drugs" ticked, it comes back labelled "Inactive".
- **Arabic.** In العربية, add an allergy class with the Arabic comma `،`: it becomes a tag. The drawer opens from the left (inline-end in RTL).
- **Admin.** `/admin/catalogue` from the admin sidebar shows the same screen.

- [ ] **Step 10: Commit**

```bash
git add web/src/lib/useDebounced.ts web/src/lib/pharmacy.ts web/src/components/pharmacist web/src/app/pharmacist/catalogue web/src/app/admin/catalogue web/src/components/Sidebar.tsx web/src/i18n/messages/pharmacy.ts
git commit -m "feat(web): drug catalogue with search and add/edit for pharmacists and admins"
```

---

## Task 5: Doctor prescription form and list (drug picker, live checks, override, urgent, resubmit)

**Files:**
- Create: `web/src/components/doctor/DrugPicker.tsx`, `web/src/components/doctor/usePrescriptionCheck.ts`.
- Modify:
  - `web/src/components/doctor/Prescriptions.tsx` (full replacement below), `web/src/components/doctor/Prescriptions.module.css`;
  - `web/src/components/doctor/PatientDetail.tsx`;
  - `web/src/i18n/messages/pharmacy.ts`.

**Interfaces:**
- Consumes:
  - from Task 1: `createPrescription` (1.12 request), `checkPrescription`, `listDrugs`; `doctorRows`, `isRunning`, `pendingSuccessor`, `hasCritical`, `OVERRIDE_MAX`, `drugLabel`; `pharmacyErrorKey`;
  - from Task 2: `useLiveRefresh`;
  - from Task 3: `CheckList`, `RxStatusBadge`;
  - from Task 4: `useDebounced`, `FORM_KEY`.
- Produces:
  ```ts
  // components/doctor/usePrescriptionCheck.ts
  export const CHECK_DEBOUNCE_MS = 400;
  export interface CheckState { checks: Check[] | null; checking: boolean; failed: boolean }
  export function usePrescriptionCheck(req: CheckRequest | null, delayMs?: number): CheckState;
  // components/doctor/DrugPicker.tsx
  export interface DrugChoice { med: string; drug_id: string | null }
  export interface DrugPickerProps { value: DrugChoice | null; onChange: (c: DrugChoice | null) => void; labelId: string; invalid?: boolean }
  export function DrugPicker(props: DrugPickerProps): JSX.Element;
  ```
  `PrescriptionsProps` is unchanged (`patient`, `prescriptions`, `actorId`, `onSaved?`, `readOnly?`). The `prescriptions` prop now receives **every** version; the component filters it with `doctorRows`.

- [ ] **Step 1: Add the i18n keys (append)**

`en`:
```ts
    drugLabel: "Medicine",
    drugSearch: "Search the formulary (name, brand, ATC)",
    nonFormulary: "Non-formulary drug: use this name",
    pickDrug: "Pick a drug, or a non-formulary name.",
    doseMg: "Dose per intake (mg)",
    doseHint: "Optional",
    errDose: "Use a dose above 0 mg, or leave it empty.",
    unitsPerIntake: "Units per intake",
    fewerUnits: "Fewer units",
    moreUnits: "More units",
    checking: "Checking…",
    checkFailed: "Couldn’t run the checks now. The pharmacist still checks before any dose.",
    checksLead: "The pharmacist will see the same warnings.",
    overrideLabel: "Reason for sending despite the critical warning",
    overrideRequired: "Give a reason to send it anyway.",
    urgentLabel: "Urgent: start now",
    urgentHint: "Doses start at once; the pharmacist reviews right after.",
    toastPendingTitle: "Sent to the pharmacist.",
    toastPendingBody: "Doses start once it is validated.",
    toastUrgentTitle: "Urgent: doses started.",
    toastUrgentBody: "No bedside unit: give by hand. The pharmacist reviews next.",
    editAndResubmit: "Edit and resubmit",
    editingTitle: "New version of {med}",
    editingHint: "The current version keeps running until the pharmacist validates this one.",
    pharmacistSaid: "Pharmacist: {comment}",
    validatedBy: "by {name}",
    newVersionPending: "New version awaiting the pharmacist",
    overrideNote: "Sent despite a warning: {reason}",
```
`fr`:
```ts
    drugLabel: "Médicament",
    drugSearch: "Rechercher dans le livret (DCI, marque, ATC)",
    nonFormulary: "Médicament hors livret : utiliser ce nom",
    pickDrug: "Choisissez un médicament, ou un nom hors livret.",
    doseMg: "Dose par prise (mg)",
    doseHint: "Facultatif",
    errDose: "Indiquez une dose supérieure à 0 mg, ou laissez vide.",
    unitsPerIntake: "Unités par prise",
    fewerUnits: "Moins d'unités",
    moreUnits: "Plus d'unités",
    checking: "Vérification…",
    checkFailed: "Contrôle impossible pour l'instant. Le pharmacien vérifie quand même avant toute prise.",
    checksLead: "Le pharmacien verra les mêmes avertissements.",
    overrideLabel: "Justification malgré l'avertissement critique",
    overrideRequired: "Donnez une justification pour l'envoyer quand même.",
    urgentLabel: "Urgent : commencer maintenant",
    urgentHint: "Les prises commencent tout de suite ; le pharmacien vérifie juste après.",
    toastPendingTitle: "Envoyée au pharmacien.",
    toastPendingBody: "Les prises commencent après validation.",
    toastUrgentTitle: "Urgent : prises lancées.",
    toastUrgentBody: "Pas de boîtier au lit : à donner à la main. Le pharmacien vérifie ensuite.",
    editAndResubmit: "Modifier et renvoyer",
    editingTitle: "Nouvelle version de {med}",
    editingHint: "La version actuelle continue jusqu'à ce que le pharmacien valide celle-ci.",
    pharmacistSaid: "Pharmacien : {comment}",
    validatedBy: "par {name}",
    newVersionPending: "Nouvelle version en attente du pharmacien",
    overrideNote: "Envoyée malgré un avertissement : {reason}",
```
`ar`:
```ts
    drugLabel: "الدواء",
    drugSearch: "ابحث في دليل الأدوية (الاسم، العلامة، ATC)",
    nonFormulary: "دواء خارج الدليل: استعمل هذا الاسم",
    pickDrug: "اختر دواءً أو اسماً خارج الدليل.",
    doseMg: "الجرعة في كل مرة (ملغ)",
    doseHint: "اختياري",
    errDose: "أدخل جرعة أكبر من 0 ملغ أو اتركها فارغة.",
    unitsPerIntake: "وحدات في كل جرعة",
    fewerUnits: "وحدات أقل",
    moreUnits: "وحدات أكثر",
    checking: "جارٍ الفحص…",
    checkFailed: "تعذّر إجراء الفحص الآن. سيتحقق الصيدلي على أي حال قبل أي جرعة.",
    checksLead: "سيرى الصيدلي التحذيرات نفسها.",
    overrideLabel: "مبرر الإرسال رغم التحذير الحرج",
    overrideRequired: "اذكر مبرراً لإرسالها رغم ذلك.",
    urgentLabel: "عاجل: البدء الآن",
    urgentHint: "تبدأ الجرعات فوراً ويراجع الصيدلي بعدها مباشرة.",
    toastPendingTitle: "أُرسلت إلى الصيدلي.",
    toastPendingBody: "تبدأ الجرعات بعد الاعتماد.",
    toastUrgentTitle: "عاجل: بدأت الجرعات.",
    toastUrgentBody: "لا جهاز بجانب السرير: تُعطى باليد. سيراجع الصيدلي لاحقاً.",
    editAndResubmit: "تعديل وإعادة الإرسال",
    editingTitle: "نسخة جديدة من {med}",
    editingHint: "تستمر النسخة الحالية حتى يعتمد الصيدلي هذه النسخة.",
    pharmacistSaid: "الصيدلي: {comment}",
    validatedBy: "من {name}",
    newVersionPending: "نسخة جديدة بانتظار الصيدلي",
    overrideNote: "أُرسلت رغم تحذير: {reason}",
```

- [ ] **Step 2: Create the debounced check hook (`web/src/components/doctor/usePrescriptionCheck.ts`)**

```ts
"use client";

// The doctor's live check panel: POST /prescriptions/check 400 ms after the last change (spec §6).
// Only the newest draft may update the panel: a slow reply to an older draft is dropped.
// While a new check runs, the previous result stays on screen with `checking` set.
import { useEffect, useState } from "react";
import { checkPrescription } from "@/lib/api";
import type { Check, CheckRequest } from "@/lib/types";

export const CHECK_DEBOUNCE_MS = 400;

export interface CheckState {
  /** null until the first result (or after a failure). */
  checks: Check[] | null;
  checking: boolean;
  failed: boolean;
}

const IDLE: CheckState = { checks: null, checking: false, failed: false };

export function usePrescriptionCheck(req: CheckRequest | null, delayMs = CHECK_DEBOUNCE_MS): CheckState {
  // A content key: a new object with the same content must not restart the timer.
  const key = req ? JSON.stringify(req) : "";
  const [state, setState] = useState<CheckState>(IDLE);

  useEffect(() => {
    if (!key) {
      setState(IDLE);
      return;
    }
    let alive = true; // false once a newer draft (or unmount) supersedes this one
    setState((s) => ({ ...s, checking: true }));
    const timer = setTimeout(() => {
      checkPrescription(JSON.parse(key) as CheckRequest).then(
        (r) => {
          if (alive) setState({ checks: r.checks, checking: false, failed: false });
        },
        () => {
          if (alive) setState({ checks: null, checking: false, failed: true });
        },
      );
    }, delayMs);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [key, delayMs]);

  return state;
}
```

- [ ] **Step 3: Create the formulary combobox (`web/src/components/doctor/DrugPicker.tsx`)**

```tsx
"use client";

// Formulary combobox for the prescription form. Typing searches GET /drugs (active drugs only, 250 ms
// debounce). The doctor picks a drug, or keeps the typed text as a non-formulary drug (drug_id null).
// Typing again un-picks the choice. Mount it with a new `key` to reset it (form reset, "Edit and resubmit").
import { useEffect, useId, useState, type KeyboardEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import { listDrugs } from "@/lib/api";
import { drugLabel, FORM_KEY } from "@/lib/pharmacy";
import type { Drug } from "@/lib/types";
import { useDebounced } from "@/lib/useDebounced";
import styles from "./Prescriptions.module.css";

/** What the item will carry: the display string and the formulary id (null = non-formulary). */
export interface DrugChoice {
  med: string;
  drug_id: string | null;
}

type Option = { kind: "drug"; drug: Drug } | { kind: "free"; text: string };

export interface DrugPickerProps {
  /** Initial value (read on mount only). */
  value: DrugChoice | null;
  onChange: (choice: DrugChoice | null) => void;
  /** id of the visible label element. */
  labelId: string;
  /** Red border: missing, or a critical check on this item. */
  invalid?: boolean;
}

export function DrugPicker({ value, onChange, labelId, invalid = false }: DrugPickerProps) {
  const { t } = useT();
  const id = useId();
  const [text, setText] = useState(value?.med ?? "");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Drug[]>([]);
  const [active, setActive] = useState(0);
  const q = useDebounced(text.trim(), 250);

  useEffect(() => {
    if (!open || !q) {
      setResults([]);
      return;
    }
    let alive = true;
    listDrugs({ q, active: true }).then(
      (list) => {
        if (!alive) return;
        setResults(list.slice(0, 8));
        setActive(0);
      },
      () => {
        if (alive) setResults([]);
      },
    );
    return () => {
      alive = false;
    };
  }, [q, open]);

  const typed = text.trim();
  const options: Option[] = [...results.map((drug): Option => ({ kind: "drug", drug })), ...(typed ? [{ kind: "free", text: typed } as Option] : [])];
  const shown = open && options.length > 0;

  function pick(o: Option) {
    const choice: DrugChoice = o.kind === "drug" ? { med: drugLabel(o.drug), drug_id: o.drug.id } : { med: o.text, drug_id: null };
    onChange(choice);
    setText(choice.med);
    setOpen(false);
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, options.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && shown && options[active]) {
      e.preventDefault();
      pick(options[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className={styles.picker}>
      <input
        role="combobox"
        aria-labelledby={labelId}
        aria-expanded={shown}
        aria-controls={`${id}-list`}
        aria-autocomplete="list"
        aria-activedescendant={shown ? `${id}-opt-${active}` : undefined}
        aria-invalid={invalid || undefined}
        dir="auto"
        autoComplete="off"
        className={`${styles.input} ${invalid ? styles.inputBad : ""}`}
        placeholder={t("pharmacy.drugSearch")}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          onChange(null);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKey}
      />
      {shown ? (
        <ul id={`${id}-list`} role="listbox" className={styles.listbox}>
          {options.map((o, i) => (
            <li
              key={o.kind === "drug" ? o.drug.id : "free"}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              className={`${styles.option} ${i === active ? styles.optionOn : ""}`}
              onMouseDown={(e) => {
                e.preventDefault(); // keep the focus, so blur doesn't close the list before the pick
                pick(o);
              }}
            >
              {o.kind === "drug" ? (
                <>
                  <span dir="auto" className={styles.optMain}>
                    {drugLabel(o.drug)}
                  </span>
                  <span dir="auto" className={styles.optSub}>
                    {[t(FORM_KEY[o.drug.form] ?? "pharmacy.formOther"), o.drug.brand_names.join(", "), o.drug.high_alert ? t("pharmacy.highAlert") : ""]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </>
              ) : (
                <>
                  <span className={styles.optMain}>{t("pharmacy.nonFormulary")}</span>
                  <span dir="auto" className={styles.optSub}>
                    {o.text}
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default DrugPicker;
```

- [ ] **Step 4: Replace `web/src/components/doctor/Prescriptions.tsx`**

The old allergy regex is gone. The live check panel replaces it with the same warnings the pharmacist sees.

```tsx
"use client";

// Prescriptions card: the doctor's list (pharmacy status, the pharmacist's comment, "Edit and resubmit"),
// then the form: formulary picker (or a non-formulary name), dose and units, times, pill slot, the live
// check panel (the warnings the pharmacist will see, 400 ms after the last change), the override reason a
// critical warning requires, and "Urgent: start now". Saving sends the prescription to the pharmacist.
import { useMemo, useState, type ReactNode } from "react";
import { useT } from "@/i18n/I18nProvider";
import { Toast, useToast } from "@/components/Toast";
import { CheckList } from "@/components/shared/CheckList";
import { RxStatusBadge } from "@/components/shared/RxStatusBadge";
import { ApiError, createPrescription } from "@/lib/api";
import { doctorRows, hasCritical, isRunning, OVERRIDE_MAX, pendingSuccessor } from "@/lib/pharmacy";
import { pharmacyErrorKey } from "@/lib/pharmacyUi";
import { daysSince, now, tunisTime } from "@/lib/time";
import type { CheckRequest, Patient, Prescription, PrescriptionItem } from "@/lib/types";
import { DrugPicker, type DrugChoice } from "./DrugPicker";
import { usePrescriptionCheck } from "./usePrescriptionCheck";
import styles from "./Prescriptions.module.css";

const TIME_CHIPS = ["06:00", "08:00", "12:00", "14:00", "18:00", "20:00", "22:00"];
const SLOTS = ["1", "2", "3", "4", "r"] as const;
type SlotKey = (typeof SLOTS)[number];
const MAX_UNITS = 10;

const drugName = (med: string) => med.split(" ")[0];

/** "" → null (no dose given); a positive number → the number; anything else → "bad". Accepts a decimal comma. */
function parseDose(raw: string): number | null | "bad" {
  const v = raw.trim().replace(",", ".");
  if (!v) return null;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : "bad";
}

interface Draft {
  choice: DrugChoice | null;
  doseMg: string;
  units: number;
  days: number;
  times: string[];
  slot: SlotKey | null;
  plan: string;
  urgent: boolean;
  override: string;
}

/** The row being edited: a new version of `rx` replaces its item `index`. */
interface Editing {
  rx: Prescription;
  index: number;
}

type FieldErrors = Partial<Record<"med" | "times" | "dose" | "override", boolean>>;

export interface PrescriptionsProps {
  patient: Patient;
  /** Every version from GET /patients/{id}/prescriptions; the list shows doctorRows() of them. */
  prescriptions: Prescription[];
  /** Doctor user id sent with the mutation (mock mode). */
  actorId: string;
  /** Called after a successful save so the page can refetch prescriptions and doses. */
  onSaved?: (rx: Prescription) => void;
  /** Shared doctor: the list stays, the edit buttons and the form go. */
  readOnly?: boolean;
}

export function Prescriptions({ patient, prescriptions, actorId, onSaved, readOnly = false }: PrescriptionsProps) {
  const { t } = useT();
  const formId = `rx-form-${patient.id}`;
  const blank = (): Draft => ({
    choice: null,
    doseMg: "",
    units: 1,
    days: 5,
    times: ["08:00"],
    slot: null,
    plan: t("doctor.defaultPlan"),
    urgent: false,
    override: "",
  });
  const visible = useMemo(() => doctorRows(prescriptions), [prescriptions]);
  const rows = useMemo(
    () => visible.flatMap((rx) => rx.items.map((item, index) => ({ key: `${rx.id}-${index}`, rx, item, index }))),
    [visible],
  );
  const [draft, setDraft] = useState<Draft>(blank);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [formKey, setFormKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [serverCritical, setServerCritical] = useState(false);
  const [toast, showToast] = useToast<{ tone: "ok" | "warn"; body: ReactNode }>(4500);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  // Slots held by every live or awaited version (not rejected ones); the item being edited frees its own.
  const slotMeds = useMemo(() => {
    const m: Partial<Record<SlotKey, string>> = {};
    for (const { rx, item, index } of rows) {
      if (rx.status === "rejected" || item.slot == null) continue;
      if (editing && editing.rx.id === rx.id && editing.index === index) continue;
      m[String(item.slot) as SlotKey] = drugName(item.med);
    }
    return m;
  }, [rows, editing]);
  const firstFree = (): SlotKey => SLOTS.find((k) => k !== "r" && !slotMeds[k]) ?? "r";
  const pickedSlot: SlotKey = draft.slot && (draft.slot === "r" || !slotMeds[draft.slot]) ? draft.slot : firstFree();
  const sortedTimes = [...draft.times].sort();
  const dose = parseDose(draft.doseMg);
  const med = draft.choice?.med.trim() ?? "";

  const item: PrescriptionItem | null =
    med && sortedTimes.length && dose !== "bad"
      ? {
          med,
          drug_id: draft.choice?.drug_id ?? null,
          dose_mg: dose,
          units_per_intake: draft.units,
          times: sortedTimes,
          slot: pickedSlot === "r" ? null : Number(pickedSlot),
          days: draft.days,
        }
      : null;
  const ed = editing;
  const items: PrescriptionItem[] | null = item ? (ed ? ed.rx.items.map((it, i) => (i === ed.index ? item : it)) : [item]) : null;
  const checkReq: CheckRequest | null = items ? { patient_id: patient.id, items, ...(ed ? { replaces_id: ed.rx.id } : {}) } : null;
  const check = usePrescriptionCheck(readOnly ? null : checkReq);
  const itemIndex = ed?.index ?? 0;
  const criticalHere = !!check.checks?.some((c) => c.severity === "critical" && (c.item_index === null || c.item_index === itemIndex));
  const needsOverride = hasCritical(check.checks) || serverCritical;

  function reset() {
    setDraft(blank());
    setEditing(null);
    setErrors({});
    setServerCritical(false);
    setFormKey((k) => k + 1);
  }

  /** "Edit and resubmit" (changes requested) and "Edit" (validated): the form, pre-filled, as a new version. */
  function startEdit(rx: Prescription, index: number) {
    const it = rx.items[index];
    if (!it) return;
    setEditing({ rx, index });
    setDraft({
      choice: { med: it.med, drug_id: it.drug_id ?? null },
      doseMg: it.dose_mg != null ? String(it.dose_mg) : "",
      units: it.units_per_intake ?? 1,
      days: it.days,
      times: [...it.times],
      slot: it.slot != null ? (String(it.slot) as SlotKey) : "r",
      plan: rx.care_plan,
      urgent: false,
      override: "",
    });
    setErrors({});
    setServerCritical(false);
    setFormKey((k) => k + 1);
    document.getElementById(formId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function firstDose(): string {
    if (!sortedTimes.length) return t("doctor.notScheduled");
    const hm = tunisTime(now().toISOString());
    const today = sortedTimes.find((x) => x > hm);
    return today ? t("doctor.todayAt", { time: today }) : t("doctor.tomorrowAt", { time: sortedTimes[0] });
  }

  async function save() {
    if (saving) return;
    const errs: FieldErrors = {
      med: !med,
      times: !draft.times.length,
      dose: dose === "bad",
      override: needsOverride && !draft.override.trim(),
    };
    if (errs.med || errs.times || errs.dose || errs.override || !items) {
      setErrors(errs);
      return;
    }
    setSaving(true);
    setErrors({});
    const slotText = pickedSlot === "r" ? t("doctor.reminderOnlyLower") : t("doctor.slotLower", { n: pickedSlot });
    const first = firstDose();
    try {
      const rx = await createPrescription(
        {
          patient_id: patient.id,
          items,
          care_plan: draft.plan.trim(),
          urgent: draft.urgent,
          ...(needsOverride ? { override_reason: draft.override.trim() } : {}),
          ...(ed ? { replaces_id: ed.rx.id } : {}),
        },
        { by: actorId },
      );
      showToast(
        rx.urgent
          ? {
              tone: rx.published_to_device ? "ok" : "warn",
              body: (
                <>
                  <b>{t("pharmacy.toastUrgentTitle")}</b>{" "}
                  {rx.published_to_device && patient.device_id
                    ? t("doctor.toastSentBody", { id: patient.device_id, slot: slotText, first })
                    : t("pharmacy.toastUrgentBody")}
                </>
              ),
            }
          : {
              tone: "ok",
              body: (
                <>
                  <b>{t("pharmacy.toastPendingTitle")}</b> {t("pharmacy.toastPendingBody")}
                </>
              ),
            },
      );
      reset();
      onSaved?.(rx);
    } catch (err) {
      if (err instanceof ApiError && err.code === "override_required") {
        setServerCritical(true);
        setErrors({ override: true });
      }
      showToast({
        tone: "warn",
        body: (
          <>
            <b>{t("doctor.toastFailTitle")}</b> {t(pharmacyErrorKey(err) ?? "doctor.toastFailBody")}
          </>
        ),
      });
    } finally {
      setSaving(false);
    }
  }

  const sel = (on: boolean) => (on ? styles.on : "");
  const deviceLine = patient.device_id ? t("doctor.deviceHasSlots", { id: patient.device_id }) : t("doctor.noDeviceAssigned");

  return (
    <section className={styles.card}>
      <div className={styles.head}>
        <h3 className={styles.h3}>{t("doctor.rxTitle")}</h3>
        <span className={styles.sub}>
          {t("doctor.rxActive", { n: rows.filter((r) => isRunning(r.rx)).length })} · {deviceLine}
        </span>
      </div>
      <div className={`${styles.rxGrid} ${styles.th}`}>
        <span>{t("doctor.colMedicine")}</span>
        <span>{t("doctor.colTimes")}</span>
        <span>{t("doctor.colPillSlot")}</span>
        <span>{t("doctor.colDaysLeft")}</span>
        <span />
      </div>
      {rows.map(({ key, rx, item, index }) => {
        const live = isRunning(rx);
        const left = live ? Math.max(0, item.days - daysSince(rx.created_at)) : null;
        const successor = pendingSuccessor(rx, prescriptions);
        const sentBack = rx.status === "changes_requested" || rx.status === "rejected";
        const by = rx.doctor_id === patient.attending_doctor_id ? patient.attending_doctor_name : null;
        const note = sentBack
          ? rx.review_comment
            ? t("pharmacy.pharmacistSaid", { comment: rx.review_comment })
            : null
          : rx.override_reason
            ? t("pharmacy.overrideNote", { reason: rx.override_reason })
            : rx.allergy_override
              ? t("doctor.allergyOverride", { name: by ?? rx.doctor_id })
              : rx.care_plan || null;
        const alert = sentBack || !!rx.override_reason || !!rx.allergy_override;
        return (
          <div key={key} className={`${styles.rxGrid} ${styles.tr}`}>
            <div className={styles.medCell}>
              <span dir="auto" className={styles.med}>
                {item.med}
              </span>
              <span className={styles.badgeLine}>
                <RxStatusBadge status={rx.status} urgent={rx.urgent} />
                {rx.status === "validated" && rx.reviewed_by_name ? <span>{t("pharmacy.validatedBy", { name: rx.reviewed_by_name })}</span> : null}
                {successor ? <span>{t("pharmacy.newVersionPending")}</span> : null}
              </span>
              {note ? (
                <span dir="auto" className={styles.note} style={{ color: alert ? "var(--danger)" : "var(--muted)" }}>
                  {note}
                </span>
              ) : null}
            </div>
            <div className={styles.times}>
              {item.times.map((tm) => (
                <span key={tm} className={styles.time}>
                  {tm}
                </span>
              ))}
            </div>
            <div className={styles.slotCell}>
              <span className={styles.cells} aria-hidden="true">
                {[1, 2, 3, 4].map((i) => (
                  <span key={i} className={styles.cell} style={{ background: i === item.slot ? "var(--ink)" : "transparent" }} />
                ))}
              </span>
              <span className={styles.slotLabel}>{item.slot != null ? t("doctor.slotN", { n: item.slot }) : t("doctor.reminderOnly")}</span>
            </div>
            <span className={styles.days}>{left ?? "—"}</span>
            {readOnly ? (
              <span />
            ) : rx.status === "changes_requested" ? (
              <button type="button" className={`${styles.edit} ${styles.resubmit}`} onClick={() => startEdit(rx, index)}>
                {t("pharmacy.editAndResubmit")}
              </button>
            ) : rx.status === "validated" && !successor ? (
              <button type="button" className={styles.edit} onClick={() => startEdit(rx, index)}>
                {t("doctor.edit")}
              </button>
            ) : (
              <span />
            )}
          </div>
        );
      })}

      {readOnly ? null : (
        <div id={formId} className={styles.form}>
          <span className={styles.formTitle}>
            {ed ? t("pharmacy.editingTitle", { med: ed.rx.items[ed.index]?.med ?? "" }) : t("doctor.newRx")}
          </span>
          {ed ? (
            <div className={styles.editBanner}>
              <span>{t("pharmacy.editingHint")}</span>
              {ed.rx.review_comment ? (
                <b dir="auto">{t("pharmacy.pharmacistSaid", { comment: ed.rx.review_comment })}</b>
              ) : null}
            </div>
          ) : null}
          <div className={styles.formRow}>
            <div className={styles.field}>
              <span id={`${formId}-drug`} className={styles.fieldLabel}>
                {t("pharmacy.drugLabel")}
              </span>
              <DrugPicker key={formKey} labelId={`${formId}-drug`} value={draft.choice} invalid={!!errors.med || criticalHere} onChange={(c) => set("choice", c)} />
              {errors.med ? (
                <span role="alert" className={styles.fieldError}>
                  {t("pharmacy.pickDrug")}
                </span>
              ) : null}
            </div>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>{t("doctor.numberOfDays")}</span>
              <span className={styles.stepper}>
                <button type="button" onClick={() => set("days", Math.max(1, draft.days - 1))} aria-label={t("doctor.fewerDays")} className={styles.step}>
                  −
                </button>
                <span className={styles.stepValue}>{draft.days}</span>
                <button type="button" onClick={() => set("days", Math.min(90, draft.days + 1))} aria-label={t("doctor.moreDays")} className={styles.step}>
                  +
                </button>
              </span>
            </label>
          </div>
          <div className={styles.formRow}>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>{t("pharmacy.doseMg")}</span>
              <input
                dir="ltr"
                inputMode="decimal"
                className={styles.input}
                value={draft.doseMg}
                placeholder={t("pharmacy.doseHint")}
                aria-invalid={errors.dose || undefined}
                onChange={(e) => set("doseMg", e.target.value)}
              />
              {errors.dose ? (
                <span role="alert" className={styles.fieldError}>
                  {t("pharmacy.errDose")}
                </span>
              ) : null}
            </label>
            <div className={styles.field}>
              <span id={`${formId}-units`} className={styles.fieldLabel}>
                {t("pharmacy.unitsPerIntake")}
              </span>
              <span className={styles.stepper} role="group" aria-labelledby={`${formId}-units`}>
                <button type="button" className={styles.step} aria-label={t("pharmacy.fewerUnits")} onClick={() => set("units", Math.max(1, draft.units - 1))}>
                  −
                </button>
                <span className={styles.stepValue}>{draft.units}</span>
                <button type="button" className={styles.step} aria-label={t("pharmacy.moreUnits")} onClick={() => set("units", Math.min(MAX_UNITS, draft.units + 1))}>
                  +
                </button>
              </span>
            </div>
          </div>
          {checkReq ? (
            <div className={styles.checkPanel} aria-live="polite">
              <span className={styles.checkHead}>
                {t("pharmacy.checksTitle")}
                {check.checking ? <span className={styles.checkLead}>{t("pharmacy.checking")}</span> : null}
              </span>
              {check.failed ? (
                <span className={styles.checkFailed}>{t("pharmacy.checkFailed")}</span>
              ) : check.checks ? (
                <CheckList checks={check.checks} items={checkReq.items} emptyText={t("pharmacy.noWarnings")} />
              ) : null}
              <span className={styles.checkLead}>{t("pharmacy.checksLead")}</span>
            </div>
          ) : null}
          {needsOverride ? (
            <label className={styles.field}>
              <span className={styles.fieldLabel}>{t("pharmacy.overrideLabel")}</span>
              <textarea
                rows={2}
                dir="auto"
                maxLength={OVERRIDE_MAX}
                value={draft.override}
                className={`${styles.textarea} ${styles.overrideBox}`}
                aria-invalid={errors.override || undefined}
                onChange={(e) => set("override", e.target.value)}
              />
              {errors.override ? (
                <span role="alert" className={styles.fieldError}>
                  {t("pharmacy.overrideRequired")}
                </span>
              ) : null}
            </label>
          ) : null}
          <div className={styles.group}>
            <span id={`${formId}-times`} className={styles.fieldLabel}>
              {t("doctor.timesOfDay")}
            </span>
            <div className={styles.chips} role="group" aria-labelledby={`${formId}-times`} aria-describedby={errors.times ? `${formId}-times-error` : undefined}>
              {TIME_CHIPS.map((tm) => {
                const on = draft.times.includes(tm);
                return (
                  <button
                    key={tm}
                    type="button"
                    aria-pressed={on}
                    onClick={() => {
                      set("times", on ? draft.times.filter((x) => x !== tm) : [...draft.times, tm]);
                      if (!on) setErrors((e) => ({ ...e, times: false }));
                    }}
                    className={`${styles.chip} ${sel(on)}`}
                  >
                    {tm}
                  </button>
                );
              })}
            </div>
            {errors.times ? (
              <span id={`${formId}-times-error`} role="alert" className={styles.fieldError}>
                {t("doctor.pickOneTime")}
              </span>
            ) : null}
          </div>
          <div className={styles.group}>
            <span className={styles.fieldLabel}>{t("doctor.pillSlotOnUnit")}</span>
            <div className={styles.slots}>
              {SLOTS.map((k) => {
                const taken = k !== "r" && !!slotMeds[k];
                const on = pickedSlot === k;
                return (
                  <button
                    key={k}
                    type="button"
                    disabled={taken}
                    aria-pressed={on}
                    onClick={() => !taken && set("slot", k)}
                    className={`${styles.slot} ${taken ? styles.taken : sel(on)}`}
                  >
                    <span className={styles.slotName}>{k === "r" ? t("doctor.reminderOnly") : t("doctor.slotN", { n: k })}</span>
                    <span className={styles.slotSub}>
                      {k === "r" ? t("doctor.noPillLoaded") : taken ? t("doctor.inUse", { med: slotMeds[k] ?? "" }) : t("doctor.slotEmpty")}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t("doctor.carePlanNote")}</span>
            <textarea rows={2} value={draft.plan} onChange={(e) => set("plan", e.target.value)} dir="auto" className={styles.textarea} />
          </label>
          <label className={styles.urgentRow}>
            <input type="checkbox" checked={draft.urgent} onChange={(e) => set("urgent", e.target.checked)} />
            <span className={styles.urgentText}>
              {t("pharmacy.urgentLabel")}
              <span className={styles.urgentHint}>{t("pharmacy.urgentHint")}</span>
            </span>
          </label>
          <div className={styles.formBar}>
            <span className={styles.formHint}>{patient.device_id ? t("doctor.hintWithDevice", { id: patient.device_id }) : t("doctor.hintNoDevice")}</span>
            <button type="button" onClick={reset} className={styles.secondary}>
              {t("doctor.cancel")}
            </button>
            <button type="button" onClick={() => void save()} disabled={saving} className={styles.primary}>
              {t("doctor.saveRx")}
            </button>
          </div>
        </div>
      )}
      {toast ? (
        <Toast tone={toast.tone} className={styles.toast}>
          {toast.body}
        </Toast>
      ) : null}
    </section>
  );
}

export default Prescriptions;
```

The `doctor.ruleTitle`/`doctor.ruleBody` keys are no longer used. Leave them, because removing keys from `doctor.ts` is out of scope.

- [ ] **Step 5: Update `web/src/components/doctor/Prescriptions.module.css`**

Change the `.rxGrid` columns, so "Edit and resubmit" fits:

```css
.rxGrid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 190px 150px 90px minmax(60px, max-content);
  gap: 14px;
}
```

Append:

```css
/* ── Pharmacy (spec 2026-10-10 §6) ──────────────────────────────────────── */
.badgeLine { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; font-size: 13px; color: var(--muted); }
.resubmit { color: var(--danger-ink); white-space: nowrap; }
.editBanner { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border-radius: 10px; background: var(--teal-tint); border: 1px solid var(--teal-line); font-size: 14px; color: var(--ink); }
.picker { position: relative; }
.picker .input { width: 100%; }
.inputBad { border-color: var(--danger); }
.listbox { position: absolute; z-index: 20; inset-inline: 0; top: calc(100% + 4px); max-height: 320px; overflow-y: auto; margin: 0; padding: 4px; list-style: none; background: var(--paper); border: 1px solid var(--line-strong); border-radius: 10px; box-shadow: var(--drawer-shadow); }
.option { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: 8px; cursor: pointer; }
.optionOn { background: var(--teal-tint); }
.optMain { font-size: 15px; font-weight: 600; color: var(--ink); }
.optSub { font-size: 13px; color: var(--muted); }
.checkPanel { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 10px; background: var(--canvas); }
.checkHead { display: flex; align-items: center; gap: 10px; font-size: 14px; font-weight: 600; color: var(--ink); }
.checkLead { font-size: 13px; font-weight: 400; color: var(--muted); }
.checkFailed { font-size: 14px; color: var(--warn-ink); }
.overrideBox { border-color: var(--danger); }
.urgentRow { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; cursor: pointer; }
.urgentRow input { width: 20px; height: 20px; margin-top: 2px; }
.urgentText { display: flex; flex-direction: column; gap: 2px; font-size: 15px; font-weight: 600; color: var(--ink); }
.urgentHint { font-size: 13px; font-weight: 400; color: var(--muted); }
```

- [ ] **Step 6: Update `web/src/components/doctor/PatientDetail.tsx` (live status for the doctor)**

Add `import { useLiveRefresh } from "@/lib/live";`. Then replace `refreshRx` with a version that can run quietly, and subscribe to the frames:

```ts
  const refreshRx = useCallback(
    async (quiet = false) => {
      try {
        const [prescriptions, doses] = await Promise.all([getPrescriptions(id), dosesOrEmpty(id)]);
        setData((d) => (d ? { ...d, prescriptions, doses } : d));
      } catch {
        if (!quiet) showNoteError(t("doctor.rxRefreshError"));
      }
    },
    [id, showNoteError, t],
  );

  // The pharmacist's decisions arrive as prescription_status frames (or every 15 s without a socket).
  useLiveRefresh(
    (frame) => {
      if (!frame || (frame.type === "prescription_status" && frame.data.patient_id === id)) void refreshRx(true);
    },
    ["prescription_status"],
    { enabled: !!data },
  );
```

`onSaved={() => void refreshRx()}` stays as it is.

- [ ] **Step 7: Run the type check and the mock build**

Run: `npx tsc --noEmit`, then `NEXT_PUBLIC_USE_MOCKS=1 npm run build`.
Expected: both pass.

- [ ] **Step 8: Run the mock-mode scenarios (`npm run dev`)**

1. **The list.** Open `/doctor/patients/p-0001`:
   - "Amoxicillin 1 g" shows "Awaiting pharmacist";
   - the running rows show "Validated" with "by Pharm. Salma";
   - Amoxicillin 1g (rx-0002) shows "Sent despite a warning: Mild rash in 2019…" in red;
   - the header counts 4 active.
2. **Live checks.** Type `amox` in Medicine: the options are "Amoxicillin 1 g", "Amoxicillin 500 mg" and "Non-formulary drug: use this name / amox". Pick Amoxicillin 1 g. Within about half a second the panel shows:
   - **Critical** "Allergy: the patient is allergic to penicillin (penicillin).";
   - **Major** "Duplicate therapy with Amoxicillin 1g.";
   - the override box appears, and the picker border turns red.
   - Save with an empty reason: "Give a reason to send it anyway." Type a reason and Save: the toast reads "Sent to the pharmacist.", and a second "Awaiting pharmacist" row appears.
3. **Clean drug.** Pick Azithromycin 250 mg at 08:00 and 20:00: "No warnings", and no override box. Then set the dose to `abc`: "Use a dose above 0 mg…".
4. **Non-formulary.** Type `Herbal X` and pick the non-formulary option: Moderate "Not in the hospital formulary."
5. **Urgent.** Pick Paracetamol 1 g at 22:00, tick "Urgent: start now" and Save:
   - the toast reads "Urgent: doses started. … bsu-001 …";
   - the row badge reads "Urgent · started, awaiting pharmacist" (red);
   - the doses timeline shows 22:00.
6. **Edit and resubmit.** Open `/doctor/patients/p-0004`:
   - "Metformin 1000 mg" shows "Changes requested", the pharmacist's comment in red, and "Edit and resubmit".
   - Click it: the form title reads "New version of Metformin 1000 mg", the comment is in the banner, and the times are pre-filled with 4 chips.
   - Untick 12:00 and 22:00, then Save. The old row disappears and a new "Awaiting pharmacist" row appears.
   - In `/pharmacist` it shows "version 2" and "Replaces: Metformin 1000 mg".
7. **Edit a validated row.** On p-0001, click "Edit" on Warfarin, change the times and Save:
   - the Warfarin v1 row shows "New version awaiting the pharmacist", with no Edit button;
   - after the pharmacist validates the new version in `/pharmacist`, v1 disappears from the doctor list (superseded).
8. **Slow reply (Review Focus 5).** Temporarily wrap the mock branch of `checkPrescription` in `api.ts`:
   ```ts
   return new Promise((r) => setTimeout(r, req.items.some((i) => i.med.startsWith("Amox")) ? 1500 : 0)).then(() => mock((s) => { /* …unchanged… */ }));
   ```
   Pick Amoxicillin 1 g, then within one second pick Azithromycin 250 mg. Expected:
   - the panel ends at "No warnings" and stays there when the late Amoxicillin reply lands;
   - the override box disappears.
   **Revert the change.**
9. **Arabic.** In العربية, the picker list aligns to the right, the critical check's red edge is on the right, and `08:00` stays as is.

- [ ] **Step 9: Commit**

```bash
git add web/src/components/doctor web/src/i18n/messages/pharmacy.ts
git commit -m "feat(web): doctor prescription form with formulary picker, live checks, override and urgent start"
```

---

## Task 6: Nurse "pending pharmacy review" badge

**Files:**
- Create: `web/src/components/nurse/PharmacyBadge.tsx`, `web/src/components/nurse/PharmacyBadge.module.css`.
- Modify:
  - `web/src/components/nurse/nurse.ts`;
  - `web/src/components/nurse/MedRound.tsx`;
  - `web/src/components/nurse/NursePatientDetail.tsx`;
  - `web/src/i18n/messages/pharmacy.ts`.

**Interfaces:**
- Consumes: `isPendingUrgent` and `isRunning` (Task 1). `MedRound` already loads `getPrescriptions` per patient into a `Map`.
- Produces: `DoseView.pendingReview: boolean` (`nurse.ts`) and `export function PendingReviewBadge(): JSX.Element` (`nurse/PharmacyBadge.tsx`). Task 12 adds `DosePharmacyNote` to the same file.

- [ ] **Step 1: Add the i18n key (append)**

- `en`: `pendingReview: "Pending pharmacy review",`
- `fr`: `pendingReview: "En attente de validation par la pharmacie",`
- `ar`: `pendingReview: "بانتظار مراجعة الصيدلية",`

- [ ] **Step 2: Extend `doseView` (`web/src/components/nurse/nurse.ts`)**

Add `import { isPendingUrgent } from "@/lib/pharmacy";`. In `interface DoseView`, after `by: string;`:

```ts
  /** The dose comes from an urgent prescription the pharmacist hasn't reviewed yet (spec §6). */
  pendingReview: boolean;
```

In `doseView()`'s returned object, after `by,`:

```ts
    pendingReview: isPendingUrgent(ctx.prescriptions?.get(dose.prescription_id)),
```

- [ ] **Step 3: Create the badge**

`web/src/components/nurse/PharmacyBadge.tsx`:

```tsx
"use client";

// Small pharmacy notes on the nurse's dose rows. "Pending pharmacy review": an urgent prescription
// whose doses already go out while the pharmacist hasn't reviewed it (spec §2 urgent bypass).
import { useT } from "@/i18n/I18nProvider";
import styles from "./PharmacyBadge.module.css";

export function PendingReviewBadge() {
  const { t } = useT();
  return <span className={`${styles.badge} ${styles.pending}`}>{t("pharmacy.pendingReview")}</span>;
}
```

`web/src/components/nurse/PharmacyBadge.module.css`:

```css
.badge {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font: 600 12px/1.3 var(--sans);
  white-space: nowrap;
}

.pending {
  background: var(--warn-bg);
  color: var(--warn-ink);
  border: 1px solid var(--warn-line);
}
```

- [ ] **Step 4: Show it on the med round and the nurse's patient page**

`MedRound.tsx`: import `PendingReviewBadge` from `./PharmacyBadge`. Inside `<div className={styles.medCol}>`, after the `medSub` span:

```tsx
                        {v.pendingReview ? <PendingReviewBadge /> : null}
```

`NursePatientDetail.tsx`:
- Import `PendingReviewBadge` from `./PharmacyBadge`, and `isPendingUrgent` and `isRunning` from `@/lib/pharmacy`.
- Inside `<div className={styles.doseMed}>`, after the `doseSub` span, add the same `{v.pendingReview ? <PendingReviewBadge /> : null}`.
- In the prescriptions card, the API now returns every version, so show only running ones. Replace the `noRx` line and the `data.prescriptions.flatMap(…)` block with:

```tsx
                {data.prescriptions.filter(isRunning).length === 0 ? <span className={styles.none}>{t("nurse.noRx")}</span> : null}
                {data.prescriptions.filter(isRunning).flatMap((rx) =>
                  rx.items.map((item, i) => (
                    <div key={`${rx.id}-${i}`} className={styles.rxRow}>
                      <span className={styles.rxMed}>{item.med}</span>
                      {isPendingUrgent(rx) ? <PendingReviewBadge /> : null}
                      <span className={styles.rxTimes}>{item.times.join(", ")}</span>
                      <span className={styles.rxSlot}>{item.slot != null ? t("nurse.slot", { n: item.slot }) : t("nurse.reminderOnly")}</span>
                    </div>
                  )),
                )}
```

- [ ] **Step 5: Run the type check and the mock build**

Run: `npx tsc --noEmit`, then `NEXT_PUBLIC_USE_MOCKS=1 npm run build`.
Expected: both pass.

- [ ] **Step 6: Check it by hand in mock mode**

- `/nurse/meds`: Omar's 20:00 "Ibuprofen 400 mg" row shows the amber "Pending pharmacy review" badge; no other row does.
- `/nurse/patients/p-0002`: the same badge on the dose, and on the Ibuprofen line of the prescriptions card.
- `/nurse/patients/p-0003`: the prescriptions card does **not** list the pending, non-urgent "Paracetamol 1 g" (rx-0014).
- In `/pharmacist`, validate Omar's Ibuprofen, then go back to `/nurse/meds` through the app links (the mock store lives in the tab): the badge is gone and the dose stays.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/nurse web/src/i18n/messages/pharmacy.ts
git commit -m "feat(web): nurse badge for doses awaiting pharmacy review"
```

---

## Task 7: Sign-up and admin approval for pharmacists

**Files:**
- Modify:
  - `web/src/lib/types.ts`, `web/src/lib/api.ts` (mock `registerAccount`);
  - `web/src/mocks/accounts.ts`;
  - `web/src/components/auth/RegisterForm.tsx`;
  - `web/src/components/admin/PendingList.tsx`, `web/src/components/admin/StaffView.tsx`;
  - `web/src/i18n/messages/pharmacy.ts`.

**Interfaces:**
- Consumes: `pharmacy.rolePharmacist` (Task 1).
- Produces:
  - `SignupRole = "patient" | "nurse" | "doctor" | "pharmacist"` (so `GrantRole` includes `"pharmacist"`);
  - the admin can grant `pharmacist`; a doctor still grants only `patient` and `nurse` (spec §2).

- [ ] **Step 1: Add the i18n key (append)**

- `en`: `roleHelpPharmacist: "Pharmacists review every prescription with only the allergies and running treatments. They never see notes, exams or vitals.",`
- `fr`: `roleHelpPharmacist: "Les pharmaciens examinent toutes les ordonnances avec seulement les allergies et les traitements en cours. Ils ne voient ni notes, ni examens, ni constantes.",`
- `ar`: `roleHelpPharmacist: "يراجع الصيادلة كل الوصفات مع الحساسية والعلاجات الجارية فقط. لا يرون الملاحظات ولا الفحوص ولا المؤشرات الحيوية.",`

- [ ] **Step 2: Widen the sign-up role and watch the type check fail**

`web/src/lib/types.ts`:

```ts
/** The roles a person can ask for on /register (`admin` is never a sign-up choice). */
export type SignupRole = "patient" | "nurse" | "doctor" | "pharmacist";
```

Update the `RegisterRequest.requested_doctor_id` doc comment to: `/** Patients and nurses only; sending it with role doctor or pharmacist is a 422. */`

Run: `npx tsc --noEmit`
Expected: FAIL at `src/components/admin/PendingList.tsx` (`ROLE_LABEL` misses `pharmacist`).

- [ ] **Step 3: Fix the approval list (`PendingList.tsx`)**

```ts
const ROLE_LABEL: Record<GrantRole, Key> = {
  patient: "shared.rolePatient",
  nurse: "admin.roleNurse",
  doctor: "admin.roleDoctor",
  pharmacist: "pharmacy.rolePharmacist",
  admin: "admin.roleAdmin",
};
/** What each viewer may grant: a doctor approves patients and nurses only; only the admin approves pharmacists (spec §2). */
const GRANTABLE: Record<Viewer, GrantRole[]> = {
  admin: ["patient", "nurse", "doctor", "pharmacist", "admin"],
  doctor: ["patient", "nurse"],
};
```

In `Row`, only patients and nurses pick a doctor, so "No doctor chosen" applies only to them:

```ts
  const chosen = u.requested_doctor_id
    ? t("accounts.pendingWorksWith", { doctor: doctorName ?? u.requested_doctor_id })
    : u.requested_role === "patient" || u.requested_role === "nurse"
      ? t("accounts.pendingNoDoctor")
      : null;
```

- [ ] **Step 4: Update the sign-up form (`RegisterForm.tsx`)**

```ts
/** The four sign-up roles; `admin` is never a sign-up choice. */
const ROLES: { value: SignupRole; label: Key }[] = [
  { value: "patient", label: "shared.rolePatient" },
  { value: "nurse", label: "admin.roleNurse" },
  { value: "doctor", label: "admin.roleDoctor" },
  { value: "pharmacist", label: "pharmacy.rolePharmacist" },
];
```

After `const set = …`, add `const picksDoctor = role === "patient" || role === "nurse";`. Then replace both `role !== "doctor"` conditions:

```ts
        // Doctors and pharmacists don't pick a doctor; the server rejects the combination.
        ...(picksDoctor && f.doctor ? { requested_doctor_id: f.doctor } : {}),
```

```tsx
        {picksDoctor && doctors.length ? (
```

- [ ] **Step 5: Update the mocks and the Staff panel**

`web/src/lib/api.ts`, in the mock `registerAccount`:

```ts
      if ((req.role === "doctor" || req.role === "pharmacist") && req.requested_doctor_id)
        throw new ApiError(422, "validation_error", "Doctors and pharmacists don't pick a doctor.");
```

`web/src/mocks/accounts.ts`, `PENDING`: add after Salma Hadded's row:

```ts
  { id: "u-0024", name: "Rim Jebali", email: "r.jebali@example.tn", note: "Pharmacie", requested_role: "pharmacist", requested_doctor_id: null, requested_doctor_name: null, status: "pending", created_at: at(TODAY, "08:05") },
```

`web/src/components/admin/StaffView.tsx`:
- in the add-staff role radiogroup, change the list to `(["doctor", "nurse", "pharmacist", "admin"] as StaffRole[])`;
- in `ROLE_HELP`, add `pharmacist: "pharmacy.roleHelpPharmacist",`.

- [ ] **Step 6: Run the type check and the mock build**

Run: `npx tsc --noEmit`, then `NEXT_PUBLIC_USE_MOCKS=1 npm run build`.
Expected: both pass.

- [ ] **Step 7: Check it by hand in mock mode**

- **Sign-up.** `/register`: the role select lists Patient, Nurse, Doctor, Pharmacist.
  - Picking Pharmacist hides the doctor picker.
  - Submitting a valid form shows the "request received" screen.
- **Admin approval.** `/admin/pending`: "Rim Jebali · Requested role: Pharmacist", with no "No doctor chosen".
  - The select defaults to Pharmacist; Approve shows the approved toast;
  - `/admin/staff` lists her with the amber "Pharmacist" chip.
- **Doctor.** `/doctor/requests`: there is no pharmacist request, and the select offers only Patient and Nurse.
- **Staff panel.** `/admin/staff?add=1`: the role segment shows Doctor, Nurse, Pharmacist, Admin. Picking Pharmacist shows the privacy help line.

- [ ] **Step 8: Commit**

```bash
git add web/src/lib/types.ts web/src/lib/api.ts web/src/mocks/accounts.ts web/src/components/auth/RegisterForm.tsx web/src/components/admin web/src/i18n/messages/pharmacy.ts
git commit -m "feat(web): pharmacist sign-up and admin-only approval"
```

---

## Task 8: Phase A gate (i18n completeness, RTL, privacy, build)

**Files:**
- Modify only what the checks below find (expected: nothing, or small fixes in the files of Tasks 1–7).

**Interfaces:** none new. This task verifies Tasks 1–7 together.

- [ ] **Step 1: Run the type check and the mock build from clean**

Run: `rm -rf .next && npx tsc --noEmit && NEXT_PUBLIC_USE_MOCKS=1 npm run build`
Expected:
- both pass;
- the route list contains `/pharmacist`, `/pharmacist/catalogue`, `/pharmacist/password` and `/admin/catalogue`.

The `messages()` types already fail `tsc` if `fr` or `ar` misses or adds a key.

- [ ] **Step 2: Check placeholder parity (a `{name}` in `en` must appear in `fr` and `ar`, and no value may be empty)**

Run from `web/`:

```bash
node - <<'EOF'
const fs = require("fs");
const src = fs.readFileSync("src/i18n/messages/pharmacy.ts", "utf8");
function block(lang) {
  const start = src.indexOf(`\n  ${lang}: {`);
  if (start < 0) throw new Error(`no ${lang} block`);
  const end = src.indexOf("\n  },", start);
  const out = {};
  for (const m of src.slice(start, end).matchAll(/^ {4}(\w+):\s*"((?:[^"\\]|\\.)*)"/gm)) out[m[1]] = m[2];
  return out;
}
const ph = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");
const en = block("en");
let bad = 0;
for (const lang of ["fr", "ar"]) {
  const msgs = block(lang);
  for (const [k, v] of Object.entries(en)) {
    const o = msgs[k];
    if (o === undefined) { console.log(`${lang}.${k}: missing`); bad++; continue; }
    if (!o.trim()) { console.log(`${lang}.${k}: empty`); bad++; }
    if (ph(o) !== ph(v)) { console.log(`${lang}.${k}: {${ph(o)}} vs en {${ph(v)}}`); bad++; }
  }
}
console.log(`en keys: ${Object.keys(en).length}; problems: ${bad}`);
process.exit(bad ? 1 : 0);
EOF
```

Expected: `problems: 0` and exit 0. On a mismatch, fix the `fr`/`ar` string; never drop a placeholder.

- [ ] **Step 3: Check that the new CSS uses no physical left/right properties (RTL, Review Focus 1)**

```bash
grep -nE "(margin|padding|border)-(left|right)|(^|[^-])(left|right):|text-align: (left|right)" src/components/pharmacist/*.css src/components/shared/Pharmacy.module.css src/components/nurse/PharmacyBadge.module.css src/components/doctor/Prescriptions.module.css
```

Expected: no output (exit 1). Replace any hit with its logical twin (`inset-inline-start`, `margin-inline-end`, `text-align: start`, …).

- [ ] **Step 4: Check pharmacist privacy (Review Focus 3)**

```bash
grep -rnE "getPatient\b|getNotes|getVitals|getPatientExams|getSummary|getDoses|PatientAiCard|NotesPanel|ExamsPanel|VitalsChart|VitalsCard|DosesTimeline|/doctor/patients|/nurse/patients" src/components/pharmacist src/app/pharmacist
grep -n "\.\.\.p\b\|\.\.\.patient\b" src/lib/api.ts | grep -i pharmacy
```

Expected: no output from either command. `pharmacyPatient()` must pick its fields explicitly.

- [ ] **Step 5: Check for string literals in the new JSX**

```bash
grep -nE ">[^<>{}]*[A-Za-z]{3,}[^<>{}]*<" src/components/pharmacist/*.tsx src/components/shared/CheckList.tsx src/components/shared/RxStatusBadge.tsx src/components/doctor/DrugPicker.tsx src/components/doctor/Prescriptions.tsx src/components/nurse/PharmacyBadge.tsx
```

Expected: no output. Every word goes through `t()`.

- [ ] **Step 6: Walk through the app in Arabic (`npm run dev`, choose العربية)**

Visit each screen and tick each item.
- `/pharmacist`:
  - the sidebar is on the right, and the red pill reads `3`;
  - the critical row's red edge is on the right;
  - the chips read حرج / كبير / متوسط;
  - "أُرسلت منذ … د" reads naturally;
  - `C-12` and `08:00 · 14:00` keep their order.
- The review panel:
  - the allergy box is red;
  - "راجعتُ التحذيرات" gates "اعتماد";
  - the dialog is right-aligned, its counter reads `0/500`, and Escape closes it.
- `/pharmacist/catalogue`:
  - the drawer comes in from the left;
  - ATC codes are LTR;
  - an Arabic comma adds a tag.
- `/doctor/patients/p-0001`:
  - the picker list is right-aligned;
  - in the check panel, the critical edge is on the right;
  - the override box accepts Arabic text.
- `/nurse/meds`: the badge reads "بانتظار مراجعة الصيدلية".
- `/register`: the role list shows "صيدلي".

- [ ] **Step 7: Smoke-test real mode (only if the backend branch is up; skip otherwise and say so in the report)**

Run: `NEXT_PUBLIC_USE_MOCKS=0 NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev`.
1. Sign in as `pharmacist@ward.tn` (seed password): you land on `/pharmacist`.
2. DevTools → WS: one `/ws?token=…` socket is open.
3. In another browser, the doctor saves a prescription for a seed patient: within a second, without polling, the pharmacist's list and badge update (`prescription_status` frame).
4. Stop the API: the socket closes, polling resumes every 15 s, and the screens keep their last data.

- [ ] **Step 8: Commit fixes, if any were needed**

```bash
git add web/src
git commit -m "fix(web): pharmacy i18n, RTL and privacy gate fixes"
```

(Skip the commit when Steps 1–7 found nothing.)

---
