"use client";

// /nurse/patients — the design has no dedicated screen: the ward's patients as bed
// cards (same component as the board), in bed order. Each card opens the detail.
import { useCallback, useEffect, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import { pausedAt, USE_MOCKS } from "@/lib/time";
import { LiveBanner } from "@/components/LiveBanner";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { useLiveTick } from "@/components/shared/useLiveTick";
import { getWard } from "@/lib/api";
import { useDemoFlags } from "@/lib/demo";
import type { WardBed } from "@/lib/types";
import { BedCard, BedCardSkeleton } from "./BedCard";
import { byBed, wardLabel } from "./nurse";
import { useWardAlerts } from "./useWardAlerts";
import styles from "./NursePage.module.css";

export function PatientsView() {
  const { t } = useT();
  const flags = useDemoFlags();
  const { tick } = useLiveTick(flags.live && USE_MOCKS);
  const { alerts } = useWardAlerts();
  const [beds, setBeds] = useState<WardBed[] | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    setFailed(false);
    getWard()
      .then((list) => setBeds(list.filter((b) => b.patient).sort(byBed)))
      .catch(() => setFailed(true));
  }, []);

  useEffect(load, [load]);

  const state = flags.state === "error" || failed ? "error" : flags.state === "loading" || !beds ? "loading" : null;
  const callFor = (patientId: string) =>
    (alerts ?? []).find((a) => a.kind === "call_nurse" && a.patient_id === patientId && !a.acked_by);

  return (
    <div className={styles.page}>
      {!flags.live ? (
        <LiveBanner className={styles.banner}>{t("nurse.frozen", { time: pausedAt() })}</LiveBanner>
      ) : null}
      <div className={styles.head}>
        <h2 className={styles.title}>{t("nurse.patients")}</h2>
        <span className={styles.sub}>
          {[wardLabel(t, (beds ?? []).map((b) => b.patient?.ward)), beds && !state ? t("nurse.patientsBy", { n: beds.length }) : null]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </div>
      {state === "error" ? (
        <ErrorCard
          variant="box"
          title={t("nurse.loadWardTitle")}
          message={t("nurse.checkInPerson")}
          onRetry={load}
          className={styles.error}
        />
      ) : (
        <div className={`${styles.grid} ward-stagger`}>
          {state === "loading" || !beds
            ? Array.from({ length: 6 }, (_, i) => <BedCardSkeleton key={i} />)
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
  );
}

export default PatientsView;
