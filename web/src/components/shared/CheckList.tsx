"use client";

// The check engine's findings: severity chip, plain-language text, and the item each one concerns.
// Shared by the pharmacist review panel and the doctor's live check panel (the same warnings, spec §2).
import { useT } from "@/i18n/I18nProvider";
import { checkText, SEVERITY_KEY, sortChecks } from "@/lib/pharmacy";
import type { Check, CheckSeverity, PrescriptionItem } from "@/lib/types";
import styles from "./Pharmacy.module.css";

const SEV_CLASS: Record<CheckSeverity, string> = {
  critical: styles.sevCritical,
  major: styles.sevMajor,
  moderate: styles.sevModerate,
  info: styles.sevInfo,
};

export function SeverityChip({ severity }: { severity: CheckSeverity }) {
  const { t } = useT();
  return <span className={`${styles.sev} ${SEV_CLASS[severity] ?? styles.sevInfo}`}>{t(SEVERITY_KEY[severity] ?? "pharmacy.sevInfo")}</span>;
}

export interface CheckListProps {
  checks: readonly Check[];
  /** The prescription's items, to name the item each check concerns. */
  items: readonly PrescriptionItem[];
  /** Shown when there is no check; omit to render nothing. */
  emptyText?: string;
}

export function CheckList({ checks, items, emptyText }: CheckListProps) {
  const { t } = useT();
  if (!checks.length) return emptyText ? <p className={styles.noChecks}>{emptyText}</p> : null;
  return (
    <ul className={styles.checks}>
      {sortChecks(checks).map((c, i) => {
        const item = c.item_index != null ? items[c.item_index] : undefined;
        return (
          <li key={`${c.code}-${c.item_index ?? "x"}-${i}`} className={`${styles.check} ${c.severity === "critical" ? styles.checkCritical : ""}`}>
            <SeverityChip severity={c.severity} />
            <span className={styles.checkBody}>
              <span dir="auto">{checkText(c, t)}</span>
              {item ? (
                <span dir="auto" className={styles.checkItem}>
                  {t("pharmacy.checkItem", { n: (c.item_index ?? 0) + 1, med: item.med })}
                </span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export default CheckList;
