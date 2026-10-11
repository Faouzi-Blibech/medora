"use client";

// Prescriptions card: active list, then the "New prescription" form (time chips, pill
// slots, allergy rule check) and the save toast.
import { useMemo, useState, type ReactNode } from "react";
import { useT } from "@/i18n/I18nProvider";
import { Toast, useToast } from "@/components/Toast";
import { createPrescription } from "@/lib/api";
import { daysSince, now, tunisTime } from "@/lib/time";
import type { Patient, Prescription } from "@/lib/types";
import styles from "./Prescriptions.module.css";

const TIME_CHIPS = ["06:00", "08:00", "12:00", "14:00", "18:00", "20:00", "22:00"];
const SLOTS = ["1", "2", "3", "4", "r"] as const;
type SlotKey = (typeof SLOTS)[number];
/** Rule check (fixed rule, not AI): penicillin-family names. */
const PENICILLIN_FAMILY = /amox|penic|ampic|augment/i;
const DEFAULT_MED = "Furosemide 40mg";

const drugName = (med: string) => med.split(" ")[0];

export interface PrescriptionsProps {
  patient: Patient;
  prescriptions: Prescription[];
  /** Doctor user id sent with the mutation (mock mode). */
  actorId: string;
  /** Called after a successful save so the page can refetch prescriptions and doses. */
  onSaved?: (rx: Prescription) => void;
  /** Shared doctor: the list stays, the edit buttons and the new-prescription form go. */
  readOnly?: boolean;
}

export function Prescriptions({ patient, prescriptions, actorId, onSaved, readOnly = false }: PrescriptionsProps) {
  const { t } = useT();
  const rows = useMemo(
    () => prescriptions.flatMap((rx) => rx.items.map((item, i) => ({ key: `${rx.id}-${i}`, rx, item }))),
    [prescriptions],
  );
  const slotMeds = useMemo(() => {
    const m: Partial<Record<SlotKey, string>> = {};
    for (const { item } of rows) if (item.slot != null) m[String(item.slot) as SlotKey] = drugName(item.med);
    return m;
  }, [rows]);
  const firstFree = (): SlotKey => SLOTS.find((k) => k !== "r" && !slotMeds[k]) ?? "r";

  const [med, setMed] = useState(DEFAULT_MED);
  const [days, setDays] = useState(5);
  const [times, setTimes] = useState<string[]>(["08:00"]);
  const [slot, setSlot] = useState<SlotKey | null>(null);
  const [plan, setPlan] = useState(() => t("doctor.defaultPlan"));
  const [saving, setSaving] = useState(false);
  const [timesError, setTimesError] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [toast, showToast] = useToast<{ tone: "ok" | "warn"; body: ReactNode }>(4500);

  const pickedSlot: SlotKey = slot && (slot === "r" || !slotMeds[slot]) ? slot : firstFree();
  const allergic = patient.allergies.some((a) => /penicillin/i.test(a));
  const allergyHit = allergic && PENICILLIN_FAMILY.test(med);
  const sortedTimes = [...times].sort();

  function reset() {
    setFormOpen(false);
    setMed(DEFAULT_MED);
    setDays(5);
    setTimes(["08:00"]);
    setTimesError(false);
    setSlot(null);
    setPlan(t("doctor.defaultPlan"));
  }

  function firstDose(): string {
    if (!sortedTimes.length) return t("doctor.notScheduled");
    const hm = tunisTime(now().toISOString());
    const today = sortedTimes.find((x) => x > hm);
    return today ? t("doctor.todayAt", { time: today }) : t("doctor.tomorrowAt", { time: sortedTimes[0] });
  }

  async function save() {
    if (!med.trim() || saving) return;
    if (!times.length) {
      setTimesError(true);
      return;
    }
    setSaving(true);
    const slotText = pickedSlot === "r" ? t("doctor.reminderOnlyLower") : t("doctor.slotLower", { n: pickedSlot });
    const first = firstDose();
    try {
      const rx = await createPrescription(
        {
          patient_id: patient.id,
          items: [{ med: med.trim(), times: sortedTimes, slot: pickedSlot === "r" ? null : Number(pickedSlot), days }],
          care_plan: plan.trim(),
        },
        { by: actorId },
      );
      if (rx.published_to_device && patient.device_id) {
        showToast({
          tone: "ok",
          body: (
            <>
              <b>{t("doctor.toastSentTitle")}</b> · {t("doctor.toastSentBody", { id: patient.device_id, slot: slotText, first })}
            </>
          ),
        });
      } else {
        showToast({
          tone: "warn",
          body: (
            <>
              <b>{t("doctor.toastSavedTitle")}</b> {t("doctor.toastSavedBody")}
            </>
          ),
        });
      }
      reset();
      onSaved?.(rx);
    } catch {
      showToast({
        tone: "warn",
        body: (
          <>
            <b>{t("doctor.toastFailTitle")}</b> {t("doctor.toastFailBody")}
          </>
        ),
      });
    } finally {
      setSaving(false);
    }
  }

  const sel = (on: boolean) => (on ? styles.on : "");
  const deviceLine = patient.device_id
    ? t("doctor.deviceHasSlots", { id: patient.device_id })
    : t("doctor.noDeviceAssigned");

  return (
    <section className={styles.card}>
      <div className={styles.head}>
        <h3 className={styles.h3}>{t("doctor.rxTitle")}</h3>
        <span className={styles.sub}>
          {t("doctor.rxActive", { n: rows.length })} · {deviceLine}
        </span>
      </div>
      <div className={`${styles.rxGrid} ${styles.th}`}>
        <span>{t("doctor.colMedicine")}</span>
        <span>{t("doctor.colTimes")}</span>
        <span>{t("doctor.colPillSlot")}</span>
        <span>{t("doctor.colDaysLeft")}</span>
        <span />
      </div>
      {rows.map(({ key, rx, item }) => {
        const left = Math.max(0, item.days - daysSince(rx.created_at));
        const override = !!rx.allergy_override;
        const by = rx.doctor_id === patient.attending_doctor_id ? patient.attending_doctor_name : null;
        const note = override ? t("doctor.allergyOverride", { name: by ?? rx.doctor_id }) : rx.care_plan;
        return (
          <div key={key} className={`${styles.rxGrid} ${styles.tr}`}>
            <div className={styles.medCell}>
              <span className={styles.med}>{item.med}</span>
              {note ? (
                <span className={styles.note} style={{ color: override ? "var(--danger)" : "var(--muted)" }}>
                  {note}
                </span>
              ) : null}
            </div>
            <div className={styles.times}>
              {item.times.map((tm) => (
                <span key={tm} className={styles.time}>
                  {tm}
                </span>
              ))}
            </div>
            <div className={styles.slotCell}>
              <span className={styles.cells} aria-hidden="true">
                {[1, 2, 3, 4].map((i) => (
                  <span key={i} className={styles.cell} style={{ background: i === item.slot ? "var(--ink)" : "transparent" }} />
                ))}
              </span>
              <span className={styles.slotLabel}>{item.slot != null ? t("doctor.slotN", { n: item.slot }) : t("doctor.reminderOnly")}</span>
            </div>
            <span className={styles.days}>{left}</span>
            {readOnly ? (
              <span />
            ) : (
              <button type="button" className={styles.edit}>
                {t("doctor.edit")}
              </button>
            )}
          </div>
        );
      })}

      {readOnly ? null : !formOpen ? (
        <button type="button" className={styles.addRx} onClick={() => setFormOpen(true)}>
          + {t("doctor.newRx")}
        </button>
      ) : (
      <div className={styles.form}>
        <span className={styles.formTitle}>{t("doctor.newRx")}</span>
        <div className={styles.formRow}>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t("doctor.medAndDose")}</span>
            <input
              value={med}
              onChange={(e) => setMed(e.target.value)}
              className={styles.input}
              style={{ borderColor: allergyHit ? "var(--danger)" : "var(--line-strong)" }}
              aria-invalid={allergyHit || undefined}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t("doctor.numberOfDays")}</span>
            <span className={styles.stepper}>
              <button type="button" onClick={() => setDays((d) => Math.max(1, d - 1))} aria-label={t("doctor.fewerDays")} className={styles.step}>
                −
              </button>
              <span className={styles.stepValue}>{days}</span>
              <button type="button" onClick={() => setDays((d) => Math.min(90, d + 1))} aria-label={t("doctor.moreDays")} className={styles.step}>
                +
              </button>
            </span>
          </label>
        </div>
        {allergyHit ? (
          <div role="alert" className={styles.rule}>
            <span className={styles.ruleDiamond} />
            <span>
              <b>{t("doctor.ruleTitle")}</b> {t("doctor.ruleBody")}
            </span>
          </div>
        ) : null}
        <div className={styles.group}>
          <span id="rx-times-label" className={styles.fieldLabel}>{t("doctor.timesOfDay")}</span>
          <div
            className={styles.chips}
            role="group"
            aria-labelledby="rx-times-label"
            aria-describedby={timesError ? "rx-times-error" : undefined}
          >
            {TIME_CHIPS.map((tm) => {
              const on = times.includes(tm);
              return (
                <button
                  key={tm}
                  type="button"
                  aria-pressed={on}
                  onClick={() => {
                    setTimes((s) => (on ? s.filter((x) => x !== tm) : [...s, tm]));
                    if (!on) setTimesError(false);
                  }}
                  className={`${styles.chip} ${sel(on)}`}
                >
                  {tm}
                </button>
              );
            })}
          </div>
          {timesError ? (
            <span id="rx-times-error" role="alert" className={styles.fieldError}>
              {t("doctor.pickOneTime")}
            </span>
          ) : null}
        </div>
        <div className={styles.group}>
          <span className={styles.fieldLabel}>{t("doctor.pillSlotOnUnit")}</span>
          <div className={styles.slots}>
            {SLOTS.map((k) => {
              const taken = k !== "r" && !!slotMeds[k];
              const on = pickedSlot === k;
              return (
                <button
                  key={k}
                  type="button"
                  disabled={taken}
                  aria-pressed={on}
                  onClick={() => !taken && setSlot(k)}
                  className={`${styles.slot} ${taken ? styles.taken : sel(on)}`}
                >
                  <span className={styles.slotName}>{k === "r" ? t("doctor.reminderOnly") : t("doctor.slotN", { n: k })}</span>
                  <span className={styles.slotSub}>{k === "r" ? t("doctor.noPillLoaded") : taken ? t("doctor.inUse", { med: slotMeds[k] ?? "" }) : t("doctor.slotEmpty")}</span>
                </button>
              );
            })}
          </div>
        </div>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t("doctor.carePlanNote")}</span>
          <textarea rows={2} value={plan} onChange={(e) => setPlan(e.target.value)} dir="auto" className={styles.textarea} />
        </label>
        <div className={styles.formBar}>
          <span className={styles.formHint}>
            {patient.device_id
              ? t("doctor.hintWithDevice", { id: patient.device_id })
              : t("doctor.hintNoDevice")}
          </span>
          <button type="button" onClick={reset} className={styles.secondary}>
            {t("doctor.cancel")}
          </button>
          <button type="button" onClick={save} disabled={saving} className={styles.primary}>
            {t("doctor.saveRx")}
          </button>
        </div>
      </div>
      )}
      {toast ? (
        <Toast tone={toast.tone} className={styles.toast}>
          {toast.body}
        </Toast>
      ) : null}
    </section>
  );
}

export default Prescriptions;
