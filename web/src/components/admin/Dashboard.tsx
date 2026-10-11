"use client";

// Admin / Dashboard (/admin): KPI tiles, requests-per-day chart, "Needs a person".
// Live tiles come from api.ts (waitlist, devices, open alerts). Figures that have no
// endpoint yet (hospital-wide admissions, reminder and refill stats, the 7-day
// history) are the design's sample values, kept below.
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { useT } from "@/i18n/I18nProvider";
import type { Lang } from "@/i18n/config";
import type { TFn } from "@/i18n/messages";
import { getAlerts, getDevices, getWaitlist } from "@/lib/api";
import { useDemoFlags } from "@/lib/demo";
import { URGENCY_BAR, urgencyWord } from "@/lib/labels";
import { daysSince, greeting, now, tunisDay, tunisTime, USE_MOCKS } from "@/lib/time";
import { useMe } from "@/lib/useMe";
import type { Alert, Appointment, Device, Urgency } from "@/lib/types";
import { usePatientWards, wardsOf } from "./wards";
import page from "./AdminPage.module.css";
import styles from "./Dashboard.module.css";

const LATEST_FW = "v0.4.2";
const BAR_MAX = 40;
/** Requests per day by urgency [5, 4, 3, 2, 1] (design sample; no stats endpoint yet). */
const BAR_DATA: [string, number[]][] = [
  ["2026-09-29T12:00:00Z", [2, 4, 9, 11, 5]],
  ["2026-09-30T12:00:00Z", [3, 5, 8, 14, 6]],
  ["2026-10-01T12:00:00Z", [2, 6, 10, 12, 4]],
  ["2026-10-02T12:00:00Z", [4, 5, 7, 13, 7]],
  ["2026-10-03T12:00:00Z", [1, 2, 4, 6, 3]],
  ["2026-10-04T12:00:00Z", [1, 2, 3, 5, 2]],
  ["2026-10-05T12:00:00Z", [3, 4, 6, 8, 3]],
];
/** "Tue 29": the weekday and day number of tunisDay. */
const barDay = (iso: string, lang: Lang) => tunisDay(iso, lang).split(" ").slice(0, 2).join(" ");

interface Data {
  waitlist: Appointment[];
  /** GET /appointments/waitlist failed (not built yet in real mode): the tiles say so instead of failing the page. */
  waitlistFailed: boolean;
  devices: Device[];
  /** null in real mode: GET /alerts is nurse/doctor only, so the tile says so instead of showing a false 0. */
  alerts: Alert[] | null;
  /** "Ward C" (mock) or the wards of the device patients (real), null when unknown. */
  ward: string | null;
}

interface Kpi {
  label: string;
  value: string | number;
  of: string;
  note: string;
  noteFg: string;
  href: string;
}

interface Todo {
  c: string;
  title: string;
  sub: string;
  cta: string;
  href: string;
}

// Every row here is unconfirmed: GET /appointments/waitlist returns only status "requested" (api.md line 83,
// mock filter in lib/api.ts getWaitlist); an urgency override sets urgency_final but does not confirm.
const urgencyOf = (a: Appointment) => a.urgency_final ?? a.urgency_ai;

function buildKpis({ waitlist, waitlistFailed, devices, alerts, ward }: Data, t: TFn): Kpi[] {
  const assigned = devices.filter((d) => d.patient_id).length;
  const free = devices.length - assigned;
  const crit = (alerts ?? []).filter((a) => a.severity === "critical");
  const veryUrgent = waitlist.filter((a) => urgencyOf(a) === 5).length;
  const online = devices.filter((d) => d.online).length;
  const offline = devices.find((d) => !d.online);
  return [
    {
      label: t("admin.dashAdmitted"),
      value: USE_MOCKS ? "42" : assigned,
      of: "",
      note: t("admin.dashAdmittedNote", {
        place: ward ?? t("admin.beds"),
        assigned,
        free: t(free === 1 ? "admin.dashBedFree" : "admin.dashBedsFree", { n: free }),
      }),
      noteFg: "var(--muted)",
      href: "/admin/devices",
    },
    {
      label: t("admin.dashOpenAlerts"),
      value: alerts ? alerts.length : "—",
      of: "",
      note: alerts
        ? `${t("admin.dashCritical", { n: crit.length })}${crit[0]?.bed ? ` · ${t("admin.bedN", { bed: crit[0].bed })}` : ""}`
        : t("admin.dashAlertsClinical"),
      noteFg: crit.length ? "var(--danger)" : "var(--muted)",
      href: "/nurse/alerts",
    },
    {
      label: t("admin.dashWaitlistKpi"),
      value: waitlistFailed ? "—" : waitlist.length,
      of: waitlistFailed ? "" : t("admin.dashRequests"),
      note: waitlistFailed ? t("admin.dashWaitlistDown") : t("admin.dashVeryUrgentNote", { n: veryUrgent }),
      noteFg: veryUrgent && !waitlistFailed ? "var(--danger)" : "var(--muted)",
      href: "/admin/waitlist",
    },
    {
      label: t("admin.dashUnitsOnline"),
      value: online,
      of: `/ ${devices.length}`,
      note: offline ? t("admin.dashOfflineSince", { id: offline.id, time: tunisTime(offline.last_seen) }) : t("admin.dashAllOnline"),
      noteFg: offline ? "var(--news-high-fg)" : "var(--muted)",
      href: "/admin/devices",
    },
    {
      label: t("admin.dashReminders"),
      value: "31",
      of: "/ 36",
      note: t("admin.dashRemindersNote"),
      noteFg: "var(--muted)",
      href: "/admin/waitlist",
    },
    {
      label: t("admin.dashRefilled"),
      value: "4",
      of: t("admin.dashThisWeek"),
      note: t("admin.dashRefillNote"),
      noteFg: "var(--news-normal-fg)",
      href: "/admin/waitlist",
    },
  ];
}

function buildTodo({ waitlist, devices }: Data, t: TFn, lang: Lang): Todo[] {
  const todo: Todo[] = [];
  const vu = waitlist.filter((a) => urgencyOf(a) === 5);
  if (vu.length) {
    const chest = vu.filter((a) => a.triage.red_flags.some((f) => f.includes("chest_pain"))).length;
    const oldest = Math.max(...vu.map((a) => daysSince(a.created_at)));
    todo.push({
      c: URGENCY_BAR[5],
      title: t(vu.length === 1 ? "admin.dashVuOne" : "admin.dashVuMany", { n: vu.length }),
      sub: `${chest ? `${t("admin.dashChestPain", { n: chest })} · ` : ""}${t(oldest === 1 ? "admin.dashOldestOne" : "admin.dashOldestMany", { n: oldest })}`,
      cta: t("admin.waitlist"),
      href: "/admin/waitlist",
    });
  }
  for (const d of devices.filter((x) => !x.online)) {
    todo.push({
      c: URGENCY_BAR[3],
      title: `${t("admin.dashOffline", { id: d.id })}${d.bed ? ` · ${t("admin.bedN", { bed: d.bed })}` : ""}`,
      sub: `${t("admin.dashLastSeen", { time: tunisTime(d.last_seen) })}${d.patient_name ? ` · ${d.patient_name}` : ""}`,
      cta: t("admin.devices"),
      href: "/admin/devices",
    });
  }
  for (const d of devices.filter((x) => x.fw_version !== LATEST_FW)) {
    todo.push({
      c: URGENCY_BAR[3],
      title: t("admin.dashFirmware", { id: d.id }),
      sub: t("admin.dashFirmwareSub", { from: d.fw_version, to: LATEST_FW }),
      cta: t("admin.devices"),
      href: "/admin/devices",
    });
  }
  // Freed-slot offers have no endpoint yet: design sample.
  todo.push({
    c: URGENCY_BAR[2],
    title: t("admin.dashSlotFreed", { slot: `${tunisDay("2026-10-07T12:00:00Z", lang)} 10:00` }),
    sub: t("admin.dashOffered", { name: "Karim Ben Ali" }),
    cta: t("admin.view"),
    href: "/admin/waitlist",
  });
  return todo;
}

export function Dashboard() {
  const { t, lang } = useT();
  const flags = useDemoFlags();
  const me = useMe("admin");
  const patientWards = usePatientWards();
  const [data, setData] = useState<Omit<Data, "ward"> | null>(null);
  const [failed, setFailed] = useState(false);

  const fallback = flags.aiFallback;
  const load = useCallback((quiet = false) => {
    if (!quiet) {
      setFailed(false);
      setData(null);
    }
    // GET /alerts is nurse/doctor only in api.md: real mode does not ask (the tile shows "—"), mock mode shows them.
    // The waitlist is optional too: a failure empties it and notes it on the tile; devices still decide the page.
    let waitlistFailed = false;
    Promise.all([
      getWaitlist({ fallback }).catch((): Appointment[] => {
        waitlistFailed = true;
        return [];
      }),
      getDevices(),
      USE_MOCKS ? getAlerts({ status: "open" }).catch((): Alert[] => []) : Promise.resolve(null),
    ])
      .then(([waitlist, devices, alerts]) => {
        setData({ waitlist, waitlistFailed, devices, alerts });
        setFailed(false);
      })
      .catch(() => {
        if (!quiet) setFailed(true);
      });
  }, [fallback]);

  useEffect(() => load(), [load]);

  // "Figures refresh every minute" (paused while live data is reconnecting).
  useEffect(() => {
    if (!flags.live) return;
    const timer = setInterval(() => load(true), 60_000);
    return () => clearInterval(timer);
  }, [flags.live, load]);

  const state = flags.state === "empty" ? null : (flags.state ?? (failed ? "error" : data == null ? "loading" : null));
  const clock = now().toISOString();
  const legend = ([5, 4, 3, 2, 1] as Urgency[]).map((n) => ({ c: URGENCY_BAR[n], label: `${n} · ${urgencyWord(n, t)}` }));
  const full: Data | null = data ? { ...data, ward: wardsOf(data.devices.map((d) => d.patient_id), patientWards, t) } : null;
  const name = USE_MOCKS ? "Mme Gharbi" : me?.name;

  return (
    <div className={`${page.page} ${styles.page}`}>
      <div className={page.head}>
        <div className={page.titles}>
          <h2 className={page.h2}>{name ? `${greeting(now(), lang)}, ${name}` : greeting(now(), lang)}</h2>
          <span className={page.sub}>
            Hôpital Régional · {tunisDay(clock, lang)}, {tunisTime(clock)}
          </span>
        </div>
        <span className={styles.refresh}>{t("admin.dashFigures")}</span>
      </div>

      {state === "loading" ? (
        <div className={styles.kpis} aria-busy="true">
          {[1, 2, 3, 4, 5, 6].map((k) => (
            <div key={k} className={styles.skelTile}>
              <span className={styles.skelLabel} />
              <span className={`ward-skeleton ${styles.skelValue}`} />
            </div>
          ))}
        </div>
      ) : state === "error" || !full ? (
        <ErrorCard title={t("admin.dashLoadError")} onRetry={() => load()} />
      ) : (
        <div className={styles.kpis}>
          {buildKpis(full, t).map((k) => (
            <Link key={k.label} href={k.href} className={styles.kpi}>
              <span className={styles.kpiLabel}>{k.label}</span>
              <span className={styles.kpiValueRow}>
                <span className={styles.kpiValue}>{k.value}</span>
                {k.of ? <span className={styles.kpiOf}>{k.of}</span> : null}
              </span>
              <span className={styles.kpiNote} style={{ color: k.noteFg }}>
                {k.note}
              </span>
            </Link>
          ))}
        </div>
      )}

      <div className={styles.lower}>
        <section className={`${styles.card} ${styles.chartCard}`}>
          <div className={styles.legendRow}>
            <h3 className={`${styles.h3} ${styles.chartTitle}`}>{t("admin.dashChartTitle")}</h3>
            {legend.map((l) => (
              <span key={l.label} className={styles.legend}>
                <span className={styles.swatch} style={{ background: l.c }} />
                {l.label}
              </span>
            ))}
          </div>
          <div className={styles.chart} dir="ltr">
            <div className={styles.axis}>
              <span>40</span>
              <span>20</span>
              <span>0</span>
            </div>
            {BAR_DATA.map(([day, segs]) => {
              const total = segs.reduce((x, y) => x + y, 0);
              return (
                <div
                  key={day}
                  title={t("admin.dashBarTitle", { day: barDay(day, lang), total })}
                  className={styles.bar}
                  style={{ height: `${(total / BAR_MAX) * 100}%` }}
                >
                  {segs.map((v, i) => (
                    <span
                      key={i}
                      className={styles.seg}
                      style={{ height: `${(v / total) * 100}%`, background: URGENCY_BAR[(5 - i) as Urgency] }}
                    />
                  ))}
                </div>
              );
            })}
          </div>
          <div className={styles.days} dir="ltr">
            <span />
            {BAR_DATA.map(([day, segs]) => (
              <span key={day} className={styles.day}>
                <b>{segs.reduce((x, y) => x + y, 0)}</b>
                {barDay(day, lang)}
              </span>
            ))}
          </div>
        </section>

        <section className={`${styles.card} ${styles.todoCard}`}>
          <h3 className={`${styles.h3} ${styles.todoTitle}`}>{t("admin.dashNeeds")}</h3>
          {full && state == null
            ? buildTodo(full, t, lang).map((item) => (
                <Link key={item.title} href={item.href} className={styles.todo}>
                  <span className={styles.todoDot} style={{ background: item.c }} />
                  <span className={styles.todoText}>
                    <span className={styles.todoHead}>{item.title}</span>
                    <span className={styles.todoSub}>{item.sub}</span>
                  </span>
                  <span className={styles.todoCta}>
                    {item.cta} <span>›</span>
                  </span>
                </Link>
              ))
            : [1, 2, 3].map((k) => (
                <div key={k} className={styles.todo} aria-busy={state === "loading" || undefined}>
                  <span className={`ward-skeleton ${styles.skelTodo}`} />
                </div>
              ))}
        </section>
      </div>
    </div>
  );
}

export default Dashboard;
