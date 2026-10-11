"use client";

// Nurse / Med round (/nurse/meds): today's doses per patient, filters, and "Mark given"
// (records who and when through POST /doses/{id}/given — not in api.md yet).
import { useCallback, useEffect, useState } from "react";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { Toast, useToast } from "@/components/Toast";
import { useT } from "@/i18n/I18nProvider";
import { getAlerts, getMedRound, getPrescriptions, markDoseGiven } from "@/lib/api";
import { useDemoFlags } from "@/lib/demo";
import { now, tunisDate, tunisDay, tunisTime } from "@/lib/time";
import type { Alert, Dose, MedRoundGroup, Prescription } from "@/lib/types";
import { DosePill } from "./DosePill";
import { DosePharmacyNote, PendingReviewBadge } from "./PharmacyBadge";
import { PharmacyDeliveries } from "./PharmacyDeliveries";
import { allergyLabel, doseView, NURSE_ID, nurseStatus, wardLabel, type DoseContext } from "./nurse";
import styles from "./MedRound.module.css";

type Filter = "all" | "due" | "missed";

interface Data {
  groups: MedRoundGroup[];
  prescriptions: Map<string, Prescription>;
  alerts: Alert[];
}

export function MedRound() {
  const { t, lang } = useT();
  const flags = useDemoFlags();
  const [data, setData] = useState<Data | null>(null);
  const [failed, setFailed] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  /** Doses as they were before "Mark given" (keeps their filter and subline). */
  const [original, setOriginal] = useState<Record<string, Dose>>({});
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());
  const [notice, showNotice] = useToast<string>();

  const load = useCallback(() => {
    setFailed(false);
    getMedRound()
      .then(async (groups) => {
        const [rxLists, alerts] = await Promise.all([
          Promise.all(groups.map((g) => getPrescriptions(g.patient.id))),
          getAlerts().catch(() => [] as Alert[]),
        ]);
        setData({ groups, prescriptions: new Map(rxLists.flat().map((r) => [r.id, r])), alerts });
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(load, [load]);

  async function give(dose: Dose) {
    if (busy.has(dose.id)) return;
    setBusy((b) => new Set(b).add(dose.id));
    try {
      const updated = await markDoseGiven(dose.id, { by: NURSE_ID });
      setOriginal((o) => (o[dose.id] ? o : { ...o, [dose.id]: dose }));
      setData((d) =>
        d
          ? { ...d, groups: d.groups.map((g) => ({ ...g, doses: g.doses.map((x) => (x.id === dose.id ? updated : x)) })) }
          : d,
      );
    } catch {
      showNotice(t("nurse.doseSaveFailed"));
    } finally {
      setBusy((b) => {
        const next = new Set(b);
        next.delete(dose.id);
        return next;
      });
    }
  }

  const ref = now();
  const refIso = ref.toISOString();
  const ctx: DoseContext = { ref, t, prescriptions: data?.prescriptions, alerts: data?.alerts };
  const origOf = (d: Dose) => original[d.id] ?? d;
  const done = (d: Dose) => d.status === "taken";
  const inDue = (d: Dose) => {
    const s = nurseStatus(origOf(d), ref);
    return (s === "Due" || s === "Dispensed") && !done(d);
  };
  const inMissed = (d: Dose) => origOf(d).status === "missed";
  const matches = (d: Dose) => filter === "all" || (filter === "due" ? inDue(d) : inMissed(d));

  const all = data?.groups.flatMap((g) => g.doses) ?? [];
  const filters: [Filter, string][] = [
    ["all", t("nurse.filterAll")],
    ["due", t("nurse.filterDue", { n: all.filter(inDue).length })],
    ["missed", t("nurse.filterMissed", { n: all.filter(inMissed).length })],
  ];

  const groups = (flags.state === "empty" ? [] : (data?.groups ?? []))
    .map((g) => ({ ...g, doses: g.doses.filter(matches).sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at)) }))
    .filter((g) => g.doses.length > 0);
  const nextRound = all
    .filter((d) => nurseStatus(d, ref) === "Scheduled")
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))[0];

  const state = flags.state === "error" || failed ? "error" : flags.state === "loading" || (!data && flags.state !== "empty") ? "loading" : null;
  const ward = wardLabel(t, (data?.groups ?? []).map((g) => g.patient.ward));
  // The ward of the round's patients (the nurse's ward): the deliveries panel lists its dispensations.
  const roundWard = data?.groups.find((g) => g.patient.ward)?.patient.ward ?? null;
  const today = tunisDate(refIso);

  return (
    <div className={styles.page}>
      <div className={styles.head}>
        <div className={styles.titleBlock}>
          <h2 className={styles.title}>{t("nurse.medRound")}</h2>
          <span className={styles.sub}>
            {t("nurse.medSub", { day: tunisDay(refIso, lang), time: tunisTime(refIso) })}
            {ward ? <> · {ward}</> : null}
          </span>
        </div>
        <div className={styles.segment} role="group" aria-label={t("nurse.filterDoses")}>
          {filters.map(([k, label]) => (
            <button
              key={k}
              type="button"
              aria-pressed={filter === k}
              className={`${styles.segBtn} ${filter === k ? styles.segOn : ""}`}
              onClick={() => setFilter(k)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {roundWard && state === null ? <PharmacyDeliveries ward={roundWard} date={today} onReceived={load} /> : null}

      {state === "error" ? (
        <ErrorCard title={t("nurse.loadMedTitle")} onRetry={load} secondaryLabel={null} />
      ) : state === "loading" ? (
        Array.from({ length: 3 }, (_, i) => (
          <div key={i} className={styles.group} aria-busy="true">
            <div className={styles.groupHead}>
              <span className="ward-skeleton" style={{ height: 26, width: 64 }} />
              <span className="ward-skeleton" style={{ height: 18, width: 160 }} />
            </div>
            <div className={styles.skelRow}>
              <span className="ward-skeleton" style={{ height: 18, width: "100%" }} />
            </div>
            <div className={styles.skelRow}>
              <span className="ward-skeleton" style={{ height: 18, width: "100%" }} />
            </div>
          </div>
        ))
      ) : groups.length === 0 ? (
        <div className={styles.empty}>
          <span className={styles.emptyTitle}>{t("nurse.nothingHere")}</span>
          <span className={styles.emptyText}>
            {t("nurse.allDone")}
            {nextRound ? ` ${t("nurse.nextRound", { time: tunisTime(nextRound.scheduled_at) })}` : ""}
          </span>
        </div>
      ) : (
        groups.map((g) => {
          const allergic = g.patient.allergies.length > 0;
          return (
            <section key={g.patient.id} className={styles.group}>
              <div className={styles.groupHead}>
                <span className={styles.bed}>{g.patient.bed ?? "—"}</span>
                <span dir="auto" className={styles.name}>
                  {g.patient.first_name} {g.patient.last_name}
                </span>
                <span className={`${styles.allergy} ${allergic ? styles.allergyOn : ""}`}>{allergyLabel(g.patient.allergies, t)}</span>
                <span className={styles.spacer} />
                <span className={styles.dev}>
                  {g.device ? t(g.device.online ? "nurse.unitOnline" : "nurse.unitOffline", { id: g.device.id }) : t("nurse.noBedsideUnit")}
                </span>
              </div>
              <div className={styles.rows}>
                {g.doses.map((d) => {
                  const v = doseView(d, ctx, origOf(d));
                  return (
                    <div key={d.id} className={styles.row} style={{ background: v.status === "Missed" ? "var(--danger-row)" : "transparent" }}>
                      <span className={styles.time}>{v.time}</span>
                      <div className={styles.medCol}>
                        <span className={styles.med}>{v.med}</span>
                        <span className={styles.medSub} style={{ color: v.subAlert ? "var(--danger)" : "var(--muted)" }}>
                          {v.sub}
                        </span>
                        {v.pendingReview ? <PendingReviewBadge /> : null}
                        <DosePharmacyNote state={v.pharmacy} canGive={v.canGive} />
                      </div>
                      <span className={styles.slot}>{v.slot}</span>
                      <DosePill status={v.status} text={v.statusText} className={styles.pill} />
                      {v.canGive ? (
                        <button
                          type="button"
                          className={styles.give}
                          disabled={busy.has(d.id)}
                          aria-busy={busy.has(d.id) || undefined}
                          onClick={() => void give(d)}
                        >
                          {t("nurse.markGiven")}
                        </button>
                      ) : (
                        <span className={styles.by}>{v.by}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })
      )}
      {notice ? <Toast tone="warn">{notice}</Toast> : null}
    </div>
  );
}

export default MedRound;
