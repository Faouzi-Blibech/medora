"use client";

// /calendar: the health calendar full width, for anyone signed in. Mock mode has no session,
// so it shows the patient's view; real mode uses the signed-in role (a dead token → sign-in,
// via the shared 401 rule in lib/api.ts).
import Link from "next/link";
import { useT } from "@/i18n/I18nProvider";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { USE_MOCKS } from "@/lib/time";
import type { Role } from "@/lib/types";
import { useMeState } from "@/lib/useMe";
import { HealthCalendar } from "./HealthCalendar";
import styles from "./FullCalendarPage.module.css";

const HOME: Record<Role, string> = { patient: "/patient", doctor: "/doctor", nurse: "/nurse", admin: "/admin" };

export function FullCalendarPage() {
  const { t } = useT();
  const { me } = useMeState(USE_MOCKS ? "patient" : undefined);
  const role: Role | null = USE_MOCKS ? "patient" : (me?.role ?? null);
  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <Link href={role ? HOME[role] : "/"} className={styles.wordmark}>
          <span className={styles.mark} aria-hidden="true" />
          <span className={styles.name}>Ward</span>
        </Link>
        <span className={styles.tag}>{t("common.prototypeTag")}</span>
        <span className={styles.flex} />
        <LanguageSwitcher compact tone="light" />
        <Link href={role ? HOME[role] : "/"} className={styles.back}>
          <span aria-hidden="true" className={styles.arrow}>
            ‹
          </span>{" "}
          {t("calendar.back")}
        </Link>
      </header>
      {role ? <HealthCalendar role={role} editable={role === "admin"} /> : null}
    </div>
  );
}

export default FullCalendarPage;
