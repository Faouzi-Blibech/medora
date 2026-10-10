"use client";

// Formulary combobox for the prescription form. Typing searches GET /drugs (active drugs only, 250 ms
// debounce). The doctor picks a drug, or keeps the typed text as a non-formulary drug (drug_id null).
// Typing again un-picks the choice. Mount it with a new `key` to reset it (form reset, "Edit and resubmit").
import { useEffect, useId, useState, type KeyboardEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import { listDrugs } from "@/lib/api";
import { drugLabel, FORM_KEY } from "@/lib/pharmacy";
import type { Drug } from "@/lib/types";
import { useDebounced } from "@/lib/useDebounced";
import styles from "./Prescriptions.module.css";

/** What the item will carry: the display string and the formulary id (null = non-formulary). */
export interface DrugChoice {
  med: string;
  drug_id: string | null;
}

type Option = { kind: "drug"; drug: Drug } | { kind: "free"; text: string };

export interface DrugPickerProps {
  /** Initial value (read on mount only). */
  value: DrugChoice | null;
  onChange: (choice: DrugChoice | null) => void;
  /** id of the visible label element. */
  labelId: string;
  /** Red border: missing, or a critical check on this item. */
  invalid?: boolean;
}

export function DrugPicker({ value, onChange, labelId, invalid = false }: DrugPickerProps) {
  const { t } = useT();
  const id = useId();
  const [text, setText] = useState(value?.med ?? "");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Drug[]>([]);
  const [active, setActive] = useState(0);
  const q = useDebounced(text.trim(), 250);

  useEffect(() => {
    if (!open || !q) {
      setResults([]);
      return;
    }
    let alive = true;
    listDrugs({ q, active: true }).then(
      (list) => {
        if (!alive) return;
        setResults(list.slice(0, 8));
        setActive(0);
      },
      () => {
        if (alive) setResults([]);
      },
    );
    return () => {
      alive = false;
    };
  }, [q, open]);

  const typed = text.trim();
  const options: Option[] = [...results.map((drug): Option => ({ kind: "drug", drug })), ...(typed ? [{ kind: "free", text: typed } as Option] : [])];
  const shown = open && options.length > 0;

  function pick(o: Option) {
    const choice: DrugChoice = o.kind === "drug" ? { med: drugLabel(o.drug), drug_id: o.drug.id } : { med: o.text, drug_id: null };
    onChange(choice);
    setText(choice.med);
    setOpen(false);
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, options.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && shown && options[active]) {
      e.preventDefault();
      pick(options[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className={styles.picker}>
      <input
        role="combobox"
        aria-labelledby={labelId}
        aria-expanded={shown}
        aria-controls={`${id}-list`}
        aria-autocomplete="list"
        aria-activedescendant={shown ? `${id}-opt-${active}` : undefined}
        aria-invalid={invalid || undefined}
        dir="auto"
        autoComplete="off"
        className={`${styles.input} ${invalid ? styles.inputBad : ""}`}
        placeholder={t("pharmacy.drugSearch")}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          onChange(null);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKey}
      />
      {shown ? (
        <ul id={`${id}-list`} role="listbox" className={styles.listbox}>
          {options.map((o, i) => (
            <li
              key={o.kind === "drug" ? o.drug.id : "free"}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              className={`${styles.option} ${i === active ? styles.optionOn : ""}`}
              onMouseDown={(e) => {
                e.preventDefault(); // keep the focus, so blur doesn't close the list before the pick
                pick(o);
              }}
            >
              {o.kind === "drug" ? (
                <>
                  <span dir="auto" className={styles.optMain}>
                    {drugLabel(o.drug)}
                  </span>
                  <span dir="auto" className={styles.optSub}>
                    {[t(FORM_KEY[o.drug.form] ?? "pharmacy.formOther"), o.drug.brand_names.join(", "), o.drug.high_alert ? t("pharmacy.highAlert") : ""]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </>
              ) : (
                <>
                  <span className={styles.optMain}>{t("pharmacy.nonFormulary")}</span>
                  <span dir="auto" className={styles.optSub}>
                    {o.text}
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default DrugPicker;
