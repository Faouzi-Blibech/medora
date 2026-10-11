"use client";

// The desktop patient platform's navigation: the staff sidebar's look (Sidebar.module.css)
// with the patient's own pages, the layout switch, the language switcher and the user card.
import { Logo } from "@/components/brand/Logo";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import { USE_MOCKS } from "@/lib/time";
import { initialsOf, useMe } from "@/lib/useMe";
import { LayoutSwitch } from "./LayoutSwitch";
import { useApptHref } from "./PatientScreen";
import styles from "../Sidebar.module.css";

type NavKey = "home" | "vitals" | "assistant" | "appts" | "calendar" | "homeCare" | "settings";

const NAV: { key: NavKey; label: Key; href: string }[] = [
  { key: "home", label: "patient.tabHome", href: "/patient" },
  { key: "vitals", label: "patient.tabVitals", href: "/patient/vitals" },
  { key: "assistant", label: "patient.tabAssistant", href: "/patient/assistant" },
  { key: "appts", label: "patient.tabAppts", href: "/patient/appointments" },
  { key: "calendar", label: "calendar.tab", href: "/patient/calendar" },
  { key: "homeCare", label: "patient.tabHomeCare", href: "/patient/home-care" },
  { key: "settings", label: "patient.navSettings", href: "/patient/settings" },
];

function activeKey(pathname: string): NavKey {
  if (pathname.startsWith("/patient/appointments") || pathname.startsWith("/patient/offers")) return "appts";
  const hit = NAV.filter((n) => n.href !== "/patient" && pathname.startsWith(n.href))[0];
  return hit?.key ?? "home";
}

export function PatientSidebar() {
  const { t } = useT();
  const pathname = usePathname();
  const me = useMe("patient");
  const appts = useApptHref();
  const current = activeKey(pathname);
  const name = USE_MOCKS ? "Amira Ben Salah" : (me?.name ?? "");
  return (
    <div className={styles.root}>
      <div className={styles.brand}>
        <Link href="/patient" className={styles.wordmark} style={{ color: "inherit", textDecoration: "none" }}>
          <Logo tone="dark" size={30} />
        </Link>
        <span className={styles.tag}>{t("patient.protoTag")}</span>
      </div>
      <nav className={styles.nav} aria-label={t("patient.navLabel")}>
        {NAV.map((n) => {
          const on = n.key === current;
          return (
            <Link
              key={n.key}
              href={n.key === "appts" ? appts : n.href}
              className={`${styles.item} ${on ? styles.itemOn : ""}`}
              aria-current={on ? "page" : undefined}
            >
              <span className={styles.dot} />
              <span className={styles.label}>{t(n.label)}</span>
            </Link>
          );
        })}
      </nav>
      <div className={styles.spacer} />
      <div className={styles.foot}>
        <LayoutSwitch tone="dark" />
        <Link href="/patient/settings" className={styles.user} style={{ color: "inherit", textDecoration: "none" }}>
          <span className={styles.avatar}>{name ? initialsOf(name) : ""}</span>
          <div className={styles.who}>
            <span className={styles.userName} dir="auto">
              {name}
            </span>
            <span className={styles.userSub}>{t("shared.rolePatient")}</span>
          </div>
        </Link>
      </div>
    </div>
  );
}

export default PatientSidebar;
