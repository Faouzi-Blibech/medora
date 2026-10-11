# Accounts and access: Web Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans; steps use - [ ] checkboxes.

**Goal:** Ship the web screens of the accounts-and-access feature (self sign-up, approval queues, one-time codes, doctor team, patient sharing, change password), working in mock mode first and against the real API unchanged.

**Architecture:** Every call goes through `web/src/lib/api.ts` (real branch = `http()`, mock branch = `mock()` over an extended `MockStore`). Pure helpers (error mapping, code normalisation, password check) live in `web/src/lib/accountsUi.ts`. One new shared component (`CodeDialog`) displays every one-time code; all other screens are thin components over existing page chrome (`AdminPage.module.css`, `page.module.css` login classes, `Toast`, `ErrorCard`, `RoleShell`).

**Tech Stack:** Next.js 16 App Router, React 19, strict TypeScript, CSS Modules, typed i18n (`messages()` in `web/src/i18n/define.ts`: `fr` and `ar` must carry exactly the keys of `en` or `tsc` fails).

**Spec:** `docs/superpowers/specs/2026-10-10-accounts-and-access-design.md` (sections 6, 9, 10).

## Global Constraints

- Build only against the fixed API contract in the dispatch brief; no new endpoints. Gaps are listed at the end of this plan, not worked around silently.
- A one-time code lives only in React state of the component that fetched it: never in `localStorage`, `sessionStorage`, cookies, URL, query cache or logs.
- Every user-visible string goes through `t()` in `fr`, `ar` and `en`; no string literal in JSX.
- Layout uses logical properties (`margin-inline-start`, `inset-inline-*`, `text-align: start`); codes, emails and passwords are `dir="ltr"`; names are `dir="auto"`.
- Components never import `@/mocks` directly; only `api.ts` does (existing rule).
- Every API error code in the contract maps to a localized message; unknown codes fall back to a generic message, never to raw English `detail` (except the weak-password reason, shown as secondary text).
- Reuse existing classes and components; add CSS only for genuinely new elements.
- No test runner exists in `web/` (scripts: `dev`, `build`, `start`, `typecheck`; no lint, no vitest/jest). Do not add one. Verification per task = `npm run typecheck` + `npm run build` + the manual steps listed.
- Commits: Conventional Commits, `feat(web): ...`, no AI attribution lines or trailers (CLAUDE.md rule).
- Run all commands from `C:/Users/MSI/Desktop/HackCure/smarty-hospital-/web`.

## Review Focus

1. **Code lost or leaked.** The one-time code disappears on refresh/navigation (accepted, but the user must be warned: `beforeunload` guard while the dialog is open) and must not be persisted anywhere. Check the copy fallback on plain-HTTP LAN installs (`navigator.clipboard` is undefined outside HTTPS).
2. **RTL layout of the code display.** In Arabic the `XXXXX-XXXXX` string must not reorder or have its dash move; the code, email and password inputs must be `dir="ltr"`; the print sheet must read correctly in `ar`.
3. **Error code with no message mapping.** Every code in the brief (`weak_password`, `invalid_code`, `already_enrolled`, `rate_limited`, `bad_credentials`, `account_pending|disabled|rejected|locked`) must show localized text in all three languages; a network failure (`TypeError`, not `ApiError`) and an unknown code must still show something sensible.
4. **Account enumeration in the UI.** Register must show the identical success screen for every 202 (new email, existing email, valid or invalid enrollment code is not distinguishable except by the documented errors); login 401 must stay a single "wrong email or password" message; do not echo whether the email exists anywhere.
5. **Wrong buttons for the wrong actor.** A doctor must never see role/ward pickers or approve as anything but nurse; "Issue enrollment code" and "Share" only for the attending doctor/admin (a doctor holding a grant gets 403); admins must not be offered "Disable" on their own row; double clicks must not issue two codes (issuing revokes the previous one).

## File Structure

Create:
- `web/src/lib/accountsUi.ts` - error mapping, `normalizeCode`, `passwordProblem`, `fmtWhen`
- `web/src/mocks/accounts.ts` - fixtures and `generateCode` for the mock store
- `web/src/i18n/messages/auth.ts` - namespace `auth` (public screens, errors, change password)
- `web/src/i18n/messages/accounts.ts` - namespace `accounts` (codes, pending, team, sharing, statuses)
- `web/src/components/auth/Auth.module.css`
- `web/src/components/auth/AuthFrame.tsx`
- `web/src/components/auth/RegisterForm.tsx`
- `web/src/components/auth/ResetForm.tsx`
- `web/src/components/auth/ChangePasswordForm.tsx`
- `web/src/components/auth/ChangePasswordPage.tsx`
- `web/src/app/register/page.tsx`
- `web/src/app/reset/page.tsx`
- `web/src/app/admin/password/page.tsx`, `web/src/app/doctor/password/page.tsx`, `web/src/app/nurse/password/page.tsx`, `web/src/app/patient/password/page.tsx`
- `web/src/components/shared/CodeDialog.tsx`, `web/src/components/shared/CodeDialog.module.css`
- `web/src/components/admin/PendingList.tsx`, `web/src/components/admin/PendingList.module.css`
- `web/src/components/admin/PendingView.tsx`
- `web/src/app/admin/pending/page.tsx`
- `web/src/components/doctor/TeamView.tsx`, `web/src/components/doctor/TeamView.module.css`
- `web/src/app/doctor/team/page.tsx`
- `web/src/components/shared/EnrollmentCode.tsx`
- `web/src/components/shared/ShareWithDoctor.tsx`
- `web/src/components/shared/AccessPanel.tsx`, `web/src/components/shared/AccessPanel.module.css`
- `web/src/components/admin/PatientLookup.tsx`
- `web/src/app/admin/patients/page.tsx`

Modify:
- `web/src/lib/types.ts` (new types, `StaffMember.status`)
- `web/src/lib/api.ts` (new functions, mock branches, 401 handling)
- `web/src/mocks/index.ts`, `web/src/mocks/people.ts` (store fields, staff status)
- `web/src/i18n/messages/index.ts` (register 2 namespaces)
- `web/src/components/LoginForm.tsx`, `web/src/app/page.tsx`
- `web/src/components/Sidebar.tsx` (nav items)
- `web/src/components/patient/PatientScreen.tsx` (patient menu link)
- `web/src/components/admin/StaffView.tsx`, `web/src/components/admin/StaffView.module.css`, `web/src/components/admin/wards.ts`
- `web/src/components/doctor/PatientDetail.tsx`
- `web/src/app/globals.css` (print rules)

---

## Task 1: Types, API client, mocks

**Files:** modify `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/mocks/index.ts`, `web/src/mocks/people.ts`; create `web/src/mocks/accounts.ts`.

**Interfaces produced** (all exported from `@/lib/api` unless noted; types from `@/lib/types`):

```ts
registerAccount(req: RegisterRequest): Promise<RegisterResponse>
resetPassword(req: ResetRequest): Promise<void>
changePassword(req: ChangePasswordRequest): Promise<void>
getDoctorDirectory(): Promise<DoctorRef[]>
listUsers(status: "pending" | "rejected", opts?: ViewerOpts): Promise<PendingUser[]>
approveUser(id: string, req: ApproveRequest, opts?: ViewerOpts): Promise<UserAdmin>
rejectUser(id: string, opts?: ViewerOpts): Promise<UserAdmin>
disableUser(id: string, opts?: ViewerOpts): Promise<UserAdmin>
enableUser(id: string, opts?: ViewerOpts): Promise<UserAdmin>
issueResetCode(userId: string): Promise<OneTimeCode>
getMyTeam(): Promise<UserAdmin[]>
issueEnrollmentCode(patientId: string): Promise<OneTimeCode>
getPatientAccess(patientId: string): Promise<PatientAccessGrant[]>
grantPatientAccess(patientId: string, req: { doctor_id: string; expires_at?: string }): Promise<PatientAccessGrant>
revokePatientAccess(patientId: string, doctorId: string): Promise<void>
interface ViewerOpts { as?: "admin" | "doctor" }   // mock mode only, like ActorOpts
```

- [ ] **1.1 Add types.** In `web/src/lib/types.ts`, replace the `StaffMember` interface (section "Devices and staff") and append the new block after it:

```ts
/** GET /staff — NOT in api.md 1.4 (admin "Staff" screen). `status` arrives with api.md 1.9. */
export interface StaffMember {
  id: string; // u-0001
  name: string;
  email: string;
  role: Exclude<Role, "patient">;
  ward: string | null; // data-model staff.ward
  scope: string; // "Cardiology · Ward C"
  last_login_at: string | null;
  status: AccountStatus;
}

// ── Accounts and access (api.md 1.9) ────────────────────────────────────────

export type AccountStatus = "pending" | "active" | "disabled" | "rejected";

export interface RegisterRequest {
  name: string;
  email: string;
  password: string;
  note?: string;
  requested_doctor_id?: string;
  enrollment_code?: string;
}
export interface RegisterResponse {
  status: "received";
  detail: string;
}
export interface ResetRequest {
  email: string;
  code: string;
  new_password: string;
}
export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}
export interface DoctorRef {
  id: string;
  name: string;
}
/** GET /users?status=pending|rejected */
export interface PendingUser {
  id: string;
  name: string;
  email: string;
  note: string | null;
  requested_doctor_id: string | null;
  requested_doctor_name: string | null;
  status: "pending" | "rejected";
  created_at: string;
}
export interface ApproveRequest {
  role: "doctor" | "nurse" | "admin";
  ward?: string | null;
}
export interface UserAdmin {
  id: string;
  name: string;
  email: string;
  role: Exclude<Role, "patient"> | null;
  status: AccountStatus;
  ward: string | null;
  supervisor_id: string | null;
}
/** Shown once to the issuer; never stored by the UI. */
export interface OneTimeCode {
  code: string; // "K7M2Q-9XR4T"
  expires_at: string;
}
export interface PatientAccessGrant {
  patient_id: string;
  doctor_id: string;
  doctor_name: string;
  expires_at: string;
}
```

- [ ] **1.2 Mock fixtures.** Create `web/src/mocks/accounts.ts`:

```ts
// Accounts-and-access fixtures. Synthetic. Magic codes let a reviewer exercise every error path.
import type { DoctorRef, PatientAccessGrant, PendingUser, UserAdmin } from "@/lib/types";
import { at, TODAY } from "./time";

/** Codes the mock API understands (anything else is "invalid_code"). */
export const MOCK_CODES = {
  enroll: "K7M2Q-9XR4T", // valid patient enrollment code
  enrollTaken: "HHHHH-HHHHH", // 409 already_enrolled
  reset: "R3SET-7PW2X", // valid reset code
  wrongPassword: "wrong", // changePassword: this current password → 401 bad_credentials
} as const;

const ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"; // 31 symbols, no 0/O/1/I/L

/** A fresh `XXXXX-XXXXX` code, like the backend's. */
export function generateCode(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(10));
  const s = Array.from(bytes, (b) => ALPHABET[b % ALPHABET.length]).join("");
  return `${s.slice(0, 5)}-${s.slice(5)}`;
}

export const DOCTOR_DIRECTORY: DoctorRef[] = [
  { id: "u-0001", name: "Dr Trabelsi" },
  { id: "u-0010", name: "Dr Ben Romdhane" },
  { id: "u-0011", name: "Dr Karoui" },
];

export const PENDING: PendingUser[] = [
  { id: "u-0020", name: "Amel Cherif", email: "a.cherif@example.tn", note: "nurse, Cardiology", requested_doctor_id: "u-0001", requested_doctor_name: "Dr Trabelsi", status: "pending", created_at: at(TODAY, "08:20") },
  { id: "u-0021", name: "Karim Zouari", email: "k.zouari@example.tn", note: "doctor, Pulmonology", requested_doctor_id: null, requested_doctor_name: null, status: "pending", created_at: at(TODAY, "07:55") },
  { id: "u-0022", name: "Salma Hadded", email: "s.hadded@example.tn", note: null, requested_doctor_id: "u-0010", requested_doctor_name: "Dr Ben Romdhane", status: "pending", created_at: at(TODAY, "07:10") },
  { id: "u-0023", name: "Test Person", email: "t.person@example.tn", note: "assistant", requested_doctor_id: "u-0001", requested_doctor_name: "Dr Trabelsi", status: "rejected", created_at: at("2026-10-03", "16:00") },
];

/** Dr Trabelsi's team (consistent with STAFF: Ines active, Sami disabled). */
export const TEAM: UserAdmin[] = [
  { id: "u-0002", name: "Nurse Ines", email: "i.mejri@hr-medora.tn", role: "nurse", status: "active", ward: "Cardiology", supervisor_id: "u-0001" },
  { id: "u-0004", name: "Nurse Sami", email: "s.dridi@hr-medora.tn", role: "nurse", status: "disabled", ward: "Cardiology", supervisor_id: "u-0001" },
];

export const GRANTS: Record<string, PatientAccessGrant[]> = {
  "p-0002": [{ patient_id: "p-0002", doctor_id: "u-0011", doctor_name: "Dr Karoui", expires_at: at("2026-11-04", "23:59") }],
};
```

- [ ] **1.3 Staff status in fixtures.** In `web/src/mocks/people.ts` change the STAFF declaration so rows keep their shape and gain `status` (Sami is the disabled demo account):

```ts
const STAFF_ROWS: Omit<StaffMember, "status">[] = [
  // ...the six existing rows, unchanged...
];
const DISABLED_DEMO = new Set(["u-0004"]);
export const STAFF: StaffMember[] = STAFF_ROWS.map((s) => ({ ...s, status: DISABLED_DEMO.has(s.id) ? "disabled" : "active" }));
```

(Change only the first line `export const STAFF: StaffMember[] = [` to `const STAFF_ROWS: Omit<StaffMember, "status">[] = [` and add the last two statements after the closing `];`.)

- [ ] **1.4 Extend the mock store.** In `web/src/mocks/index.ts`: add imports and exports, new store fields and seeds.

```ts
import type { /* existing..., */ DoctorRef, PatientAccessGrant, PendingUser, UserAdmin } from "@/lib/types";
import { DOCTOR_DIRECTORY, GRANTS, PENDING, TEAM } from "./accounts";
export { MOCK_CODES, generateCode } from "./accounts";
```

In `MockStore` add:

```ts
  directory: DoctorRef[];
  pending: PendingUser[];
  team: UserAdmin[];
  grants: Record<string, PatientAccessGrant[]>;
```

Change `seq` to `{ rx: number; dose: number; note: number; user: number }`. In `createStore()` add `directory: DOCTOR_DIRECTORY, pending: PENDING, team: TEAM, grants: GRANTS,` and `user: 100` to `seq`.

- [ ] **1.5 API functions.** In `web/src/lib/api.ts`: extend the `./types` import with `AccountStatus, ApproveRequest, ChangePasswordRequest, DoctorRef, OneTimeCode, PatientAccessGrant, PendingUser, RegisterRequest, RegisterResponse, ResetRequest, UserAdmin`; extend the mocks import with `generateCode, MOCK_CODES`. Insert this block after `getMeCached` (end of the Auth section):

```ts
// ── Accounts and access (api.md 1.9) ────────────────────────────────────────

/** Mock mode only: whose view a call is made from. The real API reads the JWT. */
export interface ViewerOpts {
  as?: "admin" | "doctor";
}

const enc = encodeURIComponent;
const mockCode = (): OneTimeCode => ({ code: generateCode(), expires_at: iso(new Date(now().getTime() + 48 * 3_600_000)) });

function userAdmin(s: MockStore, id: string): UserAdmin {
  const t = s.team.find((u) => u.id === id);
  if (t) return t;
  const m = s.staff.find((u) => u.id === id) ?? notFound(`User ${id}`);
  return { id: m.id, name: m.name, email: m.email, role: m.role, status: m.status, ward: m.ward, supervisor_id: null };
}

function setStatus(s: MockStore, id: string, status: AccountStatus, as: "admin" | "doctor"): UserAdmin {
  const member = s.team.find((u) => u.id === id);
  if (as === "doctor" && !member) throw new ApiError(403, "forbidden", "Not on your team");
  const row = s.staff.find((u) => u.id === id);
  if (!member && !row) notFound(`User ${id}`);
  if (member) member.status = status;
  if (row) row.status = status;
  return userAdmin(s, id);
}

/** POST /auth/register → always the same generic 202. Mock: weak password → 422; enrollment codes per MOCK_CODES. */
export function registerAccount(req: RegisterRequest): Promise<RegisterResponse> {
  if (USE_MOCKS)
    return mock((s) => {
      if (req.password.length < 10) throw new ApiError(422, "weak_password", "Password must be at least 10 characters.");
      if (req.enrollment_code) {
        const c = req.enrollment_code.toUpperCase();
        if (c === MOCK_CODES.enrollTaken) throw new ApiError(409, "already_enrolled", "This patient already has an account.");
        if (c !== MOCK_CODES.enroll) throw new ApiError(400, "invalid_code", "Invalid or expired code.");
      } else if (!s.pending.some((p) => p.email === req.email)) {
        s.seq.user += 1;
        s.pending.push({
          id: `u-${String(s.seq.user).padStart(4, "0")}`,
          name: req.name,
          email: req.email,
          note: req.note ?? null,
          requested_doctor_id: req.requested_doctor_id ?? null,
          requested_doctor_name: s.directory.find((d) => d.id === req.requested_doctor_id)?.name ?? null,
          status: "pending",
          created_at: iso(now()),
        });
      }
      return { status: "received" as const, detail: "If the details are valid, your account was created or is waiting for approval." };
    });
  return http<RegisterResponse>("POST", "/auth/register", req);
}

/** POST /auth/reset → 204. */
export function resetPassword(req: ResetRequest): Promise<void> {
  if (USE_MOCKS)
    return mock(() => {
      if (req.code.toUpperCase() !== MOCK_CODES.reset) throw new ApiError(400, "invalid_code", "Invalid or expired code.");
      if (req.new_password.length < 10) throw new ApiError(422, "weak_password", "Password must be at least 10 characters.");
    });
  return http<void>("POST", "/auth/reset", req);
}

/** POST /auth/change-password (Bearer) → 204. */
export function changePassword(req: ChangePasswordRequest): Promise<void> {
  if (USE_MOCKS)
    return mock(() => {
      if (req.current_password === MOCK_CODES.wrongPassword) throw new ApiError(401, "bad_credentials", "Wrong password");
      if (req.new_password.length < 10) throw new ApiError(422, "weak_password", "Password must be at least 10 characters.");
    });
  return http<void>("POST", "/auth/change-password", req);
}

/** GET /doctors/directory (no auth): ids and names only. */
export function getDoctorDirectory(): Promise<DoctorRef[]> {
  if (USE_MOCKS) return mock((s) => s.directory);
  return http<DoctorRef[]>("GET", "/doctors/directory");
}

/** GET /users?status= (admin: all; doctor: requests naming him). Mock doctor = Dr Trabelsi. */
export function listUsers(status: "pending" | "rejected", opts: ViewerOpts = {}): Promise<PendingUser[]> {
  if (USE_MOCKS)
    return mock((s) =>
      s.pending.filter((u) => u.status === status && (opts.as !== "doctor" || u.requested_doctor_id === USERS.doctor.id)),
    );
  return http<PendingUser[]>("GET", `/users?status=${status}`);
}

/** POST /users/{id}/approve. A doctor may only send role "nurse" (ward ignored). */
export function approveUser(id: string, req: ApproveRequest, opts: ViewerOpts = {}): Promise<UserAdmin> {
  if (USE_MOCKS)
    return mock((s) => {
      const as = opts.as ?? "admin";
      const p = s.pending.find((u) => u.id === id) ?? notFound(`User ${id}`);
      if (as === "doctor" && req.role !== "nurse") throw new ApiError(403, "forbidden", "A doctor can only approve nurses.");
      const ward = as === "doctor" ? null : (req.ward ?? null);
      s.pending = s.pending.filter((u) => u.id !== id);
      s.staff.push({ id: p.id, name: p.name, email: p.email, role: req.role, ward, scope: ward ?? "—", last_login_at: null, status: "active" });
      const out: UserAdmin = { id: p.id, name: p.name, email: p.email, role: req.role, status: "active", ward, supervisor_id: as === "doctor" ? USERS.doctor.id : null };
      if (as === "doctor") s.team.push(out);
      return out;
    });
  return http<UserAdmin>("POST", `/users/${enc(id)}/approve`, req);
}

/** POST /users/{id}/reject */
export function rejectUser(id: string, opts: ViewerOpts = {}): Promise<UserAdmin> {
  if (USE_MOCKS)
    return mock((s) => {
      const p = s.pending.find((u) => u.id === id) ?? notFound(`User ${id}`);
      if ((opts.as ?? "admin") === "doctor" && p.requested_doctor_id !== USERS.doctor.id) throw new ApiError(403, "forbidden", "Not your request");
      p.status = "rejected";
      return { id: p.id, name: p.name, email: p.email, role: null, status: "rejected" as const, ward: null, supervisor_id: null };
    });
  return http<UserAdmin>("POST", `/users/${enc(id)}/reject`, {});
}

/** POST /users/{id}/disable (admin: anyone; doctor: his team). */
export function disableUser(id: string, opts: ViewerOpts = {}): Promise<UserAdmin> {
  if (USE_MOCKS) return mock((s) => setStatus(s, id, "disabled", opts.as ?? "admin"));
  return http<UserAdmin>("POST", `/users/${enc(id)}/disable`, {});
}

/** POST /users/{id}/enable */
export function enableUser(id: string, opts: ViewerOpts = {}): Promise<UserAdmin> {
  if (USE_MOCKS) return mock((s) => setStatus(s, id, "active", opts.as ?? "admin"));
  return http<UserAdmin>("POST", `/users/${enc(id)}/enable`, {});
}

/** POST /users/{id}/reset-code (admin) → shown once. */
export function issueResetCode(userId: string): Promise<OneTimeCode> {
  if (USE_MOCKS)
    return mock((s) => {
      userAdmin(s, userId);
      return mockCode();
    });
  return http<OneTimeCode>("POST", `/users/${enc(userId)}/reset-code`, {});
}

/** GET /doctors/me/team (doctor). */
export function getMyTeam(): Promise<UserAdmin[]> {
  if (USE_MOCKS) return mock((s) => s.team);
  return http<UserAdmin[]>("GET", "/doctors/me/team");
}

/** POST /patients/{id}/enrollment-code → shown once. Mock: p-0001 already has an account (409). */
export function issueEnrollmentCode(patientId: string): Promise<OneTimeCode> {
  if (USE_MOCKS)
    return mock((s) => {
      s.patients.find((p) => p.id === patientId) ?? notFound(`Patient ${patientId}`);
      if (patientId === USERS.patient.patient_id) throw new ApiError(409, "already_enrolled", "This patient already has an account.");
      return mockCode();
    });
  return http<OneTimeCode>("POST", `/patients/${enc(patientId)}/enrollment-code`, {});
}

/** GET /patients/{id}/access */
export function getPatientAccess(patientId: string): Promise<PatientAccessGrant[]> {
  if (USE_MOCKS) return mock((s) => s.grants[patientId] ?? []);
  return http<PatientAccessGrant[]>("GET", `/patients/${enc(patientId)}/access`);
}

/** POST /patients/{id}/access `{doctor_id, expires_at?}` (default 30 days). */
export function grantPatientAccess(patientId: string, req: { doctor_id: string; expires_at?: string }): Promise<PatientAccessGrant> {
  if (USE_MOCKS)
    return mock((s) => {
      const doctor = s.directory.find((d) => d.id === req.doctor_id) ?? notFound(`Doctor ${req.doctor_id}`);
      const grant: PatientAccessGrant = {
        patient_id: patientId,
        doctor_id: doctor.id,
        doctor_name: doctor.name,
        expires_at: req.expires_at ?? iso(new Date(now().getTime() + 30 * 86_400_000)),
      };
      s.grants[patientId] = [...(s.grants[patientId] ?? []).filter((g) => g.doctor_id !== doctor.id), grant];
      return grant;
    });
  return http<PatientAccessGrant>("POST", `/patients/${enc(patientId)}/access`, req);
}

/** DELETE /patients/{id}/access/{doctor_id} → 204. */
export function revokePatientAccess(patientId: string, doctorId: string): Promise<void> {
  if (USE_MOCKS)
    return mock((s) => {
      s.grants[patientId] = (s.grants[patientId] ?? []).filter((g) => g.doctor_id !== doctorId);
    });
  return http<void>("DELETE", `/patients/${enc(patientId)}/access/${enc(doctorId)}`);
}
```

- [ ] **1.6 Verify.** `npm run typecheck` then `npm run build`.
  Expected: `tsc` prints nothing and exits 0; build ends with a route table and no type errors. (Existing code that builds `StaffMember` literals, e.g. `StaffView.sendInvite`, now fails: fix in Task 5; to keep this task green add `status: "pending"` to that literal in `StaffView.tsx` line ~101.)
- [ ] **1.7 Commit.** `git add web && git commit -m "feat(web): accounts and access API client, types and mocks"`

---

## Task 2: i18n namespaces and pure helpers

**Files:** create `web/src/i18n/messages/auth.ts`, `web/src/i18n/messages/accounts.ts`, `web/src/lib/accountsUi.ts`; modify `web/src/i18n/messages/index.ts`.

**Interfaces produced:**

```ts
// @/lib/accountsUi
export const MIN_PASSWORD = 10;
export interface ErrorInfo { key: Key; detail: string | null }
export type ErrorCtx = "login" | "password" | "form";
export function describeError(err: unknown, ctx?: ErrorCtx): ErrorInfo
export function normalizeCode(raw: string): string          // "k7m2q 9xr4t" -> "K7M2Q-9XR4T"
export function passwordProblem(pw: string, confirm: string): "short" | "mismatch" | null
export function fmtWhen(iso: string, lang: Lang): string   // "Mon 5 Oct 09:10" style, Tunis time
```

- [ ] **2.1 Register namespaces.** In `web/src/i18n/messages/index.ts` add `import { accounts } from "./accounts"; import { auth } from "./auth";` and change `export const ALL = { common, shared, doctor, nurse, admin, patient };` to `export const ALL = { common, shared, doctor, nurse, admin, patient, auth, accounts };`.

- [ ] **2.2 `auth.ts`.** Create `web/src/i18n/messages/auth.ts`:

```ts
import { messages } from "../define";

// Public account screens (sign-up, code reset), change password, and the error messages for the auth codes.
export const auth = messages({
  en: {
    accountLinks: "Account options",
    createAccount: "Create an account",
    haveCode: "I have a code",
    errPending: "Your account is waiting for approval.",
    errDisabled: "This account is disabled. Contact your administrator.",
    errRejected: "This account request was declined. Contact your administrator.",
    errLocked: "Too many wrong attempts. Try again in 15 minutes.",
    errRateLimited: "Too many requests. Wait a minute and try again.",
    errWeak: "That password is too weak. Use at least 10 characters that are hard to guess.",
    errInvalidCode: "That code is invalid or has expired.",
    errAlreadyEnrolled: "This patient record already has an account.",
    errBadCurrent: "The current password is wrong.",
    errGeneric: "Something went wrong. Try again.",
    errSessionExpired: "Your session ended. Sign in again.",
    errPasswordShort: "Use at least 10 characters.",
    errPasswordMismatch: "The two passwords don’t match.",
    passwordHint: "At least 10 characters. Not your name or email.",
    registerTitle: "Create an account",
    registerLead: "Staff accounts wait for approval. Patients: enter the code the hospital gave you.",
    fieldName: "Full name",
    fieldEmail: "Email",
    fieldPassword: "Password",
    fieldConfirm: "Confirm password",
    fieldNew: "New password",
    fieldNote: "Role and ward (optional)",
    fieldNoteHint: "For example: nurse, Cardiology",
    fieldDoctor: "I work with (optional)",
    doctorNone: "No one in particular",
    fieldEnrollCode: "Enrollment code (patients)",
    fieldEnrollHint: "Given by reception or your doctor.",
    fieldCode: "Code",
    registerSubmit: "Create account",
    registerBusy: "Sending…",
    registerDoneTitle: "Request received",
    registerDoneBody: "If the details are valid, your account was created or is waiting for approval.",
    registerDoneNext: "Staff: sign in once it is approved. Patients: if your code was valid, you can sign in now.",
    backToSignIn: "Back to sign in",
    resetTitle: "I have a code",
    resetLead: "Enter your email, the code you were given and a new password. The first administrator starts here too.",
    resetSubmit: "Set password",
    resetBusy: "Saving…",
    resetDoneTitle: "Password set",
    resetDoneBody: "You can now sign in with your new password.",
    pwTitle: "Change password",
    pwLead: "Choose a new password. Nobody else, including administrators, can see it.",
    pwCurrent: "Current password",
    pwSubmit: "Change password",
    pwDone: "Password changed.",
    navPassword: "Change password",
  },
  fr: {
    accountLinks: "Options du compte",
    createAccount: "Créer un compte",
    haveCode: "J’ai un code",
    errPending: "Votre compte est en attente d’approbation.",
    errDisabled: "Ce compte est désactivé. Contactez votre administrateur.",
    errRejected: "Cette demande de compte a été refusée. Contactez votre administrateur.",
    errLocked: "Trop de tentatives incorrectes. Réessayez dans 15 minutes.",
    errRateLimited: "Trop de requêtes. Patientez une minute puis réessayez.",
    errWeak: "Ce mot de passe est trop faible. Utilisez au moins 10 caractères difficiles à deviner.",
    errInvalidCode: "Ce code est invalide ou a expiré.",
    errAlreadyEnrolled: "Ce dossier patient a déjà un compte.",
    errBadCurrent: "Le mot de passe actuel est incorrect.",
    errGeneric: "Une erreur s’est produite. Réessayez.",
    errSessionExpired: "Votre session a pris fin. Reconnectez-vous.",
    errPasswordShort: "Utilisez au moins 10 caractères.",
    errPasswordMismatch: "Les deux mots de passe ne correspondent pas.",
    passwordHint: "Au moins 10 caractères. Ni votre nom ni votre e-mail.",
    registerTitle: "Créer un compte",
    registerLead: "Les comptes du personnel attendent une approbation. Patients : saisissez le code remis par l’hôpital.",
    fieldName: "Nom complet",
    fieldEmail: "E-mail",
    fieldPassword: "Mot de passe",
    fieldConfirm: "Confirmer le mot de passe",
    fieldNew: "Nouveau mot de passe",
    fieldNote: "Rôle et service (facultatif)",
    fieldNoteHint: "Par exemple : infirmier, Cardiologie",
    fieldDoctor: "Je travaille avec (facultatif)",
    doctorNone: "Personne en particulier",
    fieldEnrollCode: "Code d’inscription (patients)",
    fieldEnrollHint: "Remis par l’accueil ou votre médecin.",
    fieldCode: "Code",
    registerSubmit: "Créer le compte",
    registerBusy: "Envoi…",
    registerDoneTitle: "Demande reçue",
    registerDoneBody: "Si les informations sont valides, votre compte a été créé ou attend son approbation.",
    registerDoneNext: "Personnel : connectez-vous une fois le compte approuvé. Patients : si votre code était valide, vous pouvez vous connecter.",
    backToSignIn: "Retour à la connexion",
    resetTitle: "J’ai un code",
    resetLead: "Saisissez votre e-mail, le code reçu et un nouveau mot de passe. Le premier administrateur commence ici aussi.",
    resetSubmit: "Définir le mot de passe",
    resetBusy: "Enregistrement…",
    resetDoneTitle: "Mot de passe défini",
    resetDoneBody: "Vous pouvez maintenant vous connecter avec votre nouveau mot de passe.",
    pwTitle: "Changer le mot de passe",
    pwLead: "Choisissez un nouveau mot de passe. Personne d’autre, administrateurs compris, ne peut le voir.",
    pwCurrent: "Mot de passe actuel",
    pwSubmit: "Changer le mot de passe",
    pwDone: "Mot de passe modifié.",
    navPassword: "Changer le mot de passe",
  },
  ar: {
    accountLinks: "خيارات الحساب",
    createAccount: "إنشاء حساب",
    haveCode: "لدي رمز",
    errPending: "حسابك في انتظار الموافقة.",
    errDisabled: "هذا الحساب معطّل. تواصل مع المسؤول.",
    errRejected: "تم رفض طلب هذا الحساب. تواصل مع المسؤول.",
    errLocked: "محاولات خاطئة كثيرة. أعد المحاولة بعد 15 دقيقة.",
    errRateLimited: "طلبات كثيرة. انتظر دقيقة ثم أعد المحاولة.",
    errWeak: "كلمة المرور ضعيفة جدًا. استخدم 10 أحرف على الأقل يصعب تخمينها.",
    errInvalidCode: "الرمز غير صالح أو انتهت صلاحيته.",
    errAlreadyEnrolled: "ملف هذا المريض مرتبط بحساب بالفعل.",
    errBadCurrent: "كلمة المرور الحالية غير صحيحة.",
    errGeneric: "حدث خطأ ما. أعد المحاولة.",
    errSessionExpired: "انتهت جلستك. سجّل الدخول من جديد.",
    errPasswordShort: "استخدم 10 أحرف على الأقل.",
    errPasswordMismatch: "كلمتا المرور غير متطابقتين.",
    passwordHint: "10 أحرف على الأقل. ليست اسمك ولا بريدك الإلكتروني.",
    registerTitle: "إنشاء حساب",
    registerLead: "حسابات الموظفين تنتظر الموافقة. المرضى: أدخلوا الرمز الذي سلّمه لكم المستشفى.",
    fieldName: "الاسم الكامل",
    fieldEmail: "البريد الإلكتروني",
    fieldPassword: "كلمة المرور",
    fieldConfirm: "تأكيد كلمة المرور",
    fieldNew: "كلمة المرور الجديدة",
    fieldNote: "الدور والقسم (اختياري)",
    fieldNoteHint: "مثال: ممرض، أمراض القلب",
    fieldDoctor: "أعمل مع (اختياري)",
    doctorNone: "لا أحد بالتحديد",
    fieldEnrollCode: "رمز التسجيل (للمرضى)",
    fieldEnrollHint: "يسلّمه الاستقبال أو طبيبك.",
    fieldCode: "الرمز",
    registerSubmit: "إنشاء الحساب",
    registerBusy: "جارٍ الإرسال…",
    registerDoneTitle: "تم استلام الطلب",
    registerDoneBody: "إذا كانت البيانات صحيحة، فقد تم إنشاء حسابك أو هو في انتظار الموافقة.",
    registerDoneNext: "الموظفون: سجّلوا الدخول بعد الموافقة. المرضى: إذا كان رمزكم صحيحًا يمكنكم تسجيل الدخول الآن.",
    backToSignIn: "العودة إلى تسجيل الدخول",
    resetTitle: "لدي رمز",
    resetLead: "أدخل بريدك الإلكتروني والرمز الذي تلقيته وكلمة مرور جديدة. المسؤول الأول يبدأ من هنا أيضًا.",
    resetSubmit: "تعيين كلمة المرور",
    resetBusy: "جارٍ الحفظ…",
    resetDoneTitle: "تم تعيين كلمة المرور",
    resetDoneBody: "يمكنك الآن تسجيل الدخول بكلمة المرور الجديدة.",
    pwTitle: "تغيير كلمة المرور",
    pwLead: "اختر كلمة مرور جديدة. لا يستطيع أحد غيرك، ولا حتى المسؤولون، رؤيتها.",
    pwCurrent: "كلمة المرور الحالية",
    pwSubmit: "تغيير كلمة المرور",
    pwDone: "تم تغيير كلمة المرور.",
    navPassword: "تغيير كلمة المرور",
  },
});
```

- [ ] **2.3 `accounts.ts`.** Create `web/src/i18n/messages/accounts.ts`:

```ts
import { messages } from "../define";

// One-time codes, pending accounts, doctor team, patient access and sharing.
export const accounts = messages({
  en: {
    navPending: "Pending accounts",
    navTeam: "My team",
    navEnroll: "Patient access",
    codeOnce: "This code is shown only once. Copy or print it now. It cannot be shown again.",
    codeFor: "For {name}",
    codeValid: "Valid until {when}",
    codeCopy: "Copy",
    codeCopied: "Copied",
    codeCopyFailed: "Copy didn’t work. Select the code and copy it by hand.",
    codePrint: "Print",
    codeDone: "I have saved it",
    printInstruction: "Give this code to the person. It works once.",
    statusActive: "Active",
    statusPending: "Pending",
    statusDisabled: "Disabled",
    statusRejected: "Rejected",
    pendingTitle: "Pending accounts",
    pendingSub: "People who asked for access. Nobody has access until you approve.",
    pendingEmpty: "No pending accounts.",
    pendingLoadError: "Couldn’t load pending accounts.",
    pendingWorksWith: "Works with {doctor}",
    pendingRequested: "Requested {when}",
    rejectedHeading: "Rejected requests",
    approveAs: "Approve as",
    approveWard: "Ward",
    wardNone: "No ward yet",
    approve: "Approve",
    approveNurse: "Approve as nurse",
    reject: "Reject",
    approvedToast: "{name} approved.",
    rejectedToast: "{name} rejected.",
    actionError: "That didn’t work. Try again.",
    actionForbidden: "You aren’t allowed to do that.",
    staffColStatus: "Status",
    staffColActions: "Actions",
    disable: "Disable",
    enable: "Enable",
    issueResetCode: "Reset code",
    disabledToast: "{name} disabled.",
    enabledToast: "{name} enabled.",
    teamTitle: "My team",
    teamSub: "Nurses who work with you, and people asking to join.",
    teamRequests: "Requests to work with you",
    teamMembers: "Team members",
    teamEmpty: "No team members yet.",
    teamLoadError: "Couldn’t load your team.",
    enrollTitle: "Patient app access",
    enrollLead: "Give the patient a one-time code so they can create their own account.",
    enrollIssue: "Issue enrollment code",
    enrollBusy: "Issuing…",
    enrollSubject: "Enrollment code for {name}",
    enrollAlready: "This patient already has an account. Disable it before issuing a new code.",
    shareTitle: "Share with a doctor",
    shareLead: "Another doctor can open this record until the date you choose.",
    shareEmpty: "Not shared with anyone.",
    sharePick: "Choose a doctor",
    shareExpiry: "Access until (optional)",
    shareExpiryHint: "Default 30 days, at most 1 year.",
    shareAdd: "Share",
    shareRevoke: "Revoke",
    shareUntil: "until {when}",
    shareLoadError: "Couldn’t load sharing.",
    shareAdded: "Shared with {name}.",
    shareRevoked: "Access for {name} revoked.",
    lookupTitle: "Patient access",
    lookupSub: "Open a patient record to issue an enrollment code or share it with a doctor.",
    lookupLabel: "Patient ID",
    lookupGo: "Open",
    lookupNotFound: "No patient with this ID.",
  },
  fr: {
    navPending: "Comptes en attente",
    navTeam: "Mon équipe",
    navEnroll: "Accès patient",
    codeOnce: "Ce code n’est affiché qu’une seule fois. Copiez-le ou imprimez-le maintenant. Il ne pourra plus être affiché.",
    codeFor: "Pour {name}",
    codeValid: "Valable jusqu’au {when}",
    codeCopy: "Copier",
    codeCopied: "Copié",
    codeCopyFailed: "La copie a échoué. Sélectionnez le code et copiez-le à la main.",
    codePrint: "Imprimer",
    codeDone: "Je l’ai noté",
    printInstruction: "Remettez ce code à la personne. Il ne fonctionne qu’une fois.",
    statusActive: "Actif",
    statusPending: "En attente",
    statusDisabled: "Désactivé",
    statusRejected: "Refusé",
    pendingTitle: "Comptes en attente",
    pendingSub: "Personnes qui ont demandé un accès. Personne n’a accès avant votre approbation.",
    pendingEmpty: "Aucun compte en attente.",
    pendingLoadError: "Impossible de charger les comptes en attente.",
    pendingWorksWith: "Travaille avec {doctor}",
    pendingRequested: "Demandé {when}",
    rejectedHeading: "Demandes refusées",
    approveAs: "Approuver comme",
    approveWard: "Service",
    wardNone: "Pas encore de service",
    approve: "Approuver",
    approveNurse: "Approuver comme infirmier(ère)",
    reject: "Refuser",
    approvedToast: "{name} approuvé(e).",
    rejectedToast: "{name} refusé(e).",
    actionError: "Cela n’a pas fonctionné. Réessayez.",
    actionForbidden: "Vous n’avez pas le droit de faire cela.",
    staffColStatus: "Statut",
    staffColActions: "Actions",
    disable: "Désactiver",
    enable: "Activer",
    issueResetCode: "Code de réinitialisation",
    disabledToast: "{name} désactivé(e).",
    enabledToast: "{name} activé(e).",
    teamTitle: "Mon équipe",
    teamSub: "Les infirmiers(ères) qui travaillent avec vous et ceux qui demandent à vous rejoindre.",
    teamRequests: "Demandes pour travailler avec vous",
    teamMembers: "Membres de l’équipe",
    teamEmpty: "Aucun membre pour l’instant.",
    teamLoadError: "Impossible de charger votre équipe.",
    enrollTitle: "Accès à l’application patient",
    enrollLead: "Remettez au patient un code à usage unique pour qu’il crée son propre compte.",
    enrollIssue: "Générer un code d’inscription",
    enrollBusy: "Génération…",
    enrollSubject: "Code d’inscription pour {name}",
    enrollAlready: "Ce patient a déjà un compte. Désactivez-le avant de générer un nouveau code.",
    shareTitle: "Partager avec un médecin",
    shareLead: "Un autre médecin peut ouvrir ce dossier jusqu’à la date choisie.",
    shareEmpty: "Non partagé.",
    sharePick: "Choisir un médecin",
    shareExpiry: "Accès jusqu’au (facultatif)",
    shareExpiryHint: "30 jours par défaut, 1 an au maximum.",
    shareAdd: "Partager",
    shareRevoke: "Révoquer",
    shareUntil: "jusqu’au {when}",
    shareLoadError: "Impossible de charger le partage.",
    shareAdded: "Partagé avec {name}.",
    shareRevoked: "Accès de {name} révoqué.",
    lookupTitle: "Accès patient",
    lookupSub: "Ouvrez un dossier patient pour générer un code d’inscription ou le partager avec un médecin.",
    lookupLabel: "Identifiant patient",
    lookupGo: "Ouvrir",
    lookupNotFound: "Aucun patient avec cet identifiant.",
  },
  ar: {
    navPending: "الحسابات المعلّقة",
    navTeam: "فريقي",
    navEnroll: "وصول المرضى",
    codeOnce: "يُعرض هذا الرمز مرة واحدة فقط. انسخه أو اطبعه الآن، فلن يمكن عرضه مجددًا.",
    codeFor: "إلى {name}",
    codeValid: "صالح حتى {when}",
    codeCopy: "نسخ",
    codeCopied: "تم النسخ",
    codeCopyFailed: "تعذّر النسخ. حدّد الرمز وانسخه يدويًا.",
    codePrint: "طباعة",
    codeDone: "قمت بحفظه",
    printInstruction: "سلّم هذا الرمز إلى الشخص. يعمل مرة واحدة فقط.",
    statusActive: "نشط",
    statusPending: "معلّق",
    statusDisabled: "معطّل",
    statusRejected: "مرفوض",
    pendingTitle: "الحسابات المعلّقة",
    pendingSub: "أشخاص طلبوا الوصول. لا أحد يملك صلاحية قبل موافقتك.",
    pendingEmpty: "لا توجد حسابات معلّقة.",
    pendingLoadError: "تعذّر تحميل الحسابات المعلّقة.",
    pendingWorksWith: "يعمل مع {doctor}",
    pendingRequested: "طُلب {when}",
    rejectedHeading: "الطلبات المرفوضة",
    approveAs: "الموافقة بصفة",
    approveWard: "القسم",
    wardNone: "بلا قسم بعد",
    approve: "موافقة",
    approveNurse: "الموافقة كممرض",
    reject: "رفض",
    approvedToast: "تمت الموافقة على {name}.",
    rejectedToast: "تم رفض {name}.",
    actionError: "لم تنجح العملية. أعد المحاولة.",
    actionForbidden: "غير مسموح لك بذلك.",
    staffColStatus: "الحالة",
    staffColActions: "إجراءات",
    disable: "تعطيل",
    enable: "تفعيل",
    issueResetCode: "رمز إعادة التعيين",
    disabledToast: "تم تعطيل {name}.",
    enabledToast: "تم تفعيل {name}.",
    teamTitle: "فريقي",
    teamSub: "الممرضون الذين يعملون معك ومن يطلبون الانضمام.",
    teamRequests: "طلبات العمل معك",
    teamMembers: "أعضاء الفريق",
    teamEmpty: "لا يوجد أعضاء بعد.",
    teamLoadError: "تعذّر تحميل فريقك.",
    enrollTitle: "وصول المريض إلى التطبيق",
    enrollLead: "سلّم المريض رمزًا لمرة واحدة ليُنشئ حسابه بنفسه.",
    enrollIssue: "إصدار رمز تسجيل",
    enrollBusy: "جارٍ الإصدار…",
    enrollSubject: "رمز التسجيل للمريض {name}",
    enrollAlready: "لهذا المريض حساب بالفعل. عطّله قبل إصدار رمز جديد.",
    shareTitle: "مشاركة مع طبيب",
    shareLead: "يمكن لطبيب آخر فتح هذا الملف حتى التاريخ الذي تختاره.",
    shareEmpty: "غير مشارك مع أحد.",
    sharePick: "اختر طبيبًا",
    shareExpiry: "الوصول حتى (اختياري)",
    shareExpiryHint: "30 يومًا افتراضيًا، وسنة كحد أقصى.",
    shareAdd: "مشاركة",
    shareRevoke: "إلغاء",
    shareUntil: "حتى {when}",
    shareLoadError: "تعذّر تحميل المشاركة.",
    shareAdded: "تمت المشاركة مع {name}.",
    shareRevoked: "تم إلغاء وصول {name}.",
    lookupTitle: "وصول المرضى",
    lookupSub: "افتح ملف مريض لإصدار رمز تسجيل أو مشاركته مع طبيب.",
    lookupLabel: "معرّف المريض",
    lookupGo: "فتح",
    lookupNotFound: "لا يوجد مريض بهذا المعرّف.",
  },
});
```

- [ ] **2.4 Helpers.** Create `web/src/lib/accountsUi.ts`:

```ts
// Pure helpers for the accounts screens: error → message key, code and password checks, dates.
import type { Lang } from "@/i18n/config";
import type { Key } from "@/i18n/messages";
import { ApiError } from "./api";
import { dayLabel, now, tunisTime } from "./time";

export const MIN_PASSWORD = 10;

export interface ErrorInfo {
  key: Key;
  /** The server's reason (English); only shown as secondary text for weak passwords. */
  detail: string | null;
}
export type ErrorCtx = "login" | "password" | "form";

const BY_CODE: Partial<Record<string, Key>> = {
  account_pending: "auth.errPending",
  account_disabled: "auth.errDisabled",
  account_rejected: "auth.errRejected",
  account_locked: "auth.errLocked",
  rate_limited: "auth.errRateLimited",
  weak_password: "auth.errWeak",
  invalid_code: "auth.errInvalidCode",
  already_enrolled: "auth.errAlreadyEnrolled",
};

/** Maps any thrown value to a localized message key. Non-ApiError (fetch failed) = server unreachable. */
export function describeError(err: unknown, ctx: ErrorCtx = "form"): ErrorInfo {
  if (!(err instanceof ApiError)) return { key: "shared.loginUnreachable", detail: null };
  if (err.code === "bad_credentials") return { key: ctx === "password" ? "auth.errBadCurrent" : "shared.loginWrong", detail: null };
  const key = BY_CODE[err.code] ?? (err.status === 429 ? "auth.errRateLimited" : "auth.errGeneric");
  return { key, detail: err.code === "weak_password" && err.message ? err.message : null };
}

/** "k7m2q 9xr4t" → "K7M2Q-9XR4T". Anything that isn't 10 letters/digits is returned uppercased and stripped, for the server to reject. */
export function normalizeCode(raw: string): string {
  const s = raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
  return s.length === 10 ? `${s.slice(0, 5)}-${s.slice(5)}` : s;
}

/** Client-side checks only; the server stays the authority (common-password list, name/email rules). */
export function passwordProblem(pw: string, confirm: string): "short" | "mismatch" | null {
  if (pw.length < MIN_PASSWORD) return "short";
  if (pw !== confirm) return "mismatch";
  return null;
}

/** "Mon 5 Oct 09:10" in the hospital's time zone (Tunis), localized day label. */
export function fmtWhen(iso: string, lang: Lang): string {
  return `${dayLabel(iso, now(), lang)} ${tunisTime(iso)}`;
}
```

- [ ] **2.5 Verify.** `npm run typecheck`; expected exit 0, no output. Negative check (then revert): temporarily delete one `ar` key in `accounts.ts`, rerun `npm run typecheck`, expect an error naming that key; restore it.
- [ ] **2.6 Commit.** `git add web && git commit -m "feat(web): accounts i18n namespaces and error/code helpers"`

---

## Task 3: Sign-in links, /register, /reset, login error messages

**Files:** create `web/src/components/auth/Auth.module.css`, `AuthFrame.tsx`, `RegisterForm.tsx`, `ResetForm.tsx`, `web/src/app/register/page.tsx`, `web/src/app/reset/page.tsx`; modify `web/src/components/LoginForm.tsx`, `web/src/app/page.tsx`.

**Interfaces consumed:** `registerAccount`, `resetPassword`, `getDoctorDirectory`, `describeError`, `normalizeCode`, `passwordProblem`, `ErrorInfo`.

- [ ] **3.1 CSS.** Create `web/src/components/auth/Auth.module.css` (the form classes `login/field/fieldLabel/input/loginError/submit` are reused from `@/app/page.module.css`):

```css
.links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  font: 600 15px/1.2 var(--sans);
}

.links a,
.back {
  color: var(--teal-deep);
  text-decoration: underline;
}

.hint {
  font-size: 13px;
  line-height: 1.4;
  color: var(--muted);
}

.detail {
  font-size: 13px;
  color: var(--danger-ink);
}

.notice {
  font-size: 14px;
  line-height: 1.4;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--warn-bg);
  border: 1px solid var(--warn-line);
  color: var(--warn-ink);
}

.done {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 420px;
  padding: 24px;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 14px;
}

.doneTitle {
  margin: 0;
  font: 600 22px/1.2 var(--serif);
  color: var(--ink);
}

.doneBody {
  margin: 0;
  font-size: 15px;
  line-height: 1.5;
  color: var(--text);
}

.select {
  font-size: 16px;
  padding: 12px 14px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: var(--paper);
  color: var(--ink);
}

.pageWrap {
  padding: 36px 40px 40px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.pageTitle {
  margin: 0;
  font: 600 32px/1.1 var(--serif);
  color: var(--ink);
}

/* Codes, emails and passwords are always left-to-right, even inside Arabic pages. */
.ltr {
  direction: ltr;
  text-align: start;
  unicode-bidi: isolate;
}
```

- [ ] **3.2 AuthFrame.** Create `web/src/components/auth/AuthFrame.tsx` (same brand header as the home page):

```tsx
"use client";

import type { ReactNode } from "react";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useT } from "@/i18n/I18nProvider";
import styles from "@/app/page.module.css";

/** The landing-page chrome (brand card, title, lead) around a public account form. */
export function AuthFrame({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  const { t } = useT();
  return (
    <div className={styles.page}>
      <div className={styles.inner}>
        <header className={styles.brand}>
          <div className={styles.wordmark}>
            <span className={styles.mark} />
            <span className={styles.name}>Medora</span>
          </div>
          <span className={styles.tag}>{t("common.prototypeTag")}</span>
          <LanguageSwitcher tone="light" />
        </header>
        <div className={styles.intro}>
          <h1 className={styles.title}>{title}</h1>
          {lead ? <p className={styles.lead}>{lead}</p> : null}
        </div>
        {children}
      </div>
    </div>
  );
}

export default AuthFrame;
```

- [ ] **3.3 RegisterForm.** Create `web/src/components/auth/RegisterForm.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import { describeError, normalizeCode, passwordProblem, type ErrorInfo } from "@/lib/accountsUi";
import { getDoctorDirectory, registerAccount } from "@/lib/api";
import type { DoctorRef } from "@/lib/types";
import { AuthFrame } from "./AuthFrame";
import auth from "./Auth.module.css";
import styles from "@/app/page.module.css";

export function RegisterForm() {
  const { t } = useT();
  const [f, setF] = useState({ name: "", email: "", password: "", confirm: "", note: "", doctor: "", code: "" });
  const [doctors, setDoctors] = useState<DoctorRef[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorInfo | null>(null);
  const [done, setDone] = useState(false);
  const set = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }));

  useEffect(() => {
    let alive = true;
    // The picker is optional: if the directory fails the form still works without it.
    getDoctorDirectory().then((d) => alive && setDoctors(d), () => undefined);
    return () => {
      alive = false;
    };
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const problem = passwordProblem(f.password, f.confirm);
    if (problem) {
      setError({ key: problem === "short" ? "auth.errPasswordShort" : "auth.errPasswordMismatch", detail: null });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await registerAccount({
        name: f.name.trim(),
        email: f.email.trim(),
        password: f.password,
        ...(f.note.trim() ? { note: f.note.trim() } : {}),
        ...(f.doctor ? { requested_doctor_id: f.doctor } : {}),
        ...(f.code.trim() ? { enrollment_code: normalizeCode(f.code) } : {}),
      });
      setF((s) => ({ ...s, password: "", confirm: "" }));
      setDone(true);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  if (done)
    return (
      <AuthFrame title={t("auth.registerTitle")}>
        <div className={auth.done} role="status">
          <h2 className={auth.doneTitle}>{t("auth.registerDoneTitle")}</h2>
          <p className={auth.doneBody}>{t("auth.registerDoneBody")}</p>
          <p className={auth.doneBody}>{t("auth.registerDoneNext")}</p>
          <Link href="/" className={auth.back}>
            {t("auth.backToSignIn")}
          </Link>
        </div>
      </AuthFrame>
    );

  return (
    <AuthFrame title={t("auth.registerTitle")} lead={t("auth.registerLead")}>
      <form className={styles.login} onSubmit={submit} aria-label={t("auth.registerTitle")}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("auth.fieldName")}</span>
          <input dir="auto" required autoComplete="name" className={styles.input} value={f.name} onChange={(e) => set("name")(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("auth.fieldEmail")}</span>
          <input type="email" dir="ltr" required autoComplete="username" className={styles.input} value={f.email} onChange={(e) => set("email")(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("auth.fieldPassword")}</span>
          <input type="password" dir="ltr" required minLength={10} autoComplete="new-password" className={styles.input} value={f.password} onChange={(e) => set("password")(e.target.value)} />
          <span className={auth.hint}>{t("auth.passwordHint")}</span>
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("auth.fieldConfirm")}</span>
          <input type="password" dir="ltr" required autoComplete="new-password" className={styles.input} value={f.confirm} onChange={(e) => set("confirm")(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("auth.fieldNote")}</span>
          <input dir="auto" className={styles.input} value={f.note} placeholder={t("auth.fieldNoteHint")} onChange={(e) => set("note")(e.target.value)} />
        </label>
        {doctors.length ? (
          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t("auth.fieldDoctor")}</span>
            <select className={auth.select} value={f.doctor} onChange={(e) => set("doctor")(e.target.value)}>
              <option value="">{t("auth.doctorNone")}</option>
              {doctors.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("auth.fieldEnrollCode")}</span>
          <input dir="ltr" autoComplete="off" autoCapitalize="characters" spellCheck={false} className={styles.input} value={f.code} placeholder="XXXXX-XXXXX" onChange={(e) => set("code")(e.target.value)} />
          <span className={auth.hint}>{t("auth.fieldEnrollHint")}</span>
        </label>
        {error ? (
          <span role="alert" className={styles.loginError}>
            {t(error.key)}
            {error.detail ? <span dir="auto" className={auth.detail}> {error.detail}</span> : null}
          </span>
        ) : null}
        <button type="submit" className={styles.submit} disabled={busy}>
          {busy ? t("auth.registerBusy") : t("auth.registerSubmit")}
        </button>
      </form>
      <Link href="/" className={auth.back}>
        {t("auth.backToSignIn")}
      </Link>
    </AuthFrame>
  );
}

export default RegisterForm;
```

- [ ] **3.4 ResetForm.** Create `web/src/components/auth/ResetForm.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import { describeError, normalizeCode, passwordProblem, type ErrorInfo } from "@/lib/accountsUi";
import { resetPassword } from "@/lib/api";
import { AuthFrame } from "./AuthFrame";
import auth from "./Auth.module.css";
import styles from "@/app/page.module.css";

export function ResetForm() {
  const { t } = useT();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorInfo | null>(null);
  const [done, setDone] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const problem = passwordProblem(pw, confirm);
    if (problem) {
      setError({ key: problem === "short" ? "auth.errPasswordShort" : "auth.errPasswordMismatch", detail: null });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await resetPassword({ email: email.trim(), code: normalizeCode(code), new_password: pw });
      setPw("");
      setConfirm("");
      setDone(true);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  if (done)
    return (
      <AuthFrame title={t("auth.resetTitle")}>
        <div className={auth.done} role="status">
          <h2 className={auth.doneTitle}>{t("auth.resetDoneTitle")}</h2>
          <p className={auth.doneBody}>{t("auth.resetDoneBody")}</p>
          <Link href="/" className={auth.back}>
            {t("auth.backToSignIn")}
          </Link>
        </div>
      </AuthFrame>
    );

  return (
    <AuthFrame title={t("auth.resetTitle")} lead={t("auth.resetLead")}>
      <form className={styles.login} onSubmit={submit} aria-label={t("auth.resetTitle")}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("auth.fieldEmail")}</span>
          <input type="email" dir="ltr" required autoComplete="username" className={styles.input} value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("auth.fieldCode")}</span>
          <input dir="ltr" required autoComplete="off" autoCapitalize="characters" spellCheck={false} className={styles.input} value={code} placeholder="XXXXX-XXXXX" onChange={(e) => setCode(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("auth.fieldNew")}</span>
          <input type="password" dir="ltr" required minLength={10} autoComplete="new-password" className={styles.input} value={pw} onChange={(e) => setPw(e.target.value)} />
          <span className={auth.hint}>{t("auth.passwordHint")}</span>
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("auth.fieldConfirm")}</span>
          <input type="password" dir="ltr" required autoComplete="new-password" className={styles.input} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </label>
        {error ? (
          <span role="alert" className={styles.loginError}>
            {t(error.key)}
            {error.detail ? <span dir="auto" className={auth.detail}> {error.detail}</span> : null}
          </span>
        ) : null}
        <button type="submit" className={styles.submit} disabled={busy}>
          {busy ? t("auth.resetBusy") : t("auth.resetSubmit")}
        </button>
      </form>
      <Link href="/" className={auth.back}>
        {t("auth.backToSignIn")}
      </Link>
    </AuthFrame>
  );
}

export default ResetForm;
```

- [ ] **3.5 Pages.** Create `web/src/app/register/page.tsx`:

```tsx
import { RegisterForm } from "@/components/auth/RegisterForm";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("auth.registerTitle")} · Medora` };
}

export default function RegisterPage() {
  return <RegisterForm />;
}
```

Create `web/src/app/reset/page.tsx` identically with `ResetForm`, `auth.resetTitle`, function name `ResetPage`.

- [ ] **3.6 Login messages.** In `web/src/components/LoginForm.tsx` add `import { describeError } from "@/lib/accountsUi";`, drop the now-unused `ApiError` import (`import { login } from "@/lib/api";`), and replace the `catch` body:

```tsx
    } catch (err) {
      setError(t(describeError(err, "login").key));
      setBusy(false);
    }
```

(Behaviour change: 400/422 no longer mean "wrong password"; only `bad_credentials` does. Pending, disabled, rejected, locked and rate-limited each get their own message.)

- [ ] **3.7 Sign-in links.** In `web/src/app/page.tsx` add `import authStyles from "@/components/auth/Auth.module.css";` and, just before the closing `</div>` of `styles.inner` (after the `USE_MOCKS ? ... : ...` block), add:

```tsx
        <nav className={authStyles.links} aria-label={t("auth.accountLinks")}>
          <Link href="/register">{t("auth.createAccount")}</Link>
          <Link href="/reset">{t("auth.haveCode")}</Link>
        </nav>
```

(Shown in mock mode too so the screens can be reviewed without a backend.)

- [ ] **3.8 Verify.** `npm run typecheck && npm run build`; expected: both succeed, route table lists `/register` and `/reset`.
  Manual (mock mode, `$env:NEXT_PUBLIC_USE_MOCKS=1; npm run dev`, open http://localhost:3000): (a) home shows the two links; (b) `/register`: password `short` + submit → "Use at least 10 characters."; valid form → generic success screen, identical when repeating the same email; code `ZZZZZ-ZZZZZ` → "invalid or has expired"; `HHHHH-HHHHH` → "already has an account"; `K7M2Q-9XR4T` → success; doctor picker lists three doctors; (c) `/reset`: `R3SET-7PW2X` (also typed `r3set 7pw2x`) + 12-char password → "Password set"; other code → invalid message; (d) switch to Arabic: page flips RTL, email/password/code fields stay left-to-right.
  Manual (real-mode messages, no backend needed): run a stub in another shell `node -e "require('http').createServer((q,s)=>{s.writeHead(403,{'content-type':'application/json','access-control-allow-origin':'*','access-control-allow-headers':'*','access-control-allow-methods':'*'});q.method==='OPTIONS'?s.end():s.end(JSON.stringify({detail:'x',code:'account_pending'}))}).listen(8000)"`, then `$env:NEXT_PUBLIC_USE_MOCKS=0; npm run dev`, sign in with any email/password: expect "Your account is waiting for approval." Repeat with the stub's code changed to `account_locked`, `account_disabled`, `bad_credentials` (status 401) and `rate_limited` (status 429), expecting the matching text each time.
- [ ] **3.9 Commit.** `git add web && git commit -m "feat(web): sign-up and code-reset screens, per-code login errors"`

---

## Task 4: CodeDialog (show once, copy, print) and Change password in every role

**Files:** create `web/src/components/shared/CodeDialog.tsx`, `CodeDialog.module.css`, `web/src/components/auth/ChangePasswordForm.tsx`, `ChangePasswordPage.tsx`, the four `password/page.tsx` routes; modify `web/src/app/globals.css`, `web/src/components/Sidebar.tsx`, `web/src/components/patient/PatientScreen.tsx`.

**Interfaces produced:**

```ts
// @/components/shared/CodeDialog
export interface CodeDialogProps { subject: string; code: string; expiresAt: string; onClose: () => void }
export function CodeDialog(props: CodeDialogProps): JSX.Element
// @/components/auth/ChangePasswordForm
export function ChangePasswordForm(): JSX.Element
// @/components/auth/ChangePasswordPage
export function ChangePasswordPage(): JSX.Element   // title + form with page padding, for the three shells
```

- [ ] **4.1 Print rules.** Append to `web/src/app/globals.css` (a CSS module cannot target `body`, so the print switch is global and keyed on a data attribute set only while printing):

```css
/* One-time code print sheet: hidden on screen, the only thing printed while body[data-printing="code"]. */
[data-print-sheet] {
  display: none;
}

@media print {
  body[data-printing="code"] * {
    visibility: hidden;
  }

  body[data-printing="code"] [data-print-sheet],
  body[data-printing="code"] [data-print-sheet] * {
    visibility: visible;
  }

  body[data-printing="code"] [data-print-sheet] {
    display: flex;
    flex-direction: column;
    gap: 18px;
    position: fixed;
    inset: 0;
    padding: 48px;
    background: #fff;
    color: #000;
  }
}
```

- [ ] **4.2 CodeDialog CSS.** Create `web/src/components/shared/CodeDialog.module.css`:

```css
.overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 45, 68, 0.55);
}

.dialog {
  width: min(480px, 100%);
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 28px;
  background: var(--paper);
  border-radius: 14px;
  box-shadow: var(--shadow-frame);
}

.subject {
  margin: 0;
  font: 600 20px/1.3 var(--serif);
  color: var(--ink);
}

.warn {
  margin: 0;
  padding: 10px 12px;
  font-size: 14px;
  line-height: 1.4;
  border-radius: 8px;
  background: var(--warn-bg);
  border: 1px solid var(--warn-line);
  color: var(--warn-ink);
}

/* LTR + isolate keeps XXXXX-XXXXX in order and the dash in place inside Arabic pages. */
.code {
  direction: ltr;
  unicode-bidi: isolate;
  text-align: center;
  font: 700 36px/1.2 ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  letter-spacing: 0.08em;
  padding: 18px 12px;
  border: 2px dashed var(--line-strong);
  border-radius: 10px;
  color: var(--ink);
  user-select: all;
  overflow-wrap: anywhere;
}

.valid {
  margin: 0;
  font-size: 14px;
  color: var(--muted);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.btn,
.btnPrimary {
  min-height: 44px;
  padding: 0 16px;
  font: 600 15px/1 var(--sans);
  border-radius: 8px;
  cursor: pointer;
}

.btn {
  color: var(--ink);
  background: var(--paper);
  border: 1px solid var(--line-strong);
}

.btnPrimary {
  color: var(--paper);
  background: var(--ink);
  border: none;
  margin-inline-start: auto;
}

.feedback {
  margin: 0;
  font-size: 14px;
  color: var(--danger-ink);
}

.sheetBrand {
  font: 600 28px/1 var(--serif);
}

.sheetCode {
  direction: ltr;
  unicode-bidi: isolate;
  font: 700 56px/1.2 ui-monospace, Menlo, Consolas, monospace;
  letter-spacing: 0.1em;
}
```

- [ ] **4.3 CodeDialog component.** Create `web/src/components/shared/CodeDialog.tsx`:

```tsx
"use client";

// The only place a one-time code is shown. The code is a prop from the caller's state:
// it is never written to storage, URL or logs, and leaving the page asks for confirmation.
import { useEffect, useRef, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import { fmtWhen } from "@/lib/accountsUi";
import styles from "./CodeDialog.module.css";

export interface CodeDialogProps {
  subject: string;
  code: string;
  expiresAt: string;
  onClose: () => void;
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    /* no clipboard API on plain-HTTP LAN installs, or permission denied: fall back below */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    ta.remove();
  }
}

export function CodeDialog({ subject, code, expiresAt, onClose }: CodeDialogProps) {
  const { t, lang } = useT();
  const [copy, setCopy] = useState<"idle" | "ok" | "failed">("idle");
  const copyRef = useRef<HTMLButtonElement>(null);
  const when = fmtWhen(expiresAt, lang);

  useEffect(() => {
    copyRef.current?.focus();
    const guard = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);

  function print() {
    document.body.dataset.printing = "code";
    window.addEventListener("afterprint", () => delete document.body.dataset.printing, { once: true });
    window.print();
  }

  return (
    <div className={styles.overlay}>
      <div role="dialog" aria-modal="true" aria-labelledby="code-subject" className={styles.dialog}>
        <p id="code-subject" dir="auto" className={styles.subject}>
          {subject}
        </p>
        <p className={styles.warn}>{t("accounts.codeOnce")}</p>
        <div dir="ltr" className={styles.code}>
          {code}
        </div>
        <p className={styles.valid}>{t("accounts.codeValid", { when })}</p>
        {copy === "failed" ? (
          <p role="alert" className={styles.feedback}>
            {t("accounts.codeCopyFailed")}
          </p>
        ) : null}
        <div className={styles.actions}>
          <button ref={copyRef} type="button" className={styles.btn} onClick={async () => setCopy((await copyText(code)) ? "ok" : "failed")}>
            {copy === "ok" ? t("accounts.codeCopied") : t("accounts.codeCopy")}
          </button>
          <button type="button" className={styles.btn} onClick={print}>
            {t("accounts.codePrint")}
          </button>
          <button type="button" className={styles.btnPrimary} onClick={onClose}>
            {t("accounts.codeDone")}
          </button>
        </div>
      </div>

      <div data-print-sheet>
        <span className={styles.sheetBrand}>Medora</span>
        <span dir="auto">{subject}</span>
        <span dir="ltr" className={styles.sheetCode}>
          {code}
        </span>
        <span>{t("accounts.codeValid", { when })}</span>
        <span>{t("accounts.printInstruction")}</span>
      </div>
    </div>
  );
}

export default CodeDialog;
```

- [ ] **4.4 ChangePasswordForm.** Create `web/src/components/auth/ChangePasswordForm.tsx`:

```tsx
"use client";

import { useState, type FormEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import { describeError, passwordProblem, type ErrorInfo } from "@/lib/accountsUi";
import { changePassword } from "@/lib/api";
import auth from "./Auth.module.css";
import styles from "@/app/page.module.css";

export function ChangePasswordForm() {
  const { t } = useT();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorInfo | null>(null);
  const [done, setDone] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setDone(false);
    const problem = passwordProblem(next, confirm);
    if (problem) {
      setError({ key: problem === "short" ? "auth.errPasswordShort" : "auth.errPasswordMismatch", detail: null });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await changePassword({ current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setConfirm("");
      setDone(true);
    } catch (err) {
      setError(describeError(err, "password"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.login} onSubmit={submit} aria-label={t("auth.pwTitle")}>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>{t("auth.pwCurrent")}</span>
        <input type="password" dir="ltr" required autoComplete="current-password" className={styles.input} value={current} onChange={(e) => setCurrent(e.target.value)} />
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>{t("auth.fieldNew")}</span>
        <input type="password" dir="ltr" required minLength={10} autoComplete="new-password" className={styles.input} value={next} onChange={(e) => setNext(e.target.value)} />
        <span className={auth.hint}>{t("auth.passwordHint")}</span>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>{t("auth.fieldConfirm")}</span>
        <input type="password" dir="ltr" required autoComplete="new-password" className={styles.input} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </label>
      {error ? (
        <span role="alert" className={styles.loginError}>
          {t(error.key)}
          {error.detail ? <span dir="auto" className={auth.detail}> {error.detail}</span> : null}
        </span>
      ) : null}
      {done ? (
        <span role="status" className={auth.hint}>
          {t("auth.pwDone")}
        </span>
      ) : null}
      <button type="submit" className={styles.submit} disabled={busy}>
        {t("auth.pwSubmit")}
      </button>
    </form>
  );
}

export default ChangePasswordForm;
```

- [ ] **4.5 Page wrapper and routes.** Create `web/src/components/auth/ChangePasswordPage.tsx`:

```tsx
"use client";

import { useT } from "@/i18n/I18nProvider";
import { ChangePasswordForm } from "./ChangePasswordForm";
import auth from "./Auth.module.css";

/** Title + form inside a role shell's main area. */
export function ChangePasswordPage() {
  const { t } = useT();
  return (
    <div className={auth.pageWrap}>
      <h2 className={auth.pageTitle}>{t("auth.pwTitle")}</h2>
      <p className={auth.hint}>{t("auth.pwLead")}</p>
      <ChangePasswordForm />
    </div>
  );
}

export default ChangePasswordPage;
```

Create `web/src/app/doctor/password/page.tsx`, `web/src/app/nurse/password/page.tsx`, `web/src/app/admin/password/page.tsx` (same body, the role layout supplies the shell):

```tsx
import { ChangePasswordPage } from "@/components/auth/ChangePasswordPage";

export default function PasswordPage() {
  return <ChangePasswordPage />;
}
```

Create `web/src/app/patient/password/page.tsx` (phone frame, uses the patient screen chrome):

```tsx
import { ChangePasswordPage } from "@/components/auth/ChangePasswordPage";
import { PatientScreen } from "@/components/patient/PatientScreen";

export default function PatientPasswordPage() {
  return (
    <PatientScreen>
      <ChangePasswordPage />
    </PatientScreen>
  );
}
```

- [ ] **4.6 Menu entries.** In `web/src/components/Sidebar.tsx` append one item to each of `NAV.doctor`, `NAV.nurse`, `NAV.admin`:

```ts
{ key: "password", label: "auth.navPassword", href: "/doctor/password" },   // doctor
{ key: "password", label: "auth.navPassword", href: "/nurse/password" },    // nurse
{ key: "password", label: "auth.navPassword", href: "/admin/password" },    // admin
```

In `web/src/components/patient/PatientScreen.tsx`, inside `Brand()` just before `<LanguageSwitcher compact tone="light" />` add `<Link href="/patient/password" className={styles.protoTag}>{t("auth.navPassword")}</Link>` (reuses the existing small-pill style; patient screens have no sidebar, the Brand row is their only menu).

- [ ] **4.7 Verify.** `npm run typecheck && npm run build`; expected: success with `/doctor/password`, `/nurse/password`, `/admin/password`, `/patient/password` in the route table.
  Manual (mock mode): each role's sidebar shows "Change password" and highlights it on the page; patient Brand row has the link; current password `wrong` → "The current password is wrong."; new password of 9 chars → "Use at least 10 characters."; mismatch → mismatch message; valid → "Password changed." and fields cleared. CodeDialog is exercised in Task 5.
- [ ] **4.8 Commit.** `git add web && git commit -m "feat(web): one-time code dialog and change-password screens"`

---

## Task 5: Admin "Pending accounts" and Staff status, disable/enable, reset code

**Files:** create `web/src/components/admin/PendingList.tsx`, `PendingList.module.css`, `PendingView.tsx`, `web/src/app/admin/pending/page.tsx`; modify `web/src/components/admin/wards.ts`, `StaffView.tsx`, `StaffView.module.css`, `web/src/components/Sidebar.tsx`.

**Interfaces produced:**

```ts
// @/components/admin/PendingList
export function PendingList(props: { viewer: "admin" | "doctor" }): JSX.Element
// @/components/admin/wards
export const WARD_OPTIONS: { ward: string; label: Key }[]
```

- [ ] **5.1 Ward options.** Append to `web/src/components/admin/wards.ts` (add `import type { Key, TFn } from "@/i18n/messages";`, replacing the existing `TFn` import):

```ts
/** Wards an admin can assign on approval (same list as the Staff panel). */
export const WARD_OPTIONS: { ward: string; label: Key }[] = [
  { ward: "Cardiology", label: "admin.wardCardiology" },
  { ward: "Pediatrics", label: "admin.wardPediatrics" },
  { ward: "Pulmonology", label: "admin.wardPulmonology" },
];
```

- [ ] **5.2 PendingList CSS.** Create `web/src/components/admin/PendingList.module.css`:

```css
.list {
  display: flex;
  flex-direction: column;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 14px;
}

.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px 24px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--line-soft);
}

.row:last-child {
  border-bottom: none;
}

.who {
  flex: 1 1 260px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.name {
  font-size: 16px;
  font-weight: 600;
  color: var(--ink);
}

.meta {
  font-size: 14px;
  color: var(--muted);
}

.email {
  direction: ltr;
  unicode-bidi: isolate;
  text-align: start;
  font-size: 14px;
  color: var(--muted);
}

.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.heading {
  margin: 8px 0 0;
  font: 600 18px/1.2 var(--serif);
  color: var(--ink);
}

.empty {
  padding: 24px;
  color: var(--muted);
}
```

- [ ] **5.3 PendingList.** Create `web/src/components/admin/PendingList.tsx` (admin: role segmented choice + ward select; doctor: one "Approve as nurse" button; a rejected request can still be approved):

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import { Toast, useToast } from "@/components/Toast";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { fmtWhen } from "@/lib/accountsUi";
import { ApiError, approveUser, listUsers, rejectUser } from "@/lib/api";
import type { ApproveRequest, PendingUser } from "@/lib/types";
import { WARD_OPTIONS } from "./wards";
import page from "./AdminPage.module.css";
import styles from "./PendingList.module.css";

type Viewer = "admin" | "doctor";
type GrantRole = ApproveRequest["role"];

const ROLES: { value: GrantRole; label: Key }[] = [
  { value: "doctor", label: "admin.roleDoctor" },
  { value: "nurse", label: "admin.roleNurse" },
  { value: "admin", label: "admin.roleAdmin" },
];

interface RowProps {
  u: PendingUser;
  viewer: Viewer;
  busy: boolean;
  onApprove: (req: ApproveRequest) => void;
  onReject: () => void;
}

function Row({ u, viewer, busy, onApprove, onReject }: RowProps) {
  const { t, lang } = useT();
  const [role, setRole] = useState<GrantRole>("nurse");
  const [ward, setWard] = useState("");
  return (
    <div className={styles.row}>
      <div className={styles.who}>
        <span dir="auto" className={styles.name}>
          {u.name}
        </span>
        <span className={styles.email}>{u.email}</span>
        {u.note ? (
          <span dir="auto" className={styles.meta}>
            {u.note}
          </span>
        ) : null}
        <span className={styles.meta}>
          {u.requested_doctor_name ? `${t("accounts.pendingWorksWith", { doctor: u.requested_doctor_name })} · ` : ""}
          {t("accounts.pendingRequested", { when: fmtWhen(u.created_at, lang) })}
        </span>
      </div>
      <div className={styles.controls}>
        {viewer === "admin" ? (
          <>
            <select aria-label={t("accounts.approveAs")} className={page.select} value={role} onChange={(e) => setRole(e.target.value as GrantRole)}>
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {t(r.label)}
                </option>
              ))}
            </select>
            <select aria-label={t("accounts.approveWard")} className={page.select} value={ward} onChange={(e) => setWard(e.target.value)}>
              <option value="">{t("accounts.wardNone")}</option>
              {WARD_OPTIONS.map((w) => (
                <option key={w.ward} value={w.ward}>
                  {t(w.label)}
                </option>
              ))}
            </select>
            <button type="button" className={page.btnPrimary} disabled={busy} onClick={() => onApprove({ role, ward: ward || null })}>
              {t("accounts.approve")}
            </button>
          </>
        ) : (
          <button type="button" className={page.btnPrimary} disabled={busy} onClick={() => onApprove({ role: "nurse" })}>
            {t("accounts.approveNurse")}
          </button>
        )}
        {u.status === "pending" ? (
          <button type="button" className={page.btn} disabled={busy} onClick={onReject}>
            {t("accounts.reject")}
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function PendingList({ viewer }: { viewer: Viewer }) {
  const { t } = useT();
  const [pending, setPending] = useState<PendingUser[] | null>(null);
  const [rejected, setRejected] = useState<PendingUser[]>([]);
  const [failed, setFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toast, showToast] = useToast<{ text: string; tone: "ok" | "warn" }>(5000);

  const load = useCallback(() => {
    setFailed(false);
    Promise.all([listUsers("pending", { as: viewer }), listUsers("rejected", { as: viewer })])
      .then(([p, r]) => {
        setPending(p);
        setRejected(r);
      })
      .catch(() => setFailed(true));
  }, [viewer]);
  useEffect(load, [load]);

  async function act(u: PendingUser, run: () => Promise<unknown>, done: Key) {
    setBusyId(u.id);
    try {
      await run();
      showToast({ text: t(done, { name: u.name }), tone: "ok" });
      load();
    } catch (err) {
      const forbidden = err instanceof ApiError && err.status === 403;
      showToast({ text: t(forbidden ? "accounts.actionForbidden" : "accounts.actionError"), tone: "warn" });
    } finally {
      setBusyId(null);
    }
  }

  if (failed) return <ErrorCard title={t("accounts.pendingLoadError")} onRetry={load} />;
  if (!pending) return <div className="ward-skeleton" style={{ height: 120 }} aria-busy="true" />;

  const rows = (list: PendingUser[]) =>
    list.map((u) => (
      <Row
        key={u.id}
        u={u}
        viewer={viewer}
        busy={busyId === u.id}
        onApprove={(req) => void act(u, () => approveUser(u.id, req, { as: viewer }), "accounts.approvedToast")}
        onReject={() => void act(u, () => rejectUser(u.id, { as: viewer }), "accounts.rejectedToast")}
      />
    ));

  return (
    <>
      <div className={styles.list}>{pending.length ? rows(pending) : <p className={styles.empty}>{t("accounts.pendingEmpty")}</p>}</div>
      {rejected.length ? (
        <>
          <h3 className={styles.heading}>{t("accounts.rejectedHeading")}</h3>
          <div className={styles.list}>{rows(rejected)}</div>
        </>
      ) : null}
      {toast ? <Toast tone={toast.tone}>{toast.text}</Toast> : null}
    </>
  );
}

export default PendingList;
```

- [ ] **5.4 Admin page.** Create `web/src/components/admin/PendingView.tsx`:

```tsx
"use client";

import { useT } from "@/i18n/I18nProvider";
import { PendingList } from "./PendingList";
import page from "./AdminPage.module.css";

export function PendingView() {
  const { t } = useT();
  return (
    <div className={page.page}>
      <div className={page.head}>
        <div className={page.titles}>
          <h2 className={page.h2}>{t("accounts.pendingTitle")}</h2>
          <span className={page.sub}>{t("accounts.pendingSub")}</span>
        </div>
      </div>
      <PendingList viewer="admin" />
    </div>
  );
}

export default PendingView;
```

Create `web/src/app/admin/pending/page.tsx`:

```tsx
import { PendingView } from "@/components/admin/PendingView";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("accounts.pendingTitle")} · Medora` };
}

export default function AdminPendingPage() {
  return <PendingView />;
}
```

In `Sidebar.tsx` `NAV.admin` insert after the `staff` item: `{ key: "pending", label: "accounts.navPending", href: "/admin/pending" },`.

- [ ] **5.5 Staff table: status and actions.** In `StaffView.module.css` change `.grid` and add status styles:

```css
.grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 100px 150px 100px 130px 230px;
  gap: 16px;
}

.status {
  font-size: 14px;
  font-weight: 600;
  color: var(--news-normal-fg);
}

.statusOff {
  color: var(--danger-ink);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
```

In `StaffView.tsx`:
1. Imports: `import { CodeDialog } from "@/components/shared/CodeDialog";`, `import { useMe } from "@/lib/useMe";`, extend the api import to `disableUser, enableUser, getStaff, issueResetCode`, and add `import type { Key } from "@/i18n/messages"` merge (already imports `Key`). Add `const STATUS_LABEL: Record<StaffMember["status"], Key> = { active: "accounts.statusActive", pending: "accounts.statusPending", disabled: "accounts.statusDisabled", rejected: "accounts.statusRejected" };`.
2. In the `sendInvite` mock literal keep `status: "pending"` (from Task 1).
3. Inside the component add state and handlers:

```tsx
  const me = useMe("admin");
  const [code, setCode] = useState<{ name: string; code: string; expires_at: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function toggle(s: StaffMember) {
    setBusyId(s.id);
    try {
      const next = s.status === "active" ? await disableUser(s.id) : await enableUser(s.id);
      setStaff((list) => (list ?? []).map((x) => (x.id === s.id ? { ...x, status: next.status } : x)));
      showToast(t(next.status === "active" ? "accounts.enabledToast" : "accounts.disabledToast", { name: s.name }));
    } catch {
      showToast(t("accounts.actionError"));
    } finally {
      setBusyId(null);
    }
  }

  async function issueCode(s: StaffMember) {
    setBusyId(s.id);
    try {
      setCode({ name: s.name, ...(await issueResetCode(s.id)) });
    } catch {
      showToast(t("accounts.actionError"));
    } finally {
      setBusyId(null);
    }
  }
```

4. Header: add `<span>{t("accounts.staffColStatus")}</span>` after the Ward column and `<span>{t("accounts.staffColActions")}</span>` at the end; add two more skeleton `<span className="ward-skeleton" style={{ height: 14, width: 70 }} />` to the skeleton row.
5. Row: after the ward cell and last-login cell, add:

```tsx
                    <span className={`${styles.status} ${s.status === "active" ? "" : styles.statusOff}`}>{t(STATUS_LABEL[s.status])}</span>
                    <span className={styles.actions}>
                      {(s.status === "active" || s.status === "disabled") && s.id !== me?.id ? (
                        <button type="button" className={page.btn} disabled={busyId === s.id} onClick={() => void toggle(s)}>
                          {s.status === "active" ? t("accounts.disable") : t("accounts.enable")}
                        </button>
                      ) : null}
                      {s.status === "active" ? (
                        <button type="button" className={page.btn} disabled={busyId === s.id} onClick={() => void issueCode(s)}>
                          {t("accounts.issueResetCode")}
                        </button>
                      ) : null}
                    </span>
```

   (Place the status cell between the ward cell and last-login cell so the order matches the header: name, role, ward, last login, status, actions. Put the `Status` header after `staffColLogin` accordingly.)
6. Before `{toast ? ...}` add `{code ? <CodeDialog subject={t("accounts.codeFor", { name: code.name })} code={code.code} expiresAt={code.expires_at} onClose={() => setCode(null)} /> : null}`.

- [ ] **5.6 Verify.** `npm run typecheck && npm run build`; expected success with `/admin/pending`.
  Manual (mock): `/admin/pending` lists Amel, Karim, Salma and a "Rejected requests" group with Test Person; approve Karim as Doctor + Pulmonology → toast "Karim Zouari approved.", row gone, and `/admin/staff` (client navigation, same tab) shows him Active with role Doctor; reject Salma → moves to rejected; approve the rejected Test Person → works. Staff page: Status column; Nurse Sami shows Disabled with "Enable"; click Disable on Nurse Ines → "Disabled"; own row (Mme Gharbi) has no Disable button; "Reset code" opens the dialog with an `XXXXX-XXXXX` code, "Copy" turns into "Copied" (paste elsewhere to confirm), "Print" opens the print preview showing only the sheet (Medora, name, code, validity, instruction) in light mode, refreshing the page with the dialog open prompts "Leave site?" and the code is gone after reload. In Arabic the code stays `XXXXX-XXXXX` left-to-right and centered.
- [ ] **5.7 Commit.** `git add web && git commit -m "feat(web): admin pending accounts, staff status, disable/enable and reset codes"`

---

## Task 6: Doctor "My team"

**Files:** create `web/src/components/doctor/TeamView.tsx`, `TeamView.module.css`, `web/src/app/doctor/team/page.tsx`; modify `web/src/components/Sidebar.tsx`.

**Interfaces consumed:** `PendingList viewer="doctor"`, `getMyTeam`, `disableUser`, `enableUser`.

- [ ] **6.1 CSS.** Create `web/src/components/doctor/TeamView.module.css`:

```css
.page {
  padding: 36px 40px 40px;
  display: flex;
  flex-direction: column;
  gap: 22px;
  min-height: 100vh;
}

.h2 {
  margin: 0;
  font: 600 40px/1.1 var(--serif);
  color: var(--ink);
}

.sub {
  font-size: 16px;
  color: var(--muted);
}

.section {
  margin: 8px 0 0;
  font: 600 20px/1.2 var(--serif);
  color: var(--ink);
}

.members {
  display: flex;
  flex-direction: column;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 14px;
}

.member {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 24px;
  padding: 14px 24px;
  border-bottom: 1px solid var(--line-soft);
}

.member:last-child {
  border-bottom: none;
}

.mwho {
  flex: 1 1 240px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.mname {
  font-size: 16px;
  font-weight: 600;
  color: var(--ink);
}

.memail {
  direction: ltr;
  unicode-bidi: isolate;
  text-align: start;
  font-size: 14px;
  color: var(--muted);
}

.off {
  font-size: 14px;
  font-weight: 600;
  color: var(--danger-ink);
}

.empty {
  padding: 24px;
  color: var(--muted);
}
```

- [ ] **6.2 TeamView.** Create `web/src/components/doctor/TeamView.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { PendingList } from "@/components/admin/PendingList";
import page from "@/components/admin/AdminPage.module.css";
import { Toast, useToast } from "@/components/Toast";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { useT } from "@/i18n/I18nProvider";
import { disableUser, enableUser, getMyTeam } from "@/lib/api";
import type { UserAdmin } from "@/lib/types";
import styles from "./TeamView.module.css";

export function TeamView() {
  const { t } = useT();
  const [team, setTeam] = useState<UserAdmin[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toast, showToast] = useToast<string>(5000);

  const load = useCallback(() => {
    setFailed(false);
    getMyTeam().then(setTeam, () => setFailed(true));
  }, []);
  useEffect(load, [load]);

  async function toggle(u: UserAdmin) {
    setBusyId(u.id);
    try {
      const next = u.status === "active" ? await disableUser(u.id, { as: "doctor" }) : await enableUser(u.id, { as: "doctor" });
      setTeam((list) => (list ?? []).map((x) => (x.id === u.id ? { ...x, status: next.status } : x)));
      showToast(t(next.status === "active" ? "accounts.enabledToast" : "accounts.disabledToast", { name: u.name }));
    } catch {
      showToast(t("accounts.actionError"));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className={styles.page}>
      <div>
        <h2 className={styles.h2}>{t("accounts.teamTitle")}</h2>
        <span className={styles.sub}>{t("accounts.teamSub")}</span>
      </div>

      <h3 className={styles.section}>{t("accounts.teamRequests")}</h3>
      <PendingList viewer="doctor" />

      <h3 className={styles.section}>{t("accounts.teamMembers")}</h3>
      {failed ? (
        <ErrorCard title={t("accounts.teamLoadError")} onRetry={load} />
      ) : !team ? (
        <div className="ward-skeleton" style={{ height: 90 }} aria-busy="true" />
      ) : (
        <div className={styles.members}>
          {team.length ? (
            team.map((u) => (
              <div key={u.id} className={styles.member}>
                <div className={styles.mwho}>
                  <span dir="auto" className={styles.mname}>
                    {u.name}
                  </span>
                  <span className={styles.memail}>{u.email}</span>
                </div>
                {u.status === "disabled" ? <span className={styles.off}>{t("accounts.statusDisabled")}</span> : null}
                {u.status === "active" || u.status === "disabled" ? (
                  <button type="button" className={page.btn} disabled={busyId === u.id} onClick={() => void toggle(u)}>
                    {u.status === "active" ? t("accounts.disable") : t("accounts.enable")}
                  </button>
                ) : null}
              </div>
            ))
          ) : (
            <p className={styles.empty}>{t("accounts.teamEmpty")}</p>
          )}
        </div>
      )}
      {toast ? <Toast>{toast}</Toast> : null}
    </div>
  );
}

export default TeamView;
```

- [ ] **6.3 Page and nav.** Create `web/src/app/doctor/team/page.tsx`:

```tsx
import { TeamView } from "@/components/doctor/TeamView";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("accounts.teamTitle")} · Medora` };
}

export default function DoctorTeamPage() {
  return <TeamView />;
}
```

In `Sidebar.tsx` `NAV.doctor` insert after `requests`: `{ key: "team", label: "accounts.navTeam", href: "/doctor/team" },`.

- [ ] **6.4 Verify.** `npm run typecheck && npm run build`; expected success with `/doctor/team`.
  Manual (mock): the doctor sees only Amel Cherif in requests (not Karim or Salma) plus the rejected Test Person, with a single "Approve as nurse" button and no role/ward pickers; approving Amel moves her to Team members (Active); team shows Nurse Ines Active and Nurse Sami Disabled; Enable Sami works; Disable Ines works; sidebar item highlights on `/doctor/team`.
- [ ] **6.5 Commit.** `git add web && git commit -m "feat(web): doctor My team tab with nurse approvals and enable/disable"`

---

## Task 7: Patient detail: enrollment code and "Share with a doctor"; admin patient lookup

**Files:** create `web/src/components/shared/EnrollmentCode.tsx`, `ShareWithDoctor.tsx`, `AccessPanel.tsx`, `AccessPanel.module.css`, `web/src/components/admin/PatientLookup.tsx`, `web/src/app/admin/patients/page.tsx`; modify `web/src/components/doctor/PatientDetail.tsx`, `web/src/components/Sidebar.tsx`.

**Interfaces produced:**

```ts
export function EnrollmentCode(props: { patientId: string; patientName: string }): JSX.Element
export function ShareWithDoctor(props: { patientId: string; excludeIds: string[] }): JSX.Element
export function AccessPanel(props: { patientId: string; patientName: string; excludeIds: string[] }): JSX.Element
```

- [ ] **7.1 CSS.** Create `web/src/components/shared/AccessPanel.module.css`:

```css
.card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 20px 24px;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 14px;
}

.title {
  margin: 0;
  font: 600 18px/1.2 var(--serif);
  color: var(--ink);
}

.lead {
  margin: 0;
  font-size: 14px;
  line-height: 1.4;
  color: var(--muted);
}

.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
}

.grow {
  flex: 1 1 160px;
}

.grant {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
  padding: 8px 0;
  border-bottom: 1px solid var(--line-soft);
}

.error {
  font-size: 14px;
  color: var(--danger-ink);
}

.btn {
  min-height: 40px;
  padding: 0 14px;
  font: 600 14px/1 var(--sans);
  color: var(--ink);
  background: var(--paper);
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  cursor: pointer;
}

.btnPrimary {
  min-height: 40px;
  padding: 0 14px;
  font: 600 14px/1 var(--sans);
  color: var(--paper);
  background: var(--ink);
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.btn:disabled,
.btnPrimary:disabled {
  opacity: 0.6;
  cursor: progress;
}

.input {
  min-height: 40px;
  padding: 0 12px;
  font-size: 15px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  background: var(--paper);
  color: var(--ink);
}
```

- [ ] **7.2 EnrollmentCode.** Create `web/src/components/shared/EnrollmentCode.tsx` (the button is disabled while a request is in flight so a double click cannot issue, and revoke, two codes):

```tsx
"use client";

import { useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import { ApiError, issueEnrollmentCode } from "@/lib/api";
import type { OneTimeCode } from "@/lib/types";
import { CodeDialog } from "./CodeDialog";
import styles from "./AccessPanel.module.css";

export function EnrollmentCode({ patientId, patientName }: { patientId: string; patientName: string }) {
  const { t } = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issued, setIssued] = useState<OneTimeCode | null>(null);

  async function issue() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      setIssued(await issueEnrollmentCode(patientId));
    } catch (err) {
      setError(t(err instanceof ApiError && err.code === "already_enrolled" ? "accounts.enrollAlready" : "accounts.actionError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.card}>
      <h3 className={styles.title}>{t("accounts.enrollTitle")}</h3>
      <p className={styles.lead}>{t("accounts.enrollLead")}</p>
      <div className={styles.row}>
        <button type="button" className={styles.btnPrimary} disabled={busy} onClick={() => void issue()}>
          {busy ? t("accounts.enrollBusy") : t("accounts.enrollIssue")}
        </button>
      </div>
      {error ? (
        <span role="alert" className={styles.error}>
          {error}
        </span>
      ) : null}
      {issued ? (
        <CodeDialog subject={t("accounts.enrollSubject", { name: patientName })} code={issued.code} expiresAt={issued.expires_at} onClose={() => setIssued(null)} />
      ) : null}
    </section>
  );
}

export default EnrollmentCode;
```

- [ ] **7.3 ShareWithDoctor.** Create `web/src/components/shared/ShareWithDoctor.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { Toast, useToast } from "@/components/Toast";
import { useT } from "@/i18n/I18nProvider";
import { fmtWhen } from "@/lib/accountsUi";
import { getDoctorDirectory, getPatientAccess, grantPatientAccess, revokePatientAccess } from "@/lib/api";
import { now } from "@/lib/time";
import type { DoctorRef, PatientAccessGrant } from "@/lib/types";
import styles from "./AccessPanel.module.css";

const DAY_MS = 86_400_000;
const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);

export function ShareWithDoctor({ patientId, excludeIds }: { patientId: string; excludeIds: string[] }) {
  const { t, lang } = useT();
  const [grants, setGrants] = useState<PatientAccessGrant[] | null>(null);
  const [directory, setDirectory] = useState<DoctorRef[]>([]);
  const [failed, setFailed] = useState(false);
  const [pick, setPick] = useState("");
  const [until, setUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, showToast] = useToast<string>(5000);

  const load = useCallback(() => {
    setFailed(false);
    Promise.all([getPatientAccess(patientId), getDoctorDirectory()]).then(
      ([g, d]) => {
        setGrants(g);
        setDirectory(d);
      },
      () => setFailed(true),
    );
  }, [patientId]);
  useEffect(load, [load]);

  const choices = directory.filter((d) => !excludeIds.includes(d.id) && !(grants ?? []).some((g) => g.doctor_id === d.id));

  async function add() {
    if (!pick || busy) return;
    setBusy(true);
    try {
      // The date input is a local calendar day: share until the end of that day.
      const expires_at = until ? new Date(`${until}T23:59:59`).toISOString() : undefined;
      const g = await grantPatientAccess(patientId, { doctor_id: pick, ...(expires_at ? { expires_at } : {}) });
      setGrants((list) => [...(list ?? []).filter((x) => x.doctor_id !== g.doctor_id), g]);
      setPick("");
      setUntil("");
      showToast(t("accounts.shareAdded", { name: g.doctor_name }));
    } catch {
      showToast(t("accounts.actionError"));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(g: PatientAccessGrant) {
    setBusy(true);
    try {
      await revokePatientAccess(patientId, g.doctor_id);
      setGrants((list) => (list ?? []).filter((x) => x.doctor_id !== g.doctor_id));
      showToast(t("accounts.shareRevoked", { name: g.doctor_name }));
    } catch {
      showToast(t("accounts.actionError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.card}>
      <h3 className={styles.title}>{t("accounts.shareTitle")}</h3>
      <p className={styles.lead}>{t("accounts.shareLead")}</p>
      {failed ? (
        <span role="alert" className={styles.error}>
          {t("accounts.shareLoadError")}
        </span>
      ) : grants && grants.length === 0 ? (
        <p className={styles.lead}>{t("accounts.shareEmpty")}</p>
      ) : (
        (grants ?? []).map((g) => (
          <div key={g.doctor_id} className={styles.grant}>
            <span dir="auto" className={`${styles.grow} ${styles.title}`}>
              {g.doctor_name}
            </span>
            <span className={styles.lead}>{t("accounts.shareUntil", { when: fmtWhen(g.expires_at, lang) })}</span>
            <button type="button" className={styles.btn} disabled={busy} onClick={() => void revoke(g)}>
              {t("accounts.shareRevoke")}
            </button>
          </div>
        ))
      )}
      <div className={styles.row}>
        <select aria-label={t("accounts.sharePick")} className={`${styles.input} ${styles.grow}`} value={pick} onChange={(e) => setPick(e.target.value)}>
          <option value="">{t("accounts.sharePick")}</option>
          {choices.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <label className={styles.row}>
          <span className={styles.lead}>{t("accounts.shareExpiry")}</span>
          <input
            type="date"
            className={styles.input}
            value={until}
            min={isoDay(now().getTime() + DAY_MS)}
            max={isoDay(now().getTime() + 365 * DAY_MS)}
            onChange={(e) => setUntil(e.target.value)}
          />
        </label>
        <button type="button" className={styles.btnPrimary} disabled={!pick || busy} onClick={() => void add()}>
          {t("accounts.shareAdd")}
        </button>
      </div>
      <span className={styles.lead}>{t("accounts.shareExpiryHint")}</span>
      {toast ? <Toast>{toast}</Toast> : null}
    </section>
  );
}

export default ShareWithDoctor;
```

- [ ] **7.4 AccessPanel.** Create `web/src/components/shared/AccessPanel.tsx`:

```tsx
"use client";

import { EnrollmentCode } from "./EnrollmentCode";
import { ShareWithDoctor } from "./ShareWithDoctor";

/** Enrollment code + doctor sharing for one patient. Mount only for the attending doctor or an admin. */
export function AccessPanel({ patientId, patientName, excludeIds }: { patientId: string; patientName: string; excludeIds: string[] }) {
  return (
    <>
      <EnrollmentCode patientId={patientId} patientName={patientName} />
      <ShareWithDoctor patientId={patientId} excludeIds={excludeIds} />
    </>
  );
}

export default AccessPanel;
```

- [ ] **7.5 Mount in the doctor's patient detail.** In `web/src/components/doctor/PatientDetail.tsx` add `import { AccessPanel } from "@/components/shared/AccessPanel";` and, in the second column, before `<ExamsPanel patientId={id} />`:

```tsx
              {me && data.patient.attending_doctor_id === me.id ? (
                <AccessPanel
                  patientId={id}
                  patientName={`${data.patient.first_name} ${data.patient.last_name}`}
                  excludeIds={[me.id]}
                />
              ) : null}
```

(`me` is already `useMe("doctor")` in this component. Only the attending doctor sees it: a doctor who holds a sharing grant would get 403 from the API.)

- [ ] **7.6 Admin lookup.** Create `web/src/components/admin/PatientLookup.tsx` (admin has no patient list in the contract, so this is the minimum entry point to enroll any patient; see Contract Gaps):

```tsx
"use client";

import { useState, type FormEvent } from "react";
import { AccessPanel } from "@/components/shared/AccessPanel";
import { useT } from "@/i18n/I18nProvider";
import { getPatient } from "@/lib/api";
import type { Patient } from "@/lib/types";
import page from "./AdminPage.module.css";

export function PatientLookup() {
  const { t } = useT();
  const [id, setId] = useState("");
  const [patient, setPatient] = useState<Patient | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function open(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setPatient(null);
    try {
      setPatient(await getPatient(id.trim()));
    } catch {
      setError(t("accounts.lookupNotFound"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={page.page}>
      <div className={page.head}>
        <div className={page.titles}>
          <h2 className={page.h2}>{t("accounts.lookupTitle")}</h2>
          <span className={page.sub}>{t("accounts.lookupSub")}</span>
        </div>
      </div>
      <form onSubmit={open} style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
        <label className={page.field}>
          <span className={page.fieldLabel}>{t("accounts.lookupLabel")}</span>
          <input dir="ltr" required placeholder="p-0001" className={page.input} value={id} onChange={(e) => setId(e.target.value)} />
        </label>
        <button type="submit" className={page.btnPrimary} disabled={busy}>
          {t("accounts.lookupGo")}
        </button>
      </form>
      {error ? <span role="alert">{error}</span> : null}
      {patient ? (
        <>
          <h3 dir="auto" className={page.h2} style={{ fontSize: 28 }}>
            {patient.first_name} {patient.last_name}
          </h3>
          <AccessPanel
            patientId={patient.id}
            patientName={`${patient.first_name} ${patient.last_name}`}
            excludeIds={patient.attending_doctor_id ? [patient.attending_doctor_id] : []}
          />
        </>
      ) : null}
    </div>
  );
}

export default PatientLookup;
```

Create `web/src/app/admin/patients/page.tsx`:

```tsx
import { PatientLookup } from "@/components/admin/PatientLookup";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("accounts.lookupTitle")} · Medora` };
}

export default function AdminPatientsPage() {
  return <PatientLookup />;
}
```

In `Sidebar.tsx` `NAV.admin` insert after `pending`: `{ key: "patients", label: "accounts.navEnroll", href: "/admin/patients" },`.

- [ ] **7.7 Verify.** `npm run typecheck && npm run build`; expected success with `/admin/patients`.
  Manual (mock): open `/doctor/patients/p-0002` (Dr Trabelsi is attending): the "Patient app access" and "Share with a doctor" cards appear; "Issue enrollment code" opens the dialog titled "Enrollment code for Omar Jaziri"; closing and re-issuing gives a different code; `/doctor/patients/p-0001`: issuing shows "This patient already has an account. Disable it before issuing a new code." Sharing: Dr Karoui is listed with an expiry, the picker excludes Dr Karoui and Dr Trabelsi, sharing with Dr Ben Romdhane (no date) adds a row dated ~30 days ahead, "Revoke" removes it, the date picker cannot pick beyond one year. `/admin/patients`: enter `p-0002` -> panels appear; `p-9999` -> "No patient with this ID."; Arabic: cards mirror, code stays LTR.
- [ ] **7.8 Commit.** `git add web && git commit -m "feat(web): enrollment codes and doctor sharing on patient detail, admin patient lookup"`

---

## Task 8: Session end handling and final QA

**Files:** modify `web/src/lib/api.ts`, `web/src/components/LoginForm.tsx`, `web/src/app/page.tsx`.

Rationale: spec 6.5 says disabling an account kills its token on the next request. The current `http()` just throws, leaving a half-working screen. Make a 401 on any non-auth call return the user to sign-in with a message.

- [ ] **8.1 Expire the session on 401.** In `web/src/lib/api.ts`, add above `http()`:

```ts
/** A 401 outside /auth/* means the token is dead (expired, or the account was disabled): drop it and go to sign-in. */
function expireSession(): void {
  setToken(null);
  meCache.clear();
  if (typeof window !== "undefined" && window.location.pathname !== "/") window.location.assign("/?expired=1");
}
```

and in `http()` change the `!res.ok` block to:

```ts
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string; code?: string };
    if (res.status === 401 && token && !path.startsWith("/auth/")) expireSession();
    throw new ApiError(res.status, err.code ?? "http_error", err.detail ?? res.statusText);
  }
```

(`/auth/change-password` returns 401 `bad_credentials` for a wrong current password: the `/auth/` exclusion keeps that a form error, not a logout. Mock mode never calls `http()`, so demos are unaffected.)

- [ ] **8.2 Notice on the sign-in form.** In `LoginForm.tsx` add `import { useSearchParams } from "next/navigation";` (merge with the existing `useRouter` import), `import auth from "@/components/auth/Auth.module.css";`, inside the component `const expired = useSearchParams().get("expired") === "1";`, and as the first child of the `<form>`:

```tsx
      {expired ? (
        <span role="status" className={auth.notice}>
          {t("auth.errSessionExpired")}
        </span>
      ) : null}
```

In `web/src/app/page.tsx` wrap the form (Next requires Suspense around `useSearchParams`): add `import { Suspense } from "react";` and change `<LoginForm />` to `<Suspense fallback={null}><LoginForm /></Suspense>`.

- [ ] **8.3 Verify.** `npm run typecheck && npm run build`; expected success, no "useSearchParams should be wrapped in a suspense boundary" error.
  Manual (real mode with the Task 3 stub changed to answer 401 `{"detail":"x","code":"bad_credentials"}` for every path and `NEXT_PUBLIC_USE_MOCKS=0`): put any value in `sessionStorage.ward_token`, open `/doctor` -> redirected to `/?expired=1` with "Your session ended. Sign in again." and the token cleared; `/` itself does not loop.
- [ ] **8.4 Final QA sweep (mock mode, all three languages, desktop and 390 px width).** Check each box before the PR:
  - [ ] fr/ar/en: `/register`, `/reset`, `/admin/pending`, `/admin/staff`, `/doctor/team`, patient detail panels, change-password pages show no raw key (`accounts.` or `auth.` text) anywhere.
  - [ ] ar: sidebar and pages mirror; codes, emails, passwords, patient IDs, dates input are LTR; the code dialog is centered; print preview of a code reads correctly.
  - [ ] No code survives: after closing the dialog, search `localStorage`/`sessionStorage`/URL in devtools for the code -> not found.
  - [ ] Keyboard: Tab order in the dialog starts on "Copy"; all buttons reachable; Enter submits forms.
  - [ ] Register success text is identical for a new email and a repeated email.
  - [ ] `git status` shows only `web/` and this plan's file changed.
- [ ] **8.5 Commit.** `git add web && git commit -m "feat(web): end the session on 401 and show a sign-in notice"`

---

## Contract Gaps (the UI needs these; the API above does not give them)

1. **Admin has no way to list or find patients.** `GET /patients` is the doctor's own list (nurse: by ward). The brief wants admin "Issue enrollment code" on patient detail, but there is no admin patient screen or list. Stopgap in Task 7: `/admin/patients` takes a patient ID and calls `GET /patients/{id}`. Needs: confirm admin may `GET /patients/{id}`, and ideally an admin `GET /patients?q=` search (or a list) for reception.
2. **No endpoint to set a ward on an already-active user.** The spec says a doctor-approved nurse has `ward = null` and "the hospital admin may add a ward later", but no `PATCH /users/{id}` or similar exists. The Staff page cannot offer "assign ward". Needs: `POST /users/{id}/ward {ward}` or similar.
3. **Reset code cannot be issued for patient accounts.** `POST /users/{id}/reset-code` is admin-only and the admin screen is built on `GET /staff` (staff only), so a patient who forgets a password has no path. Needs: either patients listed in an admin accounts list, or a reset-code endpoint addressed by patient (`/patients/{id}/reset-code`).
4. **Register success cannot tell staff from patient.** Spec section 10 asks for "waiting for approval" or "you're in" screens, but the 202 is deliberately generic (anti-enumeration). The UI shows one neutral screen with both next steps. If product wants a distinct patient message, the only safe signal is the user having typed an enrollment code, which leaks nothing (it is client-side); not done by default.
5. **`weak_password` `detail` is English only.** The UI shows a localized sentence and the server detail as secondary text. Needs: stable sub-codes (`too_short`, `common`, `same_as_email`...) or accept English in fr/ar.
6. **Enrollment/reset code format on input.** UI normalises to uppercase `XXXXX-XXXXX` (dash inserted when exactly 10 chars). Needs confirmation that the backend accepts the dashed form (spec 7 says codes are "shown as XXXXX-XXXXX").
7. **Behaviour of a live session after `disable`, and after `change-password`, is unspecified.** Task 8 assumes a disabled user's token gets 401 on the next request (spec 6.5) and sends the user to sign-in. Unknown: does the API return a distinct code (e.g. 403 `account_disabled`) there, and does `change-password` invalidate other tokens or return a new one? The UI keeps the current session after a 204.
8. **`GET /staff` may not include pending/rejected rows.** Assumed it lists only active/disabled staff (pending/rejected live under `/users?status=`). If it returns all statuses, the Staff table already shows them with no actions.
9. **Ward names for the approve picker.** No endpoint lists wards; Task 5 reuses the hard-coded list already in `StaffView` (Cardiology, Pediatrics, Pulmonology). Needs `GET /wards` eventually.
10. **Rate-limit feedback.** 429 gives no `Retry-After` contract; the UI shows a generic "wait a minute" message.
11. **Doctor "disable team member" for a nurse who is also ward-scoped** is assumed to work on the same `POST /users/{id}/disable`; the 403 case is shown as "You aren't allowed to do that."

## Contract gap resolutions (2026-10-10, from the backend plan owner)

These override the stopgaps above where they differ.

1. **Admin patient search:** use the existing `GET /patients?q=…` (the admin branch already searches by name or ID
   and returns `PatientListItem`). Drop the ID-only stopgap. Admin cannot call `GET /patients/{id}` (403), so the
   admin enrollment screen works from the list row only.
2. **Ward on an active user:** the backend adds `PATCH /users/{id}` with body `{ward: string | null}`. It is
   admin-only, works for doctors and nurses, and returns `UserAdmin`. Add a ward editor on the Staff page.
3. **Patient reset code:** the backend adds `POST /patients/{id}/reset-code`. The admin or attending doctor calls it
   and gets `{code, expires_at}`; it returns 404 `not_found` when the patient has no active account. Show it next to
   "Issue enrollment code" on patient detail and on the admin patient row.
4. **Generic register success:** this is by design (no account enumeration). Keep the single neutral screen.
5. **`weak_password` detail:** stays English. The UI validates with the same rules first (`passwordProblem`:
   at least 10 characters, at most 72 bytes, not the email or name), so the server message is a fallback only.
6. **Code format:** the backend normalizes uppercase or lowercase, spaces and dashes, so any form is accepted.
7. **Sessions:** a disabled user's token returns 401 on the next request (handled by the Task 8 redirect). A password
   change does not end other sessions in v1.
8. **`GET /staff`:** lists only accounts with a role (doctor, nurse, admin) in any status except pending or rejected,
   which have no role yet. Pending and rejected appear only in `GET /users?status=…`.
9. **Wards:** keep the three hard-coded wards from `StaffView`.
10. **429:** there is no `Retry-After`. Keep the generic "wait a minute" message.
