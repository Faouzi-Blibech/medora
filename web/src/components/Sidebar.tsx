"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { LogoutButton } from "./LogoutButton";
import { getHealthEvents } from "@/lib/api";
import { addDays, badgeCount, todayIso, weatherEvents } from "@/lib/healthCalendar";
import { loadHealthWatch } from "@/components/calendar/useHealthEvents";
import { USE_MOCKS } from "@/lib/time";
import { initialsOf, useMe } from "@/lib/useMe";
import { NAV_COUNTS } from "@/mocks";
import styles from "./Sidebar.module.css";

export type StaffRole = "doctor" | "nurse" | "admin";

export interface NavItem {
  key: string;
  label: Key;
  href: string;
  count?: string;
  /** "hot" count: teal pill (nurse alerts). */
  hot?: boolean;
}

/** The design's people (mock mode). Real mode shows the signed-in user from GET /me. */
const USERS: Record<StaffRole, { name: string; sub: Key; ini: string }> = {
  doctor: { name: "Dr Trabelsi", sub: "shared.userDoctorSub", ini: "DT" },
  nurse: { name: "Nurse Ines", sub: "shared.userNurseSub", ini: "NI" },
  admin: { name: "Mme Gharbi", sub: "shared.subAdmin", ini: "MG" },
};

/** Real-mode subtitle: /me has no ward, so the role word is enough. */
const ROLE_SUB: Record<string, Key> = {
  doctor: "shared.roleDoctor",
  nurse: "shared.roleNurse",
  admin: "shared.subAdmin",
  patient: "shared.rolePatient",
};

export const NAV: Record<StaffRole, NavItem[]> = {
  doctor: [
    { key: "patients", label: "shared.navMyPatients", href: "/doctor", count: NAV_COUNTS.doctor.patients },
    { key: "requests", label: "shared.navRequests", href: "/doctor/requests", count: NAV_COUNTS.doctor.requests },
    { key: "assistant", label: "shared.navAssistant", href: "/doctor/assistant" },
    { key: "team", label: "accounts.navTeam", href: "/doctor/team" },
    { key: "calendar", label: "calendar.nav", href: "/doctor/calendar", hot: false },
    { key: "password", label: "auth.navPassword", href: "/doctor/password" },
  ],
  nurse: [
    { key: "board", label: "shared.navWardBoard", href: "/nurse", count: NAV_COUNTS.nurse.board },
    { key: "alerts", label: "shared.navAlerts", href: "/nurse/alerts", count: NAV_COUNTS.nurse.alerts, hot: true },
    { key: "meds", label: "shared.navMedRound", href: "/nurse/meds", count: NAV_COUNTS.nurse.meds },
    { key: "exams", label: "shared.navExams", href: "/nurse/exams" },
    { key: "patients", label: "shared.navPatients", href: "/nurse/patients", count: NAV_COUNTS.nurse.patients },
    { key: "assistant", label: "shared.navAssistant", href: "/nurse/assistant" },
    { key: "calendar", label: "calendar.nav", href: "/nurse/calendar", hot: false },
    { key: "password", label: "auth.navPassword", href: "/nurse/password" },
  ],
  admin: [
    { key: "dashboard", label: "shared.navDashboard", href: "/admin", count: NAV_COUNTS.admin.dashboard },
    { key: "waitlist", label: "shared.navWaitlist", href: "/admin/waitlist", count: NAV_COUNTS.admin.waitlist },
    { key: "devices", label: "shared.navDevices", href: "/admin/devices", count: NAV_COUNTS.admin.devices },
    { key: "staff", label: "shared.navStaff", href: "/admin/staff", count: NAV_COUNTS.admin.staff },
    { key: "pending", label: "accounts.navPending", href: "/admin/pending" },
    { key: "patients", label: "accounts.navPatientAccess", href: "/admin/patients" },
    { key: "calendar", label: "calendar.nav", href: "/admin/calendar", hot: false },
    { key: "password", label: "auth.navPassword", href: "/admin/password" },
  ],
};

/** The nav key for a pathname: exact match, else the longest href prefix. */
export function activeKeyFor(role: StaffRole, pathname: string): string {
  const items = NAV[role];
  const exact = items.find((n) => n.href === pathname);
  if (exact) return exact.key;
  const prefix = items
    .filter((n) => pathname.startsWith(`${n.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0];
  return prefix?.key ?? items[0].key;
}

export interface SidebarProps {
  role: StaffRole;
  /** Nav key (e.g. "patients", "requests"); defaults to the first item. */
  active?: string;
  /** false → the "Reconnecting…" pill instead of "Live". */
  live?: boolean;
  /** Override the mock counts per nav key. */
  counts?: Partial<Record<string, string | number>>;
}

/** Role navigation, exactly as Sidebar.dc.html (248 px wide in the shell). */
export function Sidebar({ role, active, live = true, counts }: SidebarProps) {
  const { t } = useT();
  const items = NAV[role];
  const current = active ?? items[0].key;
  const me = useMe(role);
  // Health calendar badge: events for me, active now or starting within 7 days.
  // A real endpoint, so it shows in mock and real mode alike.
  const [calCount, setCalCount] = useState<number | null>(null);
  useEffect(() => {
    let alive = true;
    Promise.all([getHealthEvents({ role, from: todayIso(), to: addDays(todayIso(), 7) }), loadHealthWatch(role)]).then(
      ([ev, watch]) => alive && setCalCount(badgeCount([...weatherEvents(watch, role), ...ev], todayIso())),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [role]);
  const u = USE_MOCKS
    ? { ...USERS[role], sub: t(USERS[role].sub) }
    : {
        name: me?.name ?? "",
        sub: me ? (ROLE_SUB[me.role] ? t(ROLE_SUB[me.role]) : me.role) : "",
        ini: me ? initialsOf(me.name) : "",
      };
  return (
    <div className={styles.root}>
      <div className={styles.brand}>
        <div className={styles.wordmark}>
          <span className={styles.mark} />
          <span className={styles.name}>Ward</span>
        </div>
        <span className={styles.tag}>{t("common.prototypeTag")}</span>
      </div>
      <nav className={styles.nav}>
        {items.map((n) => {
          const on = n.key === current;
          // Real mode: no stats endpoint yet (proposed in api.md), so no count pills.
          const count =
            n.key === "calendar"
              ? String(counts?.[n.key] ?? calCount ?? "")
              : USE_MOCKS
                ? String(counts?.[n.key] ?? n.count ?? "")
                : String(counts?.[n.key] ?? "");
          return (
            <Link
              key={n.key}
              href={n.href}
              className={`${styles.item} ${on ? styles.itemOn : ""}`}
              aria-current={on ? "page" : undefined}
            >
              <span className={styles.dot} />
              <span className={styles.label}>{t(n.label)}</span>
              {count && count !== "0" ? (
                <span className={`${styles.count} ${n.hot ? styles.countHot : ""}`}>{count}</span>
              ) : null}
            </Link>
          );
        })}
      </nav>
      <div className={styles.spacer} />
      <div className={styles.foot}>
        {live ? (
          // No live feed in real mode yet (snapshots only), so no "Live" pill there.
          USE_MOCKS ? (
            <span className={styles.live}>
              <span className={styles.liveDot} />
              {t("common.live")}
            </span>
          ) : null
        ) : (
          <span className={styles.paused}>
            <span className={styles.pausedDot} />
            {t("common.reconnecting")}
          </span>
        )}
        <LanguageSwitcher tone="dark" compact />
        <LogoutButton className={styles.logout} />
        <div className={styles.user}>
          <span className={styles.avatar}>{u.ini}</span>
          <div className={styles.who}>
            <span className={styles.userName}>{u.name}</span>
            <span className={styles.userSub}>{u.sub}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Sidebar;
