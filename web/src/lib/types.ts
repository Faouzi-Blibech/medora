// API types. They mirror docs/contracts/api.md v1.4 (and data-model.md for doses).
//
// Fields marked `UI extension` are NOT in the contract yet. They are optional,
// the mocks fill them in, and components must fall back gracefully when the real
// API omits them (e.g. show the id, or derive the value). They are listed in the
// Task 1 report as a proposed api.md 1.5 bump.

export type Role = "doctor" | "nurse" | "admin" | "patient";

/** `source` on every AI output (api.md 1.4). */
export type AiSource = "model" | "rules" | "llm";

/** 1 = non-urgent … 5 = very urgent. */
export type Urgency = 1 | 2 | 3 | 4 | 5;

// ── Auth ────────────────────────────────────────────────────────────────────

export interface Me {
  id: string; // u-0001
  name: string;
  email: string;
  role: Role;
  patient_id: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  user: Pick<Me, "id" | "name" | "role" | "patient_id">;
}

// ── Patients and records ────────────────────────────────────────────────────

export interface PatientSummary {
  id: string; // p-0001
  first_name: string;
  last_name: string;
  age: number;
  ward: string | null; // "Cardiology"
  bed: string | null; // "C-12"
  device_id: string | null; // "bsu-001"
  latest_news2: number | null;
  open_alerts: number;
  /** UI extension: timestamp of the latest vital ("Last vitals · 8 s ago"). */
  last_vital_at?: string | null;
  /** UI extension: is the bedside unit online. */
  device_online?: boolean | null;
}

export interface Patient extends PatientSummary {
  sex: "F" | "M";
  date_of_birth: string; // YYYY-MM-DD
  allergies: string[]; // ["penicillin"]
  history: string;
  attending_doctor_id: string | null;
  admission_id: string | null;
  /** UI extension: "admitted Fri 2 Oct". */
  admitted_at?: string | null;
  /** UI extension: "Severe rash (2019) · includes amoxicillin". */
  allergy_notes?: string | null;
  /** UI extension: display name of the attending doctor. */
  attending_doctor_name?: string | null;
  /** UI extension: display name of the assigned nurse ("Ines"). */
  nurse_name?: string | null;
}

export type VitalSource = "device" | "simulator" | "manual";

export interface Vital {
  ts: string;
  hr: number | null;
  spo2: number | null;
  temp: number | null;
  nurse_id: string | null;
  news2: number | null;
  source: VitalSource;
  /** UI extension: respiratory rate, /min (nurse detail tiles). */
  rr?: number | null;
  /** UI extension: systolic / diastolic blood pressure (nurse detail tiles). */
  bp_sys?: number | null;
  bp_dia?: number | null;
}

export interface Note {
  id: string; // n-0001
  author_id: string;
  author_role: Role;
  text: string;
  created_at: string;
  /** UI extension: "Nurse Ines". */
  author_name?: string;
}

// ── Prescriptions and doses ─────────────────────────────────────────────────

export interface PrescriptionItem {
  med: string; // "Paracetamol 500mg"
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
  active: boolean;
  created_at: string;
  schedule_version: number;
  published_to_device: boolean;
  /** UI extension: saved despite an allergy rule conflict (override logged). */
  allergy_override?: boolean;
}

export interface CreatePrescriptionRequest {
  patient_id: string;
  items: PrescriptionItem[];
  care_plan: string;
}

export type DoseStatus = "scheduled" | "dispensed" | "taken" | "missed";

/** One `med_doses` row (data-model.md). No REST path in api.md 1.4 yet. */
export interface Dose {
  id: string; // d-000001
  prescription_id: string;
  patient_id: string;
  scheduled_at: string;
  time_of_day: string; // "08:00"
  meds: string[];
  slot: number | null;
  status: DoseStatus;
  taken_method: "ir" | "button" | null;
  updated_at: string;
  /** UI extension: when it was taken / given. */
  taken_at?: string | null;
  /** UI extension: nurse who gave it by hand (user id) — the design's "Given". */
  given_by?: string | null;
  given_by_name?: string | null;
  /** UI extension: "Give by hand", "Injection", "2 puffs". */
  instructions?: string | null;
}

// ── AI ──────────────────────────────────────────────────────────────────────

export type Severity = "low" | "medium" | "high";

export interface Interaction {
  drugs: [string, string];
  severity: Severity;
  note: string;
}

export interface AiSummary {
  summary: string;
  interactions: Interaction[];
  source: AiSource;
  generated_at: string;
  human_confirmed_by: string | null;
  /** UI extension: "Dr Trabelsi". */
  human_confirmed_by_name?: string | null;
  /** UI extension: when the doctor reviewed it. */
  reviewed_at?: string | null;
  /** UI extension: "Based on: 48 vitals readings · 6 doses · 3 notes". */
  based_on?: { vitals: number; doses: number; notes: number };
}

export type AssistantIntent = "next_dose" | "next_visit" | "my_vitals" | "ask_staff" | "urgent";

export interface AssistantResponse {
  answer: string;
  sources: string[];
  intent: AssistantIntent;
  source: AiSource;
}

/** POST /ai/chat: role assistants over one patient's record. */
export type ChatRole = "user" | "assistant";
export interface ChatTurn { role: ChatRole; text: string; }
export interface ChatCitation { n?: number; source_id: string; kind: string; title: string; ts: string | null; text: string; }
export interface ChatResponse {
  id: string;
  answer: string;
  citations: ChatCitation[];
  source: "llm" | "rules";
  /** Numbers in the answer that are not in the record: staff must check them. */
  unverified?: string[];
  urgent?: boolean;
}

/** Staff assistant conversations (sidebar "AI assistant" page). */
export interface PatientRef { id: string; name: string; }
export interface ConversationMessage {
  id: string;
  role: ChatRole;
  text: string;
  patient: PatientRef | null;
  created_at: string;
  citations?: ChatCitation[];
  source?: "llm" | "rules";
  unverified?: string[];
}
export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  /** Present on GET /ai/conversations/{id}. */
  messages?: ConversationMessage[];
  /** The patient the conversation is currently about. */
  patient?: PatientRef | null;
}

/** Health watch: weather-health alerts for the hospital's city and health news. Texts come in the three languages. */
export type Tri = { en: string; fr: string; ar: string };
export interface WeatherDay {
  date: string; tmax: number | null; tmin: number | null; apparent_max: number | null; precip: number | null;
  gusts: number | null; uv: number | null; dust_max: number | null; pm10_max: number | null; aqi_max: number | null;
}
export interface HealthAlert {
  id: string; date: string; severity: "high" | "moderate"; value: string; groups: string[];
  title: Tri; staff?: Tri; patient: Tri;
  at_risk?: { id: string; name: string; groups: string[] }[]; at_risk_count?: number; concerns_me?: boolean;
}
export interface NewsItem { title: string; link: string; source: string; published: string | null; lang: string; }
export interface HealthWatch {
  city: string; available: boolean; demo: string | null; days: WeatherDay[]; alerts: HealthAlert[];
  news?: NewsItem[]; updated_at?: string;
}

// ── Appointments and waitlist ───────────────────────────────────────────────

export type AppointmentStatus = "requested" | "confirmed" | "cancelled" | "done" | "no_show";

export interface Triage {
  urgency: Urgency;
  reasons: string[];
  red_flags: string[]; // snake_case codes, see RED_FLAG_LABELS in lib/labels.ts
  source: AiSource;
  /** From POST /ai/triage; null when no trained model is loaded. 0–1. */
  confidence?: number | null;
  model_urgency?: Urgency | null;
  /** The hospital's triage scale for this urgency (display mapping; `confirmed` false until doctors confirm it). */
  scale?: { name: string; level: string; confirmed: boolean } | null;
}

export type ExamStatus = "suggested" | "ordered" | "done" | "cancelled";
export interface ExamResultFile { id: string; file_name: string; content_type: string; size_bytes: number; report_text: string; uploaded_by_name: string | null; created_at: string; }
export interface ExamOrder { id: string; patient_id: string; appointment_id: string | null; code: string; label: string; department: string; status: ExamStatus; ai_suggested?: { source: AiSource; bundles: string[]; reason: string } | null; human_confirmed_by?: string | null; ordered_at: string | null; done_at: string | null; created_at: string; patient_name: string | null; results?: ExamResultFile[]; }
export interface CatalogueItem { code: string; label: string; department: string; }

export interface Appointment {
  id: string; // a-0001
  patient_id: string;
  status: AppointmentStatus;
  urgency_ai: Urgency;
  urgency_final: Urgency | null;
  triage: Triage;
  slot_at: string | null;
  doctor_id: string | null;
  confirmed_by: string | null;
  patient_confirmed_at: string | null;
  no_show_prob: number | null; // 0–1
  created_at: string;
  /** AI-output convention (data-model.md): same as `triage`. */
  ai_suggested?: Triage;
  /** AI-output convention: who confirmed or overrode the AI urgency. */
  human_confirmed_by?: string | null;
  /** UI extensions: display fields the waitlist and the patient view need. */
  patient_name?: string;
  patient_age?: string; // "58", "4 mo"
  specialty?: string;
  referral_text?: string;
  lang?: "fr" | "ar" | "aeb-Latn" | "en";
  doctor_name?: string | null;
  room?: string | null; // "Cardiology, Room 4"
  confirmed_by_name?: string | null;
  human_confirmed_by_name?: string | null;
  exams_total?: number;
  exams_done?: number;
  exams_suggested?: number;
}

export interface ConfirmAppointmentRequest {
  slot_at: string;
  doctor_id: string;
  urgency_final?: Urgency;
}

// ── Patient app extras (NOT IN CONTRACT: no api.md 1.4 endpoint yet) ────────

/**
 * A freed slot offered to the patient (n8n W2 backfill). The contract only has the
 * n8n `backfill-accept` callback; the patient web view needs these two shapes.
 */
export interface SlotOffer {
  id: string; // of-0001
  /** The patient's own appointment the offer would replace. */
  appointment_id: string;
  slot_at: string;
  doctor_id: string;
  doctor_name: string;
  room: string;
  status: "open" | "accepted" | "taken";
  expires_at: string;
}

export type HomeCareStepState = "done" | "next" | "pending";

/** The "After discharge" screen: follow-up progress and the medicines to take at home. */
export interface HomeCarePlan {
  patient_id: string;
  discharged_at: string;
  ward_label: string; // "Ward C"
  follow_up: { title: string; steps: { title: string; sub: string; state: HomeCareStepState }[] };
  medicines: { when: string; name: string; sub: string }[];
  desk_phone: string; // "+216 71 000 000"
  emergency_number: string; // "190"
}

// ── Alerts ──────────────────────────────────────────────────────────────────

export type AlertKind = "news2" | "trend" | "call_nurse" | "dose_missed" | "device_offline";
export type AlertSeverity = "low" | "medium" | "high" | "critical";

export interface Alert {
  id: string; // al-0001
  patient_id: string;
  device_id: string | null;
  kind: AlertKind;
  severity: AlertSeverity;
  news2: number | null;
  message: string;
  created_at: string;
  acked_by: string | null;
  acked_at: string | null;
  /** UI extensions. */
  bed?: string | null;
  patient_first_name?: string | null;
  acked_by_name?: string | null;
}

// ── Devices and staff ───────────────────────────────────────────────────────

export interface Device {
  id: string; // bsu-001
  online: boolean;
  fw_version: string;
  last_seen: string;
  patient_id: string | null;
  bed: string | null;
  /** UI extension. */
  patient_name?: string | null;
  /** UI extension (proposed in api.md 1.5): the active admission, needed for discharge. */
  admission_id?: string | null;
}

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

/** The roles a person can ask for on /register (`admin` is never a sign-up choice). */
export type SignupRole = "patient" | "nurse" | "doctor";
/** The roles an approver can grant (only an admin may grant `admin`). */
export type GrantRole = SignupRole | "admin";

export interface RegisterRequest {
  name: string;
  email: string;
  password: string;
  role: SignupRole;
  note?: string;
  /** Patients and nurses only; sending it with `role: "doctor"` is a 422. */
  requested_doctor_id?: string;
}
/** GET /hospital (public): this install's hospital. */
export interface Hospital {
  name: string;
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
  requested_role: SignupRole | null;
  requested_doctor_id: string | null;
  /** UI extension: resolved from the doctor directory when the server doesn't send it. */
  requested_doctor_name?: string | null;
  status: "pending" | "rejected";
  created_at: string;
}
export interface ApproveRequest {
  role: GrantRole;
  ward?: string | null;
  /** Patient role only: link to this existing record; omit to create a new record from the request's name. */
  patient_id?: string | null;
}
export interface UserAdmin {
  id: string;
  name: string;
  email: string;
  role: Exclude<Role, "patient"> | null;
  status: AccountStatus;
  ward: string | null;
  supervisor_id: string | null;
  /** Set on pending and rejected requests. */
  requested_role: SignupRole | null;
  requested_doctor_id: string | null;
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

// ── Composed views (built client-side from several contract calls) ──────────

/** One bed on the nurse ward board. */
export interface WardBed {
  bed: string;
  patient: PatientSummary | null; // null = empty bed
  device: Device | null;
  latest: Vital | null;
  /** An open `call_nurse` alert exists for this bed. */
  calling: boolean;
}

/** One patient block of the nurse med round (today's doses). */
export interface MedRoundGroup {
  patient: Patient;
  device: Device | null;
  doses: Dose[];
}

// ── WebSocket ───────────────────────────────────────────────────────────────

export type WsFrame =
  | {
      type: "vital";
      data: {
        patient_id: string;
        device_id: string;
        ts: string;
        hr: number | null;
        spo2: number | null;
        temp: number | null;
        news2: number | null;
      };
    }
  | { type: "alert"; data: Alert }
  | { type: "call_nurse"; data: { patient_id: string; device_id: string; bed: string; ts: string } }
  | {
      type: "dose_event";
      data: {
        patient_id: string;
        dose_id: string;
        status: "dispensed" | "taken" | "missed";
        method: "ir" | "button" | null;
        ts: string;
      };
    }
  | { type: "device_status"; data: { device_id: string; online: boolean; ts: string } };

export interface ApiErrorBody {
  detail: string;
  code: string;
}

// ── Health calendar (api.md 1.12) ──
export const HEALTH_CATEGORIES = ["screening", "vaccination", "chronic_disease", "infectious_disease", "lifestyle", "mental_health", "blood_donation"] as const;
export type HealthCategory = (typeof HEALTH_CATEGORIES)[number];
/** Calendar entries also include the weather-health alerts (GET /health-watch), shown as one-day "weather" events. */
export type CalendarCategory = HealthCategory | "weather";
export interface WeatherInfo {
  severity: "high" | "moderate";
  groups: string[];
  /** Staff: the patients they can access in a risk group (admin: count only). */
  at_risk?: { id: string; name: string; groups: string[] }[];
  at_risk_count?: number;
}
export interface HealthText { en: string; fr: string; ar: string; }
export interface HealthAudience { roles: Role[]; sex: "F" | "M" | null; min_age: number | null; max_age: number | null; }
export interface HealthEvent {
  id: string;
  title: HealthText;
  description: HealthText;
  category: CalendarCategory;
  starts_on: string; // YYYY-MM-DD
  ends_on: string;
  audience: HealthAudience;
  notify_days_before: number;
  organizer: string | null;
  source_url: string | null;
  announced_at: string | null;
  matches_me: boolean;
  following: boolean;
  /** Present on weather-health entries only (built in the web app, never stored as a health event). */
  weather?: WeatherInfo;
}
export type HealthEventInput = Omit<HealthEvent, "id" | "announced_at" | "matches_me" | "following">;
export interface HealthPrefs { following: Record<HealthCategory, boolean>; }

/** GET /admin/impact (api.md 1.16): pilot impact indicators, aggregates only. */
export type ImpactGroup = "alerts" | "medication" | "appointments" | "monitoring" | "workload";
export type ImpactUnit = "count" | "pct" | "minutes" | "hours" | "days" | "rate";
export type ImpactId =
  | "alerts_total" | "ack_median_min" | "ack_p90_min" | "ack_within_5min_pct"
  | "doses_due" | "doses_taken_pct" | "doses_missed_pct" | "doses_on_time_pct" | "missed_per_patient_day"
  | "requests_received" | "request_to_booking_hours" | "request_to_slot_days" | "cancellations"
  | "backfill_refills" | "no_show_rate_pct"
  | "vitals_per_patient_day" | "vitals_automated_pct" | "news2_medium_high_pct"
  | "nurse_notes_per_shift" | "ai_reviewed_pct";
export interface ImpactIndicator {
  id: ImpactId;
  group: ImpactGroup;
  unit: ImpactUnit;
  /** Which direction is good; null = context, not a target. */
  better: "higher" | "lower" | null;
  /** not_recorded: the data model cannot measure it yet (value and previous are null). */
  status: "ok" | "not_recorded";
  /** null with status ok: nothing to measure in that period. */
  value: number | null;
  previous: number | null;
  /** Current period only: counts by severity, source, NEWS2 band, or {reviewed, pending}. */
  breakdown: Record<string, number> | null;
}
export interface ImpactReport {
  days: number;
  period: { from: string; to: string };
  previous_period: { from: string; to: string };
  patient_days: number;
  data: "synthetic";
  indicators: ImpactIndicator[];
}
