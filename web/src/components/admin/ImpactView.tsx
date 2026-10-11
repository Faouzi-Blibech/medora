"use client";

// Admin / Pilot impact (/admin/impact): the indicators a pilot ward would track, measured by
// GET /admin/impact (api.md 1.16) over 7, 30 or 90 days, each with its trend against the previous
// period of equal length. "Not recorded yet" when the data model cannot measure an indicator.
import { useCallback, useEffect, useState } from "react";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { useT } from "@/i18n/I18nProvider";
import type { Lang } from "@/i18n/config";
import type { Key, TFn } from "@/i18n/messages";
import { getImpact } from "@/lib/api";
import { tunisDay } from "@/lib/time";
import type { ImpactGroup, ImpactId, ImpactIndicator, ImpactReport } from "@/lib/types";
import page from "./AdminPage.module.css";
import styles from "./ImpactView.module.css";

const PERIODS = [7, 30, 90] as const;
const GROUPS: [ImpactGroup, Key][] = [
  ["alerts", "admin.impGroupAlerts"],
  ["medication", "admin.impGroupMedication"],
  ["appointments", "admin.impGroupAppointments"],
  ["monitoring", "admin.impGroupMonitoring"],
  ["workload", "admin.impGroupWorkload"],
];
/** Label and plain-language definition of each indicator. */
const TEXT: Record<ImpactId, [Key, Key]> = {
  alerts_total: ["admin.impLAlertsTotal", "admin.impDAlertsTotal"],
  ack_median_min: ["admin.impLAckMedian", "admin.impDAckMedian"],
  ack_p90_min: ["admin.impLAckP90", "admin.impDAckP90"],
  ack_within_5min_pct: ["admin.impLAckWithin5", "admin.impDAckWithin5"],
  doses_due: ["admin.impLDosesDue", "admin.impDDosesDue"],
  doses_taken_pct: ["admin.impLDosesTaken", "admin.impDDosesTaken"],
  doses_missed_pct: ["admin.impLDosesMissed", "admin.impDDosesMissed"],
  doses_on_time_pct: ["admin.impLDosesOnTime", "admin.impDDosesOnTime"],
  missed_per_patient_day: ["admin.impLMissedPerPd", "admin.impDMissedPerPd"],
  requests_received: ["admin.impLRequests", "admin.impDRequests"],
  request_to_booking_hours: ["admin.impLToBooking", "admin.impDToBooking"],
  request_to_slot_days: ["admin.impLToSlot", "admin.impDToSlot"],
  cancellations: ["admin.impLCancellations", "admin.impDCancellations"],
  backfill_refills: ["admin.impLRefills", "admin.impDRefills"],
  no_show_rate_pct: ["admin.impLNoShow", "admin.impDNoShow"],
  vitals_per_patient_day: ["admin.impLVitalsPerPd", "admin.impDVitalsPerPd"],
  vitals_automated_pct: ["admin.impLAutomated", "admin.impDAutomated"],
  news2_medium_high_pct: ["admin.impLNews2Raised", "admin.impDNews2Raised"],
  nurse_notes_per_shift: ["admin.impLNotesPerShift", "admin.impDNotesPerShift"],
  ai_reviewed_pct: ["admin.impLAiReviewed", "admin.impDAiReviewed"],
};
const PART: Record<string, Key> = {
  low: "admin.impSevLow",
  medium: "admin.impSevMedium",
  high: "admin.impSevHigh",
  critical: "admin.impSevCritical",
  manual: "admin.impSrcManual",
  simulator: "admin.impSrcSimulator",
  device: "admin.impSrcDevice",
  reviewed: "admin.impReviewed",
  pending: "admin.impPending",
};
const BAND: Record<string, Key> = { low: "admin.impBandLow", medium: "admin.impBandMedium", high: "admin.impBandHigh" };
const partKey = (i: ImpactIndicator, k: string): Key | undefined => (i.id === "news2_medium_high_pct" ? BAND : PART)[k];
const partLabel = (i: ImpactIndicator, k: string, t: TFn) => {
  const key = partKey(i, k);
  return key ? t(key) : k;
};

const num = (n: number, lang: Lang) => n.toLocaleString(lang === "fr" ? "fr-FR" : "en-US", { maximumFractionDigits: 2 });

function withUnit(i: ImpactIndicator, n: number, t: TFn, lang: Lang): { v: string; unit: string } {
  const v = num(n, lang);
  switch (i.unit) {
    case "pct":
      return { v, unit: "%" };
    case "minutes":
      return { v, unit: t("admin.impUnitMin") };
    case "hours":
      return { v, unit: t("admin.impUnitH") };
    case "days":
      return { v, unit: t("admin.impUnitDays") };
    default:
      return { v, unit: "" };
  }
}

type Tone = "good" | "bad" | "flat";

function delta(i: ImpactIndicator, t: TFn, lang: Lang): { text: string; tone: Tone; arrow: string } | null {
  if (i.value == null || i.previous == null) return null;
  const d = Math.round((i.value - i.previous) * 100) / 100;
  if (d === 0) return { text: t("admin.impNoChange"), tone: "flat", arrow: "" };
  const signed = `${d > 0 ? "+" : "−"}${num(Math.abs(d), lang)}`;
  const { unit } = withUnit(i, d, t, lang);
  const text = i.unit === "pct" ? t("admin.impPts", { d: signed }) : unit ? `${signed} ${unit}` : signed;
  const tone: Tone = i.better == null ? "flat" : (i.better === "higher") === d > 0 ? "good" : "bad";
  return { text, tone, arrow: d > 0 ? "▲" : "▼" };
}

const csvCell = (v: string | number | null): string => {
  let s = v == null ? "" : String(v);
  if (/^[=+\-@]/.test(s)) s = `'${s}`; // spreadsheet formula injection
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

function toCsv(r: ImpactReport, t: TFn): string {
  const head = ["period_from", "period_to", "previous_from", "previous_to", "group", "indicator_id", "indicator",
    "value", "previous_value", "unit", "status", "definition"];
  const lines: (string | number | null)[][] = [];
  const base = [r.period.from, r.period.to, r.previous_period.from, r.previous_period.to];
  for (const i of r.indicators) {
    const [label, def] = TEXT[i.id] ?? [null, null];
    const name = label ? t(label) : i.id;
    lines.push([...base, i.group, i.id, name, i.value, i.previous, i.unit, i.status, def ? t(def) : ""]);
    for (const [k, n] of Object.entries(i.breakdown ?? {})) {
      lines.push([...base, i.group, `${i.id}.${k}`, `${name} · ${partLabel(i, k, t)}`, n, null, "count", i.status, ""]);
    }
  }
  // BOM: spreadsheet apps then read French and Arabic text as UTF-8
  return `﻿${[head.join(","), ...lines.map((l) => l.map(csvCell).join(","))].join("\n")}`;
}

function Card({ i }: { i: ImpactIndicator }) {
  const { t, lang } = useT();
  const [label, def] = TEXT[i.id] ?? ["admin.impNotRecorded", "admin.impNotRecorded"];
  if (i.status === "not_recorded") {
    return (
      <article className={`${styles.card} ${styles.cardOff}`}>
        <h4 className={styles.label}>{t(label)}</h4>
        <span className={styles.off}>{t("admin.impNotRecorded")}</span>
        <p className={styles.def}>{t(def)}</p>
      </article>
    );
  }
  const shown = i.value == null ? null : withUnit(i, i.value, t, lang);
  const d = delta(i, t, lang);
  const parts = Object.entries(i.breakdown ?? {});
  const partTotal = parts.reduce((s, [, n]) => s + n, 0);
  return (
    <article className={styles.card}>
      <h4 className={styles.label}>{t(label)}</h4>
      {shown ? (
        <span className={styles.valueRow}>
          <span className={styles.value}>{shown.v}</span>
          {shown.unit ? <span className={styles.unit}>{shown.unit}</span> : null}
        </span>
      ) : (
        <span className={styles.empty}>{t("admin.impNoData")}</span>
      )}
      <span className={styles.trend}>
        {d ? (
          <span className={`${styles.delta} ${styles[d.tone]}`}>
            {d.arrow ? <span aria-hidden="true">{d.arrow}</span> : null}
            <bdi dir={d.arrow ? "ltr" : undefined}>{d.text}</bdi>
          </span>
        ) : i.value != null ? (
          <span className={`${styles.delta} ${styles.flat}`}>{t("admin.impNoPrev")}</span>
        ) : null}
        {d && i.previous != null ? (
          <span className={styles.was}>{t("admin.impWas", { v: withUnit(i, i.previous, t, lang).v })}</span>
        ) : null}
      </span>
      {parts.length && partTotal ? (
        <>
          <span className={styles.bar} aria-hidden="true">
            {parts.filter(([, n]) => n > 0).map(([k, n]) => (
              <span key={k} className={`${styles.seg} ${styles[`seg_${k}`] ?? ""}`} style={{ flexGrow: n }} />
            ))}
          </span>
          <span className={styles.parts}>
            {parts.map(([k, n]) => (
              <span key={k} className={styles.part}>
                <span className={`${styles.dot} ${styles[`seg_${k}`] ?? ""}`} />
                <bdi>{partLabel(i, k, t)}</bdi> <b>{num(n, lang)}</b>
              </span>
            ))}
          </span>
        </>
      ) : null}
      <p className={styles.def}>
        {t(def)}
        {i.better == null ? <span className={styles.context}> {t("admin.impContext")}.</span> : null}
      </p>
    </article>
  );
}

export function ImpactView() {
  const { t, lang } = useT();
  const [days, setDays] = useState<number>(30);
  const [report, setReport] = useState<ImpactReport | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    setFailed(false);
    setReport(null);
    getImpact(days)
      .then(setReport)
      .catch(() => setFailed(true));
  }, [days]);

  useEffect(() => load(), [load]);

  const exportCsv = () => {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([toCsv(report, t)], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `ward-pilot-impact-${report.days}d-${report.period.to.slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={page.page}>
      <div className={`${page.head} ${styles.head}`}>
        <div className={page.titles}>
          <h2 className={page.h2}>{t("admin.impTitle")}</h2>
          <span className={page.sub}>{t("admin.impSub", { n: days })}</span>
          {report ? (
            <span className={styles.meta}>
              {t("admin.impRange", { from: tunisDay(report.period.from, lang), to: tunisDay(report.period.to, lang) })}
              {" · "}
              {t("admin.impPatientDays", { n: num(report.patient_days, lang) })}
            </span>
          ) : null}
        </div>
        <div className={styles.controls}>
          <div role="radiogroup" aria-label={t("admin.impPeriod")} className={styles.segment}>
            {PERIODS.map((p) => (
              <button
                key={p}
                type="button"
                role="radio"
                aria-checked={days === p}
                className={`${styles.segBtn} ${days === p ? styles.segOn : ""}`}
                onClick={() => setDays(p)}
              >
                {t("admin.impDays", { n: p })}
              </button>
            ))}
          </div>
          <button type="button" className={page.btn} onClick={exportCsv} disabled={!report}>
            {t("admin.impExport")}
          </button>
        </div>
      </div>

      {failed ? (
        <ErrorCard title={t("admin.impLoadError")} onRetry={load} />
      ) : !report ? (
        <div className={styles.grid} aria-busy="true">
          {[1, 2, 3, 4].map((k) => (
            <div key={k} className={styles.card}>
              <span className={`ward-skeleton ${styles.skel}`} />
            </div>
          ))}
        </div>
      ) : (
        GROUPS.map(([g, title]) => {
          const items = report.indicators.filter((i) => i.group === g);
          if (!items.length) return null;
          return (
            <section key={g} className={styles.group} aria-labelledby={`imp-${g}`}>
              <h3 id={`imp-${g}`} className={styles.h3}>
                {t(title)}
              </h3>
              <div className={styles.grid}>
                {items.map((i) => (
                  <Card key={i.id} i={i} />
                ))}
              </div>
            </section>
          );
        })
      )}

      <p className={styles.honesty}>{t("admin.impHonesty")}</p>
    </div>
  );
}

export default ImpactView;
