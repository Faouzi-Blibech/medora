"use client";

// Admin editor for one health event (create or edit), shown in the calendar's side column.
import { useState, type FormEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import { LANG_SHORT, LANGS, type Lang } from "@/i18n/config";
import type { Key } from "@/i18n/messages";
import { ApiError, createHealthEvent, updateHealthEvent } from "@/lib/api";
import { CATEGORY_LABEL, todayIso } from "@/lib/healthCalendar";
import { HEALTH_CATEGORIES, type HealthCategory, type HealthEvent, type HealthEventInput, type Role } from "@/lib/types";
import styles from "./HealthCalendar.module.css";

export interface EventFormProps {
  initial?: HealthEvent;
  onSaved: (ev: HealthEvent) => void;
  onCancel: () => void;
}

const ROLES: { role: Role; label: Key }[] = [
  { role: "patient", label: "calendar.rolePatient" },
  { role: "nurse", label: "calendar.roleNurse" },
  { role: "doctor", label: "calendar.roleDoctor" },
  { role: "admin", label: "calendar.roleAdmin" },
];

function blank(): HealthEventInput {
  const today = todayIso();
  return {
    title: { en: "", fr: "", ar: "" },
    description: { en: "", fr: "", ar: "" },
    category: "screening",
    starts_on: today,
    ends_on: today,
    audience: { roles: ["patient", "nurse", "doctor", "admin"], sex: null, min_age: null, max_age: null },
    notify_days_before: 3,
    organizer: null,
    source_url: null,
  };
}

function fromEvent(ev: HealthEvent): HealthEventInput {
  return {
    title: { ...ev.title },
    description: { ...ev.description },
    category: ev.category,
    starts_on: ev.starts_on,
    ends_on: ev.ends_on,
    audience: { ...ev.audience, roles: [...ev.audience.roles] },
    notify_days_before: ev.notify_days_before,
    organizer: ev.organizer,
    source_url: ev.source_url,
  };
}

/** "" → null, otherwise a whole number. */
function numOrNull(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Math.round(Number(v));
  return Number.isFinite(n) ? n : null;
}

export function EventForm({ initial, onSaved, onCancel }: EventFormProps) {
  const { t } = useT();
  const [input, setInput] = useState<HealthEventInput>(() => (initial ? fromEvent(initial) : blank()));
  const [error, setError] = useState<Key | null>(null);
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof HealthEventInput>(k: K, v: HealthEventInput[K]) => setInput((s) => ({ ...s, [k]: v }));
  const setText = (field: "title" | "description", lang: Lang, v: string) =>
    setInput((s) => ({ ...s, [field]: { ...s[field], [lang]: v } }));
  const setAudience = (patch: Partial<HealthEventInput["audience"]>) => setInput((s) => ({ ...s, audience: { ...s.audience, ...patch } }));
  const toggleRole = (role: Role, on: boolean) =>
    setAudience({ roles: on ? ROLES.map((r) => r.role).filter((r) => r === role || input.audience.roles.includes(r)) : input.audience.roles.filter((r) => r !== role) });

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (input.ends_on < input.starts_on) {
      setError("calendar.badDates");
      return;
    }
    setError(null);
    setBusy(true);
    const clean: HealthEventInput = {
      ...input,
      organizer: input.organizer?.trim() || null,
      source_url: input.source_url?.trim() || null,
    };
    try {
      const saved = initial ? await updateHealthEvent(initial.id, clean) : await createHealthEvent(clean);
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError && err.code === "bad_dates" ? "calendar.badDates" : "calendar.saveError");
    } finally {
      setBusy(false);
    }
  }

  const sexValue = input.audience.sex ?? "";

  return (
    <form className={`${styles.card} ${styles.form}`} onSubmit={(e) => void submit(e)}>
      <h2 className={styles.cardTitle}>{initial ? t("calendar.edit") : t("calendar.add")}</h2>

      {LANGS.map((l) => (
        <label key={`t-${l}`} className={styles.field}>
          <span className={styles.fieldLabel}>{t("calendar.fTitle", { lang: LANG_SHORT[l] })}</span>
          <input
            className={styles.input}
            dir={l === "ar" ? "rtl" : "ltr"}
            lang={l}
            required={l === "en"}
            value={input.title[l]}
            onChange={(e) => setText("title", l, e.target.value)}
          />
        </label>
      ))}
      {LANGS.map((l) => (
        <label key={`d-${l}`} className={styles.field}>
          <span className={styles.fieldLabel}>{t("calendar.fDesc", { lang: LANG_SHORT[l] })}</span>
          <textarea
            className={`${styles.input} ${styles.textarea}`}
            dir={l === "ar" ? "rtl" : "ltr"}
            lang={l}
            rows={3}
            value={input.description[l]}
            onChange={(e) => setText("description", l, e.target.value)}
          />
        </label>
      ))}

      <label className={styles.field}>
        <span className={styles.fieldLabel}>{t("calendar.fCategory")}</span>
        <select className={styles.input} value={input.category} onChange={(e) => set("category", e.target.value as HealthCategory)}>
          {HEALTH_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {t(CATEGORY_LABEL[c])}
            </option>
          ))}
        </select>
      </label>

      <div className={styles.row2}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("calendar.fStarts")}</span>
          <input className={styles.input} type="date" required value={input.starts_on} onChange={(e) => set("starts_on", e.target.value)} />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("calendar.fEnds")}</span>
          <input className={styles.input} type="date" required value={input.ends_on} onChange={(e) => set("ends_on", e.target.value)} />
        </label>
      </div>

      <fieldset className={styles.fieldset}>
        <legend className={styles.fieldLabel}>{t("calendar.fRoles")}</legend>
        <div className={styles.checks}>
          {ROLES.map((r) => (
            <label key={r.role} className={styles.check}>
              <input type="checkbox" checked={input.audience.roles.includes(r.role)} onChange={(e) => toggleRole(r.role, e.target.checked)} />
              <span>{t(r.label)}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <label className={styles.field}>
        <span className={styles.fieldLabel}>{t("calendar.fSex")}</span>
        <select
          className={styles.input}
          value={sexValue}
          onChange={(e) => setAudience({ sex: e.target.value === "F" || e.target.value === "M" ? e.target.value : null })}
        >
          <option value="">{t("calendar.sexAny")}</option>
          <option value="F">{t("calendar.sexF")}</option>
          <option value="M">{t("calendar.sexM")}</option>
        </select>
      </label>

      <div className={styles.row2}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("calendar.fMinAge")}</span>
          <input
            className={styles.input}
            type="number"
            min={0}
            max={130}
            inputMode="numeric"
            value={input.audience.min_age ?? ""}
            onChange={(e) => setAudience({ min_age: numOrNull(e.target.value) })}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("calendar.fMaxAge")}</span>
          <input
            className={styles.input}
            type="number"
            min={0}
            max={130}
            inputMode="numeric"
            value={input.audience.max_age ?? ""}
            onChange={(e) => setAudience({ max_age: numOrNull(e.target.value) })}
          />
        </label>
      </div>

      <label className={styles.field}>
        <span className={styles.fieldLabel}>{t("calendar.fNotifyDays")}</span>
        <input
          className={styles.input}
          type="number"
          min={0}
          max={30}
          inputMode="numeric"
          value={input.notify_days_before}
          onChange={(e) => set("notify_days_before", Math.min(30, Math.max(0, numOrNull(e.target.value) ?? 0)))}
        />
      </label>

      <label className={styles.field}>
        <span className={styles.fieldLabel}>{t("calendar.fOrganizer")}</span>
        <input className={styles.input} value={input.organizer ?? ""} onChange={(e) => set("organizer", e.target.value)} />
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>{t("calendar.fSource")}</span>
        <input
          className={styles.input}
          type="url"
          dir="ltr"
          inputMode="url"
          value={input.source_url ?? ""}
          onChange={(e) => set("source_url", e.target.value)}
        />
      </label>

      {error ? (
        <p role="alert" className={styles.formError}>
          {t(error)}
        </p>
      ) : null}

      <div className={styles.actions}>
        <button type="submit" className={styles.btnPrimary} disabled={busy}>
          {t("calendar.save")}
        </button>
        <button type="button" className={styles.btn} onClick={onCancel} disabled={busy}>
          {t("calendar.cancel")}
        </button>
      </div>
    </form>
  );
}

export default EventForm;
