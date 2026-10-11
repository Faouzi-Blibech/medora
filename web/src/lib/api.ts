// The single data layer. Components read and write through these functions only.
//
// Mock mode (NEXT_PUBLIC_USE_MOCKS=1, the default when unset): every call resolves
// from an in-memory copy of `web/src/mocks` after 150 ms. Mutations write to that
// store, so a later read reflects them (until a full page reload).
// Real mode: calls NEXT_PUBLIC_API_URL with the paths of docs/contracts/api.md.
// Paths marked NOT IN CONTRACT have no api.md 1.4 endpoint yet (see the Task 1 report).
import { chainOf, checksFor, createStore, drugMatches, generateCode, MOCK_CODES, EXAM_CATALOGUE, MOCK_RADIOGRAPH_URL, MOCK_READING_DRAFTS, mockAssistant, USERS, userName, type AssistantContext, type MockLot, type MockStore } from "@/mocks";
import { publishFrame } from "./frames";
import { COMMENT_MAX, expiryState, fefoLots, hasCritical, isRunning, maxSeverity, reorderQuantity, sortWorklist, stockDay, stockFlags } from "./pharmacy";
import { now, tunisDate, USE_MOCKS } from "./time";
import { HEALTH_CATEGORIES } from "./types";
import type {
  AccountStatus,
  CreateDispensationRequest,
  Dispensation,
  DispensingWard,
  PrescriptionItem,
  ReorderItem,
  StockAdjustmentRequest,
  StockItem,
  StockLot,
  StockReceiptRequest,
  Alert,
  AiSummary,
  Appointment,
  AssistantResponse,
  CatalogueItem,
  ChatResponse,
  ChatTurn,
  Check,
  CheckRequest,
  CheckResponse,
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
  Drug,
  DrugInput,
  DrugPatch,
  ExamOrder,
  HomeCarePlan,
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
  RadiographReading,
  Patient,
  PatientAccessGrant,
  PatientSummary,
  PendingUser,
  PharmacyPatient,
  PharmacySummary,
  Prescription,
  RegisterRequest,
  RegisterResponse,
  ResetRequest,
  ReviewDecision,
  ReviewDetail,
  Role,
  SlotOffer,
  StaffMember,
  Urgency,
  UserAdmin,
  ValidateRequest,
  Vital,
  WardBed,
  WorklistItem,
  WorklistStatus,
} from "./types";

// NEXT_PUBLIC_API_URL when set; otherwise the API on port 8000 of the host the page was opened from, so the app keeps
// working when the laptop's network address changes (localhost on the laptop, the LAN address on a phone).
const BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== "undefined" ? `${window.location.protocol}//${window.location.hostname}:8000` : "http://localhost:8000");
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
    /** The error body's other keys (api 1.12: 409 `insufficient_stock` adds `drug_id`). */
    public extra: Record<string, unknown> = {},
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
    const err = (await res.json().catch(() => ({}))) as { detail?: string; code?: string; [key: string]: unknown };
    if (res.status === 401) handleUnauthorized(path, !!token, err.code);
    const { detail, code, ...extra } = err;
    throw new ApiError(res.status, code ?? "http_error", detail ?? res.statusText, extra);
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
      if ((req.role === "doctor" || req.role === "pharmacist") && req.requested_doctor_id)
        throw new ApiError(422, "validation_error", "Doctors and pharmacists don't pick a doctor.");
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

/** POST /patients/{id}/vitals: a reading taken by hand (nurse round) → the stored Vital (source "manual"). */
export function recordVitals(
  patientId: string,
  body: { hr?: number | null; spo2?: number | null; temp?: number | null },
): Promise<Vital> {
  if (USE_MOCKS)
    return mock((s) => {
      const v: Vital = {
        ts: iso(now()),
        hr: body.hr ?? null,
        spo2: body.spo2 ?? null,
        temp: body.temp ?? null,
        nurse_id: USERS.nurse.id,
        news2: null,
        source: "manual",
      };
      (s.vitals[patientId] ??= []).push(v);
      return v;
    });
  return http<Vital>("POST", `/patients/${encodeURIComponent(patientId)}/vitals`, body);
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
          pharmacy: "none",
        });
      }
    }
  }
  s.doses.sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
}

/** Deletes the future, not-yet-given doses of a prescription (reject, supersede). Mock only. */
function dropFutureDoses(s: MockStore, rxId: string): void {
  const t = now().getTime();
  const gone = new Set(
    s.doses.filter((d) => d.prescription_id === rxId && d.status === "scheduled" && Date.parse(d.scheduled_at) > t).map((d) => d.id),
  );
  s.doses = s.doses.filter((d) => !gone.has(d.id));
  // A dispensed dose that is cancelled leaves its line with dose_id null (backend Contract decision 30).
  for (const disp of s.dispensations) for (const line of disp.lines) if (line.dose_id && gone.has(line.dose_id)) line.dose_id = null;
}

/** The check engine on a saved prescription, as it stands now (the server's recompute). */
function rxChecks(s: MockStore, rx: Prescription): Check[] {
  return checksFor(s.patients, s.prescriptions, s.drugs, { patient_id: rx.patient_id, items: rx.items, ...(rx.replaces_id ? { replaces_id: rx.replaces_id } : {}) }, rx.id);
}

/** Statuses a prescription can be replaced from, and the ones that count as a live successor (Contract decision 7). */
const REPLACEABLE: ReadonlySet<string> = new Set(["pending_pharmacy", "changes_requested", "validated"]);

/** 422 `unknown_drug`: a set `drug_id` that is missing or inactive in the catalogue. */
function assertKnownDrugs(s: MockStore, items: { drug_id?: string | null }[]): void {
  for (const it of items)
    if (it.drug_id && !s.drugs.some((d) => d.id === it.drug_id && d.active))
      throw new ApiError(422, "unknown_drug", `drug ${it.drug_id} is unknown or inactive`);
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
      assertKnownDrugs(s, req.items);
      const replaced = req.replaces_id
        ? (s.prescriptions.find((r) => r.id === req.replaces_id) ?? notFound(`Prescription ${req.replaces_id}`))
        : null;
      // Contract decision 7: another patient's prescription, a status that can't be replaced, or a live newer version.
      if (replaced) {
        if (replaced.patient_id !== patient.id || !REPLACEABLE.has(replaced.status))
          throw new ApiError(409, "conflict", "This prescription can't be replaced.");
        if (s.prescriptions.some((r) => r.replaces_id === replaced.id && REPLACEABLE.has(r.status)))
          throw new ApiError(409, "conflict", "A newer version already replaces this prescription.");
      }
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
      // Contract decision 8: a replaced version that never ran is superseded now; a running one keeps running
      // until the new one is validated, unless the new one is urgent (no double dosing).
      if (replaced) {
        const wasRunning = isRunning(replaced);
        if (!wasRunning || urgent) {
          Object.assign(replaced, { status: "superseded", active: false });
          if (wasRunning) dropFutureDoses(s, replaced.id);
          statusFrame(replaced);
        }
      }
      statusFrame(rx);
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

// ── Pharmacy (api 1.12, spec 2026-10-10 §5) ─────────────────────────────────

/** WS /ws?token=<jwt> for this tab's session; null in mock mode or when signed out (used by lib/live.ts). */
export function liveSocketUrl(): string | null {
  if (USE_MOCKS) return null;
  const token = getToken();
  return token ? `${BASE.replace(/^http/, "ws")}/ws?token=${encodeURIComponent(token)}` : null;
}

/** GET /drugs?q=&active=: DCI or brand (substring) or ATC code (prefix); at most 50. Omit `active` for both (sent as `all`; the server default is active only). */
export function listDrugs(opts: { q?: string; active?: boolean } = {}): Promise<Drug[]> {
  const q = (opts.q ?? "").trim();
  if (USE_MOCKS)
    return mock((s) => s.drugs.filter((d) => (opts.active === undefined || d.active === opts.active) && drugMatches(d, q)).slice(0, 50));
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  p.set("active", opts.active === undefined ? "all" : String(opts.active));
  const qs = p.toString();
  return http<Drug[]>("GET", `/drugs${qs ? `?${qs}` : ""}`);
}

const sortDrugs = (s: MockStore) => s.drugs.sort((a, b) => a.dci.localeCompare(b.dci) || a.strength.localeCompare(b.strength));

/** 409 `conflict`: same DCI (case-insensitive) + strength + form as another drug (Contract decision 5). */
function assertNotDuplicate(s: MockStore, d: Pick<Drug, "dci" | "strength" | "form">, selfId?: string): void {
  const key = (x: Pick<Drug, "dci" | "strength" | "form">) => `${x.dci.trim().toLowerCase()}|${x.strength.trim().toLowerCase()}|${x.form}`;
  if (s.drugs.some((x) => x.id !== selfId && key(x) === key(d))) throw new ApiError(409, "conflict", "this drug already exists");
}

/** POST /drugs (pharmacist, admin). */
export function createDrug(req: DrugInput): Promise<Drug> {
  if (USE_MOCKS)
    return mock((s) => {
      if (!req.dci.trim() || !req.strength.trim()) throw new ApiError(422, "validation_error", "dci and strength are required");
      const atc = req.atc_code.trim().toUpperCase();
      if (atc && atc.length !== 7) throw new ApiError(422, "validation_error", "atc_code must be empty or 7 characters");
      assertNotDuplicate(s, req);
      s.seq.drug += 1;
      const t = iso(now());
      const drug: Drug = { ...req, atc_code: atc, id: `d-${String(s.seq.drug).padStart(4, "0")}`, created_at: t, updated_at: t };
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
      for (const k of ["dci", "strength"] as const)
        if (patch[k] !== undefined && !patch[k]?.trim()) throw new ApiError(422, "validation_error", `${k} is required`);
      if (patch.atc_code !== undefined) {
        patch.atc_code = patch.atc_code.trim().toUpperCase();
        if (patch.atc_code && patch.atc_code.length !== 7) throw new ApiError(422, "validation_error", "atc_code must be empty or 7 characters");
      }
      assertNotDuplicate(s, { ...drug, ...patch }, drug.id);
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
      assertKnownDrugs(s, req.items);
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
          .filter((r) => status === "all" || r.status === status)
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
      const chainIds = chainOf(s.prescriptions, rx.id); // the whole replaced chain (Contract decision 19)
      return {
        prescription: rx,
        patient: pharmacyPatient(p),
        doctor_name: userName(rx.doctor_id) ?? rx.doctor_id,
        running: s.prescriptions.filter((r) => r.patient_id === p.id && r.id !== rx.id && !chain.has(r.id) && isRunning(r)),
        checks: rxChecks(s, rx),
        history: s.reviews.filter((r) => chainIds.has(r.prescription_id)),
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
        ...stockSummary(s),
      };
    });
  return http<PharmacySummary>("GET", "/pharmacy/summary");
}

// ── Pharmacy Phase B: dispensing and stock (api 1.12 "Dispensing and stock") ─

const tunisToday = (): string => tunisDate(iso(now()));

function withFlags(l: MockLot, today: string): StockLot {
  const state = expiryState(l.expiry_date, today);
  return { ...l, expired: state === "expired", expiring: state === "expiring" };
}

/** GET /pharmacy/stock as the server computes it: active drugs, lots with stock only, on_hand without expired lots. */
function stockItems(s: MockStore): StockItem[] {
  const today = tunisToday();
  return s.drugs
    .filter((d) => d.active)
    .map((d) => {
      const lots = s.lots.filter((l) => l.drug_id === d.id && l.quantity > 0).sort((a, b) => a.expiry_date.localeCompare(b.expiry_date));
      return { drug_id: d.id, dci: d.dci, strength: d.strength, form: d.form, min_stock: d.min_stock, lots: lots.map((l) => withFlags(l, today)), ...stockFlags(lots, d.min_stock, today) };
    });
}

/** The summary's Phase B counts: drugs under min_stock, and lots with stock expiring within 30 days. */
function stockSummary(s: MockStore): { low_stock: number; expiring: number } {
  const items = stockItems(s);
  return { low_stock: items.filter((i) => i.low).length, expiring: items.flatMap((i) => i.lots).filter((l) => l.expiring).length };
}

/** The prescription item a dose came from (matched on its med string). */
function itemOfDose(s: MockStore, dose: Dose): { rx: Prescription | undefined; item: PrescriptionItem | undefined } {
  const rx = s.prescriptions.find((r) => r.id === dose.prescription_id);
  return { rx, item: rx?.items.find((i) => i.med === dose.meds[0]) ?? rx?.items[0] };
}

const dispensedDoseIds = (s: MockStore): Set<string> =>
  new Set(s.dispensations.flatMap((d) => d.lines.map((l) => l.dose_id)).filter((x): x is string => !!x));

/** GET /pharmacy/dispensing?date=&round=&ward=: per ward, per patient, the round's doses of active prescriptions. */
export function getDispensing(q: { date: string; round: string; ward?: string }): Promise<DispensingWard[]> {
  if (USE_MOCKS)
    return mock((s) => {
      const sent = dispensedDoseIds(s);
      const on = stockDay(q.date, tunisToday()); // lots valid on the later of the round date and today
      const wards = new Map<string, DispensingWard>();
      for (const dose of s.doses) {
        if (tunisDate(dose.scheduled_at) !== q.date || dose.time_of_day !== q.round) continue;
        const { rx, item } = itemOfDose(s, dose);
        if (!rx || !isRunning(rx)) continue;
        const p = s.patients.find((x) => x.id === dose.patient_id);
        if (!p?.ward || (q.ward && p.ward !== q.ward)) continue;
        const drugId = item?.drug_id ?? null;
        const quantity = item?.units_per_intake ?? 1;
        const usable = drugId ? fefoLots(s.lots.filter((l) => l.drug_id === drugId), on) : [];
        const lot = usable.find((l) => l.quantity >= quantity) ?? null;
        const w = wards.get(p.ward) ?? { ward: p.ward, patients: [] };
        wards.set(p.ward, w);
        let row = w.patients.find((x) => x.id === p.id);
        if (!row) {
          row = { id: p.id, name: `${p.first_name} ${p.last_name}`, bed: p.bed, doses: [] };
          w.patients.push(row);
        }
        row.doses.push({
          dose_id: dose.id,
          prescription_id: rx.id,
          med: dose.meds.join(" + "),
          drug_id: drugId,
          quantity,
          suggested_lot: lot ? { id: lot.id, lot_number: lot.lot_number, expiry_date: lot.expiry_date } : null,
          on_hand: drugId ? usable.reduce((n, l) => n + l.quantity, 0) : null,
          dispensed: sent.has(dose.id),
        });
      }
      const byBed = (a: { bed: string | null }, b: { bed: string | null }) => (a.bed ?? "").localeCompare(b.bed ?? "", undefined, { numeric: true });
      return [...wards.values()].map((w) => ({ ...w, patients: w.patients.sort(byBed) })).sort((a, b) => a.ward.localeCompare(b.ward));
    });
  const p = new URLSearchParams({ date: q.date, round: q.round });
  if (q.ward) p.set("ward", q.ward);
  return http<DispensingWard[]>("GET", `/pharmacy/dispensing?${p.toString()}`);
}

/**
 * POST /pharmacy/dispensations → Dispensation (`sent`). One transaction on the server: every line is checked
 * and planned first; a refused request writes nothing. One line takes ONE lot (FEFO when `lot_id` is missing).
 * 404 unknown dose; 422 `invalid`; 409 `bad_status`, `already_dispensed`, `insufficient_stock` (+ `drug_id`).
 */
export function createDispensation(req: CreateDispensationRequest, opts: ActorOpts = {}): Promise<Dispensation> {
  if (USE_MOCKS)
    return mock((s) => {
      if (req.lines.length < 1 || req.lines.length > 200) throw new ApiError(422, "invalid", "1-200 lines");
      const sent = dispensedDoseIds(s);
      const on = stockDay(req.date, tunisToday()); // backend: on = max(day, today_local())
      const seen = new Set<string>();
      const left = new Map<string, number>(); // lot id → units left after the lines planned so far
      const room = (l: MockLot) => left.get(l.id) ?? l.quantity;
      const planned = req.lines.map((line) => {
        const dose = s.doses.find((d) => d.id === line.dose_id) ?? notFound(`Dose ${line.dose_id}`);
        const patient = s.patients.find((p) => p.id === dose.patient_id);
        if (seen.has(dose.id) || patient?.ward !== req.ward || tunisDate(dose.scheduled_at) !== req.date || dose.time_of_day !== req.round_time)
          throw new ApiError(422, "invalid", `dose ${dose.id} is not in this round, or is listed twice`);
        seen.add(dose.id);
        const { rx, item } = itemOfDose(s, dose);
        if (!rx || !isRunning(rx)) throw new ApiError(409, "bad_status", `prescription ${dose.prescription_id} is not active`);
        if (sent.has(dose.id)) throw new ApiError(409, "already_dispensed", `dose ${dose.id} is already dispensed`);
        const drugId = item?.drug_id ?? null;
        const quantity = item?.units_per_intake ?? 1;
        if (!drugId) {
          if (line.lot_id) throw new ApiError(422, "invalid", "a non-formulary dose takes no lot");
          return { dose, patient, drugId, quantity, lot: null as MockLot | null };
        }
        let lot: MockLot | undefined;
        if (line.lot_id) {
          lot = s.lots.find((l) => l.id === line.lot_id);
          if (!lot || lot.drug_id !== drugId || expiryState(lot.expiry_date, on) === "expired")
            throw new ApiError(422, "invalid", `lot ${line.lot_id} can't serve dose ${dose.id}`);
          if (room(lot) < quantity) lot = undefined;
        } else {
          lot = fefoLots(s.lots.filter((l) => l.drug_id === drugId), on).find((l) => room(l) >= quantity);
        }
        if (!lot) throw new ApiError(409, "insufficient_stock", `Not enough stock for ${drugId}`, { drug_id: drugId });
        left.set(lot.id, room(lot) - quantity);
        return { dose, patient, drugId, quantity, lot: lot as MockLot | null };
      });
      // Everything fits: write the lots, the dispensation and the dose flags.
      for (const [lotId, quantity] of left) {
        const l = s.lots.find((x) => x.id === lotId);
        if (l) l.quantity = quantity;
      }
      s.seq.disp += 1;
      const id = `disp-${String(s.seq.disp).padStart(4, "0")}`;
      const by = opts.by ?? USERS.pharmacist.id;
      const disp: Dispensation = {
        id,
        ward: req.ward,
        round_date: req.date,
        round_time: req.round_time,
        status: "sent",
        prepared_by: by,
        prepared_by_name: userName(by) ?? by,
        prepared_at: iso(now()),
        received_by: null,
        received_by_name: null,
        received_at: null,
        lines: planned.map((p) => {
          s.seq.line += 1;
          p.dose.pharmacy = "sent";
          return {
            id: `dl-${String(s.seq.line).padStart(6, "0")}`,
            dose_id: p.dose.id,
            patient_id: p.dose.patient_id,
            patient_name: p.patient ? `${p.patient.first_name} ${p.patient.last_name}` : null,
            bed: p.patient?.bed ?? null,
            drug_id: p.drugId,
            lot_id: p.lot?.id ?? null,
            lot_number: p.lot?.lot_number ?? null,
            quantity: p.quantity,
            med: p.dose.meds.join(" + "),
          };
        }),
      };
      s.dispensations.push(disp);
      return disp;
    });
  return http<Dispensation>("POST", "/pharmacy/dispensations", req);
}

/** GET /dispensations?ward=&date= (nurse: own ward only, another ward is 403; pharmacist). `date` defaults to today. */
export function listDispensations(q: { ward?: string; date?: string } = {}): Promise<Dispensation[]> {
  if (USE_MOCKS)
    return mock((s) => {
      const date = q.date ?? tunisToday();
      return s.dispensations
        .filter((d) => (!q.ward || d.ward === q.ward) && d.round_date === date)
        .sort((a, b) => a.round_time.localeCompare(b.round_time));
    });
  const p = new URLSearchParams();
  if (q.ward) p.set("ward", q.ward);
  if (q.date) p.set("date", q.date);
  const qs = p.toString();
  return http<Dispensation[]>("GET", `/dispensations${qs ? `?${qs}` : ""}`);
}

/** POST /dispensations/{id}/receive (a nurse of that ward) → `received`. Idempotent: a second call returns it unchanged. */
export function receiveDispensation(id: string, opts: ActorOpts = {}): Promise<Dispensation> {
  if (USE_MOCKS)
    return mock((s) => {
      const d = s.dispensations.find((x) => x.id === id) ?? notFound(`Dispensation ${id}`);
      if (d.status === "received") return d;
      const by = opts.by ?? USERS.nurse.id;
      Object.assign(d, { status: "received", received_by: by, received_by_name: userName(by) ?? by, received_at: iso(now()) });
      for (const line of d.lines) {
        const dose = line.dose_id ? s.doses.find((x) => x.id === line.dose_id) : undefined;
        if (dose) dose.pharmacy = "received";
      }
      return d;
    });
  return http<Dispensation>("POST", `/dispensations/${enc(id)}/receive`, {});
}

/** GET /pharmacy/stock (pharmacist, admin) → one StockItem per active drug. */
export function getStock(): Promise<StockItem[]> {
  if (USE_MOCKS) return mock((s) => stockItems(s));
  return http<StockItem[]>("GET", "/pharmacy/stock");
}

/**
 * POST /pharmacy/stock/receipts → Lot. Tops up the lot when (drug_id, lot_number) exists; 409 `conflict` when
 * it exists with another expiry; 422 when already expired or out of range; 404 unknown drug.
 */
export function receiveStock(req: StockReceiptRequest): Promise<StockLot> {
  if (USE_MOCKS)
    return mock((s) => {
      s.drugs.find((d) => d.id === req.drug_id) ?? notFound(`Drug ${req.drug_id}`);
      const lotNumber = req.lot_number.trim();
      if (!lotNumber || lotNumber.length > 40 || !Number.isInteger(req.quantity) || req.quantity < 1 || req.quantity > 100_000 || !/^\d{4}-\d{2}-\d{2}$/.test(req.expiry_date))
        throw new ApiError(422, "validation_error", "lot_number 1-40, expiry_date YYYY-MM-DD, quantity 1-100000");
      const today = tunisToday();
      if (expiryState(req.expiry_date, today) === "expired") throw new ApiError(422, "validation_error", "this lot is already expired");
      const existing = s.lots.find((l) => l.drug_id === req.drug_id && l.lot_number === lotNumber);
      if (existing && existing.expiry_date !== req.expiry_date) throw new ApiError(409, "conflict", "this lot number exists with another expiry date");
      if (existing) {
        existing.quantity += req.quantity;
        return withFlags(existing, today);
      }
      s.seq.lot += 1;
      const lot: MockLot = { id: `lot-${String(s.seq.lot).padStart(4, "0")}`, drug_id: req.drug_id, lot_number: lotNumber, expiry_date: req.expiry_date, quantity: req.quantity, received_at: iso(now()) };
      s.lots.push(lot);
      return withFlags(lot, today);
    });
  return http<StockLot>("POST", "/pharmacy/stock/receipts", req);
}

/**
 * POST /pharmacy/stock/adjustments → Lot. delta ≠ 0 (±100000), comment 1–500, `expired` needs a negative delta
 * (422). Below zero: 409 `insufficient_stock` with `drug_id`.
 */
export function adjustStock(req: StockAdjustmentRequest): Promise<StockLot> {
  if (USE_MOCKS)
    return mock((s) => {
      const lot = s.lots.find((l) => l.id === req.lot_id) ?? notFound(`Lot ${req.lot_id}`);
      const comment = req.comment.trim();
      if (!Number.isInteger(req.delta) || req.delta === 0 || Math.abs(req.delta) > 100_000 || !comment || [...comment].length > COMMENT_MAX)
        throw new ApiError(422, "validation_error", "delta must be a non-zero integer (±100000) and the comment 1-500 characters");
      if (req.reason === "expired" && req.delta > 0) throw new ApiError(422, "validation_error", "reason expired needs a negative delta");
      if (lot.quantity + req.delta < 0) throw new ApiError(409, "insufficient_stock", "Stock can't go below zero", { drug_id: lot.drug_id });
      lot.quantity += req.delta;
      return withFlags(lot, tunisToday());
    });
  return http<StockLot>("POST", "/pharmacy/stock/adjustments", req);
}

/** GET /pharmacy/stock/reorder: drugs with on_hand < min_stock, suggested 2 × min_stock − on_hand. */
export function getReorderList(): Promise<ReorderItem[]> {
  if (USE_MOCKS)
    return mock((s) =>
      stockItems(s)
        .filter((i) => i.low)
        .map((i) => ({ drug_id: i.drug_id, dci: i.dci, strength: i.strength, form: i.form, on_hand: i.on_hand, min_stock: i.min_stock, suggested_quantity: reorderQuantity(i.min_stock, i.on_hand) })),
    );
  return http<ReorderItem[]>("GET", "/pharmacy/stock/reorder");
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
  if (USE_MOCKS) return mock((s) => (advanceMockReadings(s), s.exams.filter((e) => e.appointment_id === appointmentId)));
  return http<ExamOrder[]>("GET", `/appointments/${encodeURIComponent(appointmentId)}/exams`);
}

export async function getPatientExams(patientId: string): Promise<ExamOrder[]> {
  if (USE_MOCKS) return mock((s) => (advanceMockReadings(s), s.exams.filter((e) => e.patient_id === patientId && e.status !== "cancelled")));
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

/** Mock radiograph results get a placeholder image, everything else the sample PDF. */
function mockResultUrl(resultId: string): string {
  return resultId in MOCK_READING_DRAFTS ? MOCK_RADIOGRAPH_URL : "/mock-exam.pdf";
}

/** Authenticated download → an object URL for a new tab. Revoke it when done. */
export async function examFileUrl(resultId: string): Promise<string> {
  if (USE_MOCKS) return mockResultUrl(resultId);
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

// ── Radiograph reading (api.md 1.14) ────────────────────────────────────────

/** Mock: real wall-clock time of the first fetch of each queued reading (the demo clock is frozen). */
const READING_FIRST_SEEN = new Map<string, number>();
export const MOCK_READING_QUEUE_MS = 6000;

/** Keeps `results[].reading` in step with the reading rows. */
function syncReadingSummaries(s: MockStore): void {
  for (const e of s.exams)
    for (const r of e.results ?? []) {
      const rd = s.readings[r.id];
      if (rd) r.reading = { id: rd.id, status: rd.status, confirmed: !!rd.human_confirmed_by };
    }
}

/**
 * Mock: moves a queued reading to running, then ready, by real elapsed time since it was first seen (by the exams
 * list or the reading itself). Real time, not now(): the mock clock never moves, so polling would never see a change.
 */
function advanceMockReading(resultId: string, rd: RadiographReading): void {
  if (rd.status !== "queued" && rd.status !== "running") return;
  const first = READING_FIRST_SEEN.get(resultId) ?? Date.now();
  READING_FIRST_SEEN.set(resultId, first);
  const waited = Date.now() - first;
  if (waited >= MOCK_READING_QUEUE_MS) {
    rd.status = "ready";
    rd.ai_suggested = MOCK_READING_DRAFTS[resultId] ?? null;
    rd.finished_at = iso(now());
  } else if (waited >= MOCK_READING_QUEUE_MS / 2) rd.status = "running";
}

/** Mock: advances every pending reading (called by the exams list, which polls while one is pending). */
function advanceMockReadings(s: MockStore): void {
  for (const [resultId, rd] of Object.entries(s.readings)) advanceMockReading(resultId, rd);
  syncReadingSummaries(s);
}

/** GET /exam-results/{id}/reading (doctor: full reading; the UI polls while queued/running). */
export async function getRadiographReading(resultId: string): Promise<RadiographReading> {
  if (USE_MOCKS)
    return mock((s) => {
      const rd = s.readings[resultId] ?? notFound(`Reading for ${resultId}`);
      advanceMockReading(resultId, rd);
      syncReadingSummaries(s);
      return rd;
    });
  return http<RadiographReading>("GET", `/exam-results/${encodeURIComponent(resultId)}/reading`);
}

/** PUT /exam-results/{id}/reading (doctor): sign the final report text. */
export async function confirmRadiographReading(resultId: string, finalText: string): Promise<RadiographReading> {
  if (USE_MOCKS)
    return mock((s) => {
      const rd = s.readings[resultId] ?? notFound(`Reading for ${resultId}`);
      rd.final_text = finalText;
      rd.human_confirmed_by = "u-0001";
      rd.confirmed_by_name = "Dr Trabelsi";
      rd.confirmed_at = iso(now());
      for (const e of s.exams) for (const r of e.results ?? []) if (r.id === resultId) r.report_text = finalText;
      syncReadingSummaries(s);
      return rd;
    });
  return http<RadiographReading>("PUT", `/exam-results/${encodeURIComponent(resultId)}/reading`, { final_text: finalText });
}

/** POST /patients/{id}/radiographs (doctor): add an outside X-ray (JPEG/PNG) and queue an AI reading. */
export async function uploadOutsideRadiograph(patientId: string, file: File, title: string): Promise<ExamOrder> {
  if (USE_MOCKS) return Promise.reject(new ApiError(503, "needs_backend", "Uploading a radiograph needs the real backend."));
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  return upload<ExamOrder>(`/patients/${encodeURIComponent(patientId)}/radiographs`, form);
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

// ── Health calendar (api.md 1.13) ──────────────────────────────────────────

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

function withHealthFlags(s: MockStore, role: Role, ev: Omit<HealthEvent, "matches_me" | "following">): HealthEvent {
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
        .map((e) => withHealthFlags(s, opts.role ?? "patient", e));
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
      return withHealthFlags(s, "admin", ev);
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
      return withHealthFlags(s, "admin", ev);
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
