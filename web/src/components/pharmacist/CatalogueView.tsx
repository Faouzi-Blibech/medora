"use client";

// Drug catalogue (/pharmacist/catalogue and /admin/catalogue): search by DCI, brand or ATC code, the
// formulary table, and the add/edit side panel (pharmacists and admins; spec §2). Illustrative data.
import { useEffect, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import page from "@/components/admin/AdminPage.module.css";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { Toast, useToast } from "@/components/Toast";
import { listDrugs } from "@/lib/api";
import { drugLabel, FORM_KEY } from "@/lib/pharmacy";
import type { Drug } from "@/lib/types";
import { useDebounced } from "@/lib/useDebounced";
import { DrugForm } from "./DrugForm";
import styles from "./Pharmacist.module.css";

export function CatalogueView() {
  const { t } = useT();
  const [q, setQ] = useState("");
  const query = useDebounced(q.trim(), 250);
  const [showInactive, setShowInactive] = useState(false);
  const [drugs, setDrugs] = useState<Drug[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [editing, setEditing] = useState<Drug | "new" | null>(null);
  const [toast, showToast] = useToast<string>(4500);

  useEffect(() => {
    let alive = true; // the last query wins
    setFailed(false);
    listDrugs({ q: query, ...(showInactive ? {} : { active: true }) }).then(
      (list) => {
        if (alive) setDrugs(list);
      },
      () => {
        if (alive) setFailed(true);
      },
    );
    return () => {
      alive = false;
    };
  }, [query, showInactive, reload]);

  return (
    <div className={page.page}>
      <div className={page.head}>
        <div className={page.titles}>
          <h2 className={page.h2}>{t("pharmacy.catalogueTitle")}</h2>
          <span className={page.sub}>{t("pharmacy.catalogueSub")}</span>
        </div>
        <button type="button" className={page.btnPrimary} onClick={() => setEditing("new")}>
          {t("pharmacy.addDrug")}
        </button>
      </div>

      <div className={styles.toolbar}>
        <input
          type="search"
          dir="auto"
          aria-label={t("pharmacy.searchLabel")}
          placeholder={t("pharmacy.searchLabel")}
          className={`${page.input} ${styles.search}`}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <label className={styles.checkRow}>
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
          {t("pharmacy.showInactive")}
        </label>
      </div>

      {failed && !drugs ? (
        <ErrorCard title={t("pharmacy.catalogueLoadError")} onRetry={() => setReload((n) => n + 1)} secondaryLabel={null} />
      ) : !drugs ? (
        <div className="ward-skeleton" style={{ height: 240 }} aria-busy="true" />
      ) : (
        <div className={styles.table} role="table" aria-label={t("pharmacy.catalogueTitle")}>
          <div role="row" className={`${styles.drugGrid} ${page.th}`}>
            <span role="columnheader">{t("pharmacy.colDci")}</span>
            <span role="columnheader">{t("pharmacy.colForm")}</span>
            <span role="columnheader">{t("pharmacy.colAtc")}</span>
            <span role="columnheader">{t("pharmacy.colMaxDaily")}</span>
            <span role="columnheader">{t("pharmacy.colTags")}</span>
            <span role="columnheader">{t("pharmacy.colStatus")}</span>
            <span role="columnheader" />
          </div>
          {drugs.length === 0 ? <p className={styles.empty}>{t("pharmacy.catalogueEmpty")}</p> : null}
          {drugs.map((d) => (
            <div key={d.id} role="row" className={`${styles.drugGrid} ${page.tr}`}>
              <span role="cell">
                <span dir="auto" className={styles.cellMain}>
                  {d.dci}
                </span>
                {d.brand_names.length ? (
                  <span dir="auto" className={styles.cellSub}>
                    {d.brand_names.join(", ")}
                  </span>
                ) : null}
              </span>
              <span role="cell">
                {t(FORM_KEY[d.form] ?? "pharmacy.formOther")} · <span dir="ltr">{d.strength}</span>
              </span>
              <span role="cell" dir="ltr" className={styles.mono}>
                {d.atc_code}
              </span>
              <span role="cell" dir="ltr">
                {d.max_daily_mg != null ? `${d.max_daily_mg} mg` : <span className={styles.cellSub}>{t("pharmacy.noMaxDaily")}</span>}
              </span>
              <span role="cell" className={styles.tags}>
                {d.allergy_classes.map((c) => (
                  <span key={`a-${c}`} className={styles.tag}>
                    {c}
                  </span>
                ))}
                {d.interaction_groups.map((g) => (
                  <span key={`g-${g}`} className={`${styles.tag} ${styles.tagGroup}`}>
                    {g}
                  </span>
                ))}
              </span>
              <span role="cell" className={styles.tags}>
                {d.high_alert ? <span className={styles.flag}>{t("pharmacy.highAlert")}</span> : null}
                <span className={`${styles.flag} ${d.active ? styles.flagOk : styles.flagOff}`}>{t(d.active ? "pharmacy.active" : "pharmacy.inactive")}</span>
              </span>
              <span role="cell">
                <button type="button" className={styles.linkBtn} onClick={() => setEditing(d)}>
                  {t("pharmacy.edit")}
                </button>
              </span>
            </div>
          ))}
        </div>
      )}

      {editing ? (
        <DrugForm
          key={editing === "new" ? "new" : editing.id}
          drug={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setEditing(null);
            showToast(t("pharmacy.drugSaved", { name: drugLabel(saved) }));
            setReload((n) => n + 1);
          }}
        />
      ) : null}
      {toast ? <Toast>{toast}</Toast> : null}
    </div>
  );
}

export default CatalogueView;
