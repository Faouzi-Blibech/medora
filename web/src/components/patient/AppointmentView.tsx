"use client";

// Patient / Appointment (/patient/appointments/[id]) and Patient / Appointment · Confirmed.
// Confirm → POST /appointments/{id}/reply "confirm" → the full-screen confirmation.
// Cancel → reply "cancel" → the grey "Cancelled…" status. "Undo (demo)" (mock mode only) resets this view.
import Link from "next/link";
import { useState } from "react";
import { getMyAppointments, replyAppointment } from "@/lib/api";
import { useDemoFlags } from "@/lib/demo";
import { useT } from "@/i18n/I18nProvider";
import type { TFn } from "@/i18n/messages";
import { tunisTime, USE_MOCKS } from "@/lib/time";
import type { Appointment } from "@/lib/types";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { dayMonthLong, longDay, myPatientId, offlineSince, useLoad, useOffline, weekday } from "./patient";
import { OfflineBanner, PatientScreen, SkeletonCard } from "./PatientScreen";
import styles from "./Patient.module.css";

type View = "open" | "confirmed" | "yes" | "no";

async function loadAppointment(id: string): Promise<Appointment> {
  const list = await getMyAppointments(await myPatientId());
  const a = list.find((x) => x.id === id);
  if (!a) throw new Error("Appointment not found");
  return a;
}

function initialView(a: Appointment): View {
  if (a.status === "cancelled") return "no";
  return a.patient_confirmed_at ? "yes" : "open";
}

/** A one-event .ics file for "Add to my calendar" (built in the browser, no network). */
function downloadIcs(a: Appointment, t: TFn) {
  const hospital = t("patient.hospital");
  if (!a.slot_at) return;
  const stamp = (d: Date) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const start = new Date(a.slot_at);
  const end = new Date(start.getTime() + 30 * 60_000);
  const ics = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Medora//Patient//EN",
    "BEGIN:VEVENT",
    `UID:${a.id}@medora`,
    `DTSTAMP:${stamp(new Date())}`,
    `DTSTART:${stamp(start)}`,
    `DTEND:${stamp(end)}`,
    `SUMMARY:${[a.doctor_name, a.specialty].filter(Boolean).join(" · ") || t("patient.icsFallback")}`,
    `LOCATION:${hospital}${a.room ? `, ${a.room.split(", ").pop()}` : ""}`,
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");
  const url = URL.createObjectURL(new Blob([ics], { type: "text/calendar" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `medora-appointment-${a.id}.ics`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function AppointmentView({ id }: { id: string }) {
  const { t, lang } = useT();
  // The hospital is not in the record yet; the design's text.
  const hospital = t("patient.hospital");
  const flags = useDemoFlags();
  const offline = useOffline();
  const res = useLoad(() => loadAppointment(id), id);
  const [view, setView] = useState<View | null>(null);
  const [busy, setBusy] = useState(false);
  const [sendError, setSendError] = useState(false);

  const a = flags.state === "error" || flags.state === "loading" ? null : res.data;
  const current: View | null = a ? (view ?? initialView(a)) : null;

  async function reply(kind: "confirm" | "cancel") {
    if (!a) return;
    setBusy(true);
    setSendError(false);
    try {
      const updated = await replyAppointment(a.id, kind);
      res.setData(updated);
      setView(kind === "confirm" ? "confirmed" : "no");
    } catch {
      setSendError(true);
    } finally {
      setBusy(false);
    }
  }

  if (a && current === "confirmed") {
    const dayBefore = a.slot_at ? weekday(new Date(Date.parse(a.slot_at) - 86_400_000).toISOString(), lang) : null;
    return (
      <PatientScreen icons={false} brand={false}>
        <div role="status" className={styles.result}>
          <span className={styles.resultIcon} aria-hidden="true">
            ✓
          </span>
          <h1 className={styles.resultTitle}>
            {a.slot_at
              ? t("patient.thanksSee", { day: longDay(a.slot_at, lang), time: tunisTime(a.slot_at) })
              : t("patient.thanksSoon")}
          </h1>
          <span className={styles.resultText}>
            {dayBefore ? t("patient.reminderOn", { day: dayBefore }) : t("patient.reminder")}
          </span>
          <span className={styles.flex} />
          <button type="button" className={`${styles.primaryBtn} ${styles.fullWidth}`} onClick={() => downloadIcs(a, t)}>
            {t("patient.addCalendar")}
          </button>
          <Link href="/patient" className={`${styles.secondaryBtn} ${styles.fullWidth}`}>
            {t("patient.backHome")}
          </Link>
        </div>
      </PatientScreen>
    );
  }

  const failed = flags.state === "error" || (!!res.error && !res.data);
  const loading = flags.state === "loading" || (res.loading && !res.data);

  return (
    <PatientScreen>
      <div className={styles.apptBody}>
        {offline ? <OfflineBanner since={offlineSince(res.loadedAt)} /> : null}
        <h1 className={styles.h1Small}>{t("patient.apptTitle")}</h1>
        {failed ? (
          <ErrorCard
            variant="patient"
            title={t("patient.errTitle")}
            message={t("patient.apptLoadErr")}
            retryLabel={t("patient.tryAgain")}
            onRetry={flags.state === "error" ? undefined : res.retry}
          />
        ) : loading || !a ? (
          <SkeletonCard />
        ) : (
          <>
            <section className={styles.apptCard}>
              <div className={styles.apptHead}>
                {a.slot_at ? (
                  <>
                    <span className={styles.apptWeekday}>{weekday(a.slot_at, lang)}</span>
                    <span className={styles.apptDate}>{dayMonthLong(a.slot_at, lang)}</span>
                    <span className={styles.apptTime}>{tunisTime(a.slot_at)}</span>
                  </>
                ) : (
                  <span className={styles.apptDate}>{t("patient.dateTbc")}</span>
                )}
              </div>
              <div className={styles.apptFacts}>
                <div className={styles.fact}>
                  <span className={styles.factLabel}>{t("patient.factDoctor")}</span>
                  <b>{[a.doctor_name, a.specialty].filter(Boolean).join(" · ") || t("patient.toBeConfirmed")}</b>
                </div>
                <div className={styles.fact}>
                  <span className={styles.factLabel}>{t("patient.factWhere")}</span>
                  <span>
                    {hospital}
                    {a.room ? `, ${a.room.split(", ").pop()}` : ""}
                  </span>
                </div>
                <div className={styles.fact}>
                  <span className={styles.factLabel}>{t("patient.factBring")}</span>
                  <span>{t("patient.bringText")}</span>
                </div>
              </div>
            </section>

            {sendError ? (
              <ErrorCard
                variant="patient"
                title={t("patient.errTitle")}
                message={t("patient.sendErr")}
                retryLabel={t("patient.tryAgain")}
              />
            ) : null}

            {current === "open" ? (
              <div className={styles.apptActions}>
                <button type="button" className={styles.primaryBtn} disabled={busy} onClick={() => reply("confirm")}>
                  {t("patient.confirmComing")}
                </button>
                <button type="button" className={styles.secondaryBtn} disabled={busy} onClick={() => reply("cancel")}>
                  {t("patient.cancel")}
                </button>
                <span className={styles.apptNote}>{t("patient.cancelNote")}</span>
              </div>
            ) : (
              <div role="status" className={`${styles.apptDone} ${current === "yes" ? styles.apptDone_yes : styles.apptDone_no}`}>
                <span className={styles.apptDoneIcon} aria-hidden="true">
                  <span>{current === "yes" ? "✓" : "–"}</span>
                </span>
                <span className={styles.apptDoneMsg}>
                  {current === "yes"
                    ? a.slot_at
                      ? t("patient.thanksSee", { day: longDay(a.slot_at, lang), time: tunisTime(a.slot_at) })
                      : t("patient.thanksSoon")
                    : t("patient.cancelledMsg")}
                </span>
                {USE_MOCKS ? (
                  <button type="button" className={styles.linkBtn} onClick={() => setView("open")}>
                    {t("patient.undoDemo")}
                  </button>
                ) : null}
              </div>
            )}
          </>
        )}
      </div>
    </PatientScreen>
  );
}

export default AppointmentView;
