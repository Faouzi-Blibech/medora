// Pure pharmacy rules shared by the screens and the mocks (no React, no I/O): severity order, the
// worklist order, what "running" means, the doctor's list, check texts and decision validation.
import type { Lang } from "@/i18n/config";
import type { Key, TFn } from "@/i18n/messages";
import type {
  Check,
  CheckCode,
  CheckSeverity,
  Drug,
  DrugForm,
  Prescription,
  PrescriptionStatus,
  ReviewDecision,
  RoundDose,
  StockLot,
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
  dose_unverified: { key: "pharmacy.chkDoseUnverified", params: [] },
};

/** Plain-language text in the UI language; the server's English `message` when the code or a param is unknown. */
export function checkText(c: Check, t: TFn): string {
  const base = (CHECK_TEXT as Partial<Record<string, { key: Key; params: readonly string[] }>>)[c.code];
  if (!base) return c.message;
  // A moderate allergy is a cross-reactivity (e.g. penicillin and cephalosporins), not a declared allergy.
  const spec = c.code === "allergy" && c.severity === "moderate" ? { ...base, key: "pharmacy.chkAllergyCross" as Key } : base;
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

export const DRUG_FORMS: DrugForm[] = ["tablet", "capsule", "syrup", "injection", "inhaler", "patch", "drops", "other"];

export const FORM_KEY: Record<DrugForm, Key> = {
  tablet: "pharmacy.formTablet",
  capsule: "pharmacy.formCapsule",
  syrup: "pharmacy.formSyrup",
  injection: "pharmacy.formInjection",
  inhaler: "pharmacy.formInhaler",
  patch: "pharmacy.formPatch",
  drops: "pharmacy.formDrops",
  other: "pharmacy.formOther",
};

/** Joins a list of names with the language's comma: "،" in Arabic, "," elsewhere. */
export function joinList(items: readonly string[], lang: Lang): string {
  return items.join(lang === "ar" ? "، " : ", ");
}

// ── Phase B: stock, FEFO and rounds (backend plan Contract decisions 25, 26) ──

export const EXPIRING_DAYS = 30;
export type ExpiryState = "expired" | "expiring" | "ok";
/** The lot fields the rules need (server lots and mock lots alike). */
export type LotLike = Pick<StockLot, "id" | "expiry_date" | "quantity" | "received_at">;

/** Whole days from `from` to `to` (both YYYY-MM-DD). */
export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}

/** Expired before `today`; expiring within 30 days, today included; else ok. Dates are Tunis YYYY-MM-DD. */
export function expiryState(expiry: string, today: string): ExpiryState {
  const left = daysBetween(today, expiry);
  return left < 0 ? "expired" : left <= EXPIRING_DAYS ? "expiring" : "ok";
}

/** Lots usable on `date` (stock left, not expired that day), first-expiring first; ties: oldest receipt, then id. */
export function fefoLots<L extends LotLike>(lots: readonly L[], date: string): L[] {
  return lots
    .filter((l) => l.quantity > 0 && expiryState(l.expiry_date, date) !== "expired")
    .sort(
      (a, b) =>
        a.expiry_date.localeCompare(b.expiry_date) ||
        Date.parse(a.received_at) - Date.parse(b.received_at) ||
        a.id.localeCompare(b.id),
    );
}

/** A StockItem's numbers for one drug's lots: on_hand leaves out expired lots (used by the mocks). */
export function stockFlags(
  lots: readonly LotLike[],
  minStock: number,
  today: string,
): { on_hand: number; low: boolean; expiring: boolean; expired: boolean } {
  const withStock = lots.filter((l) => l.quantity > 0);
  const usable = withStock.filter((l) => expiryState(l.expiry_date, today) !== "expired");
  const on_hand = usable.reduce((n, l) => n + l.quantity, 0);
  return {
    on_hand,
    low: on_hand < minStock,
    expiring: usable.some((l) => expiryState(l.expiry_date, today) === "expiring"),
    expired: withStock.some((l) => expiryState(l.expiry_date, today) === "expired"),
  };
}

/** Spec §5: 2 × min_stock − on_hand. */
export const reorderQuantity = (minStock: number, onHand: number): number => Math.max(0, 2 * minStock - onHand);

/**
 * The server's FEFO for a whole round, simulated before sending: every formulary line takes ONE lot. The lot is
 * the one the pharmacist chose, or else the first-expiring usable lot that still holds the whole line after the
 * lines before it. Returns dose id → lot id, or null when no lot can serve the line (shown as a shortage).
 */
export function planLots(
  doses: readonly RoundDose[],
  lotsByDrug: ReadonlyMap<string, readonly LotLike[]>,
  date: string,
  chosen: Readonly<Record<string, string>> = {},
): Map<string, string | null> {
  const left = new Map<string, number>(); // lot id → units not yet planned
  const plan = new Map<string, string | null>();
  for (const d of doses) {
    if (!d.drug_id || d.dispensed) continue;
    const lots = fefoLots(lotsByDrug.get(d.drug_id) ?? [], date);
    const room = (l: LotLike) => left.get(l.id) ?? l.quantity;
    const want = chosen[d.dose_id];
    const pick = want ? lots.find((l) => l.id === want && room(l) >= d.quantity) : lots.find((l) => room(l) >= d.quantity);
    plan.set(d.dose_id, pick?.id ?? null);
    if (pick) left.set(pick.id, room(pick) - d.quantity);
  }
  return plan;
}

/** Round times offered by the dispensing page: every hour. */
export const ROUND_TIMES: string[] = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, "0")}:00`);

/** The first round at or after `hhmm` ("09:12" → "10:00"); after 23:00, "23:00". */
export function nextRound(hhmm: string): string {
  return ROUND_TIMES.find((r) => r >= hhmm) ?? ROUND_TIMES[ROUND_TIMES.length - 1];
}
