"use client";

// Nurse / Ward board (/nurse), desktop 1440 and tablet 1024. Bed cards (highest NEWS2
// first), the alerts panel (a drawer on tablet), the red call banner (desktop) and the
// critical-alert toast (tablet).
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { LiveBanner } from "@/components/LiveBanner";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { useLiveTick } from "@/components/shared/useLiveTick";
import { Toast } from "@/components/Toast";
import { useT } from "@/i18n/I18nProvider";
import { getWard } from "@/lib/api";
import { useDemoFlags } from "@/lib/demo";
import { news2Word } from "@/lib/labels";
import { level } from "@/lib/news2";
import { pausedAt, tunisTime, tunisTimeSeconds, USE_MOCKS } from "@/lib/time";
import type { Alert, WardBed } from "@/lib/types";
import { AlertList, AlertSkeleton } from "./AlertList";
import { BedCard, BedCardSkeleton } from "./BedCard";
import { boardOrder, wardLabel } from "./nurse";
import { useWardAlerts } from "./useWardAlerts";
import styles from "./WardBoard.module.css";

const LEGEND: [number, "Normal" | "Low" | "High" | "Critical", string][] = [
  [0, "Normal", "0"],
  [2, "Low", "1–4"],
  [5, "High", "5–6"],
  [7, "Critical", "7+"],
];

const MUTE_MS = 60_000;

const newestOpen = (alerts: Alert[], pick: (a: Alert) => boolean) =>
  alerts.filter((a) => !a.acked_by && pick(a)).sort((a, b) => b.created_at.localeCompare(a.created_at))[0];

export function WardBoard() {
  const { t } = useT();
  const flags = useDemoFlags();
  const { tick } = useLiveTick(flags.live && USE_MOCKS);
  const wardAlerts = useWardAlerts();
  const { alerts, ack, busy, notes, notice } = wardAlerts;
  const [beds, setBeds] = useState<WardBed[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [muted, setMuted] = useState<string | null>(null);
  const muteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(() => {
    setFailed(false);
    getWard()
      .then((list) => setBeds(boardOrder(list)))
      .catch(() => setFailed(true));
  }, []);

  useEffect(load, [load]);
  useEffect(() => () => {
    if (muteTimer.current) clearTimeout(muteTimer.current);
  }, []);
  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer]);

  const retry = () => {
    load();
    wardAlerts.reload();
  };

  const forceEmpty = flags.state === "empty";
  const boardState = flags.state === "error" || failed ? "error" : flags.state === "loading" || !beds ? "loading" : null;
  const alertsState = flags.state === "error" || wardAlerts.failed ? "error" : flags.state === "loading" || !alerts ? "loading" : null;
  const list = alerts && !forceEmpty ? alerts : [];
  const openCount = list.filter((a) => !a.acked_by).length;

  const callAlert = newestOpen(list, (a) => a.kind === "call_nurse");
  const critAlert = newestOpen(list, (a) => a.kind !== "call_nurse" && a.severity === "critical");
  const callFor = (patientId: string) => newestOpen(list, (a) => a.kind === "call_nurse" && a.patient_id === patientId);
  const showCall = !!callAlert && muted !== callAlert.id && !boardState;

  const occupied = beds?.filter((b) => b.patient).length ?? 0;
  const emptyBeds = (beds?.length ?? 0) - occupied;

  function mute(id: string) {
    setMuted(id);
    if (muteTimer.current) clearTimeout(muteTimer.current);
    muteTimer.current = setTimeout(() => setMuted(null), MUTE_MS);
  }

  return (
    <div className={styles.board}>
      <div className={styles.main}>
        {!flags.live ? (
          <LiveBanner className={styles.banner}>{t("nurse.frozen", { time: pausedAt() })}</LiveBanner>
        ) : null}
        <div className={styles.head}>
          <div className={styles.titleBlock}>
            <h2 className={styles.title}>{wardLabel(t, (beds ?? []).map((b) => b.patient?.ward)) ?? t("nurse.wardBoard")}</h2>
            <span className={`${styles.sub} ${styles.desk}`}>
              {t(emptyBeds === 1 ? "nurse.boardSubOne" : "nurse.boardSubMany", { n: occupied, e: emptyBeds })}
            </span>
          </div>
          <div className={`${styles.legend} ${styles.desk}`}>
            {LEGEND.map(([s, word, range]) => {
              const lv = level(s);
              const label = `${news2Word(word, t)} ${range}`;
              return (
                <span key={label} className={styles.chip} style={{ background: lv.bg, color: lv.fg }}>
                  <span className={styles.chipDot} style={{ background: lv.edge }} />
                  {label}
                </span>
              );
            })}
          </div>
          <button
            type="button"
            className={`${styles.alertsBtn} ${styles.tab}`}
            aria-expanded={drawer}
            aria-controls="nurse-alerts"
            onClick={() => setDrawer(true)}
          >
            {t("nurse.alerts")}<span className={styles.alertsCount}>{openCount}</span>
          </button>
        </div>

        {boardState === "error" ? (
          <ErrorCard
            variant="box"
            title={t("nurse.loadWardTitle")}
            message={t("nurse.checkInPerson")}
            onRetry={retry}
            className={styles.error}
          />
        ) : (
          <div className={`${styles.grid} ward-stagger`}>
            {boardState === "loading" || !beds
              ? Array.from({ length: 8 }, (_, i) => <BedCardSkeleton key={i} />)
              : beds.map((b, i) => (
                  <BedCard
                    key={b.bed}
                    bed={b}
                    index={i}
                    live={flags.live}
                    tick={tick}
                    call={b.patient ? callFor(b.patient.id) : undefined}
                  />
                ))}
          </div>
        )}
      </div>

      <aside id="nurse-alerts" aria-label={t("nurse.alerts")} className={`${styles.aside} ${drawer ? styles.drawerOpen : ""}`}>
        <div className={styles.asideHead}>
          <h3 className={styles.asideTitle}>{t("nurse.alerts")}</h3>
          <span className={styles.openCount}>{t("nurse.openCount", { n: openCount })}</span>
          <span className={styles.spacer} />
          <span className={styles.newest}>{t("nurse.newestFirst")}</span>
          <button type="button" className={`${styles.close} ${styles.tab}`} onClick={() => setDrawer(false)}>
            {t("nurse.close")}
          </button>
        </div>
        {alertsState === "error" ? (
          <ErrorCard
            variant="box"
            title={t("nurse.loadAlertsTitle")}
            message={t("nurse.checkInPerson")}
            onRetry={wardAlerts.reload}
          />
        ) : alertsState === "loading" ? (
          <>
            <AlertSkeleton />
            <AlertSkeleton />
            <AlertSkeleton />
          </>
        ) : (
          <AlertList
            alerts={list}
            aiFallback={flags.aiFallback}
            notes={notes}
            busy={busy}
            onAck={(id) => void ack(id)}
            forceEmpty={forceEmpty}
          />
        )}
      </aside>
      {drawer ? <div className={`${styles.scrim} ${styles.tab}`} onClick={() => setDrawer(false)} aria-hidden="true" /> : null}

      {showCall && callAlert ? (
        <div role="alert" className={`${styles.call} ${styles.desk}`}>
          <div className={styles.callTop}>
            <div className={styles.callText}>
              <span className={styles.callTitle}>{t("nurse.bedCalling", { bed: callAlert.bed ?? "—" })}</span>
              <span dir="auto" className={styles.callSub}>
                {t("nurse.callRequestAt", { name: callAlert.patient_first_name ?? callAlert.patient_id, time: tunisTimeSeconds(callAlert.created_at) })}
              </span>
            </div>
          </div>
          <div className={styles.callActions}>
            <button
              type="button"
              className={styles.onMyWay}
              disabled={busy.has(callAlert.id)}
              onClick={() => void ack(callAlert.id, t("nurse.onMyWayNote"))}
            >
              {t("nurse.onMyWay")}
            </button>
            <button type="button" className={styles.mute} onClick={() => mute(callAlert.id)}>
              {t("nurse.snooze")}
            </button>
          </div>
        </div>
      ) : null}

      {critAlert && !boardState ? (
        <div role="alert" className={`${styles.critToast} ${styles.tab}`}>
          <div className={styles.critHead}>
            <span className={styles.critTag}>{t("nurse.critical")}</span>
            <span className={styles.critMeta}>
              {t(critAlert.kind === "news2" ? "nurse.news2Alert" : "nurse.alert")} · {tunisTime(critAlert.created_at)}
            </span>
          </div>
          <span dir="auto" className={styles.critTitle}>
            {t("nurse.bedName", { bed: critAlert.bed ?? "—", name: critAlert.patient_first_name ?? critAlert.patient_id })}
          </span>
          <span className={styles.critMsg}>{critAlert.message}</span>
          <div className={styles.critActions}>
            <button
              type="button"
              className={styles.critAck}
              disabled={busy.has(critAlert.id)}
              onClick={() => void ack(critAlert.id)}
            >
              {t("nurse.acknowledge")}
            </button>
            <Link href={`/nurse/patients/${encodeURIComponent(critAlert.patient_id)}`} className={styles.openBed}>
              {t("nurse.openBed")}
            </Link>
          </div>
        </div>
      ) : null}

      {notice ? <Toast tone="warn">{notice}</Toast> : null}
    </div>
  );
}

export default WardBoard;
