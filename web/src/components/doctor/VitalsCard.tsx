"use client";

// Doctor vitals card: HR, SpO2 and temperature over 24 h with normal bands, the NEWS2
// dots every 2 h and the time axis. Built from the shared chart pieces. The charts draw
// hourly means (lib/series); the number above each chart is the latest raw reading.
import type React from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Lang } from "@/i18n/config";
import type { TFn } from "@/i18n/messages";
import { News2Strip } from "@/components/shared/News2Strip";
import { TimeAxisRow, trendOf, VitalChartRow } from "@/components/shared/VitalsChart";
import { hourlyMeans, news2Every2h, type VitalKey } from "@/lib/series";
import { dayLabel, tunisTime, USE_MOCKS } from "@/lib/time";
import type { Vital } from "@/lib/types";
import styles from "./PatientDetail.module.css";

export interface VitalsCardProps {
  /** Oldest first. */
  vitals: Vital[];
  live: boolean;
  /** Seconds since the last reading (live tick). */
  sec: number;
  /** Simulated change on the latest heart rate (mock live tick). */
  hrJitter?: number;
  now: Date;
  /** Shown under the charts when set: the hand-recorded reading form. */
  footer?: React.ReactNode;
}

const HOURS = 24;

/** The latest raw reading of `k` (null when the series has none). */
function latestOf(vs: Vital[], k: VitalKey): number | null {
  for (let i = vs.length - 1; i >= 0; i--) {
    const x = vs[i][k];
    if (x != null) return x;
  }
  return null;
}

/** Hourly means rounded for display (HR and SpO2 to whole numbers, temperature to 0.1). */
function hourly(vs: Vital[], k: VitalKey, ref: Date, step: number): (number | null)[] {
  return hourlyMeans(vs, k, HOURS, ref).map((x) => (x == null ? null : Math.round(x / step) * step));
}

const present = (xs: (number | null)[]) => xs.filter((x): x is number => x != null);

/** Seven evenly spaced labels over the 24 h window: "Sun 09:00", "13:00", … "Now". */
function axisLabels(ref: Date, lang: Lang, t: TFn): string[] {
  const b = ref.getTime();
  const a = b - HOURS * 3_600_000;
  return Array.from({ length: 7 }, (_, k) => {
    if (k === 6) return t("doctor.axisNow");
    const iso = new Date(a + ((b - a) * k) / 6).toISOString();
    const hour = `${tunisTime(iso).slice(0, 2)}:00`;
    const day = dayLabel(iso, ref, lang);
    return k === 0 && day !== t("common.today") ? `${day} ${hour}` : hour;
  });
}

export function VitalsCard({ vitals, live, sec, hrJitter = 0, now, footer }: VitalsCardProps) {
  const { t, lang } = useT();
  const hr = hourly(vitals, "hr", now, 1);
  const hrLatest = latestOf(vitals, "hr");
  // Mock live tick only: the simulated change moves both the number and the last point.
  const endHr = hr[hr.length - 1];
  if (hrJitter && endHr != null) hr[hr.length - 1] = endHr + hrJitter;
  const sp = hourly(vitals, "spo2", now, 1);
  const tp = hourly(vitals, "temp", now, 0.1).map((x) => (x == null ? null : Number(x.toFixed(1))));
  const news = news2Every2h(vitals, now);
  const paused = !live;
  const lastTs = vitals.length ? vitals[vitals.length - 1].ts : null;
  // Real mode has no live feed yet: show when the snapshot's last reading was taken.
  const status = !live
    ? t("doctor.statusPaused")
    : USE_MOCKS
      ? t("doctor.statusLive", { n: sec })
      : lastTs
        ? t("doctor.statusLastReading", { time: tunisTime(lastTs) })
        : t("doctor.statusNoReadings");
  const fresh = live && USE_MOCKS;
  const manual = vitals.filter((v) => v.source === "manual").length;

  return (
    <section className={styles.card}>
      <div className={styles.cardHead}>
        <h3 className={styles.h3}>{t("doctor.vitalsTitle")}</h3>
        <span className={styles.spacer} />
        <span
          className={styles.liveTag}
          style={{ color: fresh ? "var(--news-normal-fg)" : live ? "var(--muted)" : "var(--news-low-fg)" }}
        >
          <span
            className={styles.liveDot}
            style={{ background: fresh ? "var(--teal)" : live ? "var(--faint)" : "var(--news-low-edge)" }}
          />
          {status}
        </span>
        <span className={styles.legend}>
          <span className={styles.swatch} />
          {t("doctor.normalRange")}
        </span>
      </div>
      <VitalChartRow
        name={t("doctor.heartRate")}
        unit="bpm"
        values={hr}
        latest={hrLatest == null ? null : hrLatest + hrJitter}
        min={50}
        max={130}
        normalLo={51}
        normalHi={90}
        bandLabel={t("doctor.bandNormal", { range: "51–90" })}
        trend={trendOf(present(hr), 10, "up")}
        paused={paused}
      />
      <VitalChartRow
        name="SpO2"
        unit="%"
        values={sp}
        latest={latestOf(vitals, "spo2")}
        min={86}
        max={100}
        normalLo={96}
        normalHi={100}
        bandLabel={t("doctor.bandNormal", { range: "≥ 96" })}
        trend={trendOf(present(sp), 2, "down")}
        paused={paused}
      />
      <VitalChartRow
        name={t("doctor.temperature")}
        unit="°C"
        values={tp}
        latest={latestOf(vitals, "temp")}
        min={35.5}
        max={39}
        normalLo={36.1}
        normalHi={38}
        bandLabel={t("doctor.bandNormal", { range: "36.1–38.0" })}
        format={(v) => v.toFixed(1)}
        trend={trendOf(present(tp), 0.8, "up")}
        paused={paused}
      />
      <News2Strip scores={news} />
      <TimeAxisRow labels={axisLabels(now, lang, t)} />
      <span className={styles.sources}>{t("shared.vitalsSources", { manual, feed: vitals.length - manual })}</span>
      {footer}
    </section>
  );
}

export default VitalsCard;
