"use client";

// Small pharmacy notes on the nurse's dose rows. "Pending pharmacy review": an urgent prescription
// whose doses already go out while the pharmacist hasn't reviewed it (spec §2 urgent bypass).
import { useT } from "@/i18n/I18nProvider";
import type { PharmacyDelivery } from "@/lib/types";
import styles from "./PharmacyBadge.module.css";

export function PendingReviewBadge() {
  const { t } = useT();
  return <span className={`${styles.badge} ${styles.pending}`}>{t("pharmacy.pendingReview")}</span>;
}

/**
 * Phase B: where the dose comes from. "Not from the pharmacy" shows only while the dose can still be given:
 * the nurse may give it from ward stock (spec §5).
 */
export function DosePharmacyNote({ state, canGive }: { state: PharmacyDelivery | null; canGive: boolean }) {
  const { t } = useT();
  if (state === "sent") return <span className={`${styles.badge} ${styles.sent}`}>{t("pharmacy.pharmacySent")}</span>;
  if (state === "received") return <span className={`${styles.badge} ${styles.received}`}>{t("pharmacy.pharmacyReceived")}</span>;
  if (state === "none" && canGive) return <span className={styles.note}>{t("pharmacy.notFromPharmacy")}</span>;
  return null;
}
