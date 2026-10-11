"use client";

// Patient / My vitals (/patient/vitals): latest heart rate, oxygen and temperature in plain words
// ("Normal" / "Needs attention", from the usual ranges — never a NEWS2 or AI score), and the
// 24 h heart-rate line. Values are simulated for this prototype (the brand tag says so).
import { getVitals } from "@/lib/api";
import { useDemoFlags } from "@/lib/demo";
import { useT } from "@/i18n/I18nProvider";
import type { TFn } from "@/i18n/messages";
import { ago, now, tunisTime } from "@/lib/time";
import type { Vital } from "@/lib/types";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { daysBetween, myPatientId, offlineSince, useLoad, useOffline, vitalWord } from "./patient";
import { EmptyCard, OfflineBanner, PatientScreen, SkeletonCard } from "./PatientScreen";
import styles from "./Patient.module.css";

const last = (vs: Vital[], k: "hr" | "spo2" | "temp") => {
  for (let i = vs.length - 1; i >= 0; i--) if (vs[i][k] != null) return vs[i][k] as number;
  return null;
};

/** The design's mapping: 300 × 90 box, 50–130 beats/min. */
function hrPoints(values: number[]): string {
  const n = values.length;
  return values
    .map((v, i) => {
      const x = n === 1 ? 300 : (i / (n - 1)) * 300;
      const y = Math.min(90, Math.max(0, 90 - ((v - 50) / 80) * 90));
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function startLabel(iso: string, t: TFn): string {
  const d = daysBetween(iso, now().toISOString());
  const hour = `${tunisTime(iso).slice(0, 2)}:00`;
  return d === 0 ? `${t("common.today")} ${hour}` : d === 1 ? `${t("patient.yesterday")} ${hour}` : hour;
}

export function VitalsView() {
  const { t, lang } = useT();
  const flags = useDemoFlags();
  const offline = useOffline();
  const res = useLoad(async () => getVitals(await myPatientId()));

  const vitals = flags.state === "empty" ? [] : flags.state ? null : res.data;
  const failed = flags.state === "error" || (!!res.error && !res.data);

  const latest = vitals?.[vitals.length - 1];
  const hrSeries = (vitals ?? []).filter((v) => v.hr != null);
  const s = latest ? Math.round((now().getTime() - Date.parse(latest.ts)) / 1000) : 0;
  const updated = latest ? (s < 60 ? t("patient.fewSeconds") : ago(latest.ts, now(), lang)) : null;

  const tiles = vitals
    ? [
        { key: "hr", label: t("patient.heartRate"), unit: t("patient.beatsMin"), value: last(vitals, "hr"), wide: false },
        { key: "spo2", label: t("patient.oxygen"), unit: "%", value: last(vitals, "spo2"), wide: false },
        { key: "temp", label: t("patient.temperature"), unit: "°C", value: last(vitals, "temp"), wide: true },
      ].filter((tile) => tile.value != null)
    : [];

  return (
    <PatientScreen nav="vitals">
      <div className={`${styles.scroll} ${styles.vitalsBody}`}>
        {offline ? <OfflineBanner since={offlineSince(res.loadedAt)} /> : null}
        <div className={styles.titleBlock}>
          <h1 className={styles.h1Small}>{t("patient.vitalsTitle")}</h1>
          <span className={styles.sublineSmall}>
            {updated
              ? offline
                ? t("patient.last24Paused", { time: offlineSince(res.loadedAt) })
                : t("patient.last24Updated", { when: updated })
              : t("patient.last24")}
          </span>
        </div>

        {failed ? (
          <ErrorCard
            variant="patient"
            title={t("patient.errTitle")}
            message={t("patient.vitalsLoadErr")}
            retryLabel={t("patient.tryAgain")}
            onRetry={flags.state === "error" ? undefined : res.retry}
          />
        ) : !vitals ? (
          <SkeletonCard />
        ) : tiles.length === 0 ? (
          <EmptyCard title={t("patient.noReadingsTitle")}>{t("patient.noReadingsText")}</EmptyCard>
        ) : (
          <>
            <div className={`${styles.tiles} ${offline ? styles.paused : ""}`}>
              {tiles.map((tile) => {
                const v = tile.value as number;
                const word = vitalWord(tile.key as "hr" | "spo2" | "temp", v);
                return (
                  <div key={tile.key} className={`${styles.tile} ${tile.wide ? styles.tileWide : ""}`}>
                    <span className={styles.tileLabel}>{tile.label}</span>
                    <span className={styles.tileValue}>
                      <span className={styles.tileNum}>{tile.key === "temp" ? v.toFixed(1) : v}</span>
                      <span>{tile.unit}</span>
                    </span>
                    <span className={`${styles.word} ${word === "Normal" ? styles.word_ok : styles.word_attention}`}>
                      <span className={styles.wordDot} />
                      {word === "Normal" ? t("shared.news2Normal") : t("patient.needsAttention")}
                    </span>
                  </div>
                );
              })}
            </div>
            {hrSeries.length > 1 ? (
              <section className={styles.chartCard} aria-label={t("patient.hrChartLabel")}>
                <span className={styles.chartTitle}>{t("patient.hrChartTitle")}</span>
                <div dir="ltr">
                {/* Stretches to the card (the desktop card is much wider than the phone's); the stroke keeps its width. */}
                <svg viewBox="0 0 300 90" preserveAspectRatio="none" className={styles.chart} role="img" aria-label={t("patient.hrLine")}>
                  <rect x="0" y="45" width="300" height="34" className={styles.band} />
                  <polyline
                    points={hrPoints(hrSeries.map((v) => v.hr as number))}
                    className={styles.line}
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
                <div className={styles.axis}>
                  <span>{startLabel(hrSeries[0].ts, t)}</span>
                  <span>{t("patient.now")}</span>
                </div>
                </div>
                <span className={styles.legend}>
                  <span className={styles.legendSwatch} />
                  {t("patient.shaded")}
                </span>
              </section>
            ) : null}
          </>
        )}

        <div className={styles.careNote}>
          {t("patient.careNote")}
        </div>
      </div>
    </PatientScreen>
  );
}

export default VitalsView;
