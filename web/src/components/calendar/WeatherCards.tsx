"use client";

// Health calendar companions: the hospital city's forecast for the next days and the health news (WHO, Tunisian
// press), from GET /health-watch. The weather-health alerts themselves are entries in the calendar grid.
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import { tunisDay } from "@/lib/time";
import type { HealthEvent, HealthWatch, Role } from "@/lib/types";
import Link from "next/link";
import styles from "./WeatherCards.module.css";

const n = (v: number | null | undefined) => (v == null ? "—" : Math.round(v).toString());

export function ForecastCard({ watch, compact = false }: { watch: HealthWatch; compact?: boolean }) {
  const { t, lang } = useT();
  if (!watch.available || !watch.days.length) return null;
  return (
    <section className={`${styles.card} ${compact ? styles.compact : ""}`} aria-label={t("shared.hwForecast")}>
      <div className={styles.head}>
        <h2 className={styles.title}>
          {t("shared.hwForecast")} · {watch.city}
        </h2>
        {watch.demo ? <span className={styles.demo}>{t("shared.hwDemo", { name: watch.demo })}</span> : null}
      </div>
      <div className={styles.days}>
        {watch.days.map((d) => (
          <div key={d.date} className={styles.day}>
            <b>{tunisDay(`${d.date}T12:00:00Z`, lang)}</b>
            <span className={styles.temp} dir="ltr">
              {n(d.tmin)}° / {n(d.tmax)}°
            </span>
            <span className={styles.muted}>{t("shared.hwFelt", { v: n(d.apparent_max) })}</span>
            {!compact ? (
              <span className={styles.muted}>
                {t("shared.hwDust", { v: n(d.dust_max) })} · {t("shared.hwAqi", { v: n(d.aqi_max) })}
              </span>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

export function NewsCard({ watch }: { watch: HealthWatch }) {
  const { t, lang } = useT();
  const news = watch.news ?? [];
  return (
    <section className={styles.card} aria-label={t("shared.hwNews")}>
      <h2 className={styles.title}>{t("shared.hwNews")}</h2>
      {!news.length ? <span className={styles.muted}>{t("shared.hwNoNews")}</span> : null}
      <ul className={styles.news}>
        {news.slice(0, 8).map((x) => (
          <li key={x.link}>
            <a href={x.link} target="_blank" rel="noopener noreferrer" dir="auto" lang={x.lang}>
              {x.title}
            </a>
            <span className={styles.muted}>
              {x.source}
              {x.published ? ` · ${tunisDay(x.published, lang)}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The weather part of an event's detail: severity, groups most at risk, and the reader's patients at risk. */
export function WeatherDetail({ ev, role }: { ev: HealthEvent; role: Role }) {
  const { t } = useT();
  const w = ev.weather;
  if (!w) return null;
  return (
    <div className={styles.detail}>
      <span className={`${styles.sev} ${w.severity === "high" ? styles.high : styles.moderate}`}>
        {t(w.severity === "high" ? "calendar.wxSeverityHigh" : "calendar.wxSeverityModerate")}
      </span>
      <span className={styles.label}>{t("calendar.wxGroups")}</span>
      <div className={styles.groups}>
        {w.groups.map((g) => (
          <span key={g} className={styles.group}>
            {t(`shared.grp_${g}` as Key)}
          </span>
        ))}
      </div>
      {role === "admin" ? (
        <span className={styles.muted}>{t("calendar.wxAtRiskCount", { n: w.at_risk_count ?? 0 })}</span>
      ) : role !== "patient" ? (
        <>
          <span className={styles.label}>{t("calendar.wxAtRisk")}</span>
          {w.at_risk?.length ? (
            <div className={styles.groups}>
              {w.at_risk.map((p) => (
                <Link key={p.id} href={`/${role}/patients/${p.id}`} className={styles.patient} dir="auto">
                  {p.name} · {p.groups.map((g) => t(`shared.grp_${g}` as Key)).join(", ")}
                </Link>
              ))}
            </div>
          ) : (
            <span className={styles.muted}>{t("calendar.wxNoneAtRisk")}</span>
          )}
        </>
      ) : null}
    </div>
  );
}
