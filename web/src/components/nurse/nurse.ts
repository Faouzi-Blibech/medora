// Nurse view helpers: NEWS2 sub-scores, alert labels, dose statuses and sparklines.
// UI-derived values only (computed from the contract records, never stored in fixtures).
import type { Key, TFn } from "@/i18n/messages";
import { isPendingUrgent } from "@/lib/pharmacy";
import { tunisTime, USE_MOCKS } from "@/lib/time";
import type { Alert, AlertKind, Dose, Prescription, WardBed } from "@/lib/types";

/** The signed-in nurse in the mock demo (Nurse Ines). Real mode names the user from GET /me; the real API takes the actor from the JWT. */
export const NURSE_ID = "u-0002";
export const NURSE_NAME = "Nurse Ines";
/**
 * The ward named on nurse screens: the design's "Ward C" in mock mode; in real mode the
 * ward from the data (the patients' `ward`, e.g. "Cardiology"), or null when the data has none.
 */
export function wardLabel(t: TFn, wards: (string | null | undefined)[] = []): string | null {
  if (USE_MOCKS) return t("nurse.wardC");
  return wards.find((w): w is string => !!w) ?? null;
}

// ── NEWS2 component scores (RCP NEWS2, SpO2 scale 1) ─────────────────────────

export function hrPoints(v: number): number {
  if (v <= 40) return 3;
  if (v <= 50) return 1;
  if (v <= 90) return 0;
  if (v <= 110) return 1;
  if (v <= 130) return 2;
  return 3;
}

export function spo2Points(v: number): number {
  if (v <= 91) return 3;
  if (v <= 93) return 2;
  if (v <= 95) return 1;
  return 0;
}

export function tempPoints(v: number): number {
  if (v <= 35.0) return 3;
  if (v <= 36.0) return 1;
  if (v <= 38.0) return 0;
  if (v <= 39.0) return 1;
  return 2;
}

export function rrPoints(v: number): number {
  if (v <= 8) return 3;
  if (v <= 11) return 1;
  if (v <= 20) return 0;
  if (v <= 24) return 2;
  return 3;
}

export function sysPoints(v: number): number {
  if (v <= 90) return 3;
  if (v <= 100) return 2;
  if (v <= 110) return 1;
  if (v <= 219) return 0;
  return 3;
}

// ── Ward board ──────────────────────────────────────────────────────────────

const rank = (b: WardBed) => (!b.patient ? 2 : b.device && !b.device.online ? 1 : 0);

/**
 * The design's board order: highest NEWS2 first, offline units after online ones
 * at the same score, empty beds last. Applied explicitly so mock and real mode match.
 */
export function boardOrder(beds: WardBed[]): WardBed[] {
  return beds
    .map((b, i) => ({ b, i }))
    .sort((x, y) => {
      if (!x.b.patient !== !y.b.patient) return x.b.patient ? -1 : 1;
      const n = (y.b.patient?.latest_news2 ?? -1) - (x.b.patient?.latest_news2 ?? -1);
      return n || rank(x.b) - rank(y.b) || x.i - y.i;
    })
    .map(({ b }) => b);
}

/** Bed number order for the patient list ("C-11", "C-12", …). */
export const byBed = (a: WardBed, b: WardBed) => a.bed.localeCompare(b.bed, undefined, { numeric: true });

// ── Alerts ──────────────────────────────────────────────────────────────────

export const KIND_LABEL: Record<AlertKind, Key> = {
  call_nurse: "nurse.kindCall",
  news2: "nurse.kindNews2",
  device_offline: "nurse.kindOffline",
  trend: "nurse.kindTrend",
  dose_missed: "nurse.kindMissed",
};

/** Severity pill: word and [bg, fg] (design `SEV`). A call-nurse alert shows "Call". */
export function severityPill(a: Alert, t: TFn): { word: string; bg: string; fg: string } {
  if (a.kind === "call_nurse") return { word: t("nurse.sevCall"), bg: "var(--danger)", fg: "var(--paper)" };
  switch (a.severity) {
    case "critical":
      return { word: t("nurse.sevCritical"), bg: "var(--news-crit-edge)", fg: "var(--paper)" };
    case "high":
      return { word: t("nurse.sevHigh"), bg: "var(--news-high-bg)", fg: "var(--news-high-fg)" };
    case "medium":
      return { word: t("nurse.sevMedium"), bg: "var(--news-low-bg)", fg: "var(--news-low-fg)" };
    default:
      return { word: t("nurse.sevLow"), bg: "var(--disabled)", fg: "var(--text)" };
  }
}

/** Open alerts first, then newest first (design sort). */
export function alertOrder(alerts: Alert[]): Alert[] {
  return [...alerts].sort((a, b) => Number(!!a.acked_by) - Number(!!b.acked_by) || b.created_at.localeCompare(a.created_at));
}

// ── Doses (med round and nurse patient detail) ─────────────────────────────

export type NurseDoseStatus = "Missed" | "Given" | "Taken" | "Dispensed" | "Due" | "Scheduled";

/** Message keys for the status words. */
export const DOSE_WORD: Record<NurseDoseStatus, Key> = {
  Missed: "nurse.doseMissed",
  Given: "nurse.doseGiven",
  Taken: "nurse.doseTaken",
  Dispensed: "nurse.doseDispensed",
  Due: "nurse.doseDue",
  Scheduled: "nurse.doseScheduled",
};

/** Status pill colours (design `ST`): [bg, fg, border]. */
export const DOSE_PILL: Record<NurseDoseStatus, [string, string, string]> = {
  Missed: ["var(--news-crit-bg)", "var(--news-crit-fg)", "var(--missed-line)"],
  Given: ["var(--news-normal-bg)", "var(--news-normal-fg)", "var(--given-line)"],
  Taken: ["var(--news-normal-bg)", "var(--news-normal-fg)", "var(--given-line)"],
  Dispensed: ["var(--news-low-bg)", "var(--news-low-fg)", "var(--dispensed-line)"],
  Due: ["var(--paper)", "var(--ink)", "var(--ink)"],
  Scheduled: ["var(--paper)", "var(--muted)", "var(--line)"],
};

const DUE_WINDOW_MS = 60 * 60_000;

/** Nurse status: "Given" = taken by hand, "Due" = scheduled within the next hour (or overdue, not yet missed). */
export function nurseStatus(d: Dose, ref: Date): NurseDoseStatus {
  switch (d.status) {
    case "taken":
      return d.given_by ? "Given" : "Taken";
    case "missed":
      return "Missed";
    case "dispensed":
      return "Dispensed";
    default:
      return Date.parse(d.scheduled_at) - ref.getTime() <= DUE_WINDOW_MS ? "Due" : "Scheduled";
  }
}

export interface DoseView {
  id: string;
  time: string;
  med: string;
  sub: string;
  subAlert: boolean;
  slot: string;
  status: NurseDoseStatus;
  statusText: string;
  /** The "Mark given" button shows. */
  canGive: boolean;
  /** Text in the action column when there is no button. */
  by: string;
  /** The dose comes from an urgent prescription the pharmacist hasn't reviewed yet (spec §6). */
  pendingReview: boolean;
}

export interface DoseContext {
  ref: Date;
  t: TFn;
  /** Prescriptions by id (for the allergy override note). */
  prescriptions?: Map<string, Prescription>;
  /** Alerts for the "· alert sent 08:30" note on missed doses. */
  alerts?: Alert[];
}

function missedAlert(d: Dose, alerts: Alert[] = []): Alert | undefined {
  const drug = d.meds[0]?.split(" ")[0] ?? "";
  return alerts.find((a) => a.kind === "dose_missed" && a.patient_id === d.patient_id && !!drug && a.message.startsWith(drug));
}

/** Subline under the drug name, from the dose as it was scheduled (kept after "Mark given"). */
function subOf(d: Dose, ctx: DoseContext): { sub: string; subAlert: boolean } {
  switch (d.status) {
    case "missed": {
      const alert = missedAlert(d, ctx.alerts);
      const { t } = ctx;
      const base = d.slot != null ? t("nurse.notMarkedBy", { time: tunisTime(d.updated_at) }) : t("nurse.notGivenByHand");
      return { sub: alert ? `${base} · ${t("nurse.alertSent", { time: tunisTime(alert.created_at) })}` : base, subAlert: false };
    }
    case "dispensed":
      return { sub: ctx.t("nurse.dispensedWaiting", { time: tunisTime(d.updated_at) }), subAlert: false };
    case "taken":
      if (d.given_by) return { sub: d.instructions ?? ctx.t("nurse.giveByHand"), subAlert: false };
      return { sub: ctx.t("nurse.dispensedAt", { time: tunisTime(d.scheduled_at) }), subAlert: false };
    default: {
      if (ctx.prescriptions?.get(d.prescription_id)?.allergy_override)
        return { sub: ctx.t("nurse.allergyConflict"), subAlert: true };
      return { sub: d.instructions ?? ctx.t(d.slot != null ? "nurse.dispenseFromUnit" : "nurse.giveByHand"), subAlert: false };
    }
  }
}

/**
 * One dose row. `dose` is the current record; `original` (when the nurse just
 * marked it given) keeps the subline as it was, as the design does.
 */
export function doseView(dose: Dose, ctx: DoseContext, original: Dose = dose): DoseView {
  const status = nurseStatus(dose, ctx.ref);
  const done = status === "Given" || status === "Taken";
  const mins = Math.ceil((Date.parse(dose.scheduled_at) - ctx.ref.getTime()) / 60_000);
  const { t } = ctx;
  const statusText = status === "Due" ? (mins > 0 ? t("nurse.dueIn", { n: mins }) : t("nurse.dueNow")) : t(DOSE_WORD[status]);
  const at = dose.taken_at ? tunisTime(dose.taken_at) : "";
  const by =
    status === "Given"
      ? `${dose.given_by_name ?? dose.given_by} · ${at}`
      : status === "Taken"
        ? t("nurse.markedTaken", { time: at }).trim()
        : t("nurse.notYetDue");
  return {
    id: dose.id,
    time: tunisTime(dose.scheduled_at),
    med: dose.meds.join(" + "),
    ...subOf(original, ctx),
    slot: dose.slot != null ? t("nurse.slot", { n: dose.slot }) : t("nurse.reminderOnly"),
    status,
    statusText,
    canGive: !done && status !== "Scheduled",
    by,
    pendingReview: isPendingUrgent(ctx.prescriptions?.get(dose.prescription_id)),
  };
}

/** "penicillin" → "Allergy · Penicillin"; none → "No known allergies". */
export function allergyLabel(allergies: string[], t: TFn): string {
  if (!allergies.length) return t("nurse.noAllergies");
  const s = allergies.join(", ");
  return t("nurse.allergy", { a: `${s.charAt(0).toUpperCase()}${s.slice(1)}` });
}

// ── Sparkline (design `spark`, viewBox 0 0 100 28) ──────────────────────────

export function spark(values: number[]): string {
  if (values.length === 0) return "";
  if (values.length === 1) return "0,14 100,14";
  const mn = Math.min(...values);
  const mx = Math.max(...values);
  return values
    .map((v, i) => `${((i / (values.length - 1)) * 100).toFixed(1)},${(26 - ((v - mn) / (mx - mn || 1)) * 24).toFixed(1)}`)
    .join(" ");
}
