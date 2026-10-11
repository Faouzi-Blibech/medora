"use client";

// "Octobre Rose · until 31 Oct": the next health event for me (active now or within 7 days; a weather-health alert
// also shows its advice, e.g. "drink water often"),
// tinted by its category, with a link to the calendar and a dismiss button (per tab session).
import Link from "next/link";
import { useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import { CATEGORY_TONE, fmtDay, forMe, textOf, todayIso, upcoming } from "@/lib/healthCalendar";
import type { Role } from "@/lib/types";
import { useHealthEvents } from "./useHealthEvents";
import styles from "./UpcomingBanner.module.css";

const storageKey = (id: string) => `ward_cal_dismissed_${id}`;

function wasDismissed(id: string): boolean {
  try {
    return window.sessionStorage.getItem(storageKey(id)) === "1";
  } catch {
    return false;
  }
}

export interface UpcomingBannerProps {
  role: Role;
  /** Where "See the calendar" goes. */
  href: string;
}

export function UpcomingBanner({ role, href }: UpcomingBannerProps) {
  const { t, lang } = useT();
  const { events } = useHealthEvents(role);
  const [closed, setClosed] = useState<string | null>(null);
  const today = todayIso();
  // Events load in an effect, so this only runs in the browser (no hydration mismatch).
  // A weather-health alert for me comes first: it is about the next days and carries advice.
  const mine = events ? forMe(upcoming(events, today, 7)) : [];
  const ev = mine.find((e) => e.weather) ?? mine[0];
  if (!ev || closed === ev.id || wasDismissed(ev.id)) return null;

  const tone = CATEGORY_TONE[ev.category];
  const when =
    ev.starts_on <= today
      ? t("calendar.bannerNow", { date: fmtDay(ev.ends_on, lang) })
      : t("calendar.bannerSoon", { date: fmtDay(ev.starts_on, lang) });

  const dismiss = () => {
    try {
      window.sessionStorage.setItem(storageKey(ev.id), "1");
    } catch {
      // Storage blocked: the banner still hides for this page view.
    }
    setClosed(ev.id);
  };

  return (
    <div role="status" className={styles.banner} style={{ background: tone.bg, color: tone.fg }}>
      <span className={styles.dot} style={{ background: tone.fg }} aria-hidden="true" />
      <span className={styles.body}>
        <span className={styles.text}>{t("calendar.banner", { title: textOf(ev.title, lang), when })}</span>
        {ev.weather && textOf(ev.description, lang) ? (
          <span className={styles.advice} dir="auto">
            {textOf(ev.description, lang)}
          </span>
        ) : null}
        <Link href={href} className={styles.open} style={{ color: tone.fg }}>
          {t("calendar.bannerOpen")}
        </Link>
      </span>
      <button type="button" className={styles.dismiss} onClick={dismiss} aria-label={t("calendar.dismiss")} style={{ color: tone.fg }}>
        <span aria-hidden="true">×</span>
      </button>
    </div>
  );
}

export default UpcomingBanner;
