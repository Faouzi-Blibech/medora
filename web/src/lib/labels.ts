// UI-only labels and colours derived from API values (not stored in fixtures).
// Words are translated: helpers take the caller's `t` (from useT() or getT()).
import type { Key, TFn } from "@/i18n/messages";
import type { News2Word } from "./news2";
import type { AiSource, Urgency } from "./types";

/** Design: "AI suggestion · Model" / "AI suggestion · Rules fallback". */
export function aiSourceLabel(source: AiSource, t: TFn): string {
  return t(source === "rules" ? "shared.aiRulesFallback" : "shared.aiModel");
}

/** The translated word for an urgency level (`URGENCY[u].word` is the English design word). */
export function urgencyWord(u: Urgency, t: TFn): string {
  return t(`shared.urgency${u}`);
}

/** The translated word for a NEWS2 level (`level(score).word`). */
export function news2Word(word: News2Word, t: TFn): string {
  return t(`shared.news2${word}`);
}

export interface UrgencyLevel {
  word: "Very urgent" | "Urgent" | "Soon" | "Routine" | "Non-urgent";
  bg: string;
  fg: string;
  edge: string;
}

/** The waitlist's `WL_U` (Waitlist.dc.html). */
export const URGENCY: Record<Urgency, UrgencyLevel> = {
  5: { word: "Very urgent", bg: "#F7DCDF", fg: "#8A1C2B", edge: "#B4232F" },
  4: { word: "Urgent", bg: "#FBE3D6", fg: "#8F3412", edge: "#D2602A" },
  3: { word: "Soon", bg: "#FAEFD6", fg: "#6E4B00", edge: "#C7900F" },
  2: { word: "Routine", bg: "#E1F3E7", fg: "#1B6B3F", edge: "#0B8A96" },
  1: { word: "Non-urgent", bg: "#E8EEF0", fg: "#33454F", edge: "#8597A1" },
};

/** Admin dashboard bar colours (`UC` in Ward Admin.dc.html). */
export const URGENCY_BAR: Record<Urgency, string> = {
  5: "#B4232F",
  4: "#D2602A",
  3: "#C7900F",
  2: "#0B8A96",
  1: "#A4B3BB",
};

const DEPT_KEYS: Record<string, Key> = {
  Cardiology: "shared.deptCardiology",
  Laboratory: "shared.deptLaboratory",
  Imaging: "shared.deptImaging",
  Pediatrics: "shared.deptPediatrics",
  Pulmonology: "shared.deptPulmonology",
  "Internal Medicine": "shared.deptInternalMedicine",
  Report: "shared.deptReport",
};

/** A department or specialty name in the interface language; unknown names are shown as written. */
export function deptLabel(name: string | null | undefined, t: TFn): string {
  if (!name) return "";
  const key = DEPT_KEYS[name];
  return key ? t(key) : name;
}

const EXAM_CODES = new Set([
  "ecg", "echo", "troponin", "cbc", "crp", "d_dimer", "inr", "hba1c", "creatinine", "chest_xray", "xray", "xray_outside", "brain_ct", "leg_doppler",
]);

/** A catalogue exam (`rules/exam_bundles.v1.json`) by code; unknown codes keep the API label. */
export function examLabel(exam: { code: string; label: string }, t: TFn): string {
  return exam.code !== "xray_outside" && EXAM_CODES.has(exam.code) ? t(`shared.exam_${exam.code}` as Key) : exam.label;
}

/** Message keys for triage `red_flags` codes. */
export const RED_FLAG_LABELS: Record<string, Key> = {
  chest_pain: "shared.flagChestPain",
  short_of_breath: "shared.flagShortOfBreath",
  exertional_chest_pain: "shared.flagExertionalChestPain",
  infant_fever: "shared.flagInfantFever",
  cough_over_3_weeks: "shared.flagCoughOver3Weeks",
};

export function redFlagLabel(code: string, t: TFn): string {
  const key = RED_FLAG_LABELS[code];
  return key ? t(key) : code.replace(/_/g, " ");
}

/** Waitlist language column: "FR", "AR", "Darija". */
export const LANG_LABELS: Record<string, string> = {
  fr: "FR",
  ar: "AR",
  "aeb-Latn": "Darija",
  en: "EN",
};

/** Design: no-show ≥ 30 % "likely to miss", ≥ 15 % "medium", else "low". */
export function noShowWord(prob: number | null | undefined, t: TFn): string {
  const pct = Math.round((prob ?? 0) * 100);
  return t(pct >= 30 ? "shared.noShowLikely" : pct >= 15 ? "shared.noShowMedium" : "shared.noShowLow");
}

export interface ClinicDoctor {
  id: string;
  name: string;
  specialty: string;
}

/**
 * Mock mode only: which doctor a waitlist row books, by the request's specialty (ids from the
 * mock STAFF fixture; u-0005 is the patient login in the backend seed, so these use u-0010+).
 * Real mode resolves the doctor from GET /me or GET /staff (components/Waitlist.tsx).
 */
export const SPECIALTY_DOCTORS: Record<string, ClinicDoctor> = {
  Cardiology: { id: "u-0001", name: "Dr Trabelsi", specialty: "Cardiology" },
  Pediatrics: { id: "u-0010", name: "Dr Ben Romdhane", specialty: "Pediatrics" },
  Pulmonology: { id: "u-0011", name: "Dr Karoui", specialty: "Pulmonology" },
};

/** The doctor for a specialty; falls back to the doctor with `fallbackId`, then Cardiology. */
export function doctorForSpecialty(specialty: string | null | undefined, fallbackId?: string): ClinicDoctor {
  const bySpecialty = specialty ? SPECIALTY_DOCTORS[specialty] : undefined;
  if (bySpecialty) return bySpecialty;
  return Object.values(SPECIALTY_DOCTORS).find((d) => d.id === fallbackId) ?? SPECIALTY_DOCTORS.Cardiology;
}
