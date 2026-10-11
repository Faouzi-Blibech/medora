"use client";

// Pharmacist / Stock (/pharmacist/stock). On hand vs minimum per drug (expired lots don't count), the lots
// with their expiry flags (from the server: expired before today; expiring within 30 days, today included),
// receiving a delivery, adjusting a lot, and the reorder list (2 × min − on hand). Every change refreshes
// the sidebar badge and the tiles. The alerts stay in the pharmacy: they are not sent to the wards (spec §5).
import { useEffect, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import page from "@/components/admin/AdminPage.module.css";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { Toast, useToast } from "@/components/Toast";
import { getReorderList, getStock } from "@/lib/api";
import { FORM_KEY } from "@/lib/pharmacy";
import type { ReorderItem, StockItem, StockLot } from "@/lib/types";
import { AdjustDialog } from "./AdjustDialog";
import { ReceiptForm } from "./ReceiptForm";
import { refreshPharmacySummary } from "./usePharmacySummary";
import styles from "./Pharmacist.module.css";

export function StockView() {
  const { t } = useT();
  const [items, setItems] = useState<StockItem[] | null>(null);
  const [reorder, setReorder] = useState<ReorderItem[]>([]);
  const [failed, setFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [adjusting, setAdjusting] = useState<{ lot: StockLot; drug: string } | null>(null);
  const [toast, showToast] = useToast<string>(4500);

  useEffect(() => {
    let alive = true;
    setFailed(false);
    Promise.all([getStock(), getReorderList()]).then(
      ([stock, list]) => {
        if (!alive) return;
        setItems(stock);
        setReorder(list);
      },
      () => {
        if (alive) setFailed(true);
      },
    );
    return () => {
      alive = false;
    };
  }, [reload]);

  function changed(message: string) {
    showToast(message);
    setReload((n) => n + 1);
    refreshPharmacySummary();
  }

  const tiles: { key: string; label: Key; n: number | undefined; danger?: boolean }[] = [
    { key: "low", label: "pharmacy.tileLow", n: items?.filter((i) => i.low).length, danger: true },
    { key: "expiring", label: "pharmacy.tileExpiringLots", n: items?.flatMap((i) => i.lots).filter((l) => l.expiring).length },
    { key: "expired", label: "pharmacy.tileExpired", n: items?.filter((i) => i.expired).length, danger: true },
  ];

  return (
    <div className={page.page}>
      <div className={page.head}>
        <div className={page.titles}>
          <h2 className={page.h2}>{t("pharmacy.stockTitle")}</h2>
          <span className={page.sub}>{t("pharmacy.stockSub")}</span>
        </div>
      </div>

      <dl className={styles.tiles}>
        {tiles.map((x) => (
          <div key={x.key} className={`${styles.tile} ${x.danger && (x.n ?? 0) > 0 ? styles.tileDanger : ""}`}>
            <dt className={styles.tileLabel}>{t(x.label)}</dt>
            <dd className={styles.tileNum}>{x.n ?? "–"}</dd>
          </div>
        ))}
      </dl>

      {failed && !items ? (
        <ErrorCard title={t("pharmacy.stockLoadError")} onRetry={() => setReload((n) => n + 1)} secondaryLabel={null} />
      ) : !items ? (
        <div className="ward-skeleton" style={{ height: 260 }} aria-busy="true" />
      ) : (
        <div className={styles.stockLayout}>
          <div className={styles.table} role="table" aria-label={t("pharmacy.stockTitle")}>
            <div role="row" className={`${styles.stockGrid} ${page.th}`}>
              <span role="columnheader">{t("pharmacy.colDci")}</span>
              <span role="columnheader">{t("pharmacy.colStock")}</span>
              <span role="columnheader">{t("pharmacy.colStatus")}</span>
              <span role="columnheader">{t("pharmacy.colLots")}</span>
            </div>
            {items.map((r) => (
              <div key={r.drug_id} role="row" className={`${styles.stockGrid} ${page.tr}`}>
                <span role="cell">
                  <span dir="auto" className={styles.cellMain}>
                    {r.dci}
                  </span>
                  <span className={styles.cellSub}>
                    {t(FORM_KEY[r.form] ?? "pharmacy.formOther")} · <span dir="ltr">{r.strength}</span>
                  </span>
                </span>
                <span role="cell" dir="ltr" className={`${styles.num} ${r.low ? styles.lowNum : ""}`}>
                  {r.on_hand} / {r.min_stock}
                </span>
                <span role="cell" className={styles.tags}>
                  {r.low ? <span className={`${styles.flag} ${styles.flagDanger}`}>{t("pharmacy.flagLow")}</span> : null}
                  {r.expiring ? <span className={styles.flag}>{t("pharmacy.flagExpiring")}</span> : null}
                  {r.expired ? <span className={`${styles.flag} ${styles.flagDanger}`}>{t("pharmacy.flagExpired")}</span> : null}
                </span>
                <span role="cell">
                  <ul className={styles.lots}>
                    {r.lots.map((l) => (
                      <li key={l.id} className={styles.lotRow}>
                        <span className={l.expired ? styles.lotExpired : l.expiring ? styles.lotExpiring : undefined}>
                          {t("pharmacy.lotLine", { lot: l.lot_number, date: l.expiry_date, qty: l.quantity })}
                        </span>
                        <button type="button" className={styles.linkBtn} onClick={() => setAdjusting({ lot: l, drug: `${r.dci} ${r.strength}` })}>
                          {t("pharmacy.adjust")}
                        </button>
                      </li>
                    ))}
                  </ul>
                </span>
              </div>
            ))}
          </div>
          <div className={styles.side}>
            <ReceiptForm items={items} onDone={changed} />
            <section className={styles.card} aria-labelledby="reorder-title">
              <h3 id="reorder-title" className={styles.cardTitle}>
                {t("pharmacy.reorderTitle")}
              </h3>
              {reorder.length === 0 ? (
                <p className={styles.muted}>{t("pharmacy.reorderNone")}</p>
              ) : (
                <ul className={styles.lots}>
                  {reorder.map((r) => (
                    <li key={r.drug_id} dir="auto" className={styles.reorderRow}>
                      {t("pharmacy.reorderLine", { drug: `${r.dci} ${r.strength}`, n: r.suggested_quantity, on_hand: r.on_hand, min: r.min_stock })}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      )}

      {adjusting ? (
        <AdjustDialog
          lot={adjusting.lot}
          drug={adjusting.drug}
          onClose={() => setAdjusting(null)}
          onDone={(message) => {
            setAdjusting(null);
            changed(message);
          }}
        />
      ) : null}
      {toast ? <Toast>{toast}</Toast> : null}
    </div>
  );
}

export default StockView;
