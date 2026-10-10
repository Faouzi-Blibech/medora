"use client";

// Pharmacist home (/pharmacist): the title, the summary tiles and the worklist.
import { useT } from "@/i18n/I18nProvider";
import page from "@/components/admin/AdminPage.module.css";
import { SummaryStrip } from "./SummaryStrip";
import { WorklistView } from "./WorklistView";

export function PharmacistHome() {
  const { t } = useT();
  return (
    <div className={page.page}>
      <div className={page.head}>
        <div className={page.titles}>
          <h2 className={page.h2}>{t("pharmacy.worklistTitle")}</h2>
          <span className={page.sub}>{t("pharmacy.worklistSub")}</span>
        </div>
      </div>
      <SummaryStrip />
      <WorklistView />
    </div>
  );
}

export default PharmacistHome;
