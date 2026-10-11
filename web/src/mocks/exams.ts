// Synthetic exam orders for the single-visit demo (spec 2026-10-09). The ids match the waitlist fixtures.
import type { CatalogueItem, ExamOrder, RadiographAi, RadiographReading } from "@/lib/types";

export const EXAM_CATALOGUE: CatalogueItem[] = [
  { code: "ecg", label: "ECG (12-lead)", department: "Cardiology" },
  { code: "echo", label: "Echocardiography", department: "Cardiology" },
  { code: "troponin", label: "Troponin", department: "Laboratory" },
  { code: "cbc", label: "Complete blood count", department: "Laboratory" },
  { code: "crp", label: "CRP", department: "Laboratory" },
  { code: "chest_xray", label: "Chest X-ray", department: "Imaging" },
  { code: "xray", label: "X-ray (other region)", department: "Imaging" },
];

const rules = (bundle: string) => ({ source: "rules" as const, bundles: [bundle], reason: `Suggested by the exam rules for: ${bundle}` });

export function examFixtures(firstAppointmentId: string, patientId: string, patientName: string): ExamOrder[] {
  const base = { patient_id: patientId, appointment_id: firstAppointmentId, ordered_at: null, done_at: null,
    created_at: "2026-10-09T07:40:00Z", patient_name: patientName, human_confirmed_by: null, results: [] };
  return [
    { ...base, id: "ex-0001", code: "ecg", label: "ECG (12-lead)", department: "Cardiology", status: "suggested", ai_suggested: rules("chest_pain") },
    { ...base, id: "ex-0002", code: "troponin", label: "Troponin", department: "Laboratory", status: "suggested", ai_suggested: rules("chest_pain") },
    { ...base, id: "ex-0003", code: "chest_xray", label: "Chest X-ray", department: "Imaging", status: "suggested", ai_suggested: rules("chest_pain") },
  ];
}

/** A small grey PNG (1x1) standing in for a radiograph in mock mode. */
export const MOCK_RADIOGRAPH_URL =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mO8c+fOfwAIIAN8BnQ0VQAAAABJRU5ErkJggg==";

const DISCLAIMER = "AI draft from a prototype, not a diagnosis and not clinically validated. A doctor must review it.";

const CHEST_AI: RadiographAi = {
  source: "llm", model: "qwen3-vl:4b", region: "thorax", projection: "PA", quality: "adéquate",
  findings: ["Champs pulmonaires clairs, sans foyer ni épanchement.", "Silhouette cardiaque de taille normale.", "Culs-de-sac pleuraux libres."],
  impression: "Pas d'anomalie aiguë visible sur cette radiographie thoracique.",
  possible_conditions: [{ name: "Absence de pathologie cardio-pulmonaire aiguë", likelihood: "high", evidence: "poumons clairs, index cardio-thoracique normal" }],
  urgent_flags: [], recommendation: "",
  draft_text: "Technique : radiographie thoracique de face (PA), qualité adéquate.\nRésultat : champs pulmonaires clairs, silhouette cardiaque de taille normale, culs-de-sac pleuraux libres.\nConclusion : pas d'anomalie aiguë visible.",
  disclaimer: DISCLAIMER,
};

const WRIST_AI: RadiographAi = {
  source: "llm", model: "qwen3-vl:4b", region: "poignet", projection: "face et profil", quality: "correcte",
  findings: ["Solution de continuité de la métaphyse radiale distale.", "Possible déplacement du fragment distal."],
  impression: "Aspect évocateur d'une fracture de l'extrémité distale du radius.",
  possible_conditions: [{ name: "Fracture du radius distal", likelihood: "medium", evidence: "trait de fracture et angulation de la métaphyse" }],
  urgent_flags: ["Fracture déplacée du radius distal possible"],
  recommendation: "Avis orthopédique et immobilisation en attendant.",
  draft_text: "Technique : radiographie du poignet, face et profil, qualité correcte.\nRésultat : solution de continuité de la métaphyse radiale distale avec possible déplacement du fragment distal.\nConclusion : fracture du radius distal à confirmer, avis orthopédique.",
  disclaimer: DISCLAIMER,
};

/** The canned result of a mock reading by result id (used when a queued reading becomes ready). */
export const MOCK_READING_DRAFTS: Record<string, RadiographAi> = { "er-0901": CHEST_AI, "er-0902": WRIST_AI };

export function radiographExamFixtures(patientId: string, patientName: string): ExamOrder[] {
  const base = { patient_id: patientId, appointment_id: null, ordered_at: "2026-10-09T08:00:00Z", done_at: "2026-10-09T09:10:00Z",
    created_at: "2026-10-09T08:00:00Z", patient_name: patientName, ai_suggested: null, human_confirmed_by: "u-0001", department: "Imaging", status: "done" as const };
  const file = { size_bytes: 184_320, report_text: "", uploaded_by_name: "Imaging", created_at: "2026-10-09T09:10:00Z" };
  return [
    { ...base, id: "ex-0004", code: "chest_xray", label: "Chest X-ray",
      results: [{ ...file, id: "er-0901", file_name: "chest_pa_normal.jpg", content_type: "image/jpeg", reading: { id: "rr-0001", status: "ready", confirmed: false } }] },
    { ...base, id: "ex-0005", code: "xray_outside", label: "Outside X-ray — wrist",
      results: [{ ...file, id: "er-0902", file_name: "wrist_outside.jpg", content_type: "image/jpeg", reading: { id: "rr-0002", status: "queued", confirmed: false } }] },
  ];
}

export function readingFixtures(patientId: string): Record<string, RadiographReading> {
  return {
    "er-0901": { id: "rr-0001", exam_result_id: "er-0901", patient_id: patientId, status: "ready", hint: "Chest X-ray", ai_suggested: CHEST_AI,
      final_text: null, human_confirmed_by: null, confirmed_by_name: null, confirmed_at: null, created_at: "2026-10-09T09:10:00Z", finished_at: "2026-10-09T09:10:40Z" },
    "er-0902": { id: "rr-0002", exam_result_id: "er-0902", patient_id: patientId, status: "queued", hint: "Outside X-ray — wrist", ai_suggested: null,
      final_text: null, human_confirmed_by: null, confirmed_by_name: null, confirmed_at: null, created_at: "2026-10-09T09:10:00Z", finished_at: null },
  };
}
