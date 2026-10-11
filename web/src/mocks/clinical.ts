// Prescriptions, doses, notes and the AI daily summary. Synthetic, from the design scripts.
import type { AiSummary, Dose, DoseStatus, Note, Prescription } from "@/lib/types";
import { drugIdFor } from "./pharmacy";
import { at, nowIso, SUN, TODAY } from "./time";

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

let doseSeq = 0;
function dose(
  prescription_id: string,
  patient_id: string,
  date: string,
  time: string,
  med: string,
  slot: number | null,
  status: DoseStatus,
  extra: Partial<Dose> = {},
): Dose {
  doseSeq += 1;
  return {
    id: `d-${String(doseSeq).padStart(6, "0")}`,
    prescription_id,
    patient_id,
    scheduled_at: at(date, time),
    time_of_day: time,
    meds: [med],
    slot,
    status,
    taken_method: null,
    updated_at: at(date, time),
    taken_at: null,
    given_by: null,
    given_by_name: null,
    instructions: null,
    ...extra,
  };
}

const taken = (date: string, hhmm: string, method: "ir" | "button" | null = "ir"): Partial<Dose> => ({
  taken_method: method,
  taken_at: at(date, hhmm),
  updated_at: at(date, hhmm),
});

/** Ordered by scheduled time. Amira's last 24 h (doctor timeline) + today's ward med round. */
export const DOSES: Dose[] = [
  // Amira — Sun
  dose("rx-0002", "p-0001", SUN, "14:00", "Amoxicillin 1g", 2, "missed", { updated_at: at(SUN, "14:30") }),
  dose("rx-0001", "p-0001", SUN, "20:00", "Paracetamol 500mg", 1, "taken", taken(SUN, "20:06")),
  dose("rx-0003", "p-0001", SUN, "20:00", "Warfarin 5mg", 3, "taken", taken(SUN, "20:06")),
  // Amira — today
  dose("rx-0001", "p-0001", TODAY, "08:00", "Paracetamol 500mg", 1, "taken", taken(TODAY, "08:03")),
  dose("rx-0004", "p-0001", TODAY, "08:00", "Aspirin 100mg", null, "taken", {
    ...taken(TODAY, "08:20", null),
    given_by: "u-0002",
    given_by_name: "Nurse Ines",
    instructions: "Give by hand",
  }),
  dose("rx-0002", "p-0001", TODAY, "14:00", "Amoxicillin 1g", 2, "scheduled"),
  dose("rx-0001", "p-0001", TODAY, "20:00", "Paracetamol 500mg", 1, "scheduled"),
  dose("rx-0003", "p-0001", TODAY, "20:00", "Warfarin 5mg", 3, "scheduled"),
  // Omar — today
  dose("rx-0005", "p-0002", TODAY, "08:00", "Bisoprolol 2.5mg", 1, "missed", { updated_at: at(TODAY, "08:30") }),
  dose("rx-0006", "p-0002", TODAY, "10:00", "Furosemide 40mg", null, "scheduled", { instructions: "Give by hand" }),
  dose("rx-0007", "p-0002", TODAY, "20:00", "Enoxaparin 40mg", null, "scheduled", { instructions: "Injection" }),
  // Hédi — today
  dose("rx-0008", "p-0003", TODAY, "08:00", "Ramipril 5mg", 1, "missed", { updated_at: at(TODAY, "08:30") }),
  dose("rx-0009", "p-0003", TODAY, "10:00", "Furosemide 20mg", 2, "scheduled", { instructions: "Dispense from unit" }),
  // Lina — today
  dose("rx-0010", "p-0004", TODAY, "09:00", "Metformin 500mg", 1, "dispensed", { updated_at: at(TODAY, "09:00") }),
  dose("rx-0011", "p-0004", TODAY, "10:00", "Salbutamol inhaler", null, "scheduled", { instructions: "2 puffs" }),
  // Omar — urgent ibuprofen (rx-0013), started before the pharmacist's review
  dose("rx-0013", "p-0002", TODAY, "20:00", "Ibuprofen 400 mg", null, "scheduled", { instructions: "Give by hand" }),
];

let noteSeq = 0;
function note(patient_id: string, author_id: string, author_name: string, role: Note["author_role"], created_at: string, text: string) {
  noteSeq += 1;
  return { patient_id, note: { id: `n-${String(noteSeq).padStart(4, "0")}`, author_id, author_role: role, author_name, text, created_at } };
}

/** Per patient, newest first. */
export const NOTES: Record<string, Note[]> = {};
for (const { patient_id, note: n } of [
  note("p-0001", "u-0002", "Nurse Ines", "nurse", at(TODAY, "08:40"), "Mild breathlessness on exertion. O2 2 L/min started per ward protocol; SpO2 94% after 10 min."),
  note("p-0001", "u-0004", "Nurse Sami", "nurse", at(TODAY, "03:15"), "SpO2 à 93 % pendant le sommeil, patiente repositionnée. Reste calme, pas de douleur."),
  note("p-0001", "u-0001", "Dr Trabelsi", "doctor", at(SUN, "17:30"), "INR 2.4 this morning. Continue warfarin 5 mg. Recheck INR Wednesday."),
  note("p-0002", "u-0002", "Nurse Ines", "nurse", at(TODAY, "09:05"), "Patient drowsy but responds to voice. O2 increased to 4 L/min. Family informed."),
  note("p-0002", "u-0004", "Nurse Sami", "nurse", at(SUN, "23:40"), "Toux productive, mange peu. Hydratation encouragée."),
  note("p-0002", "u-0001", "Dr Trabelsi", "doctor", at(SUN, "18:10"), "Suspected chest infection. Chest X-ray requested. Monitor SpO2 closely overnight."),
]) {
  (NOTES[patient_id] ??= []).push(n);
}

const INTERACTIONS: AiSummary["interactions"] = [
  { drugs: ["Warfarin", "Aspirin"], severity: "high", note: "Bleeding risk" },
  { drugs: ["Amoxicillin", "penicillin allergy"], severity: "high", note: "Same drug family — allergic reaction risk" },
  { drugs: ["Paracetamol", "Warfarin"], severity: "medium", note: "Regular use can raise INR" },
];

/** Daily summaries (doctor patient detail). `model` = normal, `rules` = AI unavailable (`?ai=rules`). */
export const SUMMARIES: Record<string, { model: AiSummary; rules: AiSummary }> = {
  "p-0001": {
    model: {
      summary:
        "Last 24 h: HR 72–118 (latest 96), SpO2 93–97%, temperature peaked at 38.1 °C at 21:00. Max NEWS2 5. SpO2 trending down about 0.4%/h since 03:00. One missed dose: Amoxicillin at 14:00 yesterday.",
      interactions: INTERACTIONS,
      source: "model",
      generated_at: nowIso(),
      human_confirmed_by: null,
      human_confirmed_by_name: null,
      reviewed_at: null,
      based_on: { vitals: 48, doses: 6, notes: 3 },
    },
    rules: {
      summary: "HR 72–118 (latest 96). SpO2 93–97%. Max NEWS2 5. 1 missed dose (14:00).",
      interactions: INTERACTIONS,
      source: "rules",
      generated_at: nowIso(),
      human_confirmed_by: null,
      human_confirmed_by_name: null,
      reviewed_at: null,
      based_on: { vitals: 48, doses: 6, notes: 3 },
    },
  },
};
