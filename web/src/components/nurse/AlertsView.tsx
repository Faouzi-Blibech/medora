"use client";

// /nurse/alerts — the design has no dedicated screen: the board's alerts panel as a page.
import { useT } from "@/i18n/I18nProvider";
import { pausedAt } from "@/lib/time";
import { LiveBanner } from "@/components/LiveBanner";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { Toast } from "@/components/Toast";
import { useDemoFlags } from "@/lib/demo";
import { AlertList, AlertSkeleton } from "./AlertList";
import { wardLabel } from "./nurse";
import { useWardAlerts } from "./useWardAlerts";
import styles from "./NursePage.module.css";

export function AlertsView() {
  const { t } = useT();
  const flags = useDemoFlags();
  const { alerts, failed, reload, ack, busy, notes, notice } = useWardAlerts();
  const forceEmpty = flags.state === "empty";
  const state = flags.state === "error" || failed ? "error" : flags.state === "loading" || !alerts ? "loading" : null;
  const ward = wardLabel(t);
  const openCount = forceEmpty ? 0 : (alerts ?? []).filter((a) => !a.acked_by).length;

  return (
    <div className={styles.page}>
      {!flags.live ? (
        <LiveBanner className={styles.banner}>{t("nurse.frozen", { time: pausedAt() })}</LiveBanner>
      ) : null}
      <div className={styles.head}>
        <h2 className={styles.title}>{t("nurse.alerts")}</h2>
        <span className={styles.sub}>
          {/* Alerts carry no ward: real mode leaves the ward out rather than guess it. */}
          {[ward, state ? null : t("nurse.openNewest", { n: openCount })].filter(Boolean).join(" · ")}
        </span>
      </div>
      <div className={`${styles.list} ward-stagger`}>
        {state === "error" ? (
          <ErrorCard
            variant="box"
            title={t("nurse.loadAlertsTitle")}
            message={t("nurse.checkInPerson")}
            onRetry={reload}
          />
        ) : state === "loading" || !alerts ? (
          <>
            <AlertSkeleton />
            <AlertSkeleton />
            <AlertSkeleton />
          </>
        ) : (
          <AlertList
            alerts={alerts}
            aiFallback={flags.aiFallback}
            notes={notes}
            busy={busy}
            onAck={(id) => void ack(id)}
            forceEmpty={forceEmpty}
          />
        )}
      </div>
      {notice ? <Toast tone="warn">{notice}</Toast> : null}
    </div>
  );
}

export default AlertsView;
