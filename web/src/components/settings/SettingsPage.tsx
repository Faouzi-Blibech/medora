"use client";

// Settings for every role: profile (read-only), language, password, reduce motion, log out.
// `compact` is the patient phone frame: one column, mobile sizing.
import { useEffect, useState, type ReactNode } from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import { ChangePasswordForm } from "@/components/auth/ChangePasswordForm";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { LogoutButton } from "@/components/LogoutButton";
import { savedReducedMotion, setReducedMotion } from "@/lib/motion";
import type { Role } from "@/lib/types";
import { useMe } from "@/lib/useMe";
import styles from "./Settings.module.css";

const ROLE_LABEL: Record<Role, Key> = {
  doctor: "shared.roleDoctor",
  nurse: "shared.roleNurse",
  admin: "shared.roleAdmin",
  patient: "shared.rolePatient",
};

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className={styles.card}>
      <div className={styles.head}>
        <h3 className={styles.cardTitle}>{title}</h3>
        {hint ? <p className={styles.hint}>{hint}</p> : null}
      </div>
      {children}
    </section>
  );
}

export function SettingsPage({ role, compact = false }: { role: Role; compact?: boolean }) {
  const { t } = useT();
  const me = useMe(role);
  const [reduced, setReduced] = useState(false);
  useEffect(() => setReduced(savedReducedMotion()), []);

  function toggleMotion() {
    setReducedMotion(!reduced);
    setReduced(!reduced);
  }

  const profile = (
    <Section title={t("auth.settingsProfile")} hint={t("auth.settingsProfileHint")}>
      <dl className={styles.profile}>
        <div className={styles.row}>
          <dt>{t("auth.fieldName")}</dt>
          <dd>{me?.name ?? "…"}</dd>
        </div>
        <div className={styles.row}>
          <dt>{t("auth.fieldEmail")}</dt>
          <dd dir="ltr" className={styles.ltr}>
            {me?.email ?? "…"}
          </dd>
        </div>
        <div className={styles.row}>
          <dt>{t("auth.fieldRole")}</dt>
          <dd>{t(ROLE_LABEL[me?.role ?? role])}</dd>
        </div>
      </dl>
    </Section>
  );
  const language = (
    <Section title={t("auth.settingsLanguage")} hint={t("auth.settingsLanguageHint")}>
      <LanguageSwitcher tone="light" />
    </Section>
  );
  const password = (
    <Section title={t("auth.pwTitle")} hint={t("auth.pwLead")}>
      <div className={styles.pwSlot}>
        <ChangePasswordForm />
      </div>
    </Section>
  );
  const display = (
    <Section title={t("auth.settingsDisplay")}>
      <div className={styles.toggleRow}>
        <span className={styles.toggleText}>
          <span className={styles.toggleLabel} id="motion-label">
            {t("auth.settingsReduceMotion")}
          </span>
          <span className={styles.hint}>{t("auth.settingsReduceMotionHint")}</span>
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={reduced}
          aria-labelledby="motion-label"
          className={styles.switch}
          onClick={toggleMotion}
        >
          <span className={styles.knob} />
        </button>
      </div>
    </Section>
  );
  const session = (
    <Section title={t("auth.settingsSession")} hint={t("auth.settingsSessionHint")}>
      <LogoutButton className={styles.logout} />
    </Section>
  );

  return (
    <div className={`${styles.page} ${compact ? styles.compact : ""}`}>
      <header className={styles.top}>
        <h2 className={styles.title}>{t("auth.settingsTitle")}</h2>
        <p className={styles.lead}>{t("auth.settingsLead")}</p>
      </header>
      {compact ? (
        <div className={styles.col}>
          {profile}
          {language}
          {password}
          {display}
          {session}
        </div>
      ) : (
        <div className={styles.grid}>
          <div className={styles.col}>
            {profile}
            {language}
            {display}
            {session}
          </div>
          <div className={styles.col}>{password}</div>
        </div>
      )}
    </div>
  );
}

export default SettingsPage;
