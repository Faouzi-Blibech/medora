"use client";

// Doctor / Patient detail (/doctor/patients/[id]).
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import { LiveBanner } from "@/components/LiveBanner";
import { DosesTimeline } from "@/components/shared/DosesTimeline";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { NotesPanel } from "@/components/shared/NotesPanel";
import { AccessPanel } from "@/components/shared/AccessPanel";
import { ExamsPanel } from "@/components/shared/ExamsPanel";
import { PatientAiCard } from "@/components/shared/PatientAiCard";
import { LIVE_JITTER, useLiveTick } from "@/components/shared/useLiveTick";
import { Toast, useToast } from "@/components/Toast";
import { addNote, getDoses, getNotes, getPatient, getPrescriptions, getVitals } from "@/lib/api";
import { useDemoFlags } from "@/lib/demo";
import { now, pausedAt, tunisTime, USE_MOCKS } from "@/lib/time";
import type { Dose, Note, Patient, Prescription, Vital } from "@/lib/types";
import { useMe } from "@/lib/useMe";
import { DailySummary } from "./DailySummary";
import { PatientHeader } from "./PatientHeader";
import { Prescriptions } from "./Prescriptions";
import { VitalsCard } from "./VitalsCard";
import styles from "./PatientDetail.module.css";

/** The signed-in doctor in the mock demo (Dr Trabelsi). Real mode names the user from GET /me; ids are mock-only. */
const DOCTOR_ID = "u-0001";
const DOCTOR_NAME = "Dr Trabelsi";

/** Doses are not in api.md yet: a missing endpoint shows the timeline's empty state, not an error page. */
const dosesOrEmpty = (id: string): Promise<Dose[]> => getDoses(id).catch(() => []);

interface Data {
  patient: Patient;
  vitals: Vital[];
  prescriptions: Prescription[];
  doses: Dose[];
  notes: Note[];
}

export function PatientDetail({ id }: { id: string }) {
  const { t } = useT();
  const flags = useDemoFlags();
  const router = useRouter();
  const me = useMe("doctor");
  const viewer = USE_MOCKS ? DOCTOR_NAME : (me?.name ?? "…");
  const { sec, reading } = useLiveTick(flags.live && USE_MOCKS);
  const [data, setData] = useState<Data | null>(null);
  const [failed, setFailed] = useState(false);
  const [openedAt] = useState(() => tunisTime(now().toISOString()));
  const [noteError, showNoteError] = useToast<string>();

  const load = useCallback(() => {
    setFailed(false);
    Promise.all([getPatient(id), getVitals(id), getPrescriptions(id), dosesOrEmpty(id), getNotes(id)])
      .then(([patient, vitals, prescriptions, doses, notes]) => setData({ patient, vitals, prescriptions, doses, notes }))
      .catch(() => setFailed(true));
  }, [id]);

  useEffect(load, [load]);

  const refreshRx = useCallback(async () => {
    try {
      const [prescriptions, doses] = await Promise.all([getPrescriptions(id), dosesOrEmpty(id)]);
      setData((d) => (d ? { ...d, prescriptions, doses } : d));
    } catch {
      showNoteError(t("doctor.rxRefreshError"));
    }
  }, [id, showNoteError, t]);

  const onAddNote = useCallback(
    async (text: string) => {
      try {
        const note = await addNote(id, text, { by: DOCTOR_ID });
        setData((d) => (d ? { ...d, notes: [note, ...d.notes] } : d));
      } catch (e) {
        showNoteError(t("doctor.noteSaveError"));
        throw e; // keeps the draft in NotesPanel
      }
    },
    [id, showNoteError, t],
  );

  const state = flags.state === "error" || failed ? "error" : flags.state === "loading" || !data ? "loading" : null;
  // Shared doctor: signed in as a doctor who is not the attending one. Mock mode is always the attending doctor.
  const shared = !USE_MOCKS && !!me && !!data && me.role === "doctor" && data.patient.attending_doctor_id !== me.id;
  const name = data ? `${data.patient.first_name} ${data.patient.last_name}` : "";
  const jitter = flags.live && USE_MOCKS ? LIVE_JITTER[reading % LIVE_JITTER.length] : 0;

  return (
    <div className={styles.page}>
      <div className={styles.crumbs}>
        <Link href="/doctor" className={styles.crumbLink}>
          {t("doctor.myPatients")}
        </Link>
        <span>/</span>
        <span dir="auto" className={styles.crumbHere}>
          {state ? t("doctor.patientCrumb") : name}
        </span>
        <span className={styles.spacer} />
        <span className={styles.audit}>
          <span className={styles.lock} />
          {t("doctor.auditLine", { viewer, time: openedAt })}
        </span>
      </div>
      {shared ? (
        <div className={styles.sharedBanner} role="status">
          {t("doctor.sharedReadOnly")}
        </div>
      ) : null}
      {!flags.live ? <LiveBanner>{t("doctor.chartFrozen", { time: pausedAt() })}</LiveBanner> : null}

      {state === "error" ? (
        <ErrorCard
          title={t("doctor.loadPatientError")}
          onRetry={load}
          secondaryLabel={t("doctor.backToPatients")}
          onSecondary={() => router.push("/doctor")}
        />
      ) : state === "loading" || !data ? (
        <div className={styles.skelCard} aria-busy="true">
          <span className="ward-skeleton" style={{ height: 34, width: 320 }} />
          <span className="ward-skeleton" style={{ height: 14, width: 260 }} />
          <span className="ward-skeleton" style={{ height: 120, width: "100%" }} />
          <span className="ward-skeleton" style={{ height: 120, width: "100%" }} />
        </div>
      ) : (
        <>
          <PatientHeader patient={data.patient} vitals={data.vitals} />
          <div className={styles.columns}>
            <div className={styles.col}>
              <VitalsCard vitals={data.vitals} live={flags.live} sec={sec} hrJitter={jitter} now={now()} />
              <Prescriptions
                readOnly={shared}
                patient={data.patient}
                prescriptions={data.prescriptions}
                actorId={DOCTOR_ID}
                onSaved={() => void refreshRx()}
              />
            </div>
            <div className={styles.col}>
              {me && data.patient.attending_doctor_id === me.id ? (
                <AccessPanel
                  patientId={id}
                  patientName={`${data.patient.first_name} ${data.patient.last_name}`}
                  excludeIds={[me.id]}
                />
              ) : null}
              <PatientAiCard patientId={id} role="doctor" canUpload={!shared} />
              <ExamsPanel patientId={id} role="doctor" readOnly={shared} />
              <DailySummary readOnly={shared} patientId={id} aiFallback={flags.aiFallback} actorId={DOCTOR_ID} />
              <DosesTimeline doses={data.doses} now={now()} />
              <NotesPanel readOnly={shared} notes={data.notes} onAdd={onAddNote} now={now()} />
            </div>
          </div>
        </>
      )}
      {noteError ? <Toast tone="warn">{noteError}</Toast> : null}
    </div>
  );
}

export default PatientDetail;
