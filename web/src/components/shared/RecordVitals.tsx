"use client";

// "Record vitals": a reading taken by hand on a nurse round (POST /patients/{id}/vitals). It is scored with
// NEWS2 and alerted like a bedside-feed reading, and it shows in the charts with the other readings.
import { useState, type FormEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import { recordVitals } from "@/lib/api";
import type { Vital } from "@/lib/types";
import styles from "./RecordVitals.module.css";

const num = (s: string) => (s.trim() === "" ? null : Number(s.replace(",", ".")));

export function RecordVitals({ patientId, onRecorded }: { patientId: string; onRecorded: (v: Vital) => void }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ hr: "", spo2: "", temp: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = { hr: num(f.hr), spo2: num(f.spo2), temp: num(f.temp) };
    if (body.hr == null && body.spo2 == null && body.temp == null) {
      setError(t("shared.rvNeedOne"));
      return;
    }
    if ([body.hr, body.spo2, body.temp].some((x) => x != null && Number.isNaN(x))) {
      setError(t("shared.rvInvalid"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const v = await recordVitals(patientId, {
        hr: body.hr == null ? null : Math.round(body.hr),
        spo2: body.spo2 == null ? null : Math.round(body.spo2),
        temp: body.temp,
      });
      onRecorded(v);
      setF({ hr: "", spo2: "", temp: "" });
      setOpen(false);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch {
      setError(t("shared.rvFailed"));
    } finally {
      setBusy(false);
    }
  }

  if (!open)
    return (
      <div className={styles.bar}>
        <button type="button" className={styles.open} onClick={() => setOpen(true)}>
          {t("shared.rvButton")}
        </button>
        {saved ? (
          <span role="status" className={styles.saved}>
            {t("shared.rvSaved")}
          </span>
        ) : null}
      </div>
    );

  const field = (k: "hr" | "spo2" | "temp", label: string, unit: string, placeholder: string) => (
    <label className={styles.field}>
      <span className={styles.label}>{label}</span>
      <span className={styles.inputWrap}>
        <input
          inputMode="decimal"
          dir="ltr"
          className={styles.input}
          value={f[k]}
          placeholder={placeholder}
          onChange={(e) => setF({ ...f, [k]: e.target.value })}
        />
        <span className={styles.unit}>{unit}</span>
      </span>
    </label>
  );

  return (
    <form className={styles.form} onSubmit={submit} aria-label={t("shared.rvButton")}>
      <div className={styles.fields}>
        {field("hr", t("doctor.heartRate"), "bpm", "80")}
        {field("spo2", "SpO2", "%", "97")}
        {field("temp", t("doctor.temperature"), "°C", "36.8")}
      </div>
      {error ? (
        <span role="alert" className={styles.error}>
          {error}
        </span>
      ) : null}
      <div className={styles.actions}>
        <span className={styles.hint}>{t("shared.rvHint")}</span>
        <button type="button" className={styles.cancel} onClick={() => setOpen(false)} disabled={busy}>
          {t("shared.rvCancel")}
        </button>
        <button type="submit" className={styles.save} disabled={busy}>
          {busy ? t("shared.rvSaving") : t("shared.rvSave")}
        </button>
      </div>
    </form>
  );
}

export default RecordVitals;
