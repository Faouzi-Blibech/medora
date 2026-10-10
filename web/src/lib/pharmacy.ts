// Pure pharmacy rules shared by the screens and the mocks (no React, no I/O): severity order, the
// worklist order, what "running" means, the doctor's list, check texts and decision validation.
import type { Key, TFn } from "@/i18n/messages";
import type {
  Check,
  CheckCode,
  CheckSeverity,
  Drug,
  Prescription,
  PrescriptionStatus,
  ReviewDecision,
  WorklistItem,
} from "./types";

export const SEVERITY_RANK: Record<CheckSeverity, number> = { critical: 3, major: 2, moderate: 1, info: 0 };
const rank = (s: CheckSeverity | null | undefined): number => (s ? SEVERITY_RANK[s] : -1);

export const SEVERITY_KEY: Record<CheckSeverity, Key> = {
  critical: "pharmacy.sevCritical",
  major: "pharmacy.sevMajor",
  moderate: "pharmacy.sevModerate",
  info: "pharmacy.sevInfo",
};

export const STATUS_KEY: Record<PrescriptionStatus, Key> = {
  pending_pharmacy: "pharmacy.statusPending",
  validated: "pharmacy.statusValidated",
  changes_requested: "pharmacy.statusChanges",
  rejected: "pharmacy.statusRejected",
  stopped: "pharmacy.statusStopped",
  superseded: "pharmacy.statusSuperseded",
};

export const DECISION_KEY: Record<ReviewDecision, Key> = {
  validated: "pharmacy.statusValidated",
  changes_requested: "pharmacy.statusChanges",
  rejected: "pharmacy.statusRejected",
};

/** Request-changes and reject comments: 1–500 characters (spec §5), counted in code points like the server. */
export const COMMENT_MAX = 500;
/** The doctor's override reason (Contract decisions §15). */
export const OVERRIDE_MAX = 500;

export function maxSeverity(checks: readonly Check[]): CheckSeverity | null {
  return checks.reduce<CheckSeverity | null>((m, c) => (rank(c.severity) > rank(m) ? c.severity : m), null);
}

/** Most severe first, then by item. */
export function sortChecks(checks: readonly Check[]): Check[] {
  return [...checks].sort(
    (a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity] || (a.item_index ?? -1) - (b.item_index ?? -1),
  );
}

export function hasCritical(checks: readonly Check[] | null | undefined): boolean {
  return !!checks?.some((c) => c.severity === "critical");
}

/** Spec §2: urgent first, then the highest severity, then the oldest. Stable for equal rows. */
export function sortWorklist(items: readonly WorklistItem[]): WorklistItem[] {
  return items
    .map((it, i) => ({ it, i }))
    .sort(
      (a, b) =>
        Number(b.it.urgent) - Number(a.it.urgent) ||
        rank(b.it.max_severity) - rank(a.it.max_severity) ||
        Date.parse(a.it.waiting_since) - Date.parse(b.it.waiting_since) ||
        a.i - b.i,
    )
    .map(({ it }) => it);
}

/** The status, falling back to the pre-1.12 `active` flag when a server sends none. */
export function statusOf(rx: Pick<Prescription, "status" | "active">): PrescriptionStatus {
  return rx.status ?? (rx.active ? "validated" : "stopped");
}

/** Doses go out (spec §3 `active`): validated, or pending with the urgent bypass. */
export function isRunning(rx: Pick<Prescription, "status" | "active" | "urgent">): boolean {
  const s = statusOf(rx);
  return s === "validated" || (s === "pending_pharmacy" && !!rx.urgent);
}

/** Doses are already going out but the pharmacist hasn't reviewed it yet. */
export function isPendingUrgent(rx: Pick<Prescription, "status" | "active" | "urgent"> | null | undefined): boolean {
  return !!rx && statusOf(rx) === "pending_pharmacy" && !!rx.urgent;
}

const DOCTOR_ORDER: Partial<Record<PrescriptionStatus, number>> = {
  changes_requested: 0,
  pending_pharmacy: 1,
  validated: 2,
  rejected: 3,
};

/**
 * The doctor's list: no stopped or superseded rows; a version that was sent back and then resubmitted
 * hides behind its successor. Needs-action first (changes requested, pending), then running, then rejected.
 */
export function doctorRows(list: readonly Prescription[]): Prescription[] {
  const replaced = new Set(list.map((r) => r.replaces_id).filter((x): x is string => !!x));
  return list
    .filter((r) => DOCTOR_ORDER[statusOf(r)] !== undefined && (isRunning(r) || !replaced.has(r.id)))
    .sort(
      (a, b) =>
        (DOCTOR_ORDER[statusOf(a)] ?? 9) - (DOCTOR_ORDER[statusOf(b)] ?? 9) ||
        Date.parse(b.created_at) - Date.parse(a.created_at),
    );
}

/** A pending version that will replace `rx` once validated (the doctor can't edit `rx` meanwhile). */
export function pendingSuccessor(rx: Prescription, list: readonly Prescription[]): Prescription | undefined {
  return list.find((r) => r.replaces_id === rx.id && statusOf(r) === "pending_pharmacy");
}

/** "Amoxicillin 1 g": the `med` display string written for a formulary pick. */
export const drugLabel = (d: Pick<Drug, "dci" | "strength">): string => `${d.dci} ${d.strength}`;

const CHECK_TEXT: Record<CheckCode, { key: Key; params: readonly string[] }> = {
  allergy: { key: "pharmacy.chkAllergy", params: ["allergy", "class"] },
  interaction: { key: "pharmacy.chkInteraction", params: ["with_med", "group_a", "group_b"] },
  max_daily_dose: { key: "pharmacy.chkMaxDailyDose", params: ["daily_mg", "max_daily_mg"] },
  duplicate_therapy: { key: "pharmacy.chkDuplicate", params: ["with_med"] },
  non_formulary: { key: "pharmacy.chkNonFormulary", params: [] },
  high_alert: { key: "pharmacy.chkHighAlert", params: [] },
  elderly: { key: "pharmacy.chkElderly", params: ["age"] },
};

/** Plain-language text in the UI language; the server's English `message` when the code or a param is unknown. */
export function checkText(c: Check, t: TFn): string {
  const spec = (CHECK_TEXT as Partial<Record<string, { key: Key; params: readonly string[] }>>)[c.code];
  if (!spec) return c.message;
  const raw = c.params ?? {};
  // The backend sends the interaction's two groups as `groups: [a, b]`; the sentence reads them as group_a/group_b.
  const groups = Array.isArray(raw.groups) ? raw.groups : [];
  const src: Record<string, string | number | null | undefined> = { ...(raw as Record<string, never>), group_a: groups[0], group_b: groups[1] };
  const vars: Record<string, string | number> = {};
  for (const p of spec.params) {
    const v = src[p];
    if (v === undefined || v === null || v === "") return c.message;
    vars[p] = v;
  }
  return t(spec.key, vars);
}

export type Decision = "validate" | "request_changes" | "reject";
export type DecisionProblem = "ack_required" | "comment_required" | "comment_too_long";

/**
 * Client-side mirror of the decision rules (spec §2, §5): Validate needs the "warnings reviewed" tick when
 * there are checks; Request changes and Reject need a 1–500 character comment. null = the action may go.
 */
export function decisionProblem(
  d: { decision: Decision; acknowledged: boolean; comment: string },
  hasChecks: boolean,
): DecisionProblem | null {
  const length = [...d.comment.trim()].length;
  if (d.decision === "validate") {
    if (hasChecks && !d.acknowledged) return "ack_required";
    return length > COMMENT_MAX ? "comment_too_long" : null;
  }
  if (length === 0) return "comment_required";
  return length > COMMENT_MAX ? "comment_too_long" : null;
}
