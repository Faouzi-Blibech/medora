"use client";

// A prescription's pharmacy status as a coloured pill (doctor list, pharmacist panel).
import { useT } from "@/i18n/I18nProvider";
import { STATUS_KEY } from "@/lib/pharmacy";
import type { PrescriptionStatus } from "@/lib/types";
import styles from "./Pharmacy.module.css";

const TONE: Record<PrescriptionStatus, string> = {
  pending_pharmacy: styles.stPending,
  validated: styles.stValidated,
  changes_requested: styles.stChanges,
  rejected: styles.stRejected,
  stopped: styles.stClosed,
  superseded: styles.stClosed,
};

export function RxStatusBadge({ status, urgent = false }: { status: PrescriptionStatus; urgent?: boolean }) {
  const { t } = useT();
  const pendingUrgent = status === "pending_pharmacy" && urgent;
  return (
    <span className={`${styles.status} ${pendingUrgent ? styles.stUrgent : (TONE[status] ?? styles.stClosed)}`}>
      {t(pendingUrgent ? "pharmacy.statusPendingUrgent" : (STATUS_KEY[status] ?? "pharmacy.statusPending"))}
    </span>
  );
}

export default RxStatusBadge;
