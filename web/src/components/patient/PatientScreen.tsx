"use client";

// One patient screen inside the phone frame: status bar, the Ward brand row, the body
// (passed as children; each screen sets its own padding) and, on the tabbed screens, the tab bar.
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { getMyAppointments } from "@/lib/api";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { LogoutButton } from "@/components/LogoutButton";
import { now, tunisTime } from "@/lib/time";
import { myPatientId } from "./patient";
import styles from "./Patient.module.css";

export type PatientTab = "home" | "vitals" | "assistant" | "appts" | "calendar";

export interface PatientScreenProps {
  /** Status bar clock. Default: the demo clock ("09:12"). */
  time?: string;
  /** Status bar signal and battery icons (the "Confirmed" screen has none). */
  icons?: boolean;
  /** The "Ward · Prototype · simulated data" row. */
  brand?: boolean;
  /** Show the tab bar with this tab active. */
  nav?: PatientTab;
  /** Appointments tab target; default: the next appointment, found on demand. */
  apptHref?: string;
  children: ReactNode;
}

export function PatientScreen({ time, icons = true, brand = true, nav, apptHref, children }: PatientScreenProps) {
  return (
    <>
      <div className={styles.statusBar} aria-hidden="true">
        <span>{time ?? tunisTime(now().toISOString())}</span>
        {icons ? (
          <span className={styles.statusIcons}>
            <span className={styles.signal} />
            <span className={styles.battery} />
          </span>
        ) : null}
      </div>
      {brand ? <Brand /> : null}
      {children}
      {nav ? <TabBar active={nav} apptHref={apptHref} /> : null}
    </>
  );
}

export function Brand() {
  const { t } = useT();
  return (
    <div className={styles.brand}>
      <span className={styles.brandMark} />
      <Link href="/patient" className={styles.brandName}>
        Ward
      </Link>
      <span className={styles.flex} />
      <span className={styles.protoTag}>{t("patient.protoTag")}</span>
      <Link href="/patient/password" className={styles.protoTag}>{t("auth.navPassword")}</Link>
      <LogoutButton className={styles.logoutBtn} />
      <LanguageSwitcher compact tone="light" />
    </div>
  );
}

const TABS: { key: PatientTab; label: Key; shape: string }[] = [
  { key: "home", label: "patient.tabHome", shape: "tabHome" },
  { key: "vitals", label: "patient.tabVitals", shape: "tabVitals" },
  { key: "assistant", label: "patient.tabAssistant", shape: "tabAssistant" },
  { key: "appts", label: "patient.tabAppts", shape: "tabAppts" },
  { key: "calendar", label: "calendar.tab", shape: "tabCalendar" },
];

/** The next appointment's page, or Home when there is none. */
function useApptHref(given?: string): string {
  const [href, setHref] = useState(given ?? "/patient");
  useEffect(() => {
    if (given) return;
    let alive = true;
    myPatientId()
      .then(getMyAppointments)
      .then((list) => {
        const t = now().getTime();
        const next = list.find((a) => a.status !== "cancelled" && a.slot_at && Date.parse(a.slot_at) >= t) ?? list.find((a) => a.status !== "cancelled");
        if (alive && next) setHref(`/patient/appointments/${next.id}`);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [given]);
  return given ?? href;
}

export function TabBar({ active, apptHref }: { active: PatientTab; apptHref?: string }) {
  const { t } = useT();
  const appts = useApptHref(apptHref);
  const hrefs: Record<PatientTab, string> = { home: "/patient", vitals: "/patient/vitals", assistant: "/patient/assistant", appts, calendar: "/patient/calendar" };
  return (
    <nav className={styles.tabBar} aria-label={t("patient.navLabel")}>
      {TABS.map((tab) => (
        <Link
          key={tab.key}
          href={hrefs[tab.key]}
          className={`${styles.tab} ${tab.key === active ? styles.tabActive : ""}`}
          aria-current={tab.key === active ? "page" : undefined}
        >
          <span className={`${styles.tabIcon} ${styles[tab.shape]}`} aria-hidden="true" />
          {t(tab.label)}
        </Link>
      ))}
    </nav>
  );
}

/** Patient / States · loading: a shimmer title and three placeholder rows. */
export function SkeletonCard() {
  const { t } = useT();
  return (
    <div aria-busy="true" aria-label={t("patient.loading")} className={styles.skelCard}>
      <span className={`${styles.skelTitle} ward-skeleton`} />
      {[1, 2, 3].map((k) => (
        <div key={k} className={styles.skelRow}>
          <span className={styles.skelTime} />
          <span className={styles.skelText} />
          <span className={styles.skelPill} />
        </div>
      ))}
    </div>
  );
}

/** Patient / States · offline. */
export function OfflineBanner({ since }: { since: string }) {
  const { t } = useT();
  return (
    <div role="status" className={styles.offline}>
      <span className={styles.offlineRing} />
      <span>
        <b>{t("patient.offlineTitle")}</b> {t("patient.offlineBody", { since })}
      </span>
    </div>
  );
}

/** Patient / States · empty card (title + one line). */
export function EmptyCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className={styles.emptyCard}>
      <span className={styles.emptyTitle}>{title}</span>
      <span className={styles.emptyText}>{children}</span>
    </div>
  );
}

export default PatientScreen;
