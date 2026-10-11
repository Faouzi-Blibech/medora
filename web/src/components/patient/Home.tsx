"use client";

// Patient / Home (/patient): greeting, today's medicines, yesterday's missed dose,
// the next appointment and "Ask a question". Plain words only: no NEWS2.
import { examLabel, deptLabel } from "@/lib/labels";
import Link from "next/link";
import { getDoses, getMyAppointments, getPatient, getPatientExams } from "@/lib/api";
import { useDemoFlags } from "@/lib/demo";
import { useT } from "@/i18n/I18nProvider";
import type { Appointment, ExamOrder } from "@/lib/types";
import { now, tunisDate, tunisTime } from "@/lib/time";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { UpcomingBanner } from "@/components/calendar/UpcomingBanner";
import {
  bedLine,
  daysBetween,
  drugWord,
  greeting,
  longDay,
  MED_LABEL,
  medSource,
  medState,
  myPatientId,
  offlineSince,
  useLoad,
  useOffline,
} from "./patient";
import { EmptyCard, OfflineBanner, PatientScreen, SkeletonCard } from "./PatientScreen";
import styles from "./Patient.module.css";

async function loadHome() {
  const id = await myPatientId();
  // Appointments are optional here: if they fail (route not built yet), Home shows no "Next appointment"
  // card instead of failing the medicines.
  // Exams are optional too; the patient only ever sees ordered or done ones, never suggestions.
  const [patient, doses, appts, allExams] = await Promise.all([
    getPatient(id),
    getDoses(id),
    getMyAppointments(id).catch((): Appointment[] => []),
    getPatientExams(id).catch((): ExamOrder[] => []),
  ]);
  // "Before your visit": exams of a still-upcoming request (requested or confirmed), plus unattached ordered ones.
  const open = new Set(appts.filter((a) => a.status === "requested" || a.status === "confirmed").map((a) => a.id));
  const exams = allExams.filter((e) =>
    e.appointment_id ? open.has(e.appointment_id) && (e.status === "ordered" || e.status === "done") : e.status === "ordered",
  );
  return { patient, doses, appts, exams };
}

export function Home() {
  const { t, lang } = useT();
  const flags = useDemoFlags();
  const offline = useOffline();
  const res = useLoad(loadHome);
  const ref = now();
  const todayIso = ref.toISOString();
  const today = tunisDate(todayIso);

  const data = flags.state === "error" || flags.state === "loading" ? null : res.data;
  const loading = flags.state === "loading" || (res.loading && !data);
  const failed = flags.state === "error" || (!!res.error && !data);

  const todays = (data?.doses ?? [])
    .filter((d) => tunisDate(d.scheduled_at) === today)
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
  const meds = flags.state === "empty" ? [] : todays;
  const missedYesterday = (data?.doses ?? []).filter(
    (d) => d.status === "missed" && daysBetween(d.scheduled_at, todayIso) === 1,
  );
  const next = (data?.appts ?? []).find(
    (a) => a.status === "confirmed" && a.slot_at && Date.parse(a.slot_at) >= ref.getTime(),
  );
  const place = data ? bedLine(data.patient.bed, data.patient.ward, t) : null;

  return (
    <PatientScreen nav="home" apptHref={next ? `/patient/appointments/${next.id}` : undefined}>
      <div className={`${styles.scroll} ${styles.homeBody}`}>
        {offline ? <OfflineBanner since={offlineSince(res.loadedAt)} /> : null}
        <div className={styles.titleBlock}>
          <h1 className={styles.h1}>
            {greeting(ref, lang)}
            {data ? (
              <>
                {t("patient.nameSep")}
                <span dir="auto">{data.patient.first_name}</span>
              </>
            ) : null}
          </h1>
          <span className={styles.subline}>{[place, longDay(todayIso, lang)].filter(Boolean).join(" · ")}</span>
        </div>

        <UpcomingBanner role="patient" href="/patient/calendar" />

        {failed ? (
          <ErrorCard
            variant="patient"
            title={t("patient.errTitle")}
            message={t("patient.homeLoadErr")}
            retryLabel={t("patient.tryAgain")}
            onRetry={flags.state === "error" ? undefined : res.retry}
          />
        ) : loading ? (
          <SkeletonCard />
        ) : meds.length === 0 ? (
          <EmptyCard title={t("patient.noMedsTitle")}>{t("patient.noMedsText")}</EmptyCard>
        ) : (
          <section className={`${styles.card} ${styles.medsCard}`} aria-labelledby="meds-title">
            <h2 id="meds-title" className={styles.cardTitle}>
              {t("patient.todaysMeds")}
            </h2>
            {meds.map((d) => {
              const st = medState(d);
              return (
                <div key={d.id} className={styles.medRow}>
                  <span className={styles.medTime}>{d.time_of_day}</span>
                  <span className={styles.medText}>
                    <span className={styles.medName}>{d.meds.join(" + ")}</span>
                    <span className={styles.medSub}>{medSource(d, t)}</span>
                  </span>
                  <span className={`${styles.medPill} ${styles[`med_${st}`]}`}>{t(MED_LABEL[st])}</span>
                </div>
              );
            })}
          </section>
        )}

        {!failed && !loading && (data?.exams ?? []).length > 0 ? (
          <section className={`${styles.card} ${styles.medsCard}`} aria-label={t("patient.beforeVisit")}>
            <h2 className={styles.cardTitle}>{t("patient.beforeVisit")}</h2>
            {(data?.exams ?? []).map((e) => (
              <div key={e.id} className={styles.medRow}>
                <span className={styles.medText}>
                  <span className={styles.medName}>{examLabel(e, t)}</span>
                  <span className={styles.medSub}>{deptLabel(e.department, t)}</span>
                </span>
                <span className={`${styles.medPill} ${e.status === "done" ? styles.med_taken : styles.med_upcoming}`}>
                  {t(e.status === "done" ? "patient.examDone" : "patient.examTodo")}
                </span>
              </div>
            ))}
            <p className={styles.examNote}>{t("patient.examNote")}</p>
          </section>
        ) : null}

        {!failed && !loading && missedYesterday.length > 0 ? (
          <div className={styles.missed}>
            <span className={styles.missedDot} />
            <span>
              <b>{t("patient.missedYesterday")}</b>{" "}
              {missedYesterday
                .map((d) => t("patient.missedItem", { drugs: d.meds.map(drugWord).join(" + "), time: tunisTime(d.scheduled_at) }))
                .join(t("patient.listSep"))}
              . {t("patient.missedAfter")}
            </span>
          </div>
        ) : null}

        {!failed && !loading && next?.slot_at ? (
          <Link href={`/patient/appointments/${next.id}`} className={styles.nextAppt}>
            <span className={styles.nextEyebrow}>{t("patient.nextAppt")}</span>
            <span className={styles.nextWhen}>
              {longDay(next.slot_at, lang)} · {tunisTime(next.slot_at)}
            </span>
            <span className={styles.nextWho}>{[next.doctor_name, next.room].filter(Boolean).join(" · ")}</span>
            {next.patient_confirmed_at ? null : <span className={styles.nextCta}>
                {t("patient.pleaseConfirm")} <span>›</span>
              </span>}
          </Link>
        ) : null}

        <Link href="/patient/assistant" className={`${styles.outlineBtn} ${styles.ask}`}>
          {t("patient.askQuestion")}
        </Link>
      </div>
    </PatientScreen>
  );
}

export default Home;
