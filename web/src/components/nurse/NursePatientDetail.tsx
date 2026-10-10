"use client";

// Nurse / Patient detail (/nurse/patients/[id]): critical banner, vitals tiles with
// NEWS2 points, today's doses, read-only prescriptions and notes.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { LiveBanner } from "@/components/LiveBanner";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { NotesPanel } from "@/components/shared/NotesPanel";
import { PatientAiCard } from "@/components/shared/PatientAiCard";
import { trendOf } from "@/components/shared/VitalsChart";
import { Toast, useToast } from "@/components/Toast";
import { useT } from "@/i18n/I18nProvider";
import type { Key, TFn } from "@/i18n/messages";
import { addNote, getDoses, getNotes, getPatient, getPrescriptions, getVitals } from "@/lib/api";
import { useDemoFlags } from "@/lib/demo";
import { news2Word } from "@/lib/labels";
import { level, PULSE } from "@/lib/news2";
import { isPendingUrgent, isRunning } from "@/lib/pharmacy";
import { dayLabel, now, pausedAt, tunisDate, tunisTime, tunisTimeSeconds, USE_MOCKS } from "@/lib/time";
import type { Alert, Dose, Note, Patient, Prescription, Vital } from "@/lib/types";
import { useMe } from "@/lib/useMe";
import { DosePill } from "./DosePill";
import { PendingReviewBadge } from "./PharmacyBadge";
import {
  doseView,
  hrPoints,
  NURSE_ID,
  NURSE_NAME,
  rrPoints,
  spark,
  spo2Points,
  sysPoints,
  tempPoints,
} from "./nurse";
import { useWardAlerts } from "./useWardAlerts";
import styles from "./NursePatientDetail.module.css";

interface Data {
  patient: Patient;
  vitals: Vital[];
  prescriptions: Prescription[];
  doses: Dose[];
  notes: Note[];
}

/** Readings shown per tile (the design's sparklines have 7 points). */
const TILE_POINTS = 7;

interface Tile {
  k: Key | "SpO2";
  v: string;
  u: string;
  pts: number | null;
  arrow: string;
  arrowColor: string;
  trend: string;
  spark: string;
}

const TREND_WORD: Record<string, Key> = {
  steady: "nurse.trendSteady",
  rising: "nurse.trendRising",
  falling: "nurse.trendFalling",
};

function tile(
  t: TFn,
  k: Key | "SpO2",
  u: string,
  vitals: Vital[],
  pick: (v: Vital) => number | null | undefined,
  points: (v: number) => number,
  threshold: number,
  display: (v: Vital, value: number) => string,
  /** Points from which a moving trend's arrow turns crit-red (else high-orange). Design: HR and SpO2 at 2, others at 3. */
  critAt = 3,
): Tile {
  const rows = vitals.filter((v) => pick(v) != null).slice(-TILE_POINTS);
  if (rows.length === 0) return { k, v: "—", u, pts: null, arrow: "", arrowColor: "var(--muted)", trend: t("nurse.noReading"), spark: "" };
  const values = rows.map((v) => pick(v) as number);
  const last = rows[rows.length - 1];
  const value = values[values.length - 1];
  const pts = points(value);
  const tr = trendOf(values, threshold);
  const arrowColor = tr.word === "steady" ? "var(--muted)" : pts >= critAt ? "var(--news-crit-fg)" : "var(--news-high-fg)";
  return {
    k,
    v: display(last, value),
    u,
    pts,
    arrow: tr.arrow,
    arrowColor,
    trend: `${t(TREND_WORD[tr.word])} · ${tunisTimeSeconds(last.ts)}`,
    spark: spark(values),
  };
}

function tiles(vitals: Vital[], t: TFn): Tile[] {
  return [
    tile(t, "nurse.tileHeartRate", "bpm", vitals, (v) => v.hr, hrPoints, 10, (_, x) => String(x), 2),
    tile(t, "SpO2", "%", vitals, (v) => v.spo2, spo2Points, 2, (_, x) => String(x), 2),
    tile(t, "nurse.tileTemperature", "°C", vitals, (v) => v.temp, tempPoints, 0.5, (_, x) => x.toFixed(1)),
    tile(t, "nurse.tileRespRate", "/min", vitals, (v) => v.rr, rrPoints, 3, (_, x) => String(x)),
    tile(t, "nurse.tileBloodPressure", "", vitals, (v) => v.bp_sys, sysPoints, 10, (v, x) => `${x}/${v.bp_dia ?? "—"}`),
  ];
}

const tileLevel = (pts: number) => (pts >= 3 ? level(7) : pts >= 1 ? level(2) : level(0));
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function NursePatientDetail({ id }: { id: string }) {
  const { t, lang } = useT();
  const flags = useDemoFlags();
  const router = useRouter();
  const me = useMe("nurse");
  const viewer = USE_MOCKS ? NURSE_NAME : (me?.name ?? "…");
  const { alerts, ack, busy, notice } = useWardAlerts();
  const [data, setData] = useState<Data | null>(null);
  const [failed, setFailed] = useState(false);
  const [openedAt] = useState(() => tunisTime(now().toISOString()));
  const [noteError, showNoteError] = useToast<string>();

  const load = useCallback(() => {
    setFailed(false);
    const today = tunisDate(now().toISOString());
    Promise.all([getPatient(id), getVitals(id), getPrescriptions(id), getDoses(id, { date: today }).catch((): Dose[] => []), getNotes(id)])
      .then(([patient, vitals, prescriptions, doses, notes]) => setData({ patient, vitals, prescriptions, doses, notes }))
      .catch(() => setFailed(true));
  }, [id]);

  useEffect(load, [load]);

  const onAddNote = useCallback(
    async (text: string) => {
      try {
        const note = await addNote(id, text, { by: NURSE_ID });
        setData((d) => (d ? { ...d, notes: [note, ...d.notes] } : d));
      } catch (e) {
        showNoteError(t("nurse.noteSaveFailed"));
        throw e; // keeps the draft in NotesPanel
      }
    },
    [id, showNoteError, t],
  );

  const state = flags.state === "error" || failed ? "error" : flags.state === "loading" || !data ? "loading" : null;
  const ref = now();
  const p = data?.patient;
  const name = p ? `${p.first_name} ${p.last_name}` : "";

  const news2Alert: Alert | undefined = (alerts ?? [])
    .filter((a) => a.patient_id === id && a.kind === "news2")
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const critical = !!p && (p.latest_news2 ?? 0) >= 7;
  const lv = level(p?.latest_news2);

  return (
    <div className={styles.page}>
      <div className={styles.crumbs}>
        <Link href="/nurse" className={styles.crumbLink}>
          {t("nurse.crumbBoard")}
        </Link>
        <span>/</span>
        <span dir="auto" className={styles.crumbHere}>
          {p ? t("nurse.bedName", { bed: p.bed ?? "—", name }) : t("nurse.metaPatient")}
        </span>
        <span className={styles.spacer} />
        <span className={styles.audit}>
          <span className={styles.lock} />
          {t("nurse.accessLogged", { viewer, time: openedAt })}
        </span>
      </div>
      {!flags.live ? (
        <LiveBanner className={styles.banner}>{t("nurse.frozen", { time: pausedAt() })}</LiveBanner>
      ) : null}

      {state === "error" ? (
        <ErrorCard
          title={t("nurse.loadPatientTitle")}
          onRetry={load}
          secondaryLabel={t("nurse.backToBoard")}
          onSecondary={() => router.push("/nurse")}
        />
      ) : state === "loading" || !data || !p ? (
        <div className={styles.skelCard} aria-busy="true">
          <span className="ward-skeleton" style={{ height: 34, width: 320 }} />
          <span className="ward-skeleton" style={{ height: 14, width: 260 }} />
          <span className="ward-skeleton" style={{ height: 120, width: "100%" }} />
          <span className="ward-skeleton" style={{ height: 120, width: "100%" }} />
        </div>
      ) : (
        <>
          {critical ? (
            <div
              role="alert"
              className={styles.critical}
              style={{ animation: flags.live && !news2Alert?.acked_by ? PULSE : "none" }}
            >
              <span className={styles.critScore}>{p.latest_news2}</span>
              <div className={styles.critText}>
                <span className={styles.critTitle}>
                  {t("nurse.critTitle", { score: p.latest_news2 ?? "", word: news2Word(lv.word, t) })}
                </span>
                <span className={styles.critSub}>
                  {news2Alert
                    ? `${t("nurse.notifiedAt", { doctor: p.attending_doctor_name ?? t("nurse.theAttending"), time: tunisTime(news2Alert.created_at) })} `
                    : ""}
                  {t("nurse.stayWithPatient")}
                </span>
              </div>
              {news2Alert && !news2Alert.acked_by ? (
                <button
                  type="button"
                  className={styles.critAck}
                  disabled={busy.has(news2Alert.id)}
                  onClick={() => void ack(news2Alert.id)}
                >
                  {t("nurse.acknowledge")}
                </button>
              ) : news2Alert?.acked_by ? (
                <span className={styles.critAcked}>
                  {t("nurse.ackedBy", { name: news2Alert.acked_by_name ?? news2Alert.acked_by ?? "" })}
                  {news2Alert.acked_at ? ` · ${tunisTime(news2Alert.acked_at)}` : ""}
                </span>
              ) : null}
            </div>
          ) : null}

          <section className={styles.header}>
            <div className={styles.facts}>
              <h2 dir="auto" className={styles.name}>
                {name}
              </h2>
              <div className={styles.factLine}>
                <span>
                  {p.age} · {t(p.sex === "M" ? "nurse.male" : "nurse.female")}
                </span>
                <span className={styles.dotSep}>·</span>
                <span className={styles.nowrap}>
                  <b>{t("nurse.bed", { bed: p.bed ?? "—" })}</b>
                  {p.device_id ? (
                    <>
                      {" · "}
                      <span className={styles.mono}>{p.device_id}</span>{" "}
                      {p.device_online === false ? (
                        <span className={styles.offline}>● {t("nurse.offline")}</span>
                      ) : p.device_online ? (
                        <span className={styles.online}>● {t("nurse.online")}</span>
                      ) : null}
                    </>
                  ) : null}
                </span>
                {p.attending_doctor_name ? (
                  <>
                    <span className={styles.dotSep}>·</span>
                    <span>
                      {t("nurse.attending")} <b>{p.attending_doctor_name}</b>
                    </span>
                  </>
                ) : null}
              </div>
            </div>
            <div className={styles.allergy}>
              <span className={styles.allergyLabel}>{t("nurse.allergies")}</span>
              <span className={styles.allergyValue}>
                {p.allergies.length ? cap(p.allergies.join(", ")) : t("nurse.noAllergies")}
              </span>
              {p.allergy_notes ? <span className={styles.allergyNote}>{p.allergy_notes}</span> : null}
            </div>
          </section>

          <div className={styles.tiles} style={{ opacity: flags.live ? 1 : 0.55 }}>
            {tiles(data.vitals, t).map((tt) => {
              const tl = tileLevel(tt.pts ?? 0);
              return (
                <div key={tt.k} className={styles.tile} style={{ borderTopColor: tt.pts == null ? "var(--line)" : tl.edge }}>
                  <div className={styles.tileHead}>
                    <span className={styles.tileName}>{tt.k === "SpO2" ? tt.k : t(tt.k)}</span>
                    {tt.pts != null ? (
                      <span className={styles.pts} style={{ background: tl.bg, color: tl.fg }}>
                        {t("nurse.pts", { n: tt.pts })}
                      </span>
                    ) : null}
                  </div>
                  <span className={styles.tileValue}>
                    <span className={styles.tileNum}>{tt.v}</span>
                    {tt.u ? <span className={styles.tileUnit}>{tt.u}</span> : null}
                    <span className={styles.tileArrow} style={{ color: tt.arrowColor }}>
                      {tt.arrow}
                    </span>
                  </span>
                  <svg viewBox="0 0 100 28" preserveAspectRatio="none" className={styles.spark} aria-hidden="true">
                    {tt.spark ? (
                      <polyline points={tt.spark} fill="none" stroke="var(--ink)" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
                    ) : null}
                  </svg>
                  <span className={styles.tileTrend}>{tt.trend}</span>
                </div>
              );
            })}
          </div>

          <div className={styles.columns}>
            <div className={styles.col}>
              <section className={styles.card}>
                <h3 className={styles.cardTitle}>{t("nurse.todaysDoses")}</h3>
                {data.doses.length === 0 ? <span className={styles.none}>{t("nurse.noDosesToday")}</span> : null}
                {[...data.doses]
                  .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))
                  .map((d) => {
                    const v = doseView(d, {
                      ref,
                      t,
                      prescriptions: new Map(data.prescriptions.map((r) => [r.id, r])),
                      alerts: alerts ?? [],
                    });
                    return (
                      <div key={d.id} className={styles.doseRow}>
                        <span className={styles.doseTime}>{v.time}</span>
                        <div className={styles.doseMed}>
                          <span className={styles.doseName}>{v.med}</span>
                          <span className={styles.doseSub} style={v.subAlert ? { color: "var(--danger)" } : undefined}>
                            {v.sub}
                          </span>
                          {v.pendingReview ? <PendingReviewBadge /> : null}
                        </div>
                        <DosePill status={v.status} text={v.statusText} />
                      </div>
                    );
                  })}
              </section>
              <section className={styles.card}>
                <div className={styles.cardHead}>
                  <h3 className={styles.cardTitle}>{t("nurse.prescriptions")}</h3>
                  <span className={styles.readOnly}>{t("nurse.readOnly")}</span>
                </div>
                {data.prescriptions.filter(isRunning).length === 0 ? <span className={styles.none}>{t("nurse.noRx")}</span> : null}
                {data.prescriptions.filter(isRunning).flatMap((rx) =>
                  rx.items.map((item, i) => (
                    <div key={`${rx.id}-${i}`} className={styles.rxRow}>
                      <span className={styles.rxMed}>{item.med}</span>
                      {isPendingUrgent(rx) ? <PendingReviewBadge /> : null}
                      <span className={styles.rxTimes}>{item.times.join(", ")}</span>
                      <span className={styles.rxSlot}>{item.slot != null ? t("nurse.slot", { n: item.slot }) : t("nurse.reminderOnly")}</span>
                    </div>
                  )),
                )}
              </section>
            </div>
            <PatientAiCard patientId={id} role="nurse" />
            <NotesPanel
              notes={data.notes}
              onAdd={onAddNote}
              placeholder={t("nurse.notePlaceholder")}
              hint={null}
              rows={3}
              variant="nurse"
              now={ref}
              timeLabel={(iso) => (dayLabel(iso, ref, lang) === t("common.today") ? tunisTime(iso) : `${dayLabel(iso, ref, lang)} ${tunisTime(iso)}`)}
            />
          </div>
        </>
      )}
      {notice || noteError ? <Toast tone="warn">{notice ?? noteError}</Toast> : null}
    </div>
  );
}

export default NursePatientDetail;
