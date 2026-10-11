"use client";

// Tag list editor (brand names, allergy classes, interaction groups). Enter, a comma or an Arabic comma (،)
// adds the tag; × removes it; Backspace in an empty box removes the last one. Leaving the box keeps what was typed.
import { useState, type KeyboardEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import page from "@/components/admin/AdminPage.module.css";
import styles from "./Pharmacist.module.css";

export interface TagInputProps {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  /** Applied to each new tag; an empty result is dropped. Default: trim. */
  normalize?: (raw: string) => string;
}

/** Lower-case snake_case codes the check engine matches ("Beta Lactam" → "beta_lactam"). */
export const codeTag = (raw: string): string => raw.trim().toLowerCase().replace(/[\s-]+/g, "_");

const ADD_KEYS = new Set(["Enter", ",", "،"]);

export function TagInput({ label, values, onChange, normalize = (s) => s.trim() }: TagInputProps) {
  const { t } = useT();
  const [draft, setDraft] = useState("");

  function commit() {
    const v = normalize(draft);
    if (v && !values.includes(v)) onChange([...values, v]);
    setDraft("");
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (ADD_KEYS.has(e.key)) {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  }

  return (
    <div className={page.field}>
      <span className={page.fieldLabel}>{label}</span>
      <div className={styles.tagBox}>
        {values.map((v) => (
          <span key={v} className={styles.tag}>
            <span dir="auto">{v}</span>
            <button type="button" className={styles.tagX} aria-label={t("pharmacy.tagRemove", { tag: v })} onClick={() => onChange(values.filter((x) => x !== v))}>
              ×
            </button>
          </span>
        ))}
        <input dir="auto" aria-label={label} className={styles.tagEntry} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} onBlur={commit} />
      </div>
      <span className={page.help}>{t("pharmacy.tagHint")}</span>
    </div>
  );
}

export default TagInput;
