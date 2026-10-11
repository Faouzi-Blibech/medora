"use client";

// Pharmacist / Dispensing (/pharmacist/dispensing). Pick a date, a round and a ward, and see the doses due
// (active prescriptions only). Each formulary line gets ONE lot: by default the first-expiring lot that still
// holds the whole line (FEFO, simulated with planLots exactly as the server does it); the pharmacist may pick
// another lot. "Prepare and send" posts one dispensation per ward, with an explicit lot for every formulary line.
// Shortages show before sending; the server re-checks (409 insufficient_stock: nothing written).
import { useEffect, useMemo, useRef, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import page from "@/components/admin/AdminPage.module.css";
import { WARD_OPTIONS } from "@/components/admin/wards";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { Toast, useToast } from "@/components/Toast";
import { ApiError, createDispensation, getDispensing, getStock } from "@/lib/api";
import { expiryState, fefoLots, ltr, nextRound, planLots, ROUND_TIMES, stockDay } from "@/lib/pharmacy";
import { describePharmacyError, shortDrugId } from "@/lib/pharmacyUi";
import { now, tunisDate, tunisTime } from "@/lib/time";
import type { DispensingWard, RoundDose, StockItem, StockLot } from "@/lib/types";
import { refreshPharmacySummary } from "./usePharmacySummary";
import styles from "./Pharmacist.module.css";

interface LotSelectProps {
  dose: RoundDose;
  /** The drug's lots (any order); only those usable on `date` that hold the whole line are offered. */
  lots: readonly StockLot[];
  /** The day the lots must still be valid on: stockDay(round date, today). */
  date: string;
  /** The planned lot, or null when none fits (after the lines above took their share). */
  value: string | null;
  onChange: (lotId: string) => void;
}

/** FEFO lot choice for one dose: the first-expiring lot is listed first and marked; expiring lots are amber. */
function LotSelect({ dose, lots, date, value, onChange }: LotSelectProps) {
  const { t } = useT();
  const usable = fefoLots(lots, date).filter((l) => l.quantity >= dose.quantity);
  if (!usable.length) return <span className={styles.error}>{t("pharmacy.noLot")}</span>;
  // No planned lot (the lines above used up the one picked here): keep the select so another lot can be chosen.
  const chosen = value ? usable.find((l) => l.id === value) ?? null : null;
  return (
    <span className={page.selectWrap}>
      <select
        aria-label={t("pharmacy.colLot")}
        aria-invalid={!chosen || undefined}
        className={`${page.select} ${chosen && expiryState(chosen.expiry_date, date) === "expiring" ? styles.lotExpiring : ""}`}
        value={chosen?.id ?? ""}
        onChange={(e) => e.target.value && onChange(e.target.value)}
      >
        {!chosen ? <option value="">{t("pharmacy.noLot")}</option> : null}
        {usable.map((l, i) => (
          <option key={l.id} value={l.id}>
            {t(i === 0 ? "pharmacy.lotOptionFefo" : "pharmacy.lotOption", { lot: ltr(l.lot_number), date: ltr(l.expiry_date), qty: l.quantity })}
          </option>
        ))}
      </select>
    </span>
  );
}

export function DispensingView() {
  const { t } = useT();
  const today = tunisDate(now().toISOString());
  const [date, setDate] = useState(today);
  const [round, setRound] = useState(() => nextRound(tunisTime(now().toISOString())));
  const [ward, setWard] = useState("");
  const [data, setData] = useState<DispensingWard[] | null>(null);
  const [stock, setStock] = useState<StockItem[]>([]);
  const [failed, setFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [skipped, setSkipped] = useState<ReadonlySet<string>>(new Set());
  const [busyWard, setBusyWard] = useState<string | null>(null);
  const sending = useRef(false); // double-click guard: state updates are not visible to a second click in the same tick
  const [toast, showToast] = useToast<{ text: string; tone: "ok" | "warn" }>(5000);

  useEffect(() => {
    let alive = true;
    setData(null);
    setFailed(false);
    setChosen({});
    setSkipped(new Set());
    Promise.all([getDispensing({ date, round, ...(ward ? { ward } : {}) }), getStock()]).then(
      ([wards, items]) => {
        if (!alive) return;
        setData(wards);
        setStock(items);
      },
      () => {
        if (alive) setFailed(true);
      },
    );
    return () => {
      alive = false;
    };
  }, [date, round, ward, reload]);

  // Lots must still be valid on the later of the round date and today (the server's rule).
  const lotDay = stockDay(date, today);
  const lotsByDrug = useMemo(() => new Map(stock.map((r) => [r.drug_id, r.lots])), [stock]);
  const drugName = (id: string) => {
    const r = stock.find((x) => x.drug_id === id);
    return r ? `${r.dci} ${r.strength}` : id;
  };
  const wardLabel = (w: string) => {
    const o = WARD_OPTIONS.find((x) => x.ward === w);
    return o ? t(o.label) : w;
  };
  const selected = (w: DispensingWard): RoundDose[] =>
    w.patients.flatMap((p) => p.doses).filter((d) => !d.dispensed && !skipped.has(d.dose_id));

  async function send(w: DispensingWard, plan: Map<string, string | null>) {
    const doses = selected(w);
    if (!doses.length || busyWard || sending.current) return;
    sending.current = true;
    setBusyWard(w.ward);
    try {
      const disp = await createDispensation({
        ward: w.ward,
        date,
        round_time: round,
        // An explicit lot for every formulary line: the server then does exactly what the screen showed.
        lines: doses.map((d) => {
          const lot = d.drug_id ? plan.get(d.dose_id) : null;
          return lot ? { dose_id: d.dose_id, lot_id: lot } : { dose_id: d.dose_id };
        }),
      });
      showToast({ tone: "ok", text: t("pharmacy.sentToast", { ward: wardLabel(w.ward), time: round, n: disp.lines.length }) });
      refreshPharmacySummary();
    } catch (err) {
      const short = shortDrugId(err);
      const text = short
        ? t("pharmacy.errInsufficientStockOf", { drug: drugName(short) })
        : err instanceof ApiError && (err.code === "bad_status" || err.code === "invalid")
          ? t("pharmacy.errRoundChanged")
          : t(describePharmacyError(err));
      showToast({ tone: "warn", text });
    } finally {
      sending.current = false;
      setBusyWard(null);
      setReload((n) => n + 1); // every outcome reloads: sent rows, new stock, or the changed round
    }
  }

  function toggle(doseId: string, on: boolean) {
    setSkipped((s) => {
      const next = new Set(s);
      if (on) next.delete(doseId);
      else next.add(doseId);
      return next;
    });
  }

  return (
    <div className={page.page}>
      <div className={page.head}>
        <div className={page.titles}>
          <h2 className={page.h2}>{t("pharmacy.dispTitle")}</h2>
          <span className={page.sub}>{t("pharmacy.dispSub")}</span>
        </div>
      </div>

      <div className={styles.filters}>
        <label className={`${page.field} ${styles.filterField}`}>
          <span className={page.fieldLabel}>{t("pharmacy.fDate")}</span>
          <input type="date" dir="ltr" className={page.input} value={date} onChange={(e) => e.target.value && setDate(e.target.value)} />
        </label>
        <label className={`${page.field} ${styles.filterField}`}>
          <span className={page.fieldLabel}>{t("pharmacy.fRound")}</span>
          <span className={page.selectWrap}>
            <select dir="ltr" className={page.select} value={round} onChange={(e) => setRound(e.target.value)}>
              {ROUND_TIMES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </span>
        </label>
        <label className={`${page.field} ${styles.filterField}`}>
          <span className={page.fieldLabel}>{t("pharmacy.fWard")}</span>
          <span className={page.selectWrap}>
            <select className={page.select} value={ward} onChange={(e) => setWard(e.target.value)}>
              <option value="">{t("pharmacy.allWards")}</option>
              {WARD_OPTIONS.map((w) => (
                <option key={w.ward} value={w.ward}>
                  {t(w.label)}
                </option>
              ))}
            </select>
          </span>
        </label>
      </div>

      {failed ? (
        <ErrorCard title={t("pharmacy.dispLoadError")} onRetry={() => setReload((n) => n + 1)} secondaryLabel={null} />
      ) : !data ? (
        <div className="ward-skeleton" style={{ height: 220 }} aria-busy="true" />
      ) : data.length === 0 ? (
        <p className={styles.empty}>{t("pharmacy.dispEmpty")}</p>
      ) : (
        data.map((w) => {
          const toSend = selected(w);
          const plan = planLots(toSend, lotsByDrug, lotDay, chosen);
          const short = w.patients.flatMap((p) =>
            p.doses.filter((d) => d.drug_id && plan.has(d.dose_id) && plan.get(d.dose_id) === null).map((d) => ({ p, d })),
          );
          return (
            <section key={w.ward} className={styles.wardBlock} aria-labelledby={`ward-${w.ward}`}>
              <div className={styles.wardHead}>
                <h3 id={`ward-${w.ward}`} className={styles.wardName}>
                  {wardLabel(w.ward)}
                </h3>
                <button
                  type="button"
                  className={page.btnPrimary}
                  disabled={!toSend.length || short.length > 0 || busyWard !== null}
                  onClick={() => void send(w, plan)}
                >
                  {t("pharmacy.prepareSend", { n: toSend.length })}
                </button>
              </div>
              {short.length ? (
                <div role="alert" className={styles.shortBox}>
                  <b>{t("pharmacy.shortTitle")}</b>
                  {short.map(({ p, d }) => (
                    <span key={d.dose_id} dir="auto">
                      {t("pharmacy.shortLine", { bed: p.bed ?? "", name: p.name, med: d.med, qty: d.quantity })}
                    </span>
                  ))}
                </div>
              ) : null}
              <div role="table" aria-labelledby={`ward-${w.ward}`} className={styles.roundTable}>
                <div role="row" className={`${styles.doseGrid} ${page.th}`}>
                  <span role="columnheader">{t("pharmacy.colInclude")}</span>
                  <span role="columnheader">{t("pharmacy.colBed")}</span>
                  <span role="columnheader">{t("pharmacy.colPatient")}</span>
                  <span role="columnheader">{t("pharmacy.colMed")}</span>
                  <span role="columnheader">{t("pharmacy.colQty")}</span>
                  <span role="columnheader">{t("pharmacy.colLot")}</span>
                  <span role="columnheader">{t("pharmacy.colOnHand")}</span>
                </div>
                {w.patients.flatMap((p) =>
                  p.doses.map((d) => (
                    <div key={d.dose_id} role="row" className={`${styles.doseGrid} ${page.tr} ${d.dispensed ? styles.sentRow : ""}`}>
                      <span role="cell">
                        {d.dispensed ? null : (
                          <input
                            type="checkbox"
                            aria-label={t("pharmacy.includeDose", { med: d.med, name: p.name })}
                            checked={!skipped.has(d.dose_id)}
                            onChange={(e) => toggle(d.dose_id, e.target.checked)}
                          />
                        )}
                      </span>
                      <span role="cell" dir="ltr">
                        {p.bed ?? "—"}
                      </span>
                      <span role="cell" dir="auto">
                        {p.name}
                      </span>
                      <span role="cell" dir="auto">
                        {d.med}
                      </span>
                      <span role="cell" className={styles.num}>
                        {d.quantity}
                      </span>
                      <span role="cell">
                        {d.dispensed ? (
                          <span className={styles.muted}>{t("pharmacy.alreadySent")}</span>
                        ) : !d.drug_id ? (
                          <span className={styles.muted}>{t("pharmacy.nonFormularyLine")}</span>
                        ) : skipped.has(d.dose_id) ? (
                          <span className={styles.muted}>—</span>
                        ) : (
                          <LotSelect
                            dose={d}
                            lots={lotsByDrug.get(d.drug_id) ?? []}
                            date={lotDay}
                            value={plan.get(d.dose_id) ?? null}
                            onChange={(id) => setChosen((c) => ({ ...c, [d.dose_id]: id }))}
                          />
                        )}
                      </span>
                      <span role="cell" className={`${styles.num} ${d.on_hand !== null && d.on_hand < d.quantity ? styles.lowNum : ""}`}>
                        {d.on_hand ?? "—"}
                      </span>
                    </div>
                  )),
                )}
              </div>
            </section>
          );
        })
      )}
      {toast ? <Toast tone={toast.tone}>{toast.text}</Toast> : null}
    </div>
  );
}

export default DispensingView;
