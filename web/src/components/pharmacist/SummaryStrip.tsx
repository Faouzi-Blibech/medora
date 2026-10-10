"use client";

// The pharmacist dashboard tiles (GET /pharmacy/summary). The critical tile turns red when non-zero.
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import { usePharmacySummary } from "./usePharmacySummary";
import styles from "./Pharmacist.module.css";

interface Tile {
  key: string;
  label: Key;
  n: number | undefined;
  danger?: boolean;
}

export function SummaryStrip() {
  const { t } = useT();
  const s = usePharmacySummary(true);
  const tiles: Tile[] = [
    { key: "pending", label: "pharmacy.tilePending", n: s?.pending },
    { key: "urgent", label: "pharmacy.tileUrgent", n: s?.urgent_pending },
    { key: "critical", label: "pharmacy.tileCritical", n: s?.critical_pending, danger: true },
    { key: "changes", label: "pharmacy.tileChanges", n: s?.changes_requested },
  ];
  return (
    <dl className={styles.tiles} aria-busy={!s || undefined}>
      {tiles.map((x) => (
        <div key={x.key} className={`${styles.tile} ${x.danger && (x.n ?? 0) > 0 ? styles.tileDanger : ""}`}>
          <dt className={styles.tileLabel}>{t(x.label)}</dt>
          <dd className={styles.tileNum}>{x.n ?? "–"}</dd>
        </div>
      ))}
    </dl>
  );
}

export default SummaryStrip;
