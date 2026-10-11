// Mock fixtures entry point. All data is synthetic, copied from the Claude Design mockups.
// `api.ts` is the only consumer: components never import mocks directly
// (except `NAV_COUNTS`, the static sidebar counts).
import type { RadiographReading, Alert, Dispensation, AiSummary, Appointment, Device, Dose, Drug, ExamOrder, HomeCarePlan, Note, Patient, Prescription, PrescriptionReview, SlotOffer, StaffMember, Vital, DoctorRef, PatientAccessGrant, PendingUser, UserAdmin, HealthEvent, HealthCategory } from "@/lib/types";
import { checksFor, FORMULARY, LOTS, REVIEWS, seedDispensations, type MockLot } from "./pharmacy";
export type { MockLot } from "./pharmacy";
export { chainOf, checksFor, drugMatches } from "./pharmacy";
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
  drugs: Drug[];
  reviews: PrescriptionReview[];
  lots: MockLot[];
  dispensations: Dispensation[];
  healthEvents: Omit<HealthEvent, "matches_me" | "following">[];
  /** Per-role category follow overrides (missing = following). */
  healthPrefs: Record<string, Partial<Record<HealthCategory, boolean>>>;
  seq: { he: number; rx: number; dose: number; note: number; user: number; drug: number; review: number; lot: number; disp: number; line: number };
}

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
    exams: [...examFixtures(WAITLIST[0].id, WAITLIST[0].patient_id, WAITLIST[0].patient_name ?? ""), ...radiographExamFixtures("p-0001", "Amira Ben Salah")],
    readings: readingFixtures("p-0001"),
    homeCare: HOME_CARE,
    directory: DOCTOR_DIRECTORY,
    pending: PENDING,
    team: TEAM,
    grants: GRANTS,
    linkedPatients: [USERS.patient.patient_id],
    drugs: FORMULARY,
    reviews: REVIEWS,
    lots: LOTS,
    dispensations: [],
    healthEvents: HEALTH_EVENTS,
    healthPrefs: {},
    seq: {
      he: HEALTH_EVENTS.length,
      rx: PRESCRIPTIONS.length,
      dose: DOSES.length,
      note: Object.values(NOTES).flat().length,
      user: 100,
      drug: FORMULARY.length,
      review: REVIEWS.length,
      lot: LOTS.length,
      disp: 0,
      line: 0,
    },
  });
  // Checks are computed, never typed into fixtures: the same engine the mock POST /prescriptions runs.
  for (const rx of s.prescriptions)
    if (rx.status === "pending_pharmacy" || rx.status === "changes_requested")
      rx.checks = checksFor(s.patients, s.prescriptions, s.drugs, { patient_id: rx.patient_id, items: rx.items, ...(rx.replaces_id ? { replaces_id: rx.replaces_id } : {}) }, rx.id);
  for (const r of s.reviews) r.checks_snapshot = s.prescriptions.find((x) => x.id === r.prescription_id)?.checks ?? [];
  // Phase B: every dose starts "none"; the seeded 10:00 round marks its doses "sent".
  for (const d of s.doses) d.pharmacy ??= "none";
  s.dispensations = seedDispensations(s.doses, s.prescriptions, s.patients, s.lots);
  s.seq.disp = s.dispensations.length;
  s.seq.line = s.dispensations.reduce((n, d) => n + d.lines.length, 0);
  return s;
}
