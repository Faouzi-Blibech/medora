"use client";

// Add or edit one formulary drug (pharmacist, admin): a side panel. Allergy classes and interaction groups
// are tags (lower-case codes the check engine matches). Deactivating is allowed; deleting isn't (spec §5).
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import page from "@/components/admin/AdminPage.module.css";
import { createDrug, updateDrug } from "@/lib/api";
import { DRUG_FORMS, FORM_KEY } from "@/lib/pharmacy";
import { describePharmacyError } from "@/lib/pharmacyUi";
import type { Drug, DrugForm as DosageForm, DrugInput } from "@/lib/types";
import { codeTag, TagInput } from "./TagInput";
import styles from "./Pharmacist.module.css";

interface Draft {
  dci: string;
  brands: string[];
  form: DosageForm;
  strength: string;
  unitMg: string;
  maxDaily: string;
  atc: string;
  allergy: string[];
  groups: string[];
  highAlert: boolean;
  minStock: string;
  active: boolean;
}

function toDraft(d: Drug | null): Draft {
  if (!d)
    return { dci: "", brands: [], form: "tablet", strength: "", unitMg: "", maxDaily: "", atc: "", allergy: [], groups: [], highAlert: false, minStock: "0", active: true };
  return {
    dci: d.dci,
    brands: d.brand_names,
    form: d.form,
    strength: d.strength,
    unitMg: d.unit_mg != null ? String(d.unit_mg) : "",
    maxDaily: d.max_daily_mg != null ? String(d.max_daily_mg) : "",
    atc: d.atc_code,
    allergy: d.allergy_classes,
    groups: d.interaction_groups,
    highAlert: d.high_alert,
    minStock: String(d.min_stock),
    active: d.active,
  };
}

/** "" → null; a positive number (decimal comma accepted) → the number; anything else → undefined (invalid). */
function optionalPositive(raw: string): number | null | undefined {
  const v = raw.trim().replace(",", ".");
  if (!v) return null;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

/** The request body, or the message key of the first problem. */
function toInput(d: Draft): DrugInput | Key {
  if (!d.dci.trim() || !d.strength.trim()) return "pharmacy.errDrugRequired";
  const atc = d.atc.trim().toUpperCase();
  if (atc && atc.length !== 7) return "pharmacy.errAtc"; // the ATC code is optional: empty or 7 characters
  const unit = optionalPositive(d.unitMg);
  const max = optionalPositive(d.maxDaily);
  const min = d.minStock.trim() === "" ? 0 : Number(d.minStock);
  if (unit === undefined || max === undefined || !Number.isInteger(min) || min < 0) return "pharmacy.errNumber";
  return {
    dci: d.dci.trim(),
    brand_names: d.brands,
    form: d.form,
    strength: d.strength.trim(),
    unit_mg: unit,
    max_daily_mg: max,
    atc_code: atc,
    allergy_classes: d.allergy,
    interaction_groups: d.groups,
    high_alert: d.highAlert,
    min_stock: min,
    active: d.active,
  };
}

export interface DrugFormProps {
  /** null = a new drug. */
  drug: Drug | null;
  onSaved: (drug: Drug) => void;
  onClose: () => void;
}

export function DrugForm({ drug, onSaved, onClose }: DrugFormProps) {
  const { t } = useT();
  const [d, setD] = useState<Draft>(() => toDraft(drug));
  const [error, setError] = useState<Key | null>(null);
  const [busy, setBusy] = useState(false);
  const first = useRef<HTMLInputElement>(null);
  const close = useRef(onClose);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));

  useEffect(() => {
    close.current = onClose;
  });
  useEffect(() => {
    first.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const input = toInput(d);
    if (typeof input === "string") {
      setError(input);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSaved(drug ? await updateDrug(drug.id, input) : await createDrug(input));
    } catch (err) {
      setError(describePharmacyError(err, "drug"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className={styles.drawer} aria-labelledby="drug-form-title">
      <form className={styles.drawerForm} onSubmit={submit} noValidate>
        <div className={styles.drawerHead}>
          <h2 id="drug-form-title" className={styles.drawerTitle}>
            {drug ? t("pharmacy.editDrug") : t("pharmacy.addDrug")}
          </h2>
          <button type="button" className={page.btn} onClick={onClose}>
            {t("pharmacy.close")}
          </button>
        </div>
        <label className={page.field}>
          <span className={page.fieldLabel}>{t("pharmacy.fDci")}</span>
          <input ref={first} dir="auto" className={page.input} value={d.dci} onChange={(e) => set("dci", e.target.value)} />
        </label>
        <TagInput label={t("pharmacy.fBrands")} values={d.brands} onChange={(v) => set("brands", v)} />
        <div className={styles.pair}>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("pharmacy.fForm")}</span>
            <span className={page.selectWrap}>
              <select className={page.select} value={d.form} onChange={(e) => set("form", e.target.value as DosageForm)}>
                {DRUG_FORMS.map((f) => (
                  <option key={f} value={f}>
                    {t(FORM_KEY[f])}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("pharmacy.fStrength")}</span>
            <input dir="ltr" className={page.input} value={d.strength} onChange={(e) => set("strength", e.target.value)} />
          </label>
        </div>
        <div className={styles.pair}>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("pharmacy.fUnitMg")}</span>
            <input dir="ltr" inputMode="decimal" className={page.input} value={d.unitMg} onChange={(e) => set("unitMg", e.target.value)} />
          </label>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("pharmacy.fMaxDaily")}</span>
            <input dir="ltr" inputMode="decimal" className={page.input} value={d.maxDaily} onChange={(e) => set("maxDaily", e.target.value)} />
            <span className={page.help}>{t("pharmacy.fMaxDailyHint")}</span>
          </label>
        </div>
        <div className={styles.pair}>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("pharmacy.fAtc")}</span>
            <input dir="ltr" className={`${page.input} ${styles.mono}`} value={d.atc} onChange={(e) => set("atc", e.target.value)} />
          </label>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("pharmacy.fMinStock")}</span>
            <input dir="ltr" inputMode="numeric" className={page.input} value={d.minStock} onChange={(e) => set("minStock", e.target.value)} />
          </label>
        </div>
        <TagInput label={t("pharmacy.fAllergy")} values={d.allergy} normalize={codeTag} onChange={(v) => set("allergy", v)} />
        <TagInput label={t("pharmacy.fInteraction")} values={d.groups} normalize={codeTag} onChange={(v) => set("groups", v)} />
        <label className={styles.checkRow}>
          <input type="checkbox" checked={d.highAlert} onChange={(e) => set("highAlert", e.target.checked)} />
          {t("pharmacy.fHighAlert")}
        </label>
        <label className={styles.checkRow}>
          <input type="checkbox" checked={d.active} onChange={(e) => set("active", e.target.checked)} />
          {t("pharmacy.fActive")}
        </label>
        {error ? (
          <span role="alert" className={styles.error}>
            {t(error)}
          </span>
        ) : null}
        <button type="submit" className={page.btnPrimary} disabled={busy}>
          {t("pharmacy.save")}
        </button>
      </form>
    </aside>
  );
}

export default DrugForm;
