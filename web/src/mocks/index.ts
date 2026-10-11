// Mock fixtures entry point. All data is synthetic, copied from the Claude Design mockups.
// `api.ts` is the only consumer: components never import mocks directly
// (except `NAV_COUNTS`, the static sidebar counts).
import type { RadiographReading, Alert, AiSummary, Appointment, Device, Dose, ExamOrder, HomeCarePlan, Note, Patient, Prescription, SlotOffer, StaffMember, Vital, DoctorRef, PatientAccessGrant, PendingUser, UserAdmin, HealthEvent, HealthCategory } from "@/lib/types";
import { ALERTS } from "./alerts";
import { PATIENT_APPOINTMENTS, WAITLIST } from "./appointments";
import { DOSES, NOTES, PRESCRIPTIONS, SUMMARIES } from "./clinical";
import { BOARD_BED_ORDER, DEVICES, PATIENTS, STAFF, USERS } from "./people";
import { HOME_CARE, OFFERS } from "./patient";
import { VITALS } from "./vitals";
import { examFixtures, radiographExamFixtures, readingFixtures } from "./exams";
import { HEALTH_EVENTS } from "./healthEvents";
import { DOCTOR_DIRECTORY, GRANTS, PENDING, TEAM } from "./accounts";
export { MOCK_CODES, generateCode } from "./accounts";

export { mockAssistant, type AssistantContext } from "./assistant";
export { BOARD_BED_ORDER, USERS, userName } from "./people";
export { nowIso } from "./time";
export { EXAM_CATALOGUE, MOCK_RADIOGRAPH_URL, MOCK_READING_DRAFTS } from "./exams";

/** Sidebar counts, verbatim from Sidebar.dc.html's sample data. */
export const NAV_COUNTS = {
  doctor: { patients: "6", requests: "4" },
  nurse: { board: "", alerts: "4", meds: "3", patients: "8" },
  admin: { dashboard: "", waitlist: "8", devices: "", staff: "" },
} as const;

export interface MockStore {
  patients: Patient[];
  vitals: Record<string, Vital[]>;
  prescriptions: Prescription[];
  doses: Dose[];
  notes: Record<string, Note[]>;
  summaries: Record<string, { model: AiSummary; rules: AiSummary }>;
  appointments: Appointment[];
  alerts: Alert[];
  devices: Device[];
  staff: StaffMember[];
  boardBedOrder: string[];
  offers: SlotOffer[];
  exams: ExamOrder[];
  /** Radiograph readings by exam result id. */
  readings: Record<string, RadiographReading>;
  homeCare: Record<string, HomeCarePlan>;
  directory: DoctorRef[];
  pending: PendingUser[];
  team: UserAdmin[];
  grants: Record<string, PatientAccessGrant[]>;
  /** Patient records that already have an account (the real API enforces one account per record). */
  linkedPatients: string[];
  healthEvents: Omit<HealthEvent, "matches_me" | "following">[];
  /** Per-role category follow overrides (missing = following). */
  healthPrefs: Record<string, Partial<Record<HealthCategory, boolean>>>;
  seq: { rx: number; dose: number; note: number; user: number; he: number };
}

/** A fresh, deep-copied, mutable store. Mutations in api.ts write here. */
export function createStore(): MockStore {
  return structuredClone({
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
    exams: [...examFixtures(WAITLIST[0].id, WAITLIST[0].patient_id, WAITLIST[0].patient_name ?? ""), ...radiographExamFixtures("p-0001", "Amira Ben Salah")],
    readings: readingFixtures("p-0001"),
    homeCare: HOME_CARE,
    directory: DOCTOR_DIRECTORY,
    pending: PENDING,
    team: TEAM,
    grants: GRANTS,
    linkedPatients: [USERS.patient.patient_id],
    healthEvents: HEALTH_EVENTS,
    healthPrefs: {},
    seq: { he: HEALTH_EVENTS.length, rx: PRESCRIPTIONS.length, dose: DOSES.length, note: Object.values(NOTES).flat().length, user: 100 },
  });
}

