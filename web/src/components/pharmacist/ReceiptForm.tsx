"use client";

// "Receive a delivery": POST /pharmacy/stock/receipts. A known (drug, lot number) is topped up. The same lot
// number with another expiry is 409 `conflict`; a past expiry is refused here first (the server says 422).
import { useState, type FormEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import page from "@/components/admin/AdminPage.module.css";
import { ApiError, receiveStock } from "@/lib/api";
import { describePharmacyError } from "@/lib/pharmacyUi";
import { now, tunisDate } from "@/lib/time";
import type { StockItem } from "@/lib/types";
import styles from "./Pharmacist.module.css";

export interface ReceiptFormProps {
  /** The drugs to choose from (GET /pharmacy/stock: every active drug). */
  items: StockItem[];
  onDone: (message: string) => void;
}

export function ReceiptForm({ items, onDone }: ReceiptFormProps) {
  const { t } = useT();
  const [f, setF] = useState({ drug: "", lot: "", expiry: "", qty: "" });
  const [error, setError] = useState<Key | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const qty = Number(f.qty.trim());
    const today = tunisDate(now().toISOString());
    const lot = f.lot.trim();
    if (!f.drug || !lot || lot.length > 40 || !/^\d{4}-\d{2}-\d{2}$/.test(f.expiry) || f.expiry < today || !Number.isInteger(qty) || qty < 1 || qty > 100_000) {
      setError("pharmacy.errStockForm");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = await receiveStock({ drug_id: f.drug, lot_number: lot, expiry_date: f.expiry, quantity: qty });
      setF((s) => ({ ...s, lot: "", expiry: "", qty: "" }));
      onDone(t("pharmacy.receiptSaved", { lot: saved.lot_number }));
    } catch (err) {
      setError(err instanceof ApiError && err.code === "conflict" ? "pharmacy.errLotExpiryConflict" : describePharmacyError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.card} onSubmit={submit} noValidate aria-labelledby="receipt-title">
      <h3 id="receipt-title" className={styles.cardTitle}>
        {t("pharmacy.receiptTitle")}
      </h3>
      <label className={page.field}>
        <span className={page.fieldLabel}>{t("pharmacy.fDrug")}</span>
        <span className={page.selectWrap}>
          <select className={page.select} value={f.drug} onChange={(e) => set("drug")(e.target.value)}>
            <option value="">{t("pharmacy.pickDrugOption")}</option>
            {items.map((r) => (
              <option key={r.drug_id} value={r.drug_id}>
                {`${r.dci} ${r.strength}`}
              </option>
            ))}
          </select>
        </span>
      </label>
      <label className={page.field}>
        <span className={page.fieldLabel}>{t("pharmacy.fLot")}</span>
        <input dir="ltr" maxLength={40} className={page.input} value={f.lot} onChange={(e) => set("lot")(e.target.value)} />
      </label>
      <div className={styles.pair}>
        <label className={page.field}>
          <span className={page.fieldLabel}>{t("pharmacy.fExpiry")}</span>
          <input type="date" dir="ltr" className={page.input} value={f.expiry} onChange={(e) => set("expiry")(e.target.value)} />
        </label>
        <label className={page.field}>
          <span className={page.fieldLabel}>{t("pharmacy.fQty")}</span>
          <input dir="ltr" inputMode="numeric" className={page.input} value={f.qty} onChange={(e) => set("qty")(e.target.value)} />
        </label>
      </div>
      {error ? (
        <span role="alert" className={styles.error}>
          {t(error)}
        </span>
      ) : null}
      <button type="submit" className={page.btnPrimary} disabled={busy}>
        {t("pharmacy.receive")}
      </button>
    </form>
  );
}

export default ReceiptForm;
