// Accounts-and-access fixtures. Synthetic. Magic codes let a reviewer exercise every error path.
import type { DoctorRef, PatientAccessGrant, PendingUser, UserAdmin } from "@/lib/types";
import { at, TODAY } from "./time";

/** Codes the mock API understands (anything else is "invalid_code"). */
export const MOCK_CODES = {
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
  { id: "u-0020", name: "Amel Cherif", email: "a.cherif@example.tn", note: "Cardiology", requested_role: "nurse", requested_doctor_id: "u-0001", requested_doctor_name: "Dr Trabelsi", status: "pending", created_at: at(TODAY, "08:20") },
  { id: "u-0021", name: "Karim Zouari", email: "k.zouari@example.tn", note: "Pulmonology", requested_role: "doctor", requested_doctor_id: null, requested_doctor_name: null, status: "pending", created_at: at(TODAY, "07:55") },
  { id: "u-0022", name: "Salma Hadded", email: "s.hadded@example.tn", note: null, requested_role: "patient", requested_doctor_id: "u-0010", requested_doctor_name: "Dr Ben Romdhane", status: "pending", created_at: at(TODAY, "07:10") },
  { id: "u-0024", name: "Rim Jebali", email: "r.jebali@example.tn", note: "Pharmacie", requested_role: "pharmacist", requested_doctor_id: null, requested_doctor_name: null, status: "pending", created_at: at(TODAY, "08:05") },
  { id: "u-0023", name: "Test Person", email: "t.person@example.tn", note: "assistant", requested_role: "nurse", requested_doctor_id: "u-0001", requested_doctor_name: "Dr Trabelsi", status: "rejected", created_at: at("2026-10-03", "16:00") },
];

/** Dr Trabelsi's team (consistent with STAFF: Ines active, Sami disabled). */
export const TEAM: UserAdmin[] = [
  { id: "u-0002", name: "Nurse Ines", email: "i.mejri@hr-medora.tn", role: "nurse", status: "active", ward: "Cardiology", supervisor_id: "u-0001", requested_role: null, requested_doctor_id: null },
  { id: "u-0004", name: "Nurse Sami", email: "s.dridi@hr-medora.tn", role: "nurse", status: "disabled", ward: "Cardiology", supervisor_id: "u-0001", requested_role: null, requested_doctor_id: null },
];

export const GRANTS: Record<string, PatientAccessGrant[]> = {
  "p-0002": [{ patient_id: "p-0002", doctor_id: "u-0011", doctor_name: "Dr Karoui", expires_at: at("2026-11-04", "23:59") }],
};
