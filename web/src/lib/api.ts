// The single data layer. Components read and write through these functions only.
//
// Mock mode (NEXT_PUBLIC_USE_MOCKS=1, the default when unset): every call resolves
// from an in-memory copy of `web/src/mocks` after 150 ms. Mutations write to that
// store, so a later read reflects them (until a full page reload).
// Real mode: calls NEXT_PUBLIC_API_URL with the paths of docs/contracts/api.md.
// Paths marked NOT IN CONTRACT have no api.md 1.4 endpoint yet (see the Task 1 report).
import { createStore, generateCode, MOCK_CODES, EXAM_CATALOGUE, mockAssistant, USERS, userName, type AssistantContext, type MockStore } from "@/mocks";
import { now, tunisDate, USE_MOCKS } from "./time";
import { HEALTH_CATEGORIES } from "./types";
import type {
  AccountStatus,
  Alert,
  AiSummary,
  Appointment,
  AssistantResponse,
  CatalogueItem,
  ChatResponse,
  ChatTurn,
  Conversation,
  ConversationMessage,
  HealthWatch,
  ApproveRequest,
  ChangePasswordRequest,
  ConfirmAppointmentRequest,
  CreatePrescriptionRequest,
  Device,
  DoctorRef,
  Dose,
  ExamOrder,
  HomeCarePlan,
  ImpactIndicator,
  ImpactReport,
  HealthAudience,
  HealthCategory,
  HealthEvent,
  HealthEventInput,
  HealthPrefs,
  Hospital,
  LoginResponse,
  Me,
  MedRoundGroup,
  Note,
  OneTimeCode,
  Patient,
  PatientAccessGrant,
  PatientSummary,
  PendingUser,
  Prescription,
  RegisterRequest,
  RegisterResponse,
  ResetRequest,
  Role,
  SlotOffer,
  StaffMember,
  Urgency,
  UserAdmin,
  Vital,
  WardBed,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const MOCK_DELAY_MS = 150;
const TOKEN_KEY = "ward_token";
const DEFAULT_WARD = "Cardiology";

export { USE_MOCKS };

/** Who performs a mutation. Mock mode only — the real API takes the actor from the JWT. */
export interface ActorOpts {
  by?: string; // user id, e.g. "u-0001"
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ── Transport ───────────────────────────────────────────────────────────────

/** Keeps the JWT for this browser tab (sessionStorage), so a reload stays signed in. */
export function setToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

/** Forget everything this tab holds about the session: the token and the remembered /me. */
function clearSession(): void {
  setToken(null);
  meCache.clear();
}

/** A 401 outside /auth/* means the token is dead (expired, or the account was disabled): drop it and go to sign-in. */
function expireSession(): void {
  clearSession();
  if (typeof window !== "undefined" && window.location.pathname !== "/") window.location.assign("/?expired=1");
}

/**
 * Shared 401 rule for every authenticated call. /auth/* is skipped (login errors are form errors), except
 * /auth/change-password: there `bad_credentials` is a wrong current password (form error), any other 401 is a dead token.
 */
function handleUnauthorized(path: string, hadToken: boolean, code?: string): void {
  const authForm = path.startsWith("/auth/") && !(path === "/auth/change-password" && code !== "bad_credentials");
  if (authForm) return;
  // No token at all (e.g. Back after logging out): plain sign-in, no "session ended" notice.
  if (hadToken) expireSession();
  else if (typeof window !== "undefined" && window.location.pathname !== "/") window.location.assign("/");
}

async function http<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string; code?: string };
    if (res.status === 401) handleUnauthorized(path, !!token, err.code);
    throw new ApiError(res.status, err.code ?? "http_error", err.detail ?? res.statusText);
  }
  // Some endpoints (assign, discharge) have no response body in api.md.
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

async function upload<T>(path: string, form: FormData): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: form });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string; code?: string };
    if (res.status === 401) handleUnauthorized(path, !!token, err.code);
    throw new ApiError(res.status, err.code ?? "http_error", err.detail ?? res.statusText);
  }
  return (await res.json()) as T;
}

let store: MockStore | null = null;
const db = (): MockStore => (store ??= createStore());

/** Restore the fixtures (drops every mock mutation). */
export function resetMockStore(): void {
  store = createStore();
}

/** Runs `fn` against the mock store after the mock delay; returns a deep copy. */
function mock<T>(fn: (s: MockStore) => T): Promise<T> {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      try {
        resolve(structuredClone(fn(db())));
      } catch (e) {
        reject(e);
      }
    }, MOCK_DELAY_MS);
  });
}

function notFound(what: string): never {
  throw new ApiError(404, "not_found", `${what} not found`);
}

const iso = (d: Date) => d.toISOString().replace(".000Z", "Z");
const byNews = (a: { latest_news2: number | null }, b: { latest_news2: number | null }) =>
  (b.latest_news2 ?? -1) - (a.latest_news2 ?? -1);

// ── Auth ────────────────────────────────────────────────────────────────────

/** POST /auth/login `{"email","password"}` → token + user. Stores the token. Real mode only. */
export async function login(email: string, password: string): Promise<LoginResponse> {
  if (USE_MOCKS) throw new ApiError(400, "mock_mode", "Login is only used when NEXT_PUBLIC_USE_MOCKS=0");
  const res = await http<LoginResponse>("POST", "/auth/login", { email, password });
  setToken(res.access_token);
  return res;
}

/** POST /auth/logout (Bearer → 204), best effort, then forget the session on this device. Mock mode skips the network. */
export async function logout(): Promise<void> {
  const token = getToken();
  clearSession(); // local first: a slow or unreachable API must never keep the session alive
  if (USE_MOCKS || !token) return;
  try {
    await fetch(`${BASE}/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(3000),
    });
  } catch {
    /* best effort: only the server's audit row is lost */
  }
}

/** True while this tab holds a session (always true in mock mode, which has no sign-in). */
export function hasSession(): boolean {
  return USE_MOCKS || getToken() !== null;
}

/** GET /me. In mock mode, `role` picks which demo user you are (default doctor). */
export function getMe(role: Role = "doctor"): Promise<Me> {
  if (USE_MOCKS) return mock(() => USERS[role]);
  return http<Me>("GET", "/me");
}

const meCache = new Map<string, Promise<Me>>();

/** getMe() remembered for this tab: per demo role in mock mode, per session token in real mode. */
export function getMeCached(role: Role = "doctor"): Promise<Me> {
  const key = USE_MOCKS ? `mock:${role}` : `token:${getToken() ?? ""}`;
  let p = meCache.get(key);
  if (!p) {
    p = getMe(role);
    meCache.set(key, p);
    p.catch(() => meCache.delete(key));
  }
  return p;
}

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
  return { id: m.id, name: m.name, email: m.email, role: m.role, status: m.status, ward: m.ward, supervisor_id: null, requested_role: null, requested_doctor_id: null };
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

/** POST /auth/register → always the same generic 202. Mock: weak password → 422; `doctor` role with a requested doctor → 422. */
export function registerAccount(req: RegisterRequest): Promise<RegisterResponse> {
  if (USE_MOCKS)
    return mock((s) => {
      if (req.password.length < 10) throw new ApiError(422, "weak_password", "Password must be at least 10 characters.");
      if (req.role === "doctor" && req.requested_doctor_id) throw new ApiError(422, "validation_error", "A doctor can't pick a doctor.");
      if (!s.pending.some((p) => p.email === req.email)) {
        s.seq.user += 1;
        s.pending.push({
          id: `u-${String(s.seq.user).padStart(4, "0")}`,
          name: req.name,
          email: req.email,
          note: req.note ?? null,
          requested_role: req.role,
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

/** GET /hospital (no auth): this install's hospital name. */
export function getHospital(): Promise<Hospital> {
  if (USE_MOCKS) return mock(() => ({ name: "Ward Hospital" }));
  return http<Hospital>("GET", "/hospital");
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

/**
 * POST /users/{id}/approve `{role, ward?, patient_id?}`. A doctor may only grant patient or nurse (ward ignored).
 * Patient role: `patient_id` links an existing record (404 unknown, 409 already has an account); omitted = new record.
 */
export function approveUser(id: string, req: ApproveRequest, opts: ViewerOpts = {}): Promise<UserAdmin> {
  if (USE_MOCKS)
    return mock((s) => {
      const as = opts.as ?? "admin";
      const p = s.pending.find((u) => u.id === id) ?? notFound(`User ${id}`);
      if (as === "doctor" && req.role !== "nurse" && req.role !== "patient") throw new ApiError(403, "forbidden", "A doctor can only approve patients and nurses.");
      if (req.role === "patient" && req.patient_id) {
        const rec = s.patients.find((x) => x.id === req.patient_id) ?? notFound(`Patient ${req.patient_id}`);
        if (as === "doctor" && rec.attending_doctor_id !== USERS.doctor.id) throw new ApiError(403, "forbidden", "Not your patient");
        if (s.linkedPatients.includes(rec.id)) throw new ApiError(409, "conflict", "This patient already has an account.");
        s.linkedPatients.push(rec.id);
      }
      const ward = as === "doctor" || req.role !== "nurse" ? null : (req.ward ?? null);
      s.pending = s.pending.filter((u) => u.id !== id);
      if (req.role !== "patient") s.staff.push({ id: p.id, name: p.name, email: p.email, role: req.role, ward, scope: ward ?? "—", last_login_at: null, status: "active" });
      const out: UserAdmin = {
        id: p.id,
        name: p.name,
        email: p.email,
        role: req.role === "patient" ? null : req.role,
        status: "active",
        ward,
        supervisor_id: as === "doctor" && req.role === "nurse" ? USERS.doctor.id : null,
        requested_role: p.requested_role,
        requested_doctor_id: p.requested_doctor_id,
      };
      if (as === "doctor" && req.role === "nurse") s.team.push(out);
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
      return { id: p.id, name: p.name, email: p.email, role: null, status: "rejected" as const, ward: null, supervisor_id: null, requested_role: p.requested_role, requested_doctor_id: p.requested_doctor_id };
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

/** PATCH /users/{id} `{ward}` (admin) — ward editor on the Staff page. */
export function setUserWard(userId: string, ward: string | null): Promise<UserAdmin> {
  if (USE_MOCKS)
    return mock((s) => {
      userAdmin(s, userId);
      const t = s.team.find((u) => u.id === userId);
      const row = s.staff.find((u) => u.id === userId);
      if (t) t.ward = ward;
      if (row) {
        row.ward = ward;
        row.scope = ward ?? "—";
      }
      return userAdmin(s, userId);
    });
  return http<UserAdmin>("PATCH", `/users/${enc(userId)}`, { ward });
}

/** POST /patients/{id}/reset-code (admin or attending doctor) → shown once. 404 when the patient has no active account. Mock: only p-0001 has one. */
export function issuePatientResetCode(patientId: string): Promise<OneTimeCode> {
  if (USE_MOCKS)
    return mock((s) => {
      s.patients.find((p) => p.id === patientId) ?? notFound(`Patient ${patientId}`);
      if (patientId !== USERS.patient.patient_id) throw new ApiError(404, "not_found", "This patient has no active account.");
      return mockCode();
    });
  return http<OneTimeCode>("POST", `/patients/${enc(patientId)}/reset-code`, {});
}

// ── Patients and records ────────────────────────────────────────────────────

/** GET /patients (the doctor's own), highest NEWS2 first. */
export async function getMyPatients(): Promise<PatientSummary[]> {
  const list = USE_MOCKS
    ? await mock((s) => s.patients.filter((p) => p.attending_doctor_id === USERS.doctor.id))
    : await http<PatientSummary[]>("GET", "/patients");
  return [...list].sort(byNews);
}

/** GET /patients/{id} */
export function getPatient(id: string): Promise<Patient> {
  if (USE_MOCKS) return mock((s) => s.patients.find((p) => p.id === id) ?? notFound(`Patient ${id}`));
  return http<Patient>("GET", `/patients/${encodeURIComponent(id)}`);
}

/** GET /patients?q= as admin: name, bed and device only (no attending doctor, no vitals). */
export interface PatientListItem {
  id: string;
  first_name: string;
  last_name: string;
  ward: string | null;
  bed: string | null;
  device_id: string | null;
}

/**
 * GET /patients?q= (admin: every record by name or ID; doctor: his normal scope). `unlinked` adds `unlinked=true`
 * (records with no account). Mock: `as: "doctor"` keeps only Dr Trabelsi's patients.
 */
export function searchPatients(q: string, opts: ViewerOpts & { unlinked?: boolean } = {}): Promise<PatientListItem[]> {
  const needle = q.trim().toLowerCase();
  const pick = (p: PatientListItem) => ({ id: p.id, first_name: p.first_name, last_name: p.last_name, ward: p.ward, bed: p.bed, device_id: p.device_id });
  if (USE_MOCKS)
    return mock((s) =>
      s.patients
        .filter((p) => opts.as !== "doctor" || p.attending_doctor_id === USERS.doctor.id)
        .filter((p) => !opts.unlinked || !s.linkedPatients.includes(p.id))
        .filter((p) => !needle || p.id.toLowerCase().includes(needle) || `${p.first_name} ${p.last_name}`.toLowerCase().includes(needle))
        .map(pick),
    );
  return http<PatientListItem[]>("GET", `/patients?q=${encodeURIComponent(q.trim())}${opts.unlinked ? "&unlinked=true" : ""}`);
}

/** GET /patients/{id}/vitals?from=&to= — oldest first, default last 24 h. */
export function getVitals(patientId: string, opts: { from?: string; to?: string } = {}): Promise<Vital[]> {
  if (USE_MOCKS)
    return mock((s) =>
      (s.vitals[patientId] ?? []).filter(
        (v) => (!opts.from || v.ts >= opts.from) && (!opts.to || v.ts <= opts.to),
      ),
    );
  const q = new URLSearchParams();
  if (opts.from) q.set("from", opts.from);
  if (opts.to) q.set("to", opts.to);
  const qs = q.toString();
  return http<Vital[]>("GET", `/patients/${encodeURIComponent(patientId)}/vitals${qs ? `?${qs}` : ""}`);
}

/** GET /patients/{id}/notes — newest first. */
export function getNotes(patientId: string): Promise<Note[]> {
  if (USE_MOCKS) return mock((s) => s.notes[patientId] ?? []);
  return http<Note[]>("GET", `/patients/${encodeURIComponent(patientId)}/notes`);
}

/** POST /patients/{id}/notes `{"text"}` → Note. Mock author defaults to Dr Trabelsi. */
export function addNote(patientId: string, text: string, opts: ActorOpts = {}): Promise<Note> {
  if (USE_MOCKS)
    return mock((s) => {
      const by = opts.by ?? USERS.doctor.id;
      const staff = s.staff.find((u) => u.id === by);
      s.seq.note += 1;
      const note: Note = {
        id: `n-${String(s.seq.note).padStart(4, "0")}`,
        author_id: by,
        author_role: staff?.role ?? "doctor",
        author_name: staff?.name ?? userName(by) ?? by,
        text,
        created_at: iso(now()),
      };
      (s.notes[patientId] ??= []).unshift(note);
      return note;
    });
  return http<Note>("POST", `/patients/${encodeURIComponent(patientId)}/notes`, { text });
}

// ── Prescriptions and doses ─────────────────────────────────────────────────

/** GET /patients/{id}/prescriptions */
export function getPrescriptions(patientId: string): Promise<Prescription[]> {
  if (USE_MOCKS) return mock((s) => s.prescriptions.filter((r) => r.patient_id === patientId && r.active));
  return http<Prescription[]>("GET", `/patients/${encodeURIComponent(patientId)}/prescriptions`);
}

const PENICILLIN_FAMILY = /amox|penic|ampic|augment/i;

/** POST /prescriptions → Prescription (`published_to_device` false when no device). */
export function createPrescription(req: CreatePrescriptionRequest, opts: ActorOpts = {}): Promise<Prescription> {
  if (USE_MOCKS)
    return mock((s) => {
      const patient = s.patients.find((p) => p.id === req.patient_id) ?? notFound(`Patient ${req.patient_id}`);
      const version = Math.max(0, ...s.prescriptions.filter((r) => r.patient_id === patient.id).map((r) => r.schedule_version)) + 1;
      s.seq.rx += 1;
      const created = now();
      const allergic = patient.allergies.some((a) => /penicillin/i.test(a));
      const rx: Prescription = {
        id: `rx-${String(s.seq.rx).padStart(4, "0")}`,
        patient_id: patient.id,
        doctor_id: opts.by ?? USERS.doctor.id,
        items: req.items,
        care_plan: req.care_plan,
        active: true,
        created_at: iso(created),
        schedule_version: version,
        published_to_device: !!patient.device_id,
        ...(allergic && req.items.some((i) => PENICILLIN_FAMILY.test(i.med)) ? { allergy_override: true } : {}),
      };
      s.prescriptions.push(rx);
      // Regenerate doses: one per (day × time) from today, future occurrences only.
      const today = tunisDate(iso(created));
      for (const item of req.items) {
        for (let d = 0; d < item.days + 1; d++) {
          const date = new Date(Date.parse(`${today}T12:00:00Z`) + d * 86_400_000).toISOString().slice(0, 10);
          for (const t of item.times) {
            const at = new Date(Date.parse(`${date}T${t}:00+01:00`));
            if (at <= created) continue;
            s.seq.dose += 1;
            s.doses.push({
              id: `d-${String(s.seq.dose).padStart(6, "0")}`,
              prescription_id: rx.id,
              patient_id: patient.id,
              scheduled_at: iso(at),
              time_of_day: t,
              meds: [item.med],
              slot: item.slot,
              status: "scheduled",
              taken_method: null,
              updated_at: iso(created),
              taken_at: null,
              given_by: null,
              given_by_name: null,
              instructions: item.slot == null ? "Give by hand" : null,
            });
          }
        }
      }
      s.doses.sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
      return rx;
    });
  return http<Prescription>("POST", "/prescriptions", req);
}

/**
 * GET /patients/{id}/doses?date=YYYY-MM-DD — NOT IN CONTRACT (med_doses rows, data-model.md).
 * Oldest first. Without `date`: every dose of the last 24 h and the rest of today.
 */
export function getDoses(patientId: string, opts: { date?: string } = {}): Promise<Dose[]> {
  if (USE_MOCKS)
    return mock((s) => {
      const ref = now().getTime();
      return s.doses.filter(
        (d) =>
          d.patient_id === patientId &&
          (opts.date ? tunisDate(d.scheduled_at) === opts.date : Date.parse(d.scheduled_at) >= ref - 86_400_000 && tunisDate(d.scheduled_at) <= tunisDate(iso(now()))),
      );
    });
  return http<Dose[]>("GET", `/patients/${encodeURIComponent(patientId)}/doses${opts.date ? `?date=${opts.date}` : ""}`);
}

/** POST /doses/{id}/given — NOT IN CONTRACT. Nurse gave the dose by hand → status `taken`. */
export function markDoseGiven(doseId: string, opts: ActorOpts = {}): Promise<Dose> {
  if (USE_MOCKS)
    return mock((s) => {
      const dose = s.doses.find((d) => d.id === doseId) ?? notFound(`Dose ${doseId}`);
      const by = opts.by ?? USERS.nurse.id;
      const t = iso(now());
      Object.assign(dose, { status: "taken", taken_at: t, updated_at: t, given_by: by, given_by_name: userName(by) ?? by });
      return dose;
    });
  return http<Dose>("POST", `/doses/${encodeURIComponent(doseId)}/given`, {});
}

// ── AI summary and assistant ────────────────────────────────────────────────

/**
 * GET /ai/summary/{patient_id}. Mock: `fallback: true` returns the rules-only
 * summary (the `?ai=rules` demo state); the review state is shared by both.
 */
export function getSummary(patientId: string, opts: { fallback?: boolean } = {}): Promise<AiSummary> {
  if (USE_MOCKS)
    return mock((s) => {
      const entry = s.summaries[patientId] ?? notFound(`Summary for ${patientId}`);
      return opts.fallback ? entry.rules : entry.model;
    });
  return http<AiSummary>("GET", `/ai/summary/${encodeURIComponent(patientId)}`);
}

/** POST /ai/summary/{patient_id}/review → the reviewed summary. */
export function reviewSummary(patientId: string, opts: ActorOpts & { fallback?: boolean } = {}): Promise<AiSummary> {
  if (USE_MOCKS)
    return mock((s) => {
      const entry = s.summaries[patientId] ?? notFound(`Summary for ${patientId}`);
      const by = opts.by ?? USERS.doctor.id;
      for (const v of [entry.model, entry.rules]) {
        v.human_confirmed_by = by;
        v.human_confirmed_by_name = userName(by) ?? by;
        v.reviewed_at = iso(now());
      }
      return opts.fallback ? entry.rules : entry.model;
    });
  return http<AiSummary>("POST", `/ai/summary/${encodeURIComponent(patientId)}/review`, {});
}

/** The mock assistant's only data: the caller's own next dose, next visit and latest vitals. */
function assistantContext(s: MockStore, patientId: string): AssistantContext {
  const t = now().getTime();
  const next = s.doses
    .filter((d) => d.patient_id === patientId && d.status === "scheduled" && Date.parse(d.scheduled_at) >= t)
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
  const first = next[0];
  const nextDose =
    first && tunisDate(first.scheduled_at) === tunisDate(iso(now()))
      ? { time: first.time_of_day, meds: next.filter((d) => d.scheduled_at === first.scheduled_at).flatMap((d) => d.meds) }
      : null;
  const visit = s.appointments
    .filter((a) => a.patient_id === patientId && a.status === "confirmed" && a.slot_at && Date.parse(a.slot_at) >= t)
    .sort((a, b) => (a.slot_at ?? "").localeCompare(b.slot_at ?? ""))[0];
  const vitals = s.vitals[patientId] ?? [];
  const v = vitals[vitals.length - 1];
  return {
    nextDose,
    nextVisit: visit?.slot_at ? { slot_at: visit.slot_at, doctor_name: visit.doctor_name ?? null } : null,
    latestVitals: v ? { ts: v.ts, hr: v.hr, spo2: v.spo2, temp: v.temp } : null,
  };
}

/** POST /ai/assistant `{"question"}` (patient, own record only). */
export function askAssistant(question: string): Promise<AssistantResponse> {
  if (USE_MOCKS) return mock((s) => mockAssistant(question, assistantContext(s, USERS.patient.patient_id)));
  return http<AssistantResponse>("POST", "/ai/assistant", { question });
}

/**
 * POST /ai/chat: doctor and nurse ask about `patientId`; a patient asks about their own record (no id).
 * Answers come only from that record, in the language of the question. Needs the real backend.
 */
export function askChat(question: string, opts: { patientId?: string; history?: ChatTurn[]; lang?: string } = {}): Promise<ChatResponse> {
  if (USE_MOCKS) return Promise.reject(new ApiError(503, "needs_backend", "The AI assistant needs the real backend (NEXT_PUBLIC_USE_MOCKS=0)."));
  return http<ChatResponse>("POST", "/ai/chat", { question, patient_id: opts.patientId, history: opts.history ?? [], lang: opts.lang });
}

const NEEDS_BACKEND = () => Promise.reject(new ApiError(503, "needs_backend", "The AI assistant needs the real backend (NEXT_PUBLIC_USE_MOCKS=0)."));

/** GET /ai/conversations: the signed-in doctor's or nurse's conversations, newest first. */
export function listConversations(): Promise<Conversation[]> {
  if (USE_MOCKS) return NEEDS_BACKEND();
  return http<Conversation[]>("GET", "/ai/conversations");
}

export function createConversation(): Promise<Conversation> {
  if (USE_MOCKS) return NEEDS_BACKEND();
  return http<Conversation>("POST", "/ai/conversations", {});
}

export function getConversation(id: string): Promise<Conversation> {
  if (USE_MOCKS) return NEEDS_BACKEND();
  return http<Conversation>("GET", `/ai/conversations/${encodeURIComponent(id)}`);
}

export function deleteConversation(id: string): Promise<void> {
  if (USE_MOCKS) return NEEDS_BACKEND();
  return http<void>("DELETE", `/ai/conversations/${encodeURIComponent(id)}`);
}

/** One question. `patientId`: the patient mentioned with @ (else the conversation's); `clearPatient`: a general question. */
export function sendConversationMessage(
  id: string,
  question: string,
  opts: { patientId?: string; clearPatient?: boolean; lang?: string } = {},
): Promise<{ message: ConversationMessage; conversation: Conversation }> {
  if (USE_MOCKS) return NEEDS_BACKEND();
  return http("POST", `/ai/conversations/${encodeURIComponent(id)}/messages`, {
    question, patient_id: opts.patientId, clear_patient: opts.clearPatient ?? false, lang: opts.lang,
  });
}

/** GET /health-watch (doctor, nurse, admin): forecast, weather-health alerts with at-risk patients, news. */
export function getHealthWatch(): Promise<HealthWatch> {
  if (USE_MOCKS) return Promise.reject(new ApiError(503, "needs_backend", "Health watch needs the real backend."));
  return http<HealthWatch>("GET", "/health-watch");
}

/** GET /health-watch/me (patient): alerts with advice, marked when they concern this patient. */
export function getMyHealthWatch(): Promise<HealthWatch> {
  if (USE_MOCKS) return Promise.reject(new ApiError(503, "needs_backend", "Health watch needs the real backend."));
  return http<HealthWatch>("GET", "/health-watch/me");
}

/** POST /patients/{id}/reports (doctor): attach a report (PDF, image or text) to the patient's case. */
export async function uploadReport(patientId: string, file: File, title: string, reportText = ""): Promise<ExamOrder> {
  if (USE_MOCKS) return Promise.reject(new ApiError(503, "needs_backend", "Uploading a report needs the real backend."));
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  form.append("report_text", reportText);
  return upload<ExamOrder>(`/patients/${encodeURIComponent(patientId)}/reports`, form);
}

// ── Appointments and waitlist ───────────────────────────────────────────────

const finalUrgency = (a: Appointment) => a.urgency_final ?? a.urgency_ai;

/**
 * GET /appointments/waitlist — requested appointments, `urgency_final ?? urgency_ai`
 * desc then oldest first. Confirmed rows leave the list (as on the real API).
 * `specialty` filters client-side; mock `fallback: true` returns rules-only triage.
 */
export async function getWaitlist(opts: { specialty?: string; fallback?: boolean } = {}): Promise<Appointment[]> {
  let list = USE_MOCKS
    ? await mock((s) => s.appointments.filter((a) => a.status === "requested").map((a) => counted(s, a)))
    : await http<Appointment[]>("GET", "/appointments/waitlist");
  if (opts.specialty) list = list.filter((a) => a.specialty === opts.specialty);
  if (USE_MOCKS && opts.fallback) {
    list = list.map((a) => {
      const triage = { ...a.triage, source: "rules" as const, confidence: null, model_urgency: null };
      return { ...a, triage, ai_suggested: triage };
    });
  }
  return list.sort((a, b) => finalUrgency(b) - finalUrgency(a) || a.created_at.localeCompare(b.created_at));
}

/** PATCH /appointments/{id} `{"urgency_final"}` — human override, sets `human_confirmed_by`. */
export function overrideUrgency(id: string, urgency: Urgency, opts: ActorOpts = {}): Promise<Appointment> {
  if (USE_MOCKS)
    return mock((s) => {
      const a = s.appointments.find((x) => x.id === id) ?? notFound(`Appointment ${id}`);
      const by = opts.by ?? USERS.admin.id;
      Object.assign(a, { urgency_final: urgency, human_confirmed_by: by, human_confirmed_by_name: userName(by) ?? by });
      return a;
    });
  return http<Appointment>("PATCH", `/appointments/${encodeURIComponent(id)}`, { urgency_final: urgency });
}

/** POST /appointments/{id}/confirm `{"slot_at","doctor_id","urgency_final"?}`. */
export function confirmAppointment(id: string, req: ConfirmAppointmentRequest, opts: ActorOpts = {}): Promise<Appointment> {
  if (USE_MOCKS)
    return mock((s) => {
      const a = s.appointments.find((x) => x.id === id) ?? notFound(`Appointment ${id}`);
      if (a.status !== "requested") throw new ApiError(409, "not_waiting", "Appointment is not waiting");
      const taken = s.appointments.some((x) => x.status === "confirmed" && x.slot_at === req.slot_at && x.doctor_id === req.doctor_id);
      if (taken) throw new ApiError(409, "slot_taken", "Slot already taken");
      const by = opts.by ?? USERS.admin.id;
      const name = userName(by) ?? by;
      Object.assign(a, {
        status: "confirmed",
        slot_at: req.slot_at,
        doctor_id: req.doctor_id,
        doctor_name: userName(req.doctor_id),
        confirmed_by: by,
        confirmed_by_name: name,
        human_confirmed_by: by,
        human_confirmed_by_name: name,
        ...(req.urgency_final ? { urgency_final: req.urgency_final } : {}),
      });
      return a;
    });
  return http<Appointment>("POST", `/appointments/${encodeURIComponent(id)}/confirm`, req);
}

/** GET /appointments?patient_id= (the patient's own), soonest slot first. */
export async function getMyAppointments(patientId: string): Promise<Appointment[]> {
  const list = USE_MOCKS
    ? await mock((s) => s.appointments.filter((a) => a.patient_id === patientId).map((a) => counted(s, a)))
    : await http<Appointment[]>("GET", `/appointments?patient_id=${encodeURIComponent(patientId)}`);
  return list.sort((a, b) => (a.slot_at ?? "9").localeCompare(b.slot_at ?? "9"));
}

/** POST /appointments/{id}/reply `{"reply":"confirm|cancel"}` (patient). */
export function replyAppointment(id: string, reply: "confirm" | "cancel"): Promise<Appointment> {
  if (USE_MOCKS)
    return mock((s) => {
      const a = s.appointments.find((x) => x.id === id) ?? notFound(`Appointment ${id}`);
      if (reply === "confirm") a.patient_confirmed_at = iso(now());
      else a.status = "cancelled";
      return a;
    });
  return http<Appointment>("POST", `/appointments/${encodeURIComponent(id)}/reply`, { reply });
}

// ── Exams (api.md 1.8 proposal) ─────────────────────────────────────────────

const counted = (s: MockStore, a: Appointment): Appointment => {
  const rows = s.exams.filter((e) => e.appointment_id === a.id);
  const n = (st: string) => rows.filter((e) => e.status === st).length;
  return { ...a, exams_total: n("ordered") + n("done"), exams_done: n("done"), exams_suggested: n("suggested") };
};

export async function getAppointmentExams(appointmentId: string): Promise<ExamOrder[]> {
  if (USE_MOCKS) return mock((s) => s.exams.filter((e) => e.appointment_id === appointmentId));
  return http<ExamOrder[]>("GET", `/appointments/${encodeURIComponent(appointmentId)}/exams`);
}

export async function getPatientExams(patientId: string): Promise<ExamOrder[]> {
  if (USE_MOCKS) return mock((s) => s.exams.filter((e) => e.patient_id === patientId && e.status !== "cancelled"));
  return http<ExamOrder[]>("GET", `/patients/${encodeURIComponent(patientId)}/exams`);
}

export async function getExamWorklist(): Promise<ExamOrder[]> {
  if (USE_MOCKS) return mock((s) => s.exams.filter((e) => e.status === "ordered"));
  return http<ExamOrder[]>("GET", "/exams?status=ordered");
}

export async function getExamCatalogue(): Promise<CatalogueItem[]> {
  if (USE_MOCKS) return mock(() => EXAM_CATALOGUE);
  return http<CatalogueItem[]>("GET", "/exams/catalogue");
}

export async function orderExams(appointmentId: string, examIds: string[], opts: ActorOpts = {}): Promise<ExamOrder[]> {
  if (USE_MOCKS)
    return mock((s) => {
      const rows = s.exams.filter((e) => e.appointment_id === appointmentId);
      const at = iso(now());
      for (const e of rows) {
        if (examIds.includes(e.id) && e.status === "suggested") Object.assign(e, { status: "ordered", human_confirmed_by: opts.by ?? "u-0001", ordered_at: at });
        else if (e.status === "suggested") e.status = "cancelled";
      }
      return rows;
    });
  return http<ExamOrder[]>("POST", `/appointments/${encodeURIComponent(appointmentId)}/exams/order`, { exam_ids: examIds });
}

export async function addExam(req: { patient_id: string; appointment_id?: string; code: string }, opts: ActorOpts = {}): Promise<ExamOrder> {
  if (USE_MOCKS)
    return mock((s) => {
      const item = EXAM_CATALOGUE.find((c) => c.code === req.code) ?? notFound(`Exam ${req.code}`);
      const row: ExamOrder = { id: `ex-${String(s.exams.length + 1).padStart(4, "0")}`, patient_id: req.patient_id,
        appointment_id: req.appointment_id ?? null, ...item, status: "ordered", ai_suggested: null,
        human_confirmed_by: opts.by ?? "u-0001", ordered_at: iso(now()), done_at: null, created_at: iso(now()),
        patient_name: null, results: [] };
      s.exams.push(row);
      return row;
    });
  return http<ExamOrder>("POST", "/exams", req);
}

export async function uploadExamResult(examId: string, file: File, reportText: string, opts: ActorOpts = {}): Promise<ExamOrder> {
  if (USE_MOCKS)
    return mock((s) => {
      const e = s.exams.find((x) => x.id === examId) ?? notFound(`Exam ${examId}`);
      if (e.status !== "ordered") throw new ApiError(409, "bad_status", `exam is ${e.status}`);
      e.status = "done";
      e.done_at = iso(now());
      e.results = [...(e.results ?? []), { id: `er-${examId.slice(3)}`, file_name: file.name, content_type: file.type,
        size_bytes: file.size, report_text: reportText, uploaded_by_name: userName(opts.by ?? "u-0006"), created_at: iso(now()) }];
      return e;
    });
  const form = new FormData();
  form.append("file", file);
  form.append("report_text", reportText);
  return upload<ExamOrder>(`/exams/${encodeURIComponent(examId)}/results`, form);
}

/** Authenticated download → an object URL for a new tab. Revoke it when done. */
export async function examFileUrl(resultId: string): Promise<string> {
  if (USE_MOCKS) return "/mock-exam.pdf";
  const token = getToken();
  const res = await fetch(`${BASE}/exam-results/${encodeURIComponent(resultId)}/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    if (res.status === 401) handleUnauthorized("/exam-results/file", !!token);
    throw new ApiError(res.status, "http_error", res.statusText);
  }
  return URL.createObjectURL(await res.blob());
}

// ── Patient app extras (NOT IN CONTRACT) ────────────────────────────────────

/** GET /offers/{id} — NOT IN CONTRACT. A freed slot offered to the patient (n8n W2 backfill). */
export function getOffer(id: string): Promise<SlotOffer> {
  if (USE_MOCKS) return mock((s) => s.offers.find((o) => o.id === id) ?? notFound(`Offer ${id}`));
  return http<SlotOffer>("GET", `/offers/${encodeURIComponent(id)}`);
}

/**
 * POST /offers/{id}/accept — NOT IN CONTRACT (the contract only has the n8n `backfill-accept`
 * callback, with the same 409 `slot_taken` / `not_waiting`). Returns the patient's moved appointment.
 * Mock: `simulateTaken` is the design's "Demo: simulate “someone was faster”" → 409 `slot_taken`.
 */
export function acceptOffer(id: string, opts: { simulateTaken?: boolean } = {}): Promise<Appointment> {
  if (USE_MOCKS)
    return mock((s) => {
      const offer = s.offers.find((o) => o.id === id) ?? notFound(`Offer ${id}`);
      if (opts.simulateTaken || offer.status === "taken") {
        throw new ApiError(409, "slot_taken", "This slot was just taken");
      }
      const appt = s.appointments.find((a) => a.id === offer.appointment_id) ?? notFound(`Appointment ${offer.appointment_id}`);
      if (offer.status === "accepted") return appt;
      if (appt.status !== "confirmed" && appt.status !== "requested") throw new ApiError(409, "not_waiting", "Appointment is no longer waiting");
      offer.status = "accepted";
      Object.assign(appt, { status: "confirmed", slot_at: offer.slot_at, doctor_id: offer.doctor_id, doctor_name: offer.doctor_name, room: offer.room, patient_confirmed_at: iso(now()) });
      return appt;
    });
  return http<Appointment>("POST", `/offers/${encodeURIComponent(id)}/accept`, {});
}

/** GET /patients/{id}/home-care — NOT IN CONTRACT. The "After discharge" screen. */
export function getHomeCare(patientId: string): Promise<HomeCarePlan> {
  if (USE_MOCKS) return mock((s) => s.homeCare[patientId] ?? notFound(`Home care for ${patientId}`));
  return http<HomeCarePlan>("GET", `/patients/${encodeURIComponent(patientId)}/home-care`);
}

// ── Alerts ──────────────────────────────────────────────────────────────────

/** GET /alerts[?status=open] — newest first. */
export async function getAlerts(opts: { status?: "open" } = {}): Promise<Alert[]> {
  const list = USE_MOCKS
    ? await mock((s) => s.alerts.filter((a) => opts.status !== "open" || !a.acked_by))
    : await http<Alert[]>("GET", `/alerts${opts.status ? `?status=${opts.status}` : ""}`);
  return list.sort((a, b) => b.created_at.localeCompare(a.created_at));
}

/** POST /alerts/{id}/ack → Alert with `acked_by`/`acked_at`. Mock actor defaults to Nurse Ines. */
export function ackAlert(id: string, opts: ActorOpts = {}): Promise<Alert> {
  if (USE_MOCKS)
    return mock((s) => {
      const a = s.alerts.find((x) => x.id === id) ?? notFound(`Alert ${id}`);
      const by = opts.by ?? USERS.nurse.id;
      Object.assign(a, { acked_by: by, acked_at: iso(now()), acked_by_name: userName(by) ?? by });
      return a;
    });
  return http<Alert>("POST", `/alerts/${encodeURIComponent(id)}/ack`, {});
}

// ── Devices and staff ───────────────────────────────────────────────────────

/** GET /devices. Mock: adds the UI-extension `admission_id` from the patient record. */
export function getDevices(): Promise<Device[]> {
  if (USE_MOCKS)
    return mock((s) =>
      s.devices.map((d) => ({ ...d, admission_id: s.patients.find((p) => p.id === d.patient_id)?.admission_id ?? null })),
    );
  return http<Device[]>("GET", "/devices");
}

/** POST /devices/{id}/assign `{"patient_id","bed"}` (admin): creates/updates the admission, publishes the schedule. */
export function assignDevice(deviceId: string, req: { patient_id: string; bed: string }): Promise<void> {
  if (USE_MOCKS)
    return mock((s) => {
      const device = s.devices.find((d) => d.id === deviceId) ?? notFound(`Device ${deviceId}`);
      const patient = s.patients.find((p) => p.id === req.patient_id);
      const name =
        (patient ? `${patient.first_name} ${patient.last_name}` : null) ??
        s.appointments.find((a) => a.patient_id === req.patient_id)?.patient_name ??
        req.patient_id;
      Object.assign(device, { patient_id: req.patient_id, bed: req.bed, patient_name: name });
    });
  return http<void>("POST", `/devices/${encodeURIComponent(deviceId)}/assign`, req);
}

/** POST /admissions/{id}/discharge (admin, doctor): clears the device schedule and sets `discharged_at`. */
export function dischargeAdmission(admissionId: string): Promise<void> {
  if (USE_MOCKS)
    return mock((s) => {
      const patient = s.patients.find((p) => p.admission_id === admissionId) ?? notFound(`Admission ${admissionId}`);
      for (const d of s.devices) {
        if (d.patient_id === patient.id) Object.assign(d, { patient_id: null, patient_name: null });
      }
    });
  return http<void>("POST", `/admissions/${encodeURIComponent(admissionId)}/discharge`, {});
}

/** GET /staff — NOT IN CONTRACT (admin "Staff" screen). */
export function getStaff(): Promise<StaffMember[]> {
  if (USE_MOCKS) return mock((s) => s.staff);
  return http<StaffMember[]>("GET", "/staff");
}

// ── Composed nurse views ────────────────────────────────────────────────────

/**
 * The nurse ward board: one entry per bed (patients ∪ device beds), with the
 * latest vital and whether a call-nurse alert is open. Real mode composes
 * GET /patients?ward=, /devices, /alerts?status=open and /patients/{id}/vitals.
 */
export async function getWard(ward: string = DEFAULT_WARD): Promise<WardBed[]> {
  if (USE_MOCKS)
    return mock((s) => {
      const patients = s.patients.filter((p) => p.ward === ward);
      const beds = new Set([...s.boardBedOrder, ...patients.map((p) => p.bed ?? "")].filter(Boolean));
      return [...beds].map((bed) => {
        const patient = patients.find((p) => p.bed === bed) ?? null;
        const series = patient ? (s.vitals[patient.id] ?? []) : [];
        return {
          bed,
          patient,
          device: s.devices.find((d) => d.bed === bed) ?? null,
          latest: series[series.length - 1] ?? null,
          calling: !!patient && s.alerts.some((a) => a.patient_id === patient.id && a.kind === "call_nurse" && !a.acked_by),
        };
      });
    });
  const [patients, devices, alerts] = await Promise.all([
    http<PatientSummary[]>("GET", `/patients?ward=${encodeURIComponent(ward)}`),
    getDevices(),
    getAlerts({ status: "open" }),
  ]);
  const latest = await Promise.all(patients.map((p) => getVitals(p.id).then((v) => v[v.length - 1] ?? null)));
  const beds = new Set([...patients.map((p) => p.bed ?? ""), ...devices.map((d) => d.bed ?? "")].filter(Boolean));
  return [...beds]
    .map((bed) => {
      const i = patients.findIndex((p) => p.bed === bed);
      const patient = i >= 0 ? patients[i] : null;
      return {
        bed,
        patient,
        device: devices.find((d) => d.bed === bed) ?? null,
        latest: i >= 0 ? latest[i] : null,
        calling: !!patient && alerts.some((a) => a.patient_id === patient.id && a.kind === "call_nurse"),
      };
    })
    .sort((a, b) => (b.patient?.latest_news2 ?? -2) - (a.patient?.latest_news2 ?? -2));
}

/** The nurse med round: today's doses per ward patient (patients with no dose today are left out). */
export async function getMedRound(ward: string = DEFAULT_WARD): Promise<MedRoundGroup[]> {
  const today = tunisDate(iso(now()));
  if (USE_MOCKS)
    return mock((s) =>
      s.patients
        .filter((p) => p.ward === ward)
        .sort(byNews)
        .map((patient) => ({
          patient,
          device: s.devices.find((d) => d.id === patient.device_id) ?? null,
          doses: s.doses.filter((d) => d.patient_id === patient.id && tunisDate(d.scheduled_at) === today),
        }))
        .filter((g) => g.doses.length > 0),
    );
  const [summaries, devices] = await Promise.all([
    http<PatientSummary[]>("GET", `/patients?ward=${encodeURIComponent(ward)}`),
    getDevices(),
  ]);
  const groups = await Promise.all(
    [...summaries].sort(byNews).map(async (p) => ({
      patient: await getPatient(p.id),
      device: devices.find((d) => d.id === p.device_id) ?? null,
      // Doses are not in api.md yet: a missing endpoint leaves the round empty instead of failing it.
      doses: await getDoses(p.id, { date: today }).catch((): Dose[] => []),
    })),
  );
  return groups.filter((g) => g.doses.length > 0);
}

// ── Health calendar (api.md 1.12) ──────────────────────────────────────────

/** The mock profile per role: Amira (F, 1972) is the patient; staff ignore sex/age limits. */
function mockMatches(s: MockStore, role: Role, ev: Omit<HealthEvent, "matches_me" | "following">): boolean {
  const a = ev.audience;
  if (!a.roles.includes(role)) return false;
  if (role !== "patient") return true; // staff ignore sex/age limits
  if (a.sex === null && a.min_age === null && a.max_age === null) return true;
  const p = s.patients.find((x) => x.id === USERS.patient.patient_id);
  if (!p) return false;
  if (a.sex !== null && p.sex !== a.sex) return false; // unknown sex never matches a sex-limited event
  return ageOk(p.date_of_birth ?? null, ev.starts_on, a);
}

function ageOk(dob: string | null, on: string, a: HealthAudience): boolean {
  if (a.min_age === null && a.max_age === null) return true;
  if (!dob) return false;
  const [y, m, d] = dob.split("-").map(Number);
  const [oy, om, od] = on.split("-").map(Number);
  const age = oy - y - (om < m || (om === m && od < d) ? 1 : 0);
  return (a.min_age === null || age >= a.min_age) && (a.max_age === null || age <= a.max_age);
}

function mockPrefs(s: MockStore, role: Role): HealthPrefs {
  const mine = s.healthPrefs[role] ?? {};
  return { following: Object.fromEntries(HEALTH_CATEGORIES.map((c) => [c, mine[c] ?? true])) as HealthPrefs["following"] };
}

function withFlags(s: MockStore, role: Role, ev: Omit<HealthEvent, "matches_me" | "following">): HealthEvent {
  return { ...ev, matches_me: mockMatches(s, role, ev), following: mockPrefs(s, role).following[ev.category as HealthCategory] };
}

function mockEvent(s: MockStore, id: string) {
  return s.healthEvents.find((e) => e.id === id) ?? notFound(`Health event ${id}`);
}

function checkDates(starts: string, ends: string): void {
  if (ends < starts) throw new ApiError(422, "bad_dates", "ends_on is before starts_on");
}

/** GET /health-events?from&to — every role; `role` picks the mock user. */
export function getHealthEvents(opts: { from?: string; to?: string; role?: Role } = {}): Promise<HealthEvent[]> {
  if (USE_MOCKS)
    return mock((s) => {
      const from = opts.from ?? "0000-01-01";
      const to = opts.to ?? "9999-12-31";
      return s.healthEvents
        .filter((e) => e.starts_on <= to && e.ends_on >= from)
        .sort((a, b) => a.starts_on.localeCompare(b.starts_on) || a.id.localeCompare(b.id))
        .map((e) => withFlags(s, opts.role ?? "patient", e));
    });
  const q = new URLSearchParams();
  if (opts.from) q.set("from", opts.from);
  if (opts.to) q.set("to", opts.to);
  return http<HealthEvent[]>("GET", `/health-events${q.size ? `?${q}` : ""}`);
}

/** POST /health-events (admin). */
export function createHealthEvent(input: HealthEventInput): Promise<HealthEvent> {
  if (USE_MOCKS)
    return mock((s) => {
      checkDates(input.starts_on, input.ends_on);
      s.seq.he += 1;
      const ev = { ...input, id: `he-${String(s.seq.he).padStart(4, "0")}`, announced_at: null };
      s.healthEvents.push(ev);
      return withFlags(s, "admin", ev);
    });
  return http<HealthEvent>("POST", "/health-events", input);
}

/** PATCH /health-events/{id} (admin); a new start date clears announced_at. */
export function updateHealthEvent(id: string, patch: Partial<HealthEventInput>): Promise<HealthEvent> {
  if (USE_MOCKS)
    return mock((s) => {
      const ev = mockEvent(s, id);
      checkDates(patch.starts_on ?? ev.starts_on, patch.ends_on ?? ev.ends_on);
      if (patch.starts_on && patch.starts_on !== ev.starts_on) ev.announced_at = null;
      Object.assign(ev, patch);
      return withFlags(s, "admin", ev);
    });
  return http<HealthEvent>("PATCH", `/health-events/${enc(id)}`, patch);
}

/** DELETE /health-events/{id} (admin) → 204. */
export function deleteHealthEvent(id: string): Promise<void> {
  if (USE_MOCKS)
    return mock((s) => {
      mockEvent(s, id);
      s.healthEvents = s.healthEvents.filter((e) => e.id !== id);
    });
  return http<void>("DELETE", `/health-events/${enc(id)}`);
}

/** POST /health-events/{id}/notify (admin) → how many people the push targets. */
export function notifyHealthEvent(id: string): Promise<{ recipients: number }> {
  if (USE_MOCKS)
    return mock((s) => {
      const ev = mockEvent(s, id);
      ev.announced_at = now().toISOString().replace(/\.\d{3}Z$/, "Z");
      const roles: Role[] = ["patient", "nurse", "doctor", "admin"];
      const people = roles.filter((r) => mockMatches(s, r, ev) && mockPrefs(s, r).following[ev.category as HealthCategory]);
      return { recipients: people.length };
    });
  return http<{ recipients: number }>("POST", `/health-events/${enc(id)}/notify`);
}

/** GET /me/health-prefs. */
export function getHealthPrefs(role: Role = "patient"): Promise<HealthPrefs> {
  if (USE_MOCKS) return mock((s) => mockPrefs(s, role));
  return http<HealthPrefs>("GET", "/me/health-prefs");
}

/** PUT /me/health-prefs (partial). */
export function setHealthPrefs(following: Partial<Record<HealthCategory, boolean>>, role: Role = "patient"): Promise<HealthPrefs> {
  if (USE_MOCKS)
    return mock((s) => {
      s.healthPrefs[role] = { ...(s.healthPrefs[role] ?? {}), ...following };
      return mockPrefs(s, role);
    });
  return http<HealthPrefs>("PUT", "/me/health-prefs", { following });
}

/** GET /admin/impact?days= (admin): pilot impact indicators. Mock: sample numbers that scale with the period. */
export function getImpact(days: number): Promise<ImpactReport> {
  if (USE_MOCKS) return mock(() => mockImpact(days));
  return http<ImpactReport>("GET", `/admin/impact?days=${days}`);
}

function mockImpact(days: number): ImpactReport {
  const to = now();
  const from = new Date(to.getTime() - days * 86_400_000);
  const prevFrom = new Date(from.getTime() - days * 86_400_000);
  const n = (x: number) => Math.round((x * days) / 30);
  type Row = [ImpactIndicator["id"], ImpactIndicator["group"], ImpactIndicator["unit"], ImpactIndicator["better"],
    number | null, number | null, Record<string, number> | null];
  const rows: Row[] = [
    ["alerts_total", "alerts", "count", null, n(64), n(71), { low: n(18), medium: n(29), high: n(13), critical: n(4) }],
    ["ack_median_min", "alerts", "minutes", "lower", 3.4, 5.1, null],
    ["ack_p90_min", "alerts", "minutes", "lower", 9.8, 14.2, null],
    ["ack_within_5min_pct", "alerts", "pct", "higher", 76.5, 61.1, null],
    ["doses_due", "medication", "count", null, n(540), n(522), null],
    ["doses_taken_pct", "medication", "pct", "higher", 91.3, 86.4, null],
    ["doses_missed_pct", "medication", "pct", "lower", 6.1, 10.2, null],
    ["doses_on_time_pct", "medication", "pct", "higher", 84.6, 78.9, null],
    ["missed_per_patient_day", "medication", "rate", "lower", 0.18, 0.29, null],
    ["requests_received", "appointments", "count", null, n(118), n(104), null],
    ["request_to_booking_hours", "appointments", "hours", "lower", null, null, null],
    ["request_to_slot_days", "appointments", "days", "lower", 6.5, 9, null],
    ["cancellations", "appointments", "count", "lower", n(11), n(14), null],
    ["backfill_refills", "appointments", "count", "higher", n(7), n(3), null],
    ["no_show_rate_pct", "appointments", "pct", "lower", null, null, null],
    ["vitals_per_patient_day", "monitoring", "rate", "higher", 22.4, 8.7, null],
    ["vitals_automated_pct", "monitoring", "pct", "higher", 71.2, 38.5, { manual: n(1150), simulator: n(2240), device: n(600) }],
    ["news2_medium_high_pct", "monitoring", "pct", null, 8.9, 9.4, { low: n(3634), medium: n(268), high: n(88) }],
    ["nurse_notes_per_shift", "workload", "rate", null, 2.6, 2.1, null],
    ["ai_reviewed_pct", "workload", "pct", "higher", 82.4, 64, { reviewed: n(112), pending: n(24) }],
  ];
  const notRecorded = new Set<string>(["request_to_booking_hours", "no_show_rate_pct"]);
  return {
    days,
    period: { from: iso(from), to: iso(to) },
    previous_period: { from: iso(prevFrom), to: iso(from) },
    patient_days: n(178),
    data: "synthetic",
    indicators: rows.map(([id, group, unit, better, value, previous, breakdown]) => ({
      id, group, unit, better, value, previous, breakdown, status: notRecorded.has(id) ? "not_recorded" : "ok",
    })),
  };
}
