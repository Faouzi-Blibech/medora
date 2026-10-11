"use client";

// Patient / Calendar (/patient/calendar): the compact health calendar in the phone frame,
// with a link out to the full-width /calendar page. The desktop platform shows the full calendar here.
import Link from "next/link";
import { useT } from "@/i18n/I18nProvider";
import { HealthCalendar } from "@/components/calendar/HealthCalendar";
import { useFrameLayout } from "./frameLayout";
import { PatientScreen } from "./PatientScreen";
import styles from "./Patient.module.css";

export function CalendarView() {
  const { t } = useT();
  const desk = useFrameLayout().layout === "desktop";
  if (desk) {
    // The full calendar brings its own title and page padding.
    return (
      <PatientScreen nav="calendar">
        <div className={`${styles.scroll} ${styles.deskCalendar}`}>
          <HealthCalendar role="patient" />
        </div>
      </PatientScreen>
    );
  }
  return (
    <PatientScreen nav="calendar">
      <div className={`${styles.scroll} ${styles.calendarBody}`}>
        <div className={styles.titleBlock}>
          <h1 className={styles.h1Small}>{t("calendar.title")}</h1>
        </div>
        <HealthCalendar role="patient" compact />
        <Link href="/calendar" className={`${styles.outlineBtn} ${styles.fullWidth}`}>
          {t("calendar.openFull")}
        </Link>
      </div>
    </PatientScreen>
  );
}

export default CalendarView;
