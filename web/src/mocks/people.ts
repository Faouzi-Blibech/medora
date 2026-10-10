// Users, staff, patients and devices. Synthetic, copied from the Claude Design mockups.
import type { Device, Me, Patient, StaffMember } from "@/lib/types";
import { at, secondsAgo, SUN, TODAY } from "./time";

export const USERS = {
  doctor: { id: "u-0001", name: "Dr Trabelsi", email: "m.trabelsi@hr-ward.tn", role: "doctor", patient_id: null },
  nurse: { id: "u-0002", name: "Nurse Ines", email: "i.mejri@hr-ward.tn", role: "nurse", patient_id: null },
  admin: { id: "u-0003", name: "Mme Gharbi", email: "n.gharbi@hr-ward.tn", role: "admin", patient_id: null },
  patient: { id: "u-0007", name: "Amira Ben Salah", email: "patient@ward.tn", role: "patient", patient_id: "p-0001" },
  pharmacist: { id: "u-0008", name: "Pharm. Salma", email: "pharmacist@ward.tn", role: "pharmacist", patient_id: null },
} satisfies Record<Me["role"], Me>;

/** Admin "Staff" screen (Ward Admin.dc.html). */
const STAFF_ROWS: Omit<StaffMember, "status">[] = [
  { id: "u-0001", name: "Dr Trabelsi", email: "m.trabelsi@hr-ward.tn", role: "doctor", ward: "Cardiology", scope: "Cardiology · Ward C", last_login_at: at(TODAY, "09:10") },
  { id: "u-0002", name: "Nurse Ines", email: "i.mejri@hr-ward.tn", role: "nurse", ward: "Cardiology", scope: "Ward C · day", last_login_at: at(TODAY, "07:02") },
  { id: "u-0004", name: "Nurse Sami", email: "s.dridi@hr-ward.tn", role: "nurse", ward: "Cardiology", scope: "Ward C · night", last_login_at: at(TODAY, "06:58") },
  { id: "u-0010", name: "Dr Ben Romdhane", email: "a.benromdhane@hr-ward.tn", role: "doctor", ward: "Pediatrics", scope: "Pediatrics", last_login_at: at(SUN, "18:40") },
  { id: "u-0011", name: "Dr Karoui", email: "h.karoui@hr-ward.tn", role: "doctor", ward: "Pulmonology", scope: "Pulmonology", last_login_at: at("2026-10-02", "14:21") },
  { id: "u-0003", name: "Mme Gharbi", email: "n.gharbi@hr-ward.tn", role: "admin", ward: null, scope: "Administration", last_login_at: at(TODAY, "08:45") },
  { id: "u-0008", name: "Pharm. Salma", email: "pharmacist@ward.tn", role: "pharmacist", ward: null, scope: "Pharmacy", last_login_at: at(TODAY, "07:40") },
];
const DISABLED_DEMO = new Set(["u-0004"]);
export const STAFF: StaffMember[] = STAFF_ROWS.map((s) => ({ ...s, status: DISABLED_DEMO.has(s.id) ? "disabled" : "active" }));

/** Staff who appear only as names (not in the admin Staff screen), e.g. the Imaging nurse on exam results. */
const EXTRA_NAMES: Record<string, string> = { "u-0006": "Nurse Rania" };

export function userName(id: string | null | undefined): string | null {
  if (!id) return null;
  return STAFF.find((s) => s.id === id)?.name ?? Object.values(USERS).find((u) => u.id === id)?.name ?? EXTRA_NAMES[id] ?? null;
}

const base = {
  ward: "Cardiology",
  history: "",
  admitted_at: at("2026-10-02", "10:00"),
  allergy_notes: null,
  attending_doctor_id: "u-0001",
  attending_doctor_name: "Dr Trabelsi",
  nurse_name: "Ines",
} as const;

/** Ward C (Cardiology), sorted as the doctor list: highest NEWS2 first. */
export const PATIENTS: Patient[] = [
  {
    ...base, id: "p-0002", first_name: "Omar", last_name: "Jaziri", age: 72, sex: "M", date_of_birth: "1954-02-11",
    bed: "C-16", device_id: "bsu-004", latest_news2: 7, open_alerts: 3, last_vital_at: secondsAgo(12), device_online: true,
    allergies: [], history: "Heart failure", admission_id: "adm-0002",
  },
  {
    ...base, id: "p-0001", first_name: "Amira", last_name: "Ben Salah", age: 54, sex: "F", date_of_birth: "1972-03-14",
    bed: "C-12", device_id: "bsu-001", latest_news2: 5, open_alerts: 1, last_vital_at: secondsAgo(8), device_online: true,
    allergies: ["penicillin"], allergy_notes: "Severe rash (2019) · includes amoxicillin", history: "Hypertension",
    admission_id: "adm-0001",
  },
  {
    ...base, id: "p-0003", first_name: "Hédi", last_name: "Mansour", age: 66, sex: "M", date_of_birth: "1960-05-21",
    bed: "C-18", device_id: "bsu-006", latest_news2: 3, open_alerts: 1, last_vital_at: secondsAgo(20), device_online: true,
    allergies: [], admission_id: "adm-0003",
  },
  {
    ...base, id: "p-0004", first_name: "Lina", last_name: "Bouazizi", age: 38, sex: "F", date_of_birth: "1988-01-30",
    bed: "C-15", device_id: "bsu-003", latest_news2: 2, open_alerts: 0, last_vital_at: secondsAgo(15), device_online: true,
    allergies: ["ibuprofen"], history: "Type 2 diabetes, asthma", admission_id: "adm-0004",
  },
  {
    ...base, id: "p-0005", first_name: "فاطمة", last_name: "العياري", age: 59, sex: "F", date_of_birth: "1967-07-08",
    bed: "C-17", device_id: "bsu-005", latest_news2: 1, open_alerts: 0, last_vital_at: secondsAgo(9), device_online: true,
    allergies: [], admission_id: "adm-0005",
  },
  {
    ...base, id: "p-0006", first_name: "Sami", last_name: "Gharbi", age: 61, sex: "M", date_of_birth: "1965-09-02",
    bed: "C-14", device_id: "bsu-002", latest_news2: 0, open_alerts: 0, last_vital_at: secondsAgo(360), device_online: false,
    allergies: [], admission_id: "adm-0006",
  },
  {
    ...base, id: "p-0007", first_name: "Youssef", last_name: "Khelifi", age: 49, sex: "M", date_of_birth: "1977-04-17",
    bed: "C-11", device_id: "bsu-008", latest_news2: 0, open_alerts: 0, last_vital_at: secondsAgo(5), device_online: true,
    allergies: [], admission_id: "adm-0007", attending_doctor_id: null, attending_doctor_name: null,
  },
];

/** Beds and devices (Ward Admin.dc.html `DEVICES`). */
export const DEVICES: Device[] = [
  { id: "bsu-001", online: true, fw_version: "v0.4.2", last_seen: secondsAgo(2), patient_id: "p-0001", bed: "C-12", patient_name: "Amira Ben Salah" },
  { id: "bsu-002", online: false, fw_version: "v0.4.2", last_seen: at(TODAY, "09:06"), patient_id: "p-0006", bed: "C-14", patient_name: "Sami Gharbi" },
  { id: "bsu-003", online: true, fw_version: "v0.4.2", last_seen: secondsAgo(3), patient_id: "p-0004", bed: "C-15", patient_name: "Lina Bouazizi" },
  { id: "bsu-004", online: true, fw_version: "v0.4.2", last_seen: secondsAgo(1), patient_id: "p-0002", bed: "C-16", patient_name: "Omar Jaziri" },
  { id: "bsu-005", online: true, fw_version: "v0.4.2", last_seen: secondsAgo(4), patient_id: "p-0005", bed: "C-17", patient_name: "فاطمة العياري" },
  { id: "bsu-006", online: true, fw_version: "v0.3.9", last_seen: secondsAgo(2), patient_id: "p-0003", bed: "C-18", patient_name: "Hédi Mansour" },
  { id: "bsu-007", online: true, fw_version: "v0.4.2", last_seen: secondsAgo(5), patient_id: null, bed: "C-13", patient_name: null },
  { id: "bsu-008", online: true, fw_version: "v0.4.2", last_seen: secondsAgo(3), patient_id: "p-0007", bed: "C-11", patient_name: "Youssef Khelifi" },
];

/** Bed order on the nurse ward board (Ward Nurse.dc.html `BEDS`). */
export const BOARD_BED_ORDER = ["C-16", "C-12", "C-18", "C-15", "C-17", "C-11", "C-14", "C-13"];
