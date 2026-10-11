"use client";

import type { ReactNode } from "react";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useT } from "@/i18n/I18nProvider";
import styles from "@/app/page.module.css";

/** The public-page chrome: the ink brand panel (what Medora is) beside the form panel (title, lead, form). */
export function AuthFrame({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  const { t } = useT();
  return (
    <div className={styles.page}>
      <aside className={styles.brand}>
        <div className={styles.brandTop}>
          <div className={styles.wordmark}>
            <span className={styles.mark} />
            <span className={styles.name}>Medora</span>
          </div>
          <span className={styles.tag}>{t("common.prototypeTag")}</span>
        </div>
        <div className={styles.pitch}>
          <h2 className={styles.pitchTitle}>{t("auth.pitchTitle")}</h2>
          <ul className={styles.points}>
            <li>{t("auth.pitchPoint1")}</li>
            <li>{t("auth.pitchPoint2")}</li>
            <li>{t("auth.pitchPoint3")}</li>
          </ul>
        </div>
        <LanguageSwitcher tone="dark" />
      </aside>
      <main className={styles.panel}>
        <div className={styles.inner}>
          <div className={styles.intro}>
            <h1 className={styles.title}>{title}</h1>
            {lead ? <p className={styles.lead}>{lead}</p> : null}
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}

export default AuthFrame;
