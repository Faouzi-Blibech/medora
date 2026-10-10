"use client";

// Small pharmacy notes on the nurse's dose rows. "Pending pharmacy review": an urgent prescription
// whose doses already go out while the pharmacist hasn't reviewed it (spec §2 urgent bypass).
import { useT } from "@/i18n/I18nProvider";
import styles from "./PharmacyBadge.module.css";

export function PendingReviewBadge() {
  const { t } = useT();
  return <span className={`${styles.badge} ${styles.pending}`}>{t("pharmacy.pendingReview")}</span>;
}
