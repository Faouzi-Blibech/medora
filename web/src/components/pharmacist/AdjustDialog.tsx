"use client";

// Adjust one lot: POST /pharmacy/stock/adjustments {lot_id, delta, reason, comment}. The delta is a whole
// number ≠ 0 (±100000); "expired" needs a negative delta (choosing it pre-fills −quantity); the comment is
// 1–500 characters. Below zero, the server answers 409 insufficient_stock: no client pre-check hides that path.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import page from "@/components/admin/AdminPage.module.css";
import { adjustStock, ApiError } from "@/lib/api";
import { COMMENT_MAX } from "@/lib/pharmacy";
import { describePharmacyError } from "@/lib/pharmacyUi";
import type { AdjustmentReason, StockLot } from "@/lib/types";
import styles from "./Pharmacist.module.css";

const REASONS: [AdjustmentReason, Key][] = [
  ["adjustment", "pharmacy.reasonAdjustment"],
  ["expired", "pharmacy.reasonExpired"],
  ["return", "pharmacy.reasonReturn"],
];

export interface AdjustDialogProps {
  lot: StockLot;
  /** "Enoxaparin 40 mg", for the dialog's subtitle. */
  drug: string;
  onClose: () => void;
  onDone: (message: string) => void;
}

export function AdjustDialog({ lot, drug, onClose, onDone }: AdjustDialogProps) {
  const { t } = useT();
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState<AdjustmentReason>("adjustment");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<Key | null>(null);
  const [busy, setBusy] = useState(false);
  const first = useRef<HTMLInputElement>(null);
  const close = useRef(onClose);

  useEffect(() => {
    close.current = onClose;
  });
  useEffect(() => {
    first.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const n = Number(delta.trim().replace("−", "-")); // accept the typographic minus
    const text = comment.trim();
    if (!Number.isInteger(n) || n === 0 || Math.abs(n) > 100_000 || !text || [...text].length > COMMENT_MAX) {
      setError("pharmacy.errAdjustForm");
      return;
    }
    if (reason === "expired" && n > 0) {
      setError("pharmacy.errExpiredDelta");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await adjustStock({ lot_id: lot.id, delta: n, reason, comment: text });
      onDone(t("pharmacy.adjustSaved"));
    } catch (err) {
      setError(err instanceof ApiError && err.code === "insufficient_stock" ? "pharmacy.errBelowZero" : describePharmacyError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.overlay}>
      <form role="dialog" aria-modal="true" aria-labelledby="adjust-title" className={styles.dialog} onSubmit={submit} noValidate>
        <h2 id="adjust-title" className={styles.dialogTitle}>
          {t("pharmacy.adjustTitle", { lot: lot.lot_number })}
        </h2>
        <p dir="auto" className={styles.muted}>
          {drug} · {t("pharmacy.lotLine", { lot: lot.lot_number, date: lot.expiry_date, qty: lot.quantity })}
        </p>
        <label className={page.field}>
          <span className={page.fieldLabel}>{t("pharmacy.fReason")}</span>
          <span className={page.selectWrap}>
            <select
              className={page.select}
              value={reason}
              onChange={(e) => {
                const r = e.target.value as AdjustmentReason;
                setReason(r);
                if (r === "expired") setDelta(String(-lot.quantity));
              }}
            >
              {REASONS.map(([r, k]) => (
                <option key={r} value={r}>
                  {t(k)}
                </option>
              ))}
            </select>
          </span>
        </label>
        <label className={page.field}>
          <span className={page.fieldLabel}>{t("pharmacy.fDelta")}</span>
          <input ref={first} dir="ltr" className={page.input} value={delta} onChange={(e) => setDelta(e.target.value)} />
        </label>
        <label className={page.field}>
          <span className={page.fieldLabel}>{t("pharmacy.fComment")}</span>
          <textarea dir="auto" rows={2} maxLength={COMMENT_MAX} className={styles.textarea} value={comment} onChange={(e) => setComment(e.target.value)} />
        </label>
        {error ? (
          <span role="alert" className={styles.error}>
            {t(error)}
          </span>
        ) : null}
        <div className={styles.dialogActions}>
          <button type="button" className={page.btn} disabled={busy} onClick={onClose}>
            {t("pharmacy.cancel")}
          </button>
          <button type="submit" className={page.btnPrimary} disabled={busy}>
            {t("pharmacy.save")}
          </button>
        </div>
      </form>
    </div>
  );
}

export default AdjustDialog;
