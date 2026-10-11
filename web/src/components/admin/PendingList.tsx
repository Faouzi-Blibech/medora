"use client";

import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Key } from "@/i18n/messages";
import { Toast, useToast } from "@/components/Toast";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { describeError, fmtWhen } from "@/lib/accountsUi";
import { ApiError, approveUser, getDoctorDirectory, listUsers, rejectUser, searchPatients, type PatientListItem } from "@/lib/api";
import type { ApproveRequest, GrantRole, PendingUser } from "@/lib/types";
import { WARD_OPTIONS } from "./wards";
import page from "./AdminPage.module.css";
import styles from "./PendingList.module.css";

type Viewer = "admin" | "doctor";

const ROLE_LABEL: Record<GrantRole, Key> = {
  patient: "shared.rolePatient",
  nurse: "admin.roleNurse",
  doctor: "admin.roleDoctor",
  pharmacist: "pharmacy.rolePharmacist",
  admin: "admin.roleAdmin",
};
/** What each viewer may grant: a doctor approves patients and nurses only; only the admin approves pharmacists (spec §2). */
const GRANTABLE: Record<Viewer, GrantRole[]> = {
  admin: ["patient", "nurse", "doctor", "pharmacist", "admin"],
  doctor: ["patient", "nurse"],
};

interface RecordLinkProps {
  viewer: Viewer;
  initialQuery: string;
  /** The chosen existing record; `null` = create a new record. */
  value: PatientListItem | null;
  onChange: (p: PatientListItem | null) => void;
}

/** "Link to medical record" step of a patient request: pick an existing record or create a new one. */
function RecordLink({ viewer, initialQuery, value, onChange }: RecordLinkProps) {
  const { t } = useT();
  const [q, setQ] = useState(initialQuery);
  const [results, setResults] = useState<PatientListItem[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const group = useId();

  async function search(e?: FormEvent) {
    e?.preventDefault();
    if (busy || !q.trim()) return;
    setBusy(true);
    setError(false);
    try {
      // The admin searches every record, so ask only for those without an account. A doctor keeps his normal scope.
      setResults(await searchPatients(q, { as: viewer, unlinked: viewer === "admin" }));
    } catch {
      setResults(null);
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  const options = value ? [value, ...(results ?? []).filter((r) => r.id !== value.id)] : (results ?? []);
  return (
    <fieldset className={styles.link}>
      <legend className={styles.linkLegend}>{t("accounts.linkTitle")}</legend>
      <label className={styles.linkOption}>
        <input type="radio" name={group} checked={value === null} onChange={() => onChange(null)} />
        <span>{t("accounts.linkNew")}</span>
      </label>
      <div className={styles.linkSearch}>
        <input
          dir="auto"
          aria-label={t("accounts.linkSearchLabel")}
          placeholder={t("accounts.linkSearchLabel")}
          className={page.input}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void search(e);
          }}
        />
        <button type="button" className={page.btn} disabled={busy || !q.trim()} onClick={() => void search()}>
          {t("accounts.linkSearchGo")}
        </button>
      </div>
      {error ? (
        <span role="alert" className={styles.linkError}>
          {t("accounts.linkSearchError")}
        </span>
      ) : null}
      {results && results.length === 0 && !value ? <span className={styles.meta}>{t("accounts.linkNoMatch")}</span> : null}
      {options.map((p) => (
        <label key={p.id} className={styles.linkOption}>
          <input type="radio" name={group} checked={value?.id === p.id} onChange={() => onChange(p)} />
          <span dir="auto">
            {p.first_name} {p.last_name}
          </span>
          <span dir="ltr" className={styles.meta}>
            {p.id}
          </span>
        </label>
      ))}
    </fieldset>
  );
}

interface RowProps {
  u: PendingUser;
  viewer: Viewer;
  doctorName: string | null;
  busy: boolean;
  onApprove: (req: ApproveRequest) => void;
  onReject: () => void;
}

function Row({ u, viewer, doctorName, busy, onApprove, onReject }: RowProps) {
  const { t, lang } = useT();
  const allowed = GRANTABLE[viewer];
  const [role, setRole] = useState<GrantRole>(u.requested_role && allowed.includes(u.requested_role) ? u.requested_role : "nurse");
  const [ward, setWard] = useState("");
  const [record, setRecord] = useState<PatientListItem | null>(null);

  function approve() {
    onApprove({
      role,
      ...(viewer === "admin" && role === "nurse" ? { ward: ward || null } : {}),
      ...(role === "patient" && record ? { patient_id: record.id } : {}),
    });
  }

  const requested = u.requested_role ? t("accounts.pendingRole", { role: t(ROLE_LABEL[u.requested_role]) }) : null;
  const chosen = u.requested_doctor_id
    ? t("accounts.pendingWorksWith", { doctor: doctorName ?? u.requested_doctor_id })
    : u.requested_role === "patient" || u.requested_role === "nurse"
      ? t("accounts.pendingNoDoctor")
      : null;

  return (
    <div className={styles.row}>
      <div className={styles.who}>
        <span dir="auto" className={styles.name}>
          {u.name}
        </span>
        <span className={styles.email}>{u.email}</span>
        {u.note ? (
          <span dir="auto" className={styles.meta}>
            {u.note}
          </span>
        ) : null}
        <span className={styles.meta}>{[requested, chosen].filter(Boolean).join(" · ")}</span>
        <span className={styles.meta}>{t("accounts.pendingRequested", { when: fmtWhen(u.created_at, lang) })}</span>
      </div>
      <div className={styles.controls}>
        <select aria-label={t("accounts.approveAs")} className={page.select} value={role} onChange={(e) => setRole(e.target.value as GrantRole)}>
          {allowed.map((r) => (
            <option key={r} value={r}>
              {t(ROLE_LABEL[r])}
            </option>
          ))}
        </select>
        {viewer === "admin" && role === "nurse" ? (
          <select aria-label={t("accounts.approveWard")} className={page.select} value={ward} onChange={(e) => setWard(e.target.value)}>
            <option value="">{t("accounts.wardNone")}</option>
            {WARD_OPTIONS.map((w) => (
              <option key={w.ward} value={w.ward}>
                {t(w.label)}
              </option>
            ))}
          </select>
        ) : null}
        <button type="button" className={page.btnPrimary} disabled={busy} onClick={approve}>
          {t("accounts.approve")}
        </button>
        {u.status === "pending" ? (
          <button type="button" className={page.btn} disabled={busy} onClick={onReject}>
            {t("accounts.reject")}
          </button>
        ) : null}
      </div>
      {role === "patient" ? <RecordLink viewer={viewer} initialQuery={u.name} value={record} onChange={setRecord} /> : null}
    </div>
  );
}

export function PendingList({ viewer, onChanged }: { viewer: Viewer; onChanged?: () => void }) {
  const { t } = useT();
  const [pending, setPending] = useState<PendingUser[] | null>(null);
  const [rejected, setRejected] = useState<PendingUser[]>([]);
  const [failed, setFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [doctorNames, setDoctorNames] = useState<Record<string, string>>({});
  const [toast, showToast] = useToast<{ text: string; tone: "ok" | "warn" }>(5000);

  const load = useCallback(() => {
    setFailed(false);
    Promise.all([listUsers("pending", { as: viewer }), listUsers("rejected", { as: viewer })])
      .then(([p, r]) => {
        setPending(p);
        setRejected(r);
      })
      .catch(() => setFailed(true));
  }, [viewer]);
  useEffect(load, [load]);
  useEffect(() => {
    // Best effort: a request carries only the chosen doctor's id, so resolve the name from the public directory.
    let alive = true;
    getDoctorDirectory().then(
      (d) => alive && setDoctorNames(Object.fromEntries(d.map((x) => [x.id, x.name]))),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, []);

  async function act(u: PendingUser, run: () => Promise<unknown>, done: Key, conflict?: Key) {
    setBusyId(u.id);
    try {
      await run();
      showToast({ text: t(done, { name: u.name }), tone: "ok" });
      load();
      onChanged?.();
    } catch (err) {
      showToast({ text: t(conflict && err instanceof ApiError && err.status === 409 ? conflict : describeError(err).key), tone: "warn" });
    } finally {
      setBusyId(null);
    }
  }

  if (failed) return <ErrorCard title={t("accounts.pendingLoadError")} onRetry={load} />;
  if (!pending) return <div className="ward-skeleton" style={{ height: 120 }} aria-busy="true" />;

  const rows = (list: PendingUser[]) =>
    list.map((u) => (
      <Row
        key={u.id}
        u={u}
        viewer={viewer}
        doctorName={u.requested_doctor_name ?? (u.requested_doctor_id ? (doctorNames[u.requested_doctor_id] ?? null) : null)}
        busy={busyId === u.id}
        onApprove={(req) => void act(u, () => approveUser(u.id, req, { as: viewer }), "accounts.approvedToast", req.patient_id ? "accounts.linkTaken" : undefined)}
        onReject={() => void act(u, () => rejectUser(u.id, { as: viewer }), "accounts.rejectedToast")}
      />
    ));

  return (
    <>
      <div className={styles.list}>{pending.length ? rows(pending) : <p className={styles.empty}>{t("accounts.pendingEmpty")}</p>}</div>
      {rejected.length ? (
        <>
          <h3 className={styles.heading}>{t("accounts.rejectedHeading")}</h3>
          <div className={styles.list}>{rows(rejected)}</div>
        </>
      ) : null}
      {toast ? <Toast tone={toast.tone}>{toast.text}</Toast> : null}
    </>
  );
}

export default PendingList;
