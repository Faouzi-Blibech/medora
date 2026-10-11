"use client";

// One bed on the nurse ward board. Desktop and tablet (≤ 1024 px) variants come from
// the same markup: the few tablet-only differences are switched by the CSS module.
import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";
import { useT } from "@/i18n/I18nProvider";
import { news2Word } from "@/lib/labels";
import { level, PULSE } from "@/lib/news2";
import { pausedAt, tunisTime, USE_MOCKS } from "@/lib/time";
import type { Alert, WardBed } from "@/lib/types";
import { hrPoints, spo2Points, tempPoints } from "./nurse";
import styles from "./BedCard.module.css";

/** Design jitter on the bed cards' HR while live (mock mode only). */
const BOARD_JITTER = [0, 1, -1, 2, 0, -2, 1];

export interface BedCardProps {
  bed: WardBed;
  /** Position on the board (staggers the "s ago" counters, as in the design). */
  index: number;
  live: boolean;
  /** Seconds since the board opened (useLiveTick().tick). */
  tick: number;
  /** The open call-nurse alert for this bed, if any. */
  call?: Alert;
}

interface VitalCell {
  k: string;
  u: string;
  v: string;
  arrow: string;
  bad: boolean;
}

function cells(bed: WardBed, offline: boolean, jitter: number): VitalCell[] {
  const l = bed.latest;
  const cell = (k: string, u: string, raw: number | null | undefined, pts: (v: number) => number, fmt: (v: number) => string, low: number): VitalCell => {
    if (offline || raw == null) return { k, u, v: "—", arrow: "", bad: raw != null && pts(raw) > 0 };
    const bad = pts(raw) > 0;
    const arrow = !bad ? "" : k === "SpO2" ? "↓" : raw <= low ? "↓" : "↑";
    return { k, u, v: fmt(raw), arrow, bad };
  };
  return [
    cell("HR", "bpm", l?.hr == null ? null : l.hr + jitter, hrPoints, String, 50),
    cell("SpO2", "%", l?.spo2, spo2Points, String, 100),
    cell("TEMP", "°C", l?.temp, tempPoints, (v) => v.toFixed(1), 36.0),
  ];
}

export function BedCard({ bed, index, live, tick, call }: BedCardProps) {
  const { t } = useT();
  const p = bed.patient;
  const empty = !p;
  const offline = !empty && (bed.device ? !bed.device.online : p.device_online === false);
  const news = p?.latest_news2 ?? 0;
  const lv = level(news);
  const crit = !empty && news >= 7;
  const jitter = live && !offline && USE_MOCKS ? BOARD_JITTER[(tick + index) % BOARD_JITTER.length] : 0;

  const cardStyle = {
    background: crit ? "var(--danger-row)" : empty || offline ? "var(--bed-idle)" : "var(--paper)",
    "--bd": crit ? "var(--crit-line)" : "var(--line)",
    "--bd-style": empty || offline ? "dashed" : "solid",
    "--edge": empty ? "var(--line)" : offline ? "var(--faint)" : lv.edge,
    animation: crit && live ? PULSE : "none",
  } as CSSProperties;

  let agoText: string;
  if (empty) agoText = t("nurse.idle");
  else if (offline) agoText = t("nurse.deviceOffline", { time: bed.device ? tunisTime(bed.device.last_seen) : "—" });
  else if (!live) agoText = t("nurse.paused", { time: pausedAt() });
  else if (USE_MOCKS) agoText = t("nurse.updatedAgo", { n: ((tick + index * 3) % 9) + 1 });
  // Real mode shows a snapshot (no live feed yet): when the last reading was taken, never a counter.
  else agoText = bed.latest ? t("nurse.lastReading", { time: tunisTime(bed.latest.ts) }) : t("nurse.noReadings");

  const body: ReactNode = (
    <>
      <div className={styles.top}>
        <span className={styles.bed}>{bed.bed}</span>
        <span className={styles.spacer} />
        {!empty ? (
          <span className={styles.news} style={{ background: lv.bg, color: lv.fg }}>
            <span className={styles.bubble} style={{ background: lv.edge }}>
              {news}
            </span>
            {news2Word(lv.word, t)}
          </span>
        ) : null}
      </div>
      <div className={styles.who}>
        <span dir="auto" className={styles.name}>
          {p ? p.first_name : t("nurse.emptyBed")}
        </span>
        {p ? <span className={`${styles.age} ${styles.desk}`}>{p.age}</span> : null}
      </div>
      {call ? (
        <span className={styles.calling}>
          <span className={`${styles.callDot} ${styles.desk}`} />
          {t("nurse.callRequest", { time: tunisTime(call.created_at) })}
        </span>
      ) : null}
      {empty ? <span className={`${styles.idle} ${styles.desk}`}>{t("nurse.readyAdmission")}</span> : null}
      {!empty ? (
        <div className={styles.vitals} style={{ opacity: offline || !live ? 0.5 : 1 }}>
          {cells(bed, offline, jitter).map((c) => (
            <div key={c.k} className={styles.cell}>
              <span className={styles.label}>
                {c.k}
                <span className={styles.desk}>
                  {" "}
                  <span className={styles.unit}>{c.u}</span>
                </span>
              </span>
              <span className={styles.reading} style={{ color: c.bad ? "var(--news-crit-fg)" : "var(--ink)" }}>
                <span className={styles.value}>{c.v}</span>
                <span className={styles.arrow}>{c.arrow}</span>
              </span>
            </div>
          ))}
        </div>
      ) : null}
      <div className={styles.foot}>
        <span
          className={styles.devDot}
          style={{
            background: offline || empty ? "transparent" : "var(--teal)",
            borderColor: offline || empty ? "var(--faint)" : "var(--teal)",
          }}
        />
        <span className={`${styles.dev} ${styles.desk}`}>{bed.device?.id ?? t("nurse.noUnit")}</span>
        <span
          className={styles.ago}
          style={{ color: offline ? "var(--news-high-fg)" : "var(--muted)", fontWeight: offline ? 700 : 400 }}
        >
          {agoText}
        </span>
      </div>
    </>
  );

  if (!p)
    return (
      <div className={styles.card} style={cardStyle}>
        {body}
      </div>
    );
  return (
    <Link href={`/nurse/patients/${encodeURIComponent(p.id)}`} className={`${styles.card} ward-lift`} style={cardStyle}>
      {body}
    </Link>
  );
}

/** Nurse / States · "Bed card · Loading". */
export function BedCardSkeleton() {
  return (
    <div aria-busy="true" className={styles.skeleton}>
      <span className="ward-skeleton" style={{ height: 36, width: 90, borderRadius: 6 }} />
      <span className={styles.skelLine} />
      <div className={styles.skelGrid}>
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

export default BedCard;
