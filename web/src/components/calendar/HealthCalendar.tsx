"use client";

// The health calendar: a month grid of Tunisian public-health days and campaigns plus the weather-health alerts
// for the next days (one-day "weather" entries with the groups and patients at risk), the selected event, what's
// coming up, the forecast, health news, and the categories this person follows.
// Staff pages use the full layout; the patient tab uses `compact`; admins get `editable`.
import { useEffect, useMemo, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import { localeOf, type Lang } from "@/i18n/config";
import { Toast, useToast } from "@/components/Toast";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { deleteHealthEvent, getHealthPrefs, notifyHealthEvent, setHealthPrefs } from "@/lib/api";
import {
  CATEGORY_LABEL,
  CATEGORY_TONE,
  eventsOn,
  fmtDay,
  fmtRange,
  monthGrid,
  textOf,
  todayIso,
  upcoming,
} from "@/lib/healthCalendar";
import { HEALTH_CATEGORIES, type HealthCategory, type HealthEvent, type HealthPrefs, type Role } from "@/lib/types";
import { EventForm } from "./EventForm";
import { useHealthEvents } from "./useHealthEvents";
import { ForecastCard, NewsCard, WeatherDetail } from "./WeatherCards";
import styles from "./HealthCalendar.module.css";

export interface HealthCalendarProps {
  role: Role;
  /** Admin: add / edit / delete / notify now. Ignored when `compact`. */
  editable?: boolean;
  /** Patient phone: a small month with dots, then the list, the detail and the follow switches. */
  compact?: boolean;
}

type Editing = { kind: "add" } | { kind: "edit"; ev: HealthEvent } | null;

/** "Monday" … "Sunday" short names in the UI language (2024-01-01 was a Monday). */
function weekdayNames(lang: Lang): string[] {
  const fmt = new Intl.DateTimeFormat(localeOf(lang), { weekday: "short", timeZone: "UTC" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(Date.UTC(2024, 0, 1 + i))));
}

function monthName(year: number, month0: number, lang: Lang): string {
  return new Intl.DateTimeFormat(localeOf(lang), { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(year, month0, 1)));
}

/** The Tunis date of an ISO timestamp (UTC+1). */
function tunisDate(ts: string): string {
  return new Date(new Date(ts).getTime() + 3_600_000).toISOString().slice(0, 10);
}

export function HealthCalendar({ role, editable = false, compact = false }: HealthCalendarProps) {
  const { t, lang } = useT();
  const { events, watch, failed, reload } = useHealthEvents(role);
  const today = todayIso();
  const canEdit = editable && !compact;

  const [month, setMonth] = useState(() => ({ y: Number(today.slice(0, 4)), m: Number(today.slice(5, 7)) - 1 }));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const [busy, setBusy] = useState(false);
  const [toast, showToast] = useToast<string>(5000);
  const [prefs, setPrefs] = useState<HealthPrefs | null>(null);

  useEffect(() => {
    let alive = true;
    getHealthPrefs(role).then(
      (p) => alive && setPrefs(p),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [role]);

  const list = useMemo(() => events ?? [], [events]);
  const soon = useMemo(() => upcoming(list, today, 45), [list, today]);
  const selected = list.find((e) => e.id === selectedId) ?? soon[0] ?? null;
  const grid = useMemo(() => monthGrid(month.y, month.m), [month]);
  const weekdays = useMemo(() => weekdayNames(lang), [lang]);
  const monthPrefix = `${month.y}-${String(month.m + 1).padStart(2, "0")}`;

  const shift = (n: number) =>
    setMonth(({ y, m }) => {
      const d = new Date(Date.UTC(y, m + n, 1));
      return { y: d.getUTCFullYear(), m: d.getUTCMonth() };
    });
  const goToday = () => setMonth({ y: Number(today.slice(0, 4)), m: Number(today.slice(5, 7)) - 1 });

  async function follow(c: HealthCategory, on: boolean) {
    setPrefs((p) => (p ? { following: { ...p.following, [c]: on } } : p));
    try {
      setPrefs(await setHealthPrefs({ [c]: on }, role));
    } catch {
      setPrefs((p) => (p ? { following: { ...p.following, [c]: !on } } : p));
    }
    reload();
  }

  async function remove(ev: HealthEvent) {
    if (!window.confirm(t("calendar.confirmDelete"))) return;
    setBusy(true);
    try {
      await deleteHealthEvent(ev.id);
      setSelectedId(null);
      reload();
    } catch {
      showToast(t("calendar.saveError"));
    } finally {
      setBusy(false);
    }
  }

  async function notify(ev: HealthEvent) {
    if (!window.confirm(t("calendar.confirmNotify"))) return;
    setBusy(true);
    try {
      const r = await notifyHealthEvent(ev.id);
      showToast(t("calendar.notified", { n: r.recipients }));
      reload();
    } catch {
      showToast(t("calendar.saveError"));
    } finally {
      setBusy(false);
    }
  }

  const toolbar = (
    <div className={styles.toolbar}>
      <button type="button" className={styles.navBtn} onClick={() => shift(-1)} aria-label={t("calendar.prev")}>
        <span className={styles.flip} aria-hidden="true">
          ‹
        </span>
      </button>
      <h2 className={styles.month} aria-live="polite">
        {monthName(month.y, month.m, lang)}
      </h2>
      <button type="button" className={styles.navBtn} onClick={() => shift(1)} aria-label={t("calendar.next")}>
        <span className={styles.flip} aria-hidden="true">
          ›
        </span>
      </button>
      <button type="button" className={styles.btn} onClick={goToday}>
        {t("calendar.today")}
      </button>
    </div>
  );

  const monthCard = (
    <section className={`${styles.card} ${styles.monthCard}`} aria-busy={events === null}>
      {toolbar}
      <div className={styles.grid} role="grid" aria-label={monthName(month.y, month.m, lang)}>
        <div className={styles.week} role="row">
          {weekdays.map((w) => (
            <span key={w} className={styles.weekday} role="columnheader">
              {w}
            </span>
          ))}
        </div>
        {grid.map((week) => (
          <div key={week[0]} className={styles.week} role="row">
            {week.map((iso) => {
              const on = eventsOn(list, iso);
              const outside = !iso.startsWith(monthPrefix);
              const cls = `${styles.cell} ${outside ? styles.outside : ""} ${iso === today ? styles.today : ""}`;
              const day = <span className={styles.dayNum}>{Number(iso.slice(8))}</span>;
              if (compact) {
                return (
                  <div key={iso} role="gridcell" className={cls}>
                    {on.length ? (
                      <button
                        type="button"
                        className={styles.dayBtn}
                        onClick={() => setSelectedId(on[0].id)}
                        aria-label={`${fmtDay(iso, lang)}: ${on.map((e) => textOf(e.title, lang)).join(", ")}`}
                      >
                        {day}
                        <span className={styles.dots}>
                          {on.slice(0, 3).map((e) => (
                            <span key={e.id} className={styles.dot} style={{ background: CATEGORY_TONE[e.category].fg }} />
                          ))}
                        </span>
                      </button>
                    ) : (
                      day
                    )}
                  </div>
                );
              }
              return (
                <div key={iso} role="gridcell" className={cls}>
                  {day}
                  {on.slice(0, 2).map((e) => (
                    <button
                      key={e.id}
                      type="button"
                      className={`${styles.chip} ${selected?.id === e.id ? styles.chipOn : ""}`}
                      style={{ background: CATEGORY_TONE[e.category].bg, color: CATEGORY_TONE[e.category].fg }}
                      onClick={() => setSelectedId(e.id)}
                      aria-pressed={selected?.id === e.id}
                      title={textOf(e.title, lang)}
                    >
                      {e.matches_me && e.following ? <span className={styles.meDot} aria-hidden="true" /> : null}
                      {textOf(e.title, lang)}
                    </button>
                  ))}
                  {on.length > 2 ? <span className={styles.more}>{t("calendar.more", { n: on.length - 2 })}</span> : null}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );

  const detail = selected ? (
    <section className={styles.card} aria-labelledby="hc-detail-title">
      <div className={styles.tags}>
        <span className={styles.tag} style={{ background: CATEGORY_TONE[selected.category].bg, color: CATEGORY_TONE[selected.category].fg }}>
          {t(CATEGORY_LABEL[selected.category])}
        </span>
        {selected.matches_me ? <span className={`${styles.tag} ${styles.forYou}`}>{t("calendar.forYou")}</span> : null}
      </div>
      <h2 id="hc-detail-title" className={styles.cardTitle}>
        {textOf(selected.title, lang)}
      </h2>
      <span className={styles.when}>{fmtRange(selected, lang)}</span>
      {textOf(selected.description, lang) ? <p className={styles.desc}>{textOf(selected.description, lang)}</p> : null}
      <WeatherDetail ev={selected} role={role} />
      {selected.organizer ? <span className={styles.meta}>{t("calendar.organizer", { org: selected.organizer })}</span> : null}
      {selected.source_url ? (
        <a className={styles.link} href={selected.source_url} target="_blank" rel="noreferrer">
          {t("calendar.source")}
        </a>
      ) : null}
      {canEdit && !selected.weather ? (
        <>
          {selected.announced_at ? (
            <span className={styles.meta}>{t("calendar.announced", { date: fmtDay(tunisDate(selected.announced_at), lang) })}</span>
          ) : null}
          <div className={styles.actions}>
            <button type="button" className={styles.btn} disabled={busy} onClick={() => setEditing({ kind: "edit", ev: selected })}>
              {t("calendar.edit")}
            </button>
            <button type="button" className={styles.btn} disabled={busy} onClick={() => void remove(selected)}>
              {t("calendar.delete")}
            </button>
            <button type="button" className={styles.btnPrimary} disabled={busy} onClick={() => void notify(selected)}>
              {t("calendar.notify")}
            </button>
          </div>
        </>
      ) : null}
      {toast ? (
        <Toast placement="inline" size="sm">
          {toast}
        </Toast>
      ) : null}
    </section>
  ) : toast ? (
    <Toast placement="inline" size="sm">
      {toast}
    </Toast>
  ) : null;

  const upcomingCard = (
    <section className={styles.card} aria-labelledby="hc-upcoming">
      <h2 id="hc-upcoming" className={styles.cardTitle}>
        {t("calendar.upcoming")}
      </h2>
      {events !== null && soon.length === 0 ? <span className={styles.meta}>{t("calendar.noUpcoming")}</span> : null}
      <ul className={styles.list}>
        {soon.map((e) => (
          <li key={e.id}>
            <button
              type="button"
              className={`${styles.listRow} ${selected?.id === e.id ? styles.listRowOn : ""}`}
              onClick={() => setSelectedId(e.id)}
              aria-pressed={selected?.id === e.id}
            >
              <span className={styles.bar} style={{ background: CATEGORY_TONE[e.category].fg }} aria-hidden="true" />
              <span className={styles.listText}>
                <span className={styles.listTitle}>{textOf(e.title, lang)}</span>
                <span className={styles.listWhen}>{fmtRange(e, lang)}</span>
              </span>
              {e.matches_me && e.following ? <span className={styles.meDot} aria-label={t("calendar.forYou")} /> : null}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );

  const followCard = (
    <section className={styles.card} aria-labelledby="hc-following">
      <h2 id="hc-following" className={styles.cardTitle}>
        {t("calendar.following")}
      </h2>
      <div className={styles.follows}>
        {HEALTH_CATEGORIES.map((c) => (
          <label key={c} className={styles.check}>
            <input type="checkbox" disabled={!prefs} checked={prefs?.following[c] ?? false} onChange={(e) => void follow(c, e.target.checked)} />
            <span className={styles.swatch} style={{ background: CATEGORY_TONE[c].fg }} aria-hidden="true" />
            <span>{t(CATEGORY_LABEL[c])}</span>
          </label>
        ))}
      </div>
      <span className={styles.meta}>{t("calendar.followHint")}</span>
    </section>
  );

  const honesty = (
    <p className={styles.honesty}>
      {t("calendar.honesty")}
      {watch ? ` ${t("calendar.wxHonesty")}` : ""}
    </p>
  );

  if (compact) {
    return (
      <div className={`${styles.root} ${styles.compact}`}>
        {failed ? <ErrorCard variant="patient" title={t("calendar.loadError")} message={null} onRetry={reload} /> : null}
        {watch ? <ForecastCard watch={watch} compact /> : null}
        {monthCard}
        {upcomingCard}
        {detail}
        {followCard}
        {honesty}
      </div>
    );
  }

  return (
    <div className={`${styles.root} ${styles.page}`}>
      <header className={styles.head}>
        <div className={styles.titles}>
          <h1 className={styles.h1}>{t("calendar.title")}</h1>
          <span className={styles.sub}>{t("calendar.sub")}</span>
        </div>
        {canEdit ? (
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={() => setEditing({ kind: "add" })}
            aria-expanded={editing?.kind === "add"}
          >
            {t("calendar.add")}
          </button>
        ) : null}
      </header>

      {watch && !failed ? <ForecastCard watch={watch} /> : null}

      {failed ? (
        <ErrorCard title={t("calendar.loadError")} onRetry={reload} secondaryLabel={null} />
      ) : (
        <div className={styles.columns}>
          {monthCard}
          <div className={styles.side}>
            {canEdit && editing ? (
              <EventForm
                key={editing.kind === "edit" ? editing.ev.id : "new"}
                initial={editing.kind === "edit" ? editing.ev : undefined}
                onSaved={(ev) => {
                  setEditing(null);
                  setSelectedId(ev.id);
                  reload();
                }}
                onCancel={() => setEditing(null)}
              />
            ) : (
              detail
            )}
            {upcomingCard}
            {followCard}
            {watch ? <NewsCard watch={watch} /> : null}
          </div>
        </div>
      )}

      {honesty}
    </div>
  );
}

export default HealthCalendar;
