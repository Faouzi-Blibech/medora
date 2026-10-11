"use client";

// Nurse "Pharmacy deliveries" (med round): today's dispensations for the ward. A sent one gets "Confirm receipt"
// (POST /dispensations/{id}/receive: idempotent, own ward only). It polls every 15 s, because no frame announces a
// delivery. A 403 (another ward) hides the panel instead of showing an error.
import { useCallback, useEffect, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { Toast, useToast } from "@/components/Toast";
import { fmtWhen } from "@/lib/accountsUi";
import { ApiError, listDispensations, receiveDispensation } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live";
import { tunisTime } from "@/lib/time";
import type { Dispensation } from "@/lib/types";
import { NURSE_ID } from "./nurse";
import styles from "./PharmacyDeliveries.module.css";

export interface PharmacyDeliveriesProps {
  ward: string;
  /** YYYY-MM-DD (Tunis). */
  date: string;
  /** After a receipt: the round reloads, so the doses show "From the pharmacy". */
  onReceived: () => void;
}

export function PharmacyDeliveries({ ward, date, onReceived }: PharmacyDeliveriesProps) {
  const { t, lang } = useT();
  const [list, setList] = useState<Dispensation[] | null>(null);
  const [state, setState] = useState<"ok" | "failed" | "hidden">("ok");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, showNotice] = useToast<string>();

  const load = useCallback(() => {
    listDispensations({ ward, date }).then(
      (d) => {
        setList(d);
        setState("ok");
      },
      (err) => setState(err instanceof ApiError && err.status === 403 ? "hidden" : "failed"),
    );
  }, [ward, date]);
  useEffect(load, [load]);
  useLiveRefresh(load, [], { poll: "always" });

  async function receive(d: Dispensation) {
    if (busy) return;
    setBusy(d.id);
    try {
      await receiveDispensation(d.id, { by: NURSE_ID });
      onReceived();
    } catch {
      showNotice(t("pharmacy.receiveFailed"));
    } finally {
      setBusy(null);
      load();
    }
  }

  if (state === "hidden") return null;
  if (state === "failed" && !list) return <ErrorCard variant="box" title={t("pharmacy.deliveriesLoadError")} onRetry={load} />;
  if (!list) return null;

  return (
    <section className={styles.card} aria-labelledby="deliveries-title">
      <h3 id="deliveries-title" className={styles.title}>
        {t("pharmacy.deliveriesTitle")}
      </h3>
      {list.length === 0 ? <p className={styles.none}>{t("pharmacy.deliveriesNone")}</p> : null}
      {list.map((d) => (
        <div key={d.id} className={styles.row}>
          <div className={styles.main}>
            <span className={styles.line}>{t("pharmacy.deliveryLine", { time: d.round_time, n: d.lines.length, sent: tunisTime(d.prepared_at) })}</span>
            <details className={styles.details}>
              <summary>{t("pharmacy.deliveryShow")}</summary>
              <ul className={styles.lines}>
                {d.lines.map((l) => (
                  <li key={l.id} dir="auto">
                    {t("pharmacy.deliveryItem", { who: [l.bed, l.patient_name].filter(Boolean).join(" "), med: l.med, qty: l.quantity })}
                    {l.lot_number ? (
                      <span dir="ltr" className={styles.lot}>
                        {l.lot_number}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </details>
          </div>
          {d.status === "sent" ? (
            <button type="button" className={styles.confirm} disabled={busy === d.id} aria-busy={busy === d.id || undefined} onClick={() => void receive(d)}>
              {t("pharmacy.confirmReceipt")}
            </button>
          ) : (
            <span className={styles.received}>
              {t("pharmacy.receivedAt", { when: fmtWhen(d.received_at ?? d.prepared_at, lang), name: d.received_by_name ?? d.received_by ?? "" })}
            </span>
          )}
        </div>
      ))}
      {notice ? <Toast tone="warn">{notice}</Toast> : null}
    </section>
  );
}

export default PharmacyDeliveries;
