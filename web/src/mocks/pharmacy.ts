// Pharmacy fixtures and the mock check engine. Synthetic and illustrative, not a clinical reference.
// The engine follows spec §4 closely enough for the demo; the backend's rule files are the authority.
import { fefoLots, isRunning, SEVERITY_RANK } from "@/lib/pharmacy";
import { tunisDate } from "@/lib/time";
import type { Check, CheckRequest, CheckSeverity, Dispensation, DispensationLine, Dose, Drug, Patient, Prescription, PrescriptionItem, PrescriptionReview, StockLot } from "@/lib/types";
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
  "beta-lactam": "beta_lactam", "bêta-lactamine": "beta_lactam", beta_lactam: "beta_lactam",
};
const ELDERLY_CAUTION = new Set(["diazepam", "ibuprofen"]);

const norm = (s: string) => s.trim().toLowerCase();
const allergyClass = (a: string) => ALLERGY_SYNONYMS[norm(a)] ?? norm(a);

/** Spec §4, simplified. Pairs are reported only when at least one side is a candidate item. */
export function mockChecks(
  patient: { age: number | null; allergies: string[] },
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
      if (hit) add({ code: "allergy", severity: "critical", item_index: i, drug_id: d.id, params: { med: it.med, allergy: hit, class: cls } }, `Allergy: ${hit} (${cls})`);
    }
    const perIntake = it.dose_mg ?? (d.unit_mg != null ? (it.units_per_intake ?? 1) * d.unit_mg : null);
    if (perIntake != null && d.max_daily_mg != null) {
      const daily = perIntake * it.times.length;
      if (daily > d.max_daily_mg)
        add(
          { code: "max_daily_dose", severity: daily > 2 * d.max_daily_mg ? "critical" : "major", item_index: i, drug_id: d.id, params: { med: it.med, daily_mg: daily, max_daily_mg: d.max_daily_mg } },
          `Daily dose ${daily} mg > max ${d.max_daily_mg} mg`,
        );
    }
    const others = [...runningItems, ...items.slice(i + 1).map((x) => ({ it: x, drug: drugOf(x) }))];
    for (const o of others) {
      if (!o.drug) continue;
      const sameDci = o.drug.dci === d.dci;
      // An empty (or short) ATC code never matches: the catalogue allows drugs without one.
      const sameClass = d.atc_code.length >= 5 && o.drug.atc_code.slice(0, 5) === d.atc_code.slice(0, 5);
      if (sameDci || sameClass)
        add(
          { code: "duplicate_therapy", severity: "major", item_index: i, drug_id: d.id, params: { med: it.med, reason: sameDci ? "same_dci" : "same_atc_class", with_med: o.it.med } },
          `Duplicate therapy with ${o.it.med}`,
        );
      for (const [a, b, severity] of INTERACTIONS) {
        const hit =
          (d.interaction_groups.includes(a) && o.drug.interaction_groups.includes(b)) ||
          (d.interaction_groups.includes(b) && o.drug.interaction_groups.includes(a));
        if (hit) add({ code: "interaction", severity, item_index: i, drug_id: d.id, params: { med: it.med, groups: [a, b], with_med: o.it.med } }, `Interaction with ${o.it.med} (${a} + ${b})`);
      }
    }
    if (d.high_alert) add({ code: "high_alert", severity: "info", item_index: i, drug_id: d.id, params: { med: it.med } }, `${d.dci} is a high-alert drug`);
    if (patient.age != null && patient.age >= 75 && ELDERLY_CAUTION.has(norm(d.dci)))
      add({ code: "elderly", severity: "moderate", item_index: i, drug_id: d.id, params: { med: it.med, age: patient.age } }, `Elderly caution (${patient.age})`);
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

/** A lot as the mock stores it; `expired`/`expiring` are computed when read. */
export type MockLot = Omit<StockLot, "expired" | "expiring">;

const RECEIVED = at("2026-09-01", "09:00");
const mockLot = (n: number, drug_id: string, lot_number: string, expiry_date: string, quantity: number): MockLot => ({
  id: `lot-${String(n).padStart(4, "0")}`,
  drug_id,
  lot_number,
  expiry_date,
  quantity,
  received_at: RECEIVED,
});

/**
 * One lot for every formulary drug, plus the spec §7 demo cases: Enoxaparin under min_stock (6 < 20), an
 * Amoxicillin 1 g lot expiring in 10 days (FEFO serves it first), and an expired Paracetamol 500 mg lot.
 */
export const LOTS: MockLot[] = [
  ...FORMULARY.map((d, i) => mockLot(i + 1, d.id, `L26-${String(i + 1).padStart(3, "0")}`, "2027-06-30", d.id === "d-0009" ? 6 : 200)),
  mockLot(FORMULARY.length + 1, "d-0003", "L26-003B", "2026-10-15", 30),
  mockLot(FORMULARY.length + 2, "d-0001", "L25-001X", "2026-09-30", 40),
];

/**
 * The 10:00 Cardiology round, already sent at 07:45 (the nurse's "Confirm receipt" demo). The 20:00 round is
 * left for the pharmacist's demo (spec §7, step 6). Marks those doses `pharmacy: "sent"`.
 */
export function seedDispensations(doses: Dose[], prescriptions: Prescription[], patients: Patient[], lots: MockLot[]): Dispensation[] {
  const id = "disp-0001";
  const lines: DispensationLine[] = doses
    .filter((d) => d.time_of_day === "10:00" && tunisDate(d.scheduled_at) === TODAY)
    .map((d, i) => {
      const rx = prescriptions.find((r) => r.id === d.prescription_id);
      const item = rx?.items.find((x) => x.med === d.meds[0]) ?? rx?.items[0];
      const drugId = item?.drug_id ?? null;
      const lot = drugId ? (fefoLots(lots.filter((l) => l.drug_id === drugId), TODAY)[0] ?? null) : null;
      const p = patients.find((x) => x.id === d.patient_id);
      d.pharmacy = "sent";
      return {
        id: `dl-${String(i + 1).padStart(6, "0")}`,
        dose_id: d.id,
        patient_id: d.patient_id,
        patient_name: p ? `${p.first_name} ${p.last_name}` : null,
        bed: p?.bed ?? null,
        drug_id: drugId,
        lot_id: lot?.id ?? null,
        lot_number: lot?.lot_number ?? null,
        quantity: item?.units_per_intake ?? 1,
        med: d.meds.join(" + "),
      };
    });
  return [
    {
      id,
      ward: "Cardiology",
      round_date: TODAY,
      round_time: "10:00",
      status: "sent",
      prepared_by: USERS.pharmacist.id,
      prepared_by_name: USERS.pharmacist.name,
      prepared_at: at(TODAY, "07:45"),
      received_by: null,
      received_by_name: null,
      received_at: null,
      lines,
    },
  ];
}
