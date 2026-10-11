"use client";

// Nurse / Shift handover (/nurse/handover): one SBAR card per patient, drafted by rules from the last
// 8/12/24 h of the record (optional LLM narrative). The outgoing nurse reads it and confirms (api.md 1.15).
import { useCallback, useEffect, useState } from "react";
import { AiBadge } from "@/components/AiBadge";
import { News2Badge } from "@/components/News2Badge";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { useT } from "@/i18n/I18nProvider";
import type { Key, TFn } from "@/i18n/messages";
import { confirmHandover, getHandovers } from "@/lib/api";
import { tunisTime } from "@/lib/time";
import type { AlertKind, AlertSeverity, Handover, HandoverRange, HandoverRecCode, HandoverRecommendation, HandoverTrend } from "@/lib/types";
import { NURSE_ID } from "./nurse";
import styles from "./ShiftHandover.module.css";

const WINDOWS = [8, 12, 24] as const;

const TREND: Record<HandoverTrend, Key> = {
  rising: "nurse.hoTrendRising",
  falling: "nurse.hoTrendFalling",
  stable: "nurse.hoTrendStable",
};

const KIND: Record<AlertKind, Key> = {
  news2: "nurse.kindNews2",
  trend: "nurse.kindTrend",
  call_nurse: "nurse.kindCall",
  dose_missed: "nurse.kindMissed",
  device_offline: "nurse.kindOffline",
};

const SEV: Record<AlertSeverity, Key> = {
  low: "nurse.sevLow",
  medium: "nurse.sevMedium",
  high: "nurse.sevHigh",
  critical: "nurse.sevCritical",
};

const REC: Record<HandoverRecCode, { key: Key; tone: "danger" | "warn" | "info" | "ok" }> = {
  news2_high: { key: "nurse.hoRecNews2High", tone: "danger" },
  news2_rising: { key: "nurse.hoRecNews2Rising", tone: "warn" },
  open_alert: { key: "nurse.hoRecOpenAlert", tone: "danger" },
  missed_dose: { key: "nurse.hoRecMissedDose", tone: "warn" },
  no_vitals: { key: "nurse.hoRecNoVitals", tone: "warn" },
  pending_exam: { key: "nurse.hoRecPendingExam", tone: "info" },
  next_dose: { key: "nurse.hoRecNextDose", tone: "info" },
  routine: { key: "nurse.hoRecRoutine", tone: "ok" },
};

function recText(r: HandoverRecommendation, t: TFn, lang: string): string {
  const p = { ...r.params };
  if (r.code === "open_alert") {
    p.kind = KIND[p.kind as AlertKind] ? t(KIND[p.kind as AlertKind]) : String(p.kind);
    p.severity = SEV[p.severity as AlertSeverity] ? t(SEV[p.severity as AlertSeverity]).toLocaleLowerCase(lang) : String(p.severity);
  }
  return t(REC[r.code].key, p);
}

function Range({ label, r, unit = "" }: { label: string; r: HandoverRange | null; unit?: string }) {
  const { t } = useT();
  if (!r) return null;
  return (
    <li className={styles.vital}>
      <span className={styles.vitalLabel}>{label}</span>
      <span className={styles.vitalVal} dir="ltr">
        {r.min}–{r.max}
        {unit}
      </span>
      <span className={styles.vitalMeta}>
        {/* LRI…PDI keeps "98%" and "37°C" in reading order inside Arabic text */}
        {t("nurse.hoLatest", { v: `⁦${r.latest}${unit}⁩` })} · <span className={styles[`trend_${r.trend}`]}>{t(TREND[r.trend])}</span>
      </span>
    </li>
  );
}

function HandoverCard({ h, hours, onConfirmed }: { h: Handover; hours: number; onConfirmed: (h: Handover) => void }) {
  const { t, lang } = useT();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const s = h.situation;
  const b = h.background;
  const a = h.assessment;
  const c = h.confirmation;

  async function confirm() {
    if (busy) return;
    setBusy(true);
    setFailed(false);
    try {
      onConfirmed(await confirmHandover(h.patient.id, hours, { by: NURSE_ID, lang }));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  const sex = h.patient.sex ? ` · ${h.patient.sex}` : "";
  return (
    <article className={styles.card}>
      <header className={styles.cardHead}>
        <span className={styles.bed}>{s.bed ? t("nurse.hoBed", { bed: s.bed }) : t("nurse.hoNoBed")}</span>
        <div className={styles.who}>
          <span className={styles.name} dir="auto">
            {h.patient.first_name} {h.patient.last_name}
          </span>
          <span className={styles.meta}>
            {h.patient.age != null ? t("nurse.hoAge", { age: h.patient.age }) : ""}
            {sex}
          </span>
        </div>
        {s.latest_news2 != null ? <News2Badge score={s.latest_news2} pulse={false} /> : null}
        <AiBadge
          source={h.source}
          state={c ? "confirmed" : "needs_review"}
          stateLabel={c ? t("nurse.hoConfirmed") : undefined}
          className={styles.badge}
        />
      </header>

      {h.narrative && h.source === "llm" ? (
        <div className={styles.narrative}>
          <span className={styles.secLabel}>{t("nurse.hoNarrative")}</span>
          <p dir="auto">{h.narrative}</p>
        </div>
      ) : null}

      <div className={styles.sbar}>
        <section className={styles.sec}>
          <h3 className={styles.secTitle}>
            <span className={styles.letter}>S</span>
            {t("nurse.hoSituation")}
          </h3>
          <dl className={styles.dl}>
            <dt>{t("nurse.hoReason")}</dt>
            <dd dir="auto">{s.reason || t("nurse.hoNotRecorded")}</dd>
            <dt>{t("nurse.hoNews2")}</dt>
            <dd>
              {s.latest_news2 != null ? (
                <>
                  {s.latest_news2}
                  {s.news2_trend ? <> · <span className={styles[`trend_${s.news2_trend}`]}>{t(TREND[s.news2_trend])}</span></> : null}
                </>
              ) : (
                t("nurse.hoNoNews2")
              )}
            </dd>
          </dl>
        </section>

        <section className={styles.sec}>
          <h3 className={styles.secTitle}>
            <span className={styles.letter}>B</span>
            {t("nurse.hoBackground")}
          </h3>
          <dl className={styles.dl}>
            <dt>{t("nurse.hoAllergies")}</dt>
            <dd>
              {b.allergies.length ? (
                <span className={styles.allergies}>
                  {b.allergies.map((x) => (
                    <span key={x} className={styles.allergy} dir="auto">
                      {x}
                    </span>
                  ))}
                </span>
              ) : (
                t("nurse.hoNoAllergies")
              )}
            </dd>
            <dt>{t("nurse.hoMeds")}</dt>
            <dd>
              {b.meds.length ? (
                <ul className={styles.plain}>
                  {b.meds.map((m, i) => (
                    <li key={`${m.med}-${i}`} dir="auto">
                      {m.med}
                      {m.times.length ? <span className={styles.times}> · {m.times.join(", ")}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                t("nurse.hoNone")
              )}
            </dd>
            {b.care_plans.length ? (
              <>
                <dt>{t("nurse.hoCarePlan")}</dt>
                <dd dir="auto">{b.care_plans.join(" · ")}</dd>
              </>
            ) : null}
          </dl>
        </section>

        <section className={styles.sec}>
          <h3 className={styles.secTitle}>
            <span className={styles.letter}>A</span>
            {t("nurse.hoAssessment")}
          </h3>
          {a.vitals.count ? (
            <>
              <span className={styles.secLabel}>{t("nurse.hoVitals", { n: a.vitals.count })}</span>
              <ul className={styles.vitals}>
                <Range label={t("nurse.hoHr")} r={a.vitals.hr} />
                <Range label={t("nurse.hoSpo2")} r={a.vitals.spo2} unit="%" />
                <Range label={t("nurse.hoTemp")} r={a.vitals.temp} unit="°C" />
              </ul>
            </>
          ) : (
            <p className={styles.muted}>{t("nurse.hoNoVitals")}</p>
          )}
          <dl className={styles.dl}>
            <dt>{t("nurse.hoAlerts")}</dt>
            <dd>{t("nurse.hoAlertsLine", { raised: a.alerts.raised, acked: a.alerts.acked, open: a.alerts.open.length })}</dd>
            <dt>{t("nurse.hoDoses")}</dt>
            <dd>{t("nurse.hoDosesLine", { given: a.doses.given, missed: a.doses.missed.length })}</dd>
          </dl>
          <span className={styles.secLabel}>{t("nurse.hoNotes", { n: a.notes_count })}</span>
          {a.notes.length ? (
            <ul className={styles.notes}>
              {a.notes.map((n, i) => (
                <li key={`${n.created_at}-${i}`}>
                  <span className={styles.noteMeta}>
                    {tunisTime(n.created_at)}
                    {n.author_name ? ` · ${n.author_name}` : ""}
                  </span>
                  <span dir="auto">{n.text}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.muted}>{t("nurse.hoNoNotes")}</p>
          )}
        </section>

        <section className={styles.sec}>
          <h3 className={styles.secTitle}>
            <span className={styles.letter}>R</span>
            {t("nurse.hoRecommendation")}
          </h3>
          <ul className={styles.recs}>
            {h.recommendations.map((r, i) => (
              <li key={`${r.code}-${i}`} className={`${styles.rec} ${styles[`tone_${REC[r.code].tone}`]}`}>
                <span className={styles.recDot} aria-hidden />
                <span dir="auto">{recText(r, t, lang)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <footer className={styles.cardFoot}>
        {c ? (
          <div className={styles.confirmed}>
            <span className={styles.check} aria-hidden>
              ✓
            </span>
            {t("nurse.hoConfirmedBy", { name: c.human_confirmed_by_name ?? c.human_confirmed_by, time: tunisTime(c.confirmed_at) })}
          </div>
        ) : (
          <>
            <button type="button" className={styles.confirm} onClick={confirm} disabled={busy}>
              {t("nurse.hoConfirm")}
            </button>
            {failed ? (
              <span role="alert" className={styles.error}>
                {t("nurse.hoConfirmFailed")}
              </span>
            ) : null}
          </>
        )}
      </footer>
    </article>
  );
}

export function ShiftHandover() {
  const { t, lang } = useT();
  const [hours, setHours] = useState<number>(12);
  const [items, setItems] = useState<Handover[] | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    setFailed(false);
    setItems(null);
    getHandovers(hours, { lang })
      .then((r) => {
        setItems(r.items);
        setGeneratedAt(r.generated_at);
      })
      .catch(() => setFailed(true));
  }, [hours, lang]);

  useEffect(load, [load]);

  function confirmed(next: Handover) {
    setItems((list) => (list ? list.map((h) => (h.patient.id === next.patient.id ? next : h)) : list));
  }

  return (
    <div className={styles.page}>
      <div className={styles.head}>
        <div className={styles.titleBlock}>
          <h2 className={styles.title}>{t("nurse.hoTitle")}</h2>
          <span className={styles.sub}>
            {generatedAt ? t("nurse.hoSub", { time: tunisTime(generatedAt), h: hours }) : " "}
          </span>
        </div>
        <div className={`${styles.tools} ${styles.noPrint}`}>
          <div className={styles.segment} role="group" aria-label={t("nurse.hoWindow")}>
            {WINDOWS.map((w) => (
              <button
                key={w}
                type="button"
                aria-pressed={hours === w}
                className={`${styles.segBtn} ${hours === w ? styles.segOn : ""}`}
                onClick={() => setHours(w)}
              >
                {t("nurse.hoHours", { h: w })}
              </button>
            ))}
          </div>
          <button type="button" className={styles.print} onClick={() => window.print()} disabled={!items?.length}>
            {t("nurse.hoPrint")}
          </button>
        </div>
      </div>
      <p className={styles.disclaimer}>{t("nurse.hoDisclaimer")}</p>

      {failed ? (
        <ErrorCard title={t("nurse.hoLoadFailed")} onRetry={load} secondaryLabel={null} />
      ) : items === null ? (
        <div className={styles.list} aria-busy="true">
          {Array.from({ length: 2 }, (_, i) => (
            <div key={i} className={styles.card}>
              <span className="ward-skeleton" style={{ height: 26, width: 220 }} />
              <span className="ward-skeleton" style={{ height: 16, width: "90%" }} />
              <span className="ward-skeleton" style={{ height: 16, width: "75%" }} />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className={styles.empty}>
          <span className={styles.emptyTitle}>{t("nurse.hoEmpty")}</span>
          <span className={styles.emptyText}>{t("nurse.hoEmptyText", { h: hours })}</span>
        </div>
      ) : (
        <div className={`${styles.list} ward-stagger`}>
          {items.map((h) => (
            <HandoverCard key={h.patient.id} h={h} hours={hours} onConfirmed={confirmed} />
          ))}
        </div>
      )}
    </div>
  );
}

export default ShiftHandover;
