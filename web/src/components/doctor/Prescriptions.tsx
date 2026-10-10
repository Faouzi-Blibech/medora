"use client";

// Prescriptions card: the doctor's list (pharmacy status, the pharmacist's comment, "Edit and resubmit"),
// then the form: formulary picker (or a non-formulary name), dose and units, times, pill slot, the live
// check panel (the warnings the pharmacist will see, 400 ms after the last change), the override reason a
// critical warning requires, and "Urgent: start now". Saving sends the prescription to the pharmacist.
import { useMemo, useRef, useState, type ReactNode } from "react";
import { useT } from "@/i18n/I18nProvider";
import { Toast, useToast } from "@/components/Toast";
import { CheckList } from "@/components/shared/CheckList";
import { RxStatusBadge } from "@/components/shared/RxStatusBadge";
import { ApiError, createPrescription } from "@/lib/api";
import { doctorRows, hasCritical, isRunning, OVERRIDE_MAX, pendingSuccessor } from "@/lib/pharmacy";
import { pharmacyErrorKey } from "@/lib/pharmacyUi";
import { daysSince, now, tunisTime } from "@/lib/time";
import type { CheckRequest, Patient, Prescription, PrescriptionItem } from "@/lib/types";
import { DrugPicker, type DrugChoice } from "./DrugPicker";
import { checkKeyOf, usePrescriptionCheck } from "./usePrescriptionCheck";
import styles from "./Prescriptions.module.css";

const TIME_CHIPS = ["06:00", "08:00", "12:00", "14:00", "18:00", "20:00", "22:00"];
const SLOTS = ["1", "2", "3", "4", "r"] as const;
type SlotKey = (typeof SLOTS)[number];
const MAX_UNITS = 10;
const MAX_DAYS = 60;

const clampDays = (n: number) => Math.min(MAX_DAYS, Math.max(1, n));
const clampUnits = (n: number) => Math.min(MAX_UNITS, Math.max(1, n));

const drugName = (med: string) => med.split(" ")[0];

/** "" → null (no dose given); a positive number → the number; anything else → "bad". Accepts a decimal comma. */
function parseDose(raw: string): number | null | "bad" {
  const v = raw.trim().replace(",", ".");
  if (!v) return null;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : "bad";
}

interface Draft {
  choice: DrugChoice | null;
  doseMg: string;
  units: number;
  days: number;
  times: string[];
  slot: SlotKey | null;
  plan: string;
  urgent: boolean;
  override: string;
}

/** The row being edited: a new version of `rx` replaces its item `index`. */
interface Editing {
  rx: Prescription;
  index: number;
}

type FieldErrors = Partial<Record<"med" | "times" | "dose" | "override", boolean>>;

export interface PrescriptionsProps {
  patient: Patient;
  /** Every version from GET /patients/{id}/prescriptions; the list shows doctorRows() of them. */
  prescriptions: Prescription[];
  /** Doctor user id sent with the mutation (mock mode). */
  actorId: string;
  /** Called after a successful save so the page can refetch prescriptions and doses. */
  onSaved?: (rx: Prescription) => void;
  /** Shared doctor: the list stays, the edit buttons and the form go. */
  readOnly?: boolean;
}

export function Prescriptions({ patient, prescriptions, actorId, onSaved, readOnly = false }: PrescriptionsProps) {
  const { t } = useT();
  const formId = `rx-form-${patient.id}`;
  const blank = (): Draft => ({
    choice: null,
    doseMg: "",
    units: 1,
    days: 5,
    times: ["08:00"],
    slot: null,
    plan: t("doctor.defaultPlan"),
    urgent: false,
    override: "",
  });
  const visible = useMemo(() => doctorRows(prescriptions), [prescriptions]);
  const rows = useMemo(
    () => visible.flatMap((rx) => rx.items.map((item, index) => ({ key: `${rx.id}-${index}`, rx, item, index }))),
    [visible],
  );
  const [draft, setDraft] = useState<Draft>(blank);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [formKey, setFormKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  // The draft key the server answered 422 override_required for (the client preview had missed the critical check).
  const [serverCritical, setServerCritical] = useState<string | null>(null);
  const inflight = useRef(false); // set synchronously in save(): a double click can't send two requests
  const [toast, showToast] = useToast<{ tone: "ok" | "warn"; body: ReactNode }>(4500);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  // Slots held by every live or awaited version (not rejected ones); the item being edited frees its own.
  const slotMeds = useMemo(() => {
    const m: Partial<Record<SlotKey, string>> = {};
    for (const { rx, item, index } of rows) {
      if (rx.status === "rejected" || item.slot == null) continue;
      if (editing && editing.rx.id === rx.id && editing.index === index) continue;
      m[String(item.slot) as SlotKey] = drugName(item.med);
    }
    return m;
  }, [rows, editing]);
  const firstFree = (): SlotKey => SLOTS.find((k) => k !== "r" && !slotMeds[k]) ?? "r";
  const pickedSlot: SlotKey = draft.slot && (draft.slot === "r" || !slotMeds[draft.slot]) ? draft.slot : firstFree();
  const sortedTimes = [...draft.times].sort();
  const dose = parseDose(draft.doseMg);
  const med = draft.choice?.med.trim() ?? "";

  const item: PrescriptionItem | null =
    med && sortedTimes.length && dose !== "bad"
      ? {
          med,
          drug_id: draft.choice?.drug_id ?? null,
          dose_mg: dose,
          units_per_intake: draft.units,
          times: sortedTimes,
          slot: pickedSlot === "r" ? null : Number(pickedSlot),
          days: draft.days,
        }
      : null;
  const ed = editing;
  const items: PrescriptionItem[] | null = item ? (ed ? ed.rx.items.map((it, i) =>
          i === ed.index ? item : { ...it, days: clampDays(it.days), units_per_intake: clampUnits(it.units_per_intake ?? 1) },
        ) : [item]) : null;
  const checkReq: CheckRequest | null = items ? { patient_id: patient.id, items, ...(ed ? { replaces_id: ed.rx.id } : {}) } : null;
  const check = usePrescriptionCheck(readOnly ? null : checkReq);
  const itemIndex = ed?.index ?? 0;
  const criticalHere = !!check.checks?.some((c) => c.severity === "critical" && (c.item_index === null || c.item_index === itemIndex));
  // The preview is current only when it was computed for this very draft; Save waits for it.
  const checkKey = checkKeyOf(checkReq);
  const checkCurrent = !!checkReq && !check.checking && !check.failed && check.checkedKey === checkKey;
  const checkBlocks = !readOnly && !!checkReq && !checkCurrent;
  // The 422 flag only holds for the draft it was raised on: once the draft changes, the fresh check decides.
  // save() runs only when checkCurrent, so there `check.checks` is the check of this very draft; between
  // edits the previous result keeps the box on screen (no flicker) but Save is disabled.
  const needsOverride = hasCritical(check.checks) || (serverCritical !== null && serverCritical === checkKey);

  function reset() {
    setDraft(blank());
    setEditing(null);
    setErrors({});
    setServerCritical(null);
    setFormKey((k) => k + 1);
  }

  /** "Edit and resubmit" (changes requested) and "Edit" (validated): the form, pre-filled, as a new version. */
  function startEdit(rx: Prescription, index: number) {
    const it = rx.items[index];
    if (!it) return;
    setEditing({ rx, index });
    setDraft({
      choice: { med: it.med, drug_id: it.drug_id ?? null },
      doseMg: it.dose_mg != null ? String(it.dose_mg) : "",
      units: clampUnits(it.units_per_intake ?? 1),
      days: clampDays(it.days),
      times: [...it.times],
      slot: it.slot != null ? (String(it.slot) as SlotKey) : "r",
      plan: rx.care_plan,
      urgent: false,
      override: "",
    });
    setErrors({});
    setServerCritical(null);
    setFormKey((k) => k + 1);
    document.getElementById(formId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function firstDose(): string {
    if (!sortedTimes.length) return t("doctor.notScheduled");
    const hm = tunisTime(now().toISOString());
    const today = sortedTimes.find((x) => x > hm);
    return today ? t("doctor.todayAt", { time: today }) : t("doctor.tomorrowAt", { time: sortedTimes[0] });
  }

  async function save() {
    if (inflight.current || saving) return;
    if (checkBlocks) return; // the preview is stale, running or failed: the override gate can't be trusted
    const errs: FieldErrors = {
      med: !med,
      times: !draft.times.length,
      dose: dose === "bad",
      override: needsOverride && !draft.override.trim(),
    };
    if (errs.med || errs.times || errs.dose || errs.override || !items) {
      setErrors(errs);
      return;
    }
    inflight.current = true;
    setSaving(true);
    setErrors({});
    const slotText = pickedSlot === "r" ? t("doctor.reminderOnlyLower") : t("doctor.slotLower", { n: pickedSlot });
    const first = firstDose();
    try {
      const rx = await createPrescription(
        {
          patient_id: patient.id,
          items,
          care_plan: draft.plan.trim(),
          urgent: draft.urgent,
          ...(needsOverride ? { override_reason: draft.override.trim() } : {}),
          ...(ed ? { replaces_id: ed.rx.id } : {}),
        },
        { by: actorId },
      );
      showToast(
        rx.urgent
          ? {
              tone: rx.published_to_device ? "ok" : "warn",
              body: (
                <>
                  <b>{t("pharmacy.toastUrgentTitle")}</b>{" "}
                  {rx.published_to_device && patient.device_id
                    ? t("doctor.toastSentBody", { id: patient.device_id, slot: slotText, first })
                    : t("pharmacy.toastUrgentBody")}
                </>
              ),
            }
          : {
              tone: "ok",
              body: (
                <>
                  <b>{t("pharmacy.toastPendingTitle")}</b> {t("pharmacy.toastPendingBody")}
                </>
              ),
            },
      );
      reset();
      onSaved?.(rx);
    } catch (err) {
      if (err instanceof ApiError && err.code === "override_required") {
        setServerCritical(checkKey);
        setErrors({ override: true });
      }
      showToast({
        tone: "warn",
        body: (
          <>
            <b>{t("doctor.toastFailTitle")}</b> {t(pharmacyErrorKey(err) ?? "doctor.toastFailBody")}
          </>
        ),
      });
    } finally {
      inflight.current = false;
      setSaving(false);
    }
  }

  const sel = (on: boolean) => (on ? styles.on : "");
  const deviceLine = patient.device_id ? t("doctor.deviceHasSlots", { id: patient.device_id }) : t("doctor.noDeviceAssigned");

  return (
    <section className={styles.card}>
      <div className={styles.head}>
        <h3 className={styles.h3}>{t("doctor.rxTitle")}</h3>
        <span className={styles.sub}>
          {t("doctor.rxActive", { n: rows.filter((r) => isRunning(r.rx)).length })} · {deviceLine}
        </span>
      </div>
      <div className={`${styles.rxGrid} ${styles.th}`}>
        <span>{t("doctor.colMedicine")}</span>
        <span>{t("doctor.colTimes")}</span>
        <span>{t("doctor.colPillSlot")}</span>
        <span>{t("doctor.colDaysLeft")}</span>
        <span />
      </div>
      {rows.map(({ key, rx, item, index }) => {
        const live = isRunning(rx);
        const left = live ? Math.max(0, item.days - daysSince(rx.created_at)) : null;
        const successor = pendingSuccessor(rx, prescriptions);
        const sentBack = rx.status === "changes_requested" || rx.status === "rejected";
        const by = rx.doctor_id === patient.attending_doctor_id ? patient.attending_doctor_name : null;
        const note = sentBack
          ? rx.review_comment
            ? t("pharmacy.pharmacistSaid", { comment: rx.review_comment })
            : null
          : rx.override_reason
            ? t("pharmacy.overrideNote", { reason: rx.override_reason })
            : rx.allergy_override
              ? t("doctor.allergyOverride", { name: by ?? rx.doctor_id })
              : rx.care_plan || null;
        const alert = sentBack || !!rx.override_reason || !!rx.allergy_override;
        return (
          <div key={key} className={`${styles.rxGrid} ${styles.tr}`}>
            <div className={styles.medCell}>
              <span dir="auto" className={styles.med}>
                {item.med}
              </span>
              <span className={styles.badgeLine}>
                <RxStatusBadge status={rx.status} urgent={rx.urgent} />
                {rx.status === "validated" && rx.reviewed_by_name ? <span>{t("pharmacy.validatedBy", { name: rx.reviewed_by_name })}</span> : null}
                {successor ? <span>{t("pharmacy.newVersionPending")}</span> : null}
              </span>
              {note ? (
                <span dir="auto" className={styles.note} style={{ color: alert ? "var(--danger)" : "var(--muted)" }}>
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
            <span className={styles.days}>{left ?? "—"}</span>
            {readOnly ? (
              <span />
            ) : rx.status === "changes_requested" ? (
              <button type="button" className={`${styles.edit} ${styles.resubmit}`} disabled={saving} onClick={() => startEdit(rx, index)}>
                {t("pharmacy.editAndResubmit")}
              </button>
            ) : rx.status === "validated" && !successor ? (
              <button type="button" className={styles.edit} disabled={saving} onClick={() => startEdit(rx, index)}>
                {t("doctor.edit")}
              </button>
            ) : (
              <span />
            )}
          </div>
        );
      })}

      {readOnly ? null : (
        <div id={formId} className={styles.form}>
          <span className={styles.formTitle}>
            {ed ? t("pharmacy.editingTitle", { med: ed.rx.items[ed.index]?.med ?? "" }) : t("doctor.newRx")}
          </span>
          {ed ? (
            <div className={styles.editBanner}>
              <span>{t("pharmacy.editingHint")}</span>
              {ed.rx.review_comment ? (
                <b dir="auto">{t("pharmacy.pharmacistSaid", { comment: ed.rx.review_comment })}</b>
              ) : null}
            </div>
          ) : null}
          <div className={styles.formRow}>
            <div className={styles.field}>
              <span id={`${formId}-drug`} className={styles.fieldLabel}>
                {t("pharmacy.drugLabel")}
              </span>
              <DrugPicker key={formKey} labelId={`${formId}-drug`} value={draft.choice} invalid={!!errors.med || criticalHere} onChange={(c) => set("choice", c)} />
              {errors.med ? (
                <span role="alert" className={styles.fieldError}>
                  {t("pharmacy.pickDrug")}
                </span>
              ) : null}
            </div>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>{t("doctor.numberOfDays")}</span>
              <span className={styles.stepper}>
                <button type="button" onClick={() => set("days", Math.max(1, draft.days - 1))} aria-label={t("doctor.fewerDays")} className={styles.step}>
                  −
                </button>
                <span className={styles.stepValue}>{draft.days}</span>
                <button type="button" onClick={() => set("days", Math.min(MAX_DAYS, draft.days + 1))} aria-label={t("doctor.moreDays")} className={styles.step}>
                  +
                </button>
              </span>
            </label>
          </div>
          <div className={styles.formRow}>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>{t("pharmacy.doseMg")}</span>
              <input
                dir="ltr"
                inputMode="decimal"
                className={styles.input}
                value={draft.doseMg}
                placeholder={t("pharmacy.doseHint")}
                aria-invalid={errors.dose || undefined}
                onChange={(e) => set("doseMg", e.target.value)}
              />
              {errors.dose ? (
                <span role="alert" className={styles.fieldError}>
                  {t("pharmacy.errDose")}
                </span>
              ) : null}
            </label>
            <div className={styles.field}>
              <span id={`${formId}-units`} className={styles.fieldLabel}>
                {t("pharmacy.unitsPerIntake")}
              </span>
              <span className={styles.stepper} role="group" aria-labelledby={`${formId}-units`}>
                <button type="button" className={styles.step} aria-label={t("pharmacy.fewerUnits")} onClick={() => set("units", Math.max(1, draft.units - 1))}>
                  −
                </button>
                <span className={styles.stepValue}>{draft.units}</span>
                <button type="button" className={styles.step} aria-label={t("pharmacy.moreUnits")} onClick={() => set("units", Math.min(MAX_UNITS, draft.units + 1))}>
                  +
                </button>
              </span>
            </div>
          </div>
          {checkReq ? (
            <div className={styles.checkPanel} aria-live="polite">
              <span className={styles.checkHead}>
                {t("pharmacy.checksTitle")}
                {check.checking ? <span className={styles.checkLead}>{t("pharmacy.checking")}</span> : null}
              </span>
              {check.failed ? (
                <span className={styles.checkFailed}>{t("pharmacy.checkFailed")}</span>
              ) : check.checks ? (
                <CheckList checks={check.checks} items={checkReq.items} emptyText={t("pharmacy.noWarnings")} />
              ) : null}
              <span className={styles.checkLead}>{t("pharmacy.checksLead")}</span>
            </div>
          ) : null}
          {needsOverride ? (
            <label className={styles.field}>
              <span className={styles.fieldLabel}>{t("pharmacy.overrideLabel")}</span>
              <textarea
                rows={2}
                dir="auto"
                maxLength={OVERRIDE_MAX}
                value={draft.override}
                className={`${styles.textarea} ${styles.overrideBox}`}
                aria-invalid={errors.override || undefined}
                onChange={(e) => set("override", e.target.value)}
              />
              {errors.override ? (
                <span role="alert" className={styles.fieldError}>
                  {t("pharmacy.overrideRequired")}
                </span>
              ) : null}
            </label>
          ) : null}
          <div className={styles.group}>
            <span id={`${formId}-times`} className={styles.fieldLabel}>
              {t("doctor.timesOfDay")}
            </span>
            <div className={styles.chips} role="group" aria-labelledby={`${formId}-times`} aria-describedby={errors.times ? `${formId}-times-error` : undefined}>
              {TIME_CHIPS.map((tm) => {
                const on = draft.times.includes(tm);
                return (
                  <button
                    key={tm}
                    type="button"
                    aria-pressed={on}
                    onClick={() => {
                      set("times", on ? draft.times.filter((x) => x !== tm) : [...draft.times, tm]);
                      if (!on) setErrors((e) => ({ ...e, times: false }));
                    }}
                    className={`${styles.chip} ${sel(on)}`}
                  >
                    {tm}
                  </button>
                );
              })}
            </div>
            {errors.times ? (
              <span id={`${formId}-times-error`} role="alert" className={styles.fieldError}>
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
                    onClick={() => !taken && set("slot", k)}
                    className={`${styles.slot} ${taken ? styles.taken : sel(on)}`}
                  >
                    <span className={styles.slotName}>{k === "r" ? t("doctor.reminderOnly") : t("doctor.slotN", { n: k })}</span>
                    <span className={styles.slotSub}>
                      {k === "r" ? t("doctor.noPillLoaded") : taken ? t("doctor.inUse", { med: slotMeds[k] ?? "" }) : t("doctor.slotEmpty")}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t("doctor.carePlanNote")}</span>
            <textarea rows={2} value={draft.plan} onChange={(e) => set("plan", e.target.value)} dir="auto" className={styles.textarea} />
          </label>
          <label className={styles.urgentRow}>
            <input type="checkbox" checked={draft.urgent} onChange={(e) => set("urgent", e.target.checked)} />
            <span className={styles.urgentText}>
              {t("pharmacy.urgentLabel")}
              <span className={styles.urgentHint}>{t("pharmacy.urgentHint")}</span>
            </span>
          </label>
          <div className={styles.formBar}>
            <span className={styles.formHint}>{patient.device_id ? t("doctor.hintWithDevice", { id: patient.device_id }) : t("doctor.hintNoDevice")}</span>
            <button type="button" onClick={reset} disabled={saving} className={styles.secondary}>
              {t("doctor.cancel")}
            </button>
            <button type="button" onClick={() => void save()} disabled={saving || checkBlocks} className={styles.primary}>
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
