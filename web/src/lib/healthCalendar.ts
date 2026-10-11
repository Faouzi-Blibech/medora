// Pure helpers for the health calendar: dates are plain "YYYY-MM-DD" strings in Africa/Tunis.
import type { Lang } from "@/i18n/config";
import { localeOf } from "@/i18n/config";
import type { Key } from "@/i18n/messages";
import type { CalendarCategory, HealthEvent, HealthText, HealthWatch, Role } from "./types";
import { now } from "./time";

/** Today in Tunis (UTC+1, no DST). */
export function todayIso(): string {
  return new Date(now().getTime() + 3_600_000).toISOString().slice(0, 10);
}

export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Six Monday-first weeks covering the month (dates outside the month included). */
export function monthGrid(year: number, month0: number): string[][] {
  const first = new Date(Date.UTC(year, month0, 1));
  const back = (first.getUTCDay() + 6) % 7;
  const start = addDays(first.toISOString().slice(0, 10), -back);
  return Array.from({ length: 6 }, (_, w) => Array.from({ length: 7 }, (_, d) => addDays(start, w * 7 + d)));
}

export function eventsOn(events: HealthEvent[], iso: string): HealthEvent[] {
  return events.filter((e) => e.starts_on <= iso && e.ends_on >= iso);
}

/** Active today or starting within `days`, soonest first. */
export function upcoming(events: HealthEvent[], today: string, days: number): HealthEvent[] {
  const until = addDays(today, days);
  return events
    .filter((e) => e.ends_on >= today && e.starts_on <= until)
    .sort((a, b) => a.starts_on.localeCompare(b.starts_on) || a.id.localeCompare(b.id));
}

export function forMe(events: HealthEvent[]): HealthEvent[] {
  return events.filter((e) => e.matches_me && e.following);
}

/** Sidebar badge: events for me, active now or starting within 7 days. */
export function badgeCount(events: HealthEvent[], today: string): number {
  return forMe(upcoming(events, today, 7)).length;
}

export function textOf(t: HealthText, lang: Lang): string {
  return t[lang] || t.en;
}

export function fmtDay(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(localeOf(lang), { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));
}

export function fmtRange(ev: HealthEvent, lang: Lang): string {
  return ev.starts_on === ev.ends_on ? fmtDay(ev.starts_on, lang) : `${fmtDay(ev.starts_on, lang)} – ${fmtDay(ev.ends_on, lang)}`;
}

/** Category colours from the design tokens (globals.css). */
export const CATEGORY_TONE: Record<CalendarCategory, { bg: string; fg: string }> = {
  screening: { bg: "var(--news-crit-bg)", fg: "var(--news-crit-fg)" },
  vaccination: { bg: "var(--teal-tint)", fg: "var(--teal-deep)" },
  chronic_disease: { bg: "var(--news-high-bg)", fg: "var(--news-high-fg)" },
  infectious_disease: { bg: "var(--news-low-bg)", fg: "var(--news-low-fg)" },
  lifestyle: { bg: "var(--news-normal-bg)", fg: "var(--news-normal-fg)" },
  mental_health: { bg: "var(--ai-bg)", fg: "var(--ai)" },
  blood_donation: { bg: "var(--danger-bg)", fg: "var(--danger-ink)" },
  weather: { bg: "#e3eef8", fg: "#1f5f8b" },
};

export const CATEGORY_LABEL: Record<CalendarCategory, Key> = {
  screening: "calendar.catScreening",
  vaccination: "calendar.catVaccination",
  chronic_disease: "calendar.catChronic",
  infectious_disease: "calendar.catInfectious",
  lifestyle: "calendar.catLifestyle",
  mental_health: "calendar.catMental",
  blood_donation: "calendar.catBlood",
  weather: "calendar.catWeather",
};

/**
 * Weather-health alerts as one-day calendar entries. Staff see the staff advice, a patient the patient advice;
 * "for you" = always for staff (they prepare the ward), and for a patient only when they are in a risk group.
 */
export function weatherEvents(w: HealthWatch | null, role: Role): HealthEvent[] {
  if (!w) return [];
  const staff = role !== "patient";
  return w.alerts.map((a) => ({
    id: `wx-${a.id}-${a.date}`,
    title: a.title,
    description: (staff ? a.staff : a.patient) ?? a.patient,
    category: "weather" as const,
    starts_on: a.date,
    ends_on: a.date,
    audience: { roles: ["patient", "nurse", "doctor", "admin"], sex: null, min_age: null, max_age: null },
    notify_days_before: 1,
    organizer: w.demo ? `Open-Meteo · ${w.city} · demo` : `Open-Meteo · ${w.city}`,
    source_url: null,
    announced_at: null,
    matches_me: staff || !!a.concerns_me,
    following: true,
    weather: { severity: a.severity, groups: a.groups, at_risk: a.at_risk, at_risk_count: a.at_risk_count },
  }));
}
