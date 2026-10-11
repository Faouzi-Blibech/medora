"use client";

// "Phone view · Desktop view": flips the patient frame for the presenter (saved per user).
import { useT } from "@/i18n/I18nProvider";
import type { PatientLayout } from "@/lib/patientLayout";
import { useFrameLayout } from "./frameLayout";
import styles from "../LanguageSwitcher.module.css";

const OPTIONS: { key: PatientLayout; label: "patient.layoutPhone" | "patient.layoutDesktop" }[] = [
  { key: "phone", label: "patient.layoutPhone" },
  { key: "desktop", label: "patient.layoutDesktop" },
];

/** Same look as the language switcher: "dark" on the ink sidebar, "light" in the phone header. */
export function LayoutSwitch({ tone }: { tone: "dark" | "light" }) {
  const { t } = useT();
  const { layout, setLayout } = useFrameLayout();
  return (
    <div role="group" aria-label={t("patient.layoutLabel")} className={`${styles.root} ${styles[tone]}`}>
      {OPTIONS.map((o) => (
        <button
          key={o.key}
          type="button"
          aria-pressed={o.key === layout}
          className={styles.btn}
          onClick={() => o.key !== layout && setLayout(o.key)}
        >
          {t(o.label)}
        </button>
      ))}
    </div>
  );
}

export default LayoutSwitch;
