"use client";

// A doctor reviews the AI draft of one radiograph and signs the final report. The AI only suggests: nothing is
// stored as a report until the doctor confirms the text (human in the loop).
import { useEffect, useRef, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import { confirmRadiographReading, examFileUrl, getRadiographReading } from "@/lib/api";
import { tunisDay, tunisTime } from "@/lib/time";
import type { RadiographCondition, RadiographReading, ReadingStatus } from "@/lib/types";
import styles from "./RadiographReadingCard.module.css";

const POLL_MS = 4000;
const PENDING: ReadingStatus[] = ["queued", "running"];

const LIKELIHOOD_CLASS: Record<RadiographCondition["likelihood"], string> = {
  low: styles.likeLow,
  medium: styles.likeMedium,
  high: styles.likeHigh,
};
const LIKELIHOOD_KEY = { low: "radiology.likelihoodLow", medium: "radiology.likelihoodMedium", high: "radiology.likelihoodHigh" } as const;
const STATUS_KEY = {
  queued: "radiology.statusQueued",
  running: "radiology.statusRunning",
  ready: "radiology.statusReady",
  unavailable: "radiology.statusUnavailable",
  failed: "radiology.statusFailed",
} as const;

export function RadiographReadingCard({
  resultId,
  readOnly = false,
  onConfirmed,
  onStatus,
}: {
  resultId: string;
  /** A doctor with a read-only sharing grant sees the draft but cannot confirm (the server refuses it too). */
  readOnly?: boolean;
  onConfirmed?: () => void;
  /** Called when the reading's status changes (lets the exams list refresh its chip). */
  onStatus?: (status: ReadingStatus) => void;
}) {
  const { t, lang } = useT();
  const [reading, setReading] = useState<RadiographReading | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [text, setText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const [imgUrl, setImgUrl] = useState<string | null>(null);

  // Load, then poll while the AI is still queued/running.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function load() {
      try {
        const rd = await getRadiographReading(resultId);
        if (!alive) return;
        setReading(rd);
        setLoadFailed(false);
        if (PENDING.includes(rd.status)) timer = setTimeout(load, POLL_MS);
      } catch {
        // Show the error but keep trying on the next tick while mounted (a blip must not stop polling forever).
        if (!alive) return;
        setLoadFailed(true);
        timer = setTimeout(load, POLL_MS);
      }
    }
    void load();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [resultId]);

  // Tell the parent about status changes (the callback is read through a ref, so a new closure never re-fires it).
  const onStatusRef = useRef(onStatus);
  useEffect(() => {
    onStatusRef.current = onStatus;
  });
  const status = reading?.status;
  useEffect(() => {
    if (status) onStatusRef.current?.(status);
  }, [status]);

  // Prefill the report once the draft (or the signed text) arrives, unless the doctor already typed.
  const prefill = reading?.final_text ?? reading?.ai_suggested?.draft_text ?? "";
  useEffect(() => {
    if (!dirty) setText(prefill);
  }, [prefill, dirty]);

  // Image preview; blob: URLs (real backend) are revoked on unmount.
  useEffect(() => {
    let alive = true;
    let url: string | null = null;
    examFileUrl(resultId)
      .then((u) => {
        url = u;
        if (alive) setImgUrl(u);
        else if (u.startsWith("blob:")) URL.revokeObjectURL(u);
      })
      .catch(() => alive && setImgUrl(null));
    return () => {
      alive = false;
      if (url && url.startsWith("blob:")) URL.revokeObjectURL(url);
    };
  }, [resultId]);

  async function confirm() {
    if (saving || !text.trim()) return;
    setSaving(true);
    setSaveFailed(false);
    try {
      const rd = await confirmRadiographReading(resultId, text.trim());
      setReading(rd);
      setDirty(false);
      onConfirmed?.();
    } catch {
      setSaveFailed(true);
    } finally {
      setSaving(false);
    }
  }

  const ai = reading?.ai_suggested ?? null;
  const pending = reading ? PENDING.includes(reading.status) : true;
  const confirmedAt = reading?.confirmed_at;

  return (
    <div className={styles.card} aria-label={t("radiology.title")} role="region">
      <div className={styles.head}>
        <b className={styles.title}>{t("radiology.title")}</b>
        {/* Stable live region: it exists before the status text first appears or changes. */}
        <span aria-live="polite" className={styles.chipSlot}>
          {reading ? (
            <span className={`${styles.chip} ${pending ? styles.chipPending : styles.chipDone}`}>
              {pending ? <span className={styles.pulse} aria-hidden="true" /> : null}
              {reading.human_confirmed_by ? t("radiology.statusConfirmed") : t(STATUS_KEY[reading.status])}
            </span>
          ) : null}
        </span>
      </div>

      {/* The UI disclaimer is always shown; a different one from the model run is added below, never instead. */}
      <div className={styles.disclaimer} role="note">
        <p>{t("radiology.disclaimer")}</p>
        {ai?.disclaimer && ai.disclaimer !== t("radiology.disclaimer") ? <p dir="auto">{ai.disclaimer}</p> : null}
      </div>

      {imgUrl ? (
        <img className={styles.img} src={imgUrl} alt={t("radiology.imageAlt")} />
      ) : null}

      {loadFailed ? <p className={styles.warn} role="alert">{t("radiology.loadError")}</p> : null}
      {!reading && !loadFailed ? <span className="ward-skeleton" style={{ height: 80, width: "100%" }} /> : null}

      {ai && ai.source === "llm" ? (
        <div className={styles.ai}>
          {ai.urgent_flags?.length ? (
            <div className={styles.urgent}>
              <b className={styles.label}>{t("radiology.urgent")}</b>
              <div className={styles.chips}>
                {ai.urgent_flags.map((f) => (
                  <span key={f} className={styles.dangerChip}>{f}</span>
                ))}
              </div>
            </div>
          ) : null}
          <p className={styles.meta}>
            {ai.region ? <span><b>{t("radiology.region")}:</b> {ai.region}</span> : null}
            {ai.projection ? <span><b>{t("radiology.projection")}:</b> {ai.projection}</span> : null}
            {ai.quality ? <span><b>{t("radiology.quality")}:</b> {ai.quality}</span> : null}
          </p>
          {ai.model ? <span className={styles.caption}>{t("radiology.model", { model: ai.model })}</span> : null}
          {ai.findings?.length ? (
            <div>
              <b className={styles.label}>{t("radiology.findings")}</b>
              <ul className={styles.list}>
                {ai.findings.map((f, i) => (
                  <li key={i} dir="auto">{f}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {ai.possible_conditions?.length ? (
            <div>
              <b className={styles.label}>{t("radiology.conditions")}</b>
              <ul className={styles.list}>
                {ai.possible_conditions.map((c) => (
                  <li key={c.name} className={styles.cond}>
                    <span dir="auto">{c.name}</span>
                    <span className={`${styles.like} ${LIKELIHOOD_CLASS[c.likelihood]}`}>{t(LIKELIHOOD_KEY[c.likelihood])}</span>
                    {c.evidence ? <span className={styles.evidence} dir="auto">{c.evidence}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {ai.impression ? (
            <div>
              <b className={styles.label}>{t("radiology.impression")}</b>
              <p className={styles.text} dir="auto">{ai.impression}</p>
            </div>
          ) : null}
          {ai.recommendation ? (
            <div>
              <b className={styles.label}>{t("radiology.recommendation")}</b>
              <p className={styles.text} dir="auto">{ai.recommendation}</p>
            </div>
          ) : null}
        </div>
      ) : null}
      {ai && ai.source === "rules" ? (
        <p className={styles.note}>{reading?.status === "failed" ? t("radiology.statusFailed") : t("radiology.noModel")}</p>
      ) : null}

      {reading && !readOnly ? (
        <div className={styles.form}>
          {pending ? <p className={styles.note}>{t("radiology.draftRunning")}</p> : null}
          <label className={styles.label} htmlFor={`report-${resultId}`}>{t("radiology.report")}</label>
          <textarea
            id={`report-${resultId}`}
            className={styles.textarea}
            rows={12}
            dir="auto"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setDirty(true);
              setSaveFailed(false);
            }}
          />
          <div className={styles.actions}>
            <button type="button" className={styles.btn} disabled={saving || !text.trim()} onClick={() => void confirm()}>
              {t("radiology.confirm")}
            </button>
            {reading.human_confirmed_by && !dirty ? (
              <span className={styles.ok} role="status">
                {t("radiology.confirmed", {
                  name: reading.confirmed_by_name ?? reading.human_confirmed_by,
                  when: confirmedAt ? `${tunisDay(confirmedAt, lang)} ${tunisTime(confirmedAt)}` : "",
                })}
              </span>
            ) : null}
          </div>
          {saveFailed ? <p className={styles.warn} role="alert">{t("radiology.saveError")}</p> : null}
        </div>
      ) : null}
    </div>
  );
}

export default RadiographReadingCard;
