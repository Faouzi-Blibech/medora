"use client";

// Admin / Waitlist (/admin/waitlist) and Admin / Waitlist confirm (/admin/waitlist?confirm=[id]).
// The shared Waitlist component, all specialties, acting as the signed-in admin (mock: Mme Gharbi).
// `?why=[id]` opens a row's "Why?" popover; `?state=empty|error` shows the States cards.
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import { Toast, useToast } from "@/components/Toast";
import { Waitlist } from "@/components/Waitlist";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { getWaitlist } from "@/lib/api";
import { useDemoFlags } from "@/lib/demo";
import { LANG_LABELS } from "@/lib/labels";
import type { Appointment } from "@/lib/types";
import page from "./AdminPage.module.css";
import styles from "./WaitlistView.module.css";

const csvCell = (v: unknown) => {
  let s = v == null ? "" : String(v);
  // Neutralise spreadsheet formulas (CSV injection).
  if (/^[=+\-@]/.test(s)) s = `'${s}`;
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

function toCsv(rows: Appointment[]): string {
  const head = ["id", "patient_id", "patient", "specialty", "language", "urgency_ai", "urgency_final", "source", "requested_at", "referral"];
  const lines = rows.map((a) =>
    [
      a.id,
      a.patient_id,
      a.patient_name,
      a.specialty,
      a.lang ? LANG_LABELS[a.lang] : "",
      a.urgency_ai,
      a.urgency_final,
      a.triage.source,
      a.created_at,
      a.referral_text,
    ]
      .map(csvCell)
      .join(","),
  );
  return [head.join(","), ...lines].join("\n");
}

export function WaitlistView() {
  const { t } = useT();
  const flags = useDemoFlags();
  const params = useSearchParams();
  const confirmId = params.get("confirm") ?? undefined;
  const whyId = params.get("why") ?? undefined;
  const [retryKey, setRetryKey] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [toast, showToast] = useToast<{ text: string; tone: "ok" | "warn" }>(5000);

  const exportCsv = () => {
    setExporting(true);
    getWaitlist({ fallback: flags.aiFallback })
      .then((rows) => {
        const url = URL.createObjectURL(new Blob([toCsv(rows)], { type: "text/csv;charset=utf-8" }));
        const a = document.createElement("a");
        a.href = url;
        a.download = "medora-waitlist.csv";
        a.click();
        URL.revokeObjectURL(url);
      })
      .catch(() => showToast({ text: t("admin.wlExportFail"), tone: "warn" }))
      .finally(() => setExporting(false));
  };

  return (
    <div className={page.page}>
      {confirmId ? (
        <h2 className={page.h2}>{t("admin.waitlist")}</h2>
      ) : (
        <div className={page.head}>
          <div className={page.titles}>
            <h2 className={page.h2}>{t("admin.waitlist")}</h2>
            <span className={page.sub}>{t("admin.wlSubtitle")}</span>
          </div>
          <button type="button" className={page.btn} onClick={exportCsv} disabled={exporting} aria-busy={exporting}>
            {t("admin.wlExport")}
          </button>
        </div>
      )}

      {flags.state === "empty" ? (
        <div className={styles.empty}>
          <span className={styles.emptyTitle}>{t("admin.wlNobody")}</span>
          <span className={styles.emptyText}>{t("admin.wlNobodyText")}</span>
          <button type="button" className={page.btn}>
            {t("admin.wlAddByHand")}
          </button>
        </div>
      ) : flags.state === "error" ? (
        <ErrorCard title={t("admin.wlLoadErrorCard")} onRetry={() => setRetryKey((k) => k + 1)} />
      ) : (
        <div className={styles.waitlist}>
          <Waitlist
            key={retryKey}
            caller="admin"
            actor="Mme Gharbi"
            actorId="u-0003"
            aiFallback={flags.aiFallback}
            confirmId={confirmId}
            whyId={whyId}
          />
        </div>
      )}

      {toast ? (
        <Toast tone={toast.tone} placement="fixed">
          {toast.text}
        </Toast>
      ) : null}
    </div>
  );
}

export default WaitlistView;
