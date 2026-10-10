"use client";

// Pharmacist / Worklist (/pharmacist): the list (urgent, then severity, then oldest) and the review panel
// of the selected row (?rx=). Refreshes on every prescription_status frame, or every 15 s without a socket.
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import { SeverityChip } from "@/components/shared/CheckList";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { Toast, useToast } from "@/components/Toast";
import { getWorklist } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live";
import { ago, now } from "@/lib/time";
import type { CheckSeverity, Prescription, ReviewDecision, WorklistItem, WorklistStatus } from "@/lib/types";
import { ReviewPanel } from "./ReviewPanel";
import styles from "./Pharmacist.module.css";

const FILTERS: [WorklistStatus, Key][] = [
  ["pending_pharmacy", "pharmacy.filterPending"],
  ["changes_requested", "pharmacy.filterChanges"],
  ["all", "pharmacy.filterAll"],
];
const SEVERITIES: CheckSeverity[] = ["critical", "major", "moderate", "info"];
const TOAST: Record<ReviewDecision, Key> = {
  validated: "pharmacy.toastValidated",
  changes_requested: "pharmacy.toastChanges",
  rejected: "pharmacy.toastRejected",
};

/** [severity, count] for the row chips, most severe first. */
function chipsOf(it: WorklistItem): [CheckSeverity, number][] {
  return SEVERITIES.map((s): [CheckSeverity, number] => [s, it.checks.filter((c) => c.severity === s).length]).filter(([, n]) => n > 0);
}

export function WorklistView() {
  const { t, lang } = useT();
  const router = useRouter();
  const pathname = usePathname();
  const selected = useSearchParams().get("rx");
  const [filter, setFilter] = useState<WorklistStatus>("pending_pharmacy");
  const [items, setItems] = useState<WorklistItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [toast, showToast] = useToast<string>(4500);

  const load = useCallback(() => {
    getWorklist(filter).then(
      (list) => {
        setItems(list);
        setFailed(false);
      },
      () => setFailed(true), // a failed refresh keeps the rows on screen
    );
  }, [filter]);
  useEffect(() => {
    setItems(null);
    load();
  }, [load]);
  useLiveRefresh(load, ["prescription_status"]);

  const select = useCallback(
    (id: string | null) => router.replace(id ? `${pathname}?rx=${encodeURIComponent(id)}` : pathname, { scroll: false }),
    [router, pathname],
  );

  // After a decision, open the next row, so a run of reviews stays at 3 steps or fewer each.
  const onDecided = useCallback(
    (rx: Prescription, decision: ReviewDecision) => {
      const list = items ?? [];
      const i = list.findIndex((x) => x.prescription.id === rx.id);
      const next = i >= 0 ? (list[i + 1] ?? list[i - 1] ?? null) : null;
      showToast(t(TOAST[decision], { name: i >= 0 ? list[i].doctor_name : "" }));
      select(next ? next.prescription.id : null);
      load();
    },
    [items, load, select, showToast, t],
  );

  const ref = now();
  return (
    <div className={styles.split}>
      <section className={styles.listCol} aria-label={t("pharmacy.worklistTitle")}>
        <div className={styles.segment} role="group" aria-label={t("pharmacy.filterAria")}>
          {FILTERS.map(([k, label]) => (
            <button
              key={k}
              type="button"
              aria-pressed={filter === k}
              className={`${styles.segBtn} ${filter === k ? styles.segOn : ""}`}
              onClick={() => setFilter(k)}
            >
              {t(label)}
            </button>
          ))}
        </div>
        {failed && !items ? (
          <ErrorCard title={t("pharmacy.worklistLoadError")} onRetry={load} secondaryLabel={null} />
        ) : !items ? (
          <div className="ward-skeleton" style={{ height: 180 }} aria-busy="true" />
        ) : items.length === 0 ? (
          <p className={styles.empty}>{t("pharmacy.worklistEmpty")}</p>
        ) : (
          <ul className={styles.rows}>
            {items.map((it) => {
              const on = it.prescription.id === selected;
              const chips = chipsOf(it);
              const where = it.patient.ward && it.patient.bed ? t("pharmacy.bedWard", { ward: it.patient.ward, bed: it.patient.bed }) : (it.patient.ward ?? it.patient.bed);
              const meta = [where, t("pharmacy.byDoctor", { name: it.doctor_name }), t("pharmacy.sentAgo", { ago: ago(it.waiting_since, ref, lang) })].filter(
                (x): x is string => !!x,
              );
              return (
                <li key={it.prescription.id}>
                  <button
                    type="button"
                    aria-current={on ? "true" : undefined}
                    className={`${styles.row} ${on ? styles.rowOn : ""} ${it.max_severity === "critical" ? styles.rowCrit : ""}`}
                    onClick={() => select(it.prescription.id)}
                  >
                    <span className={styles.rowTop}>
                      <span dir="auto" className={styles.rowName}>
                        {it.patient.name}
                      </span>
                      {it.urgent ? <span className={styles.urgent}>{t("pharmacy.urgentBadge")}</span> : null}
                    </span>
                    <span className={styles.rowMeta}>{meta.join(" · ")}</span>
                    <span className={styles.rowChips}>
                      {chips.length ? (
                        chips.map(([s, n]) => (
                          <span key={s} className={styles.chipWrap}>
                            <SeverityChip severity={s} />
                            {n > 1 ? <span className={styles.chipN}>{t("pharmacy.chipCount", { n })}</span> : null}
                          </span>
                        ))
                      ) : (
                        <span className={styles.noWarn}>{t("pharmacy.noWarnings")}</span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
      <section className={styles.panelCol}>
        {selected ? (
          <ReviewPanel key={selected} id={selected} onDecided={onDecided} onStale={load} />
        ) : (
          <p className={styles.pick}>{t("pharmacy.pickRow")}</p>
        )}
      </section>
      {toast ? <Toast>{toast}</Toast> : null}
    </div>
  );
}

export default WorklistView;
