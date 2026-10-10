"use client";

// Admin / Staff accounts (/admin/staff) with the "Add staff" side panel.
// `?add=1` opens the panel pre-filled as in the design. There is no invite
// endpoint in api.md yet: in mock mode "Send invite" adds the row locally; in real
// mode it says invites aren't available instead of claiming one was sent.
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import type { Key, TFn } from "@/i18n/messages";
import type { Lang } from "@/i18n/config";
import { Toast, useToast } from "@/components/Toast";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { CodeDialog } from "@/components/shared/CodeDialog";
import { disableUser, enableUser, getStaff, issueResetCode, setUserWard } from "@/lib/api";
import { describeError } from "@/lib/accountsUi";
import { useMe } from "@/lib/useMe";
import { useDemoFlags } from "@/lib/demo";
import { dayLabel, now, tunisTime, USE_MOCKS } from "@/lib/time";
import type { StaffMember } from "@/lib/types";
import { WardEditor } from "./WardEditor";
import page from "./AdminPage.module.css";
import styles from "./StaffView.module.css";

type StaffRole = StaffMember["role"];

const ROLE_LABEL: Record<StaffRole, Key> = { doctor: "admin.roleDoctor", nurse: "admin.roleNurse", admin: "admin.roleAdmin", pharmacist: "pharmacy.rolePharmacist" };
const ROLE_COLORS: Record<StaffRole, [string, string]> = {
  doctor: ["var(--doctor-bg)", "var(--doctor-fg)"],
  nurse: ["var(--ai-bg)", "var(--news-normal-fg)"],
  admin: ["var(--segment)", "var(--text)"],
  pharmacist: ["var(--warn-bg)", "var(--warn-ink)"],
};
const STATUS_LABEL: Record<StaffMember["status"], Key> = {
  active: "accounts.statusActive",
  pending: "accounts.statusPending",
  disabled: "accounts.statusDisabled",
  rejected: "accounts.statusRejected",
};
const WARDS: { value: string; ward: string | null; label: Key }[] = [
  { value: "Cardiology · Ward C", ward: "Cardiology", label: "admin.wardCardiology" },
  { value: "Pediatrics", ward: "Pediatrics", label: "admin.wardPediatrics" },
  { value: "Pulmonology", ward: "Pulmonology", label: "admin.wardPulmonology" },
  { value: "Administration", ward: null, label: "admin.wardAdministration" },
];
// What GET /staff puts in `scope`: the ward name, or this when the account has none.
const ALL_WARDS = "All wards";
const ROLE_HELP: Partial<Record<StaffRole, Key>> = {
  nurse: "admin.roleHelpNurse",
};
const DESIGN_DRAFT = { name: "Nour Hammami", email: "n.hammami@hr-ward.tn", role: "nurse" as StaffRole, scope: WARDS[0].value };
const EMPTY_DRAFT = { name: "", email: "", role: "nurse" as StaffRole, scope: WARDS[0].value };

const lastLogin = (iso: string | null, t: TFn, lang: Lang) => (iso ? `${dayLabel(iso, now(), lang)} ${tunisTime(iso)}` : t("admin.staffInvited"));

export function StaffView() {
  const { t, lang } = useT();
  const flags = useDemoFlags();
  const params = useSearchParams();
  const startOpen = params.get("add") === "1";
  const [staff, setStaff] = useState<StaffMember[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(startOpen);
  const [draft, setDraft] = useState(startOpen ? DESIGN_DRAFT : EMPTY_DRAFT);
  const [invalid, setInvalid] = useState(false);
  const [toast, showToast] = useToast<string>(5000);
  const me = useMe("admin");
  const [code, setCode] = useState<{ name: string; code: string; expires_at: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const addBtnRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(() => {
    setFailed(false);
    setStaff(null);
    getStaff()
      .then(setStaff)
      .catch(() => setFailed(true));
  }, []);
  useEffect(load, [load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const state = flags.state === "empty" ? null : (flags.state ?? (failed ? "error" : staff == null ? "loading" : null));

  const openPanel = () => {
    setOpen(true);
    setInvalid(false);
    setTimeout(() => nameRef.current?.focus(), 0);
  };
  function close() {
    setOpen(false);
    addBtnRef.current?.focus();
  }

  const sendInvite = () => {
    const name = draft.name.trim();
    const email = draft.email.trim();
    if (!name || !/^[^\s@]+@[^\s@]+$/.test(email)) {
      setInvalid(true);
      return;
    }
    if (!USE_MOCKS) {
      showToast(t("admin.staffNoInvites"));
      return;
    }
    const ward = WARDS.find((w) => w.value === draft.scope)?.ward ?? null;
    setStaff((s) => [
      ...(s ?? []),
      { id: `u-new-${(s?.length ?? 0) + 1}`, name, email, role: draft.role, ward, scope: draft.scope, last_login_at: null, status: "pending" },
    ]);
    setDraft(EMPTY_DRAFT);
    setInvalid(false);
    setOpen(false);
    showToast(t("admin.staffInviteSent", { email }));
  };

  async function toggle(s: StaffMember) {
    setBusyId(s.id);
    try {
      const next = s.status === "active" ? await disableUser(s.id) : await enableUser(s.id);
      setStaff((list) => (list ?? []).map((x) => (x.id === s.id ? { ...x, status: next.status } : x)));
      setEditingId((id) => (id === s.id ? null : id));
      showToast(t(next.status === "active" ? "accounts.enabledToast" : "accounts.disabledToast", { name: s.name }));
    } catch (err) {
      showToast(t(describeError(err).key));
    } finally {
      setBusyId(null);
    }
  }

  async function issueCode(s: StaffMember) {
    setBusyId(s.id);
    try {
      setCode({ name: s.name, ...(await issueResetCode(s.id)) });
    } catch (err) {
      showToast(t(describeError(err).key));
    } finally {
      setBusyId(null);
    }
  }

  async function saveWard(s: StaffMember, ward: string | null) {
    setBusyId(s.id);
    try {
      const next = await setUserWard(s.id, ward);
      setStaff((list) => (list ?? []).map((x) => (x.id === s.id ? { ...x, ward: next.ward, scope: next.ward ?? ALL_WARDS } : x)));
      setEditingId(null);
      showToast(t("accounts.wardSavedToast", { name: s.name }));
    } catch (err) {
      showToast(t(describeError(err).key));
    } finally {
      setBusyId(null);
    }
  }

  const help = ROLE_HELP[draft.role];

  return (
    <div className={styles.frame}>
      <div className={`${page.page} ${styles.main}`}>
        <div className={page.head}>
          <div className={page.titles}>
            <h2 className={page.h2}>{t("admin.staff")}</h2>
            <span className={page.sub}>{t("admin.staffSub")}</span>
          </div>
          <button
            ref={addBtnRef}
            type="button"
            className={`${page.btnPrimary} ${styles.addBtn}`}
            onClick={openPanel}
            aria-expanded={open}
            aria-controls="add-staff"
          >
            {t("admin.staffAdd")}
          </button>
        </div>

        {state === "error" ? (
          <ErrorCard title={t("admin.staffLoadError")} onRetry={load} />
        ) : (
          <div className={`${styles.table} ${page.scrollX}`}>
            <div className={`${styles.grid} ${page.th}`}>
              <span>{t("admin.staffColName")}</span>
              <span>{t("admin.staffColRole")}</span>
              <span>{t("admin.staffColWard")}</span>
              <span>{t("admin.staffColLogin")}</span>
              <span>{t("accounts.staffColStatus")}</span>
              <span>{t("accounts.staffColActions")}</span>
            </div>
            {state === "loading"
              ? [1, 2, 3, 4, 5, 6].map((k) => (
                  <div key={k} className={`${styles.grid} ${page.skelRow}`} aria-busy="true">
                    <span className="ward-skeleton" style={{ height: 14, width: "40%" }} />
                    <span className="ward-skeleton" style={{ height: 22, width: 60, borderRadius: 6 }} />
                    <span className="ward-skeleton" style={{ height: 14, width: 120 }} />
                    <span className="ward-skeleton" style={{ height: 14, width: 90 }} />
                    <span className="ward-skeleton" style={{ height: 14, width: 70 }} />
                    <span className="ward-skeleton" style={{ height: 14, width: 70 }} />
                  </div>
                ))
              : (staff ?? []).map((s) => (
                  <div key={s.id} className={`${styles.grid} ${page.tr}`}>
                    <span className={styles.who}>
                      <span dir="auto" className={styles.name}>
                        {s.name}
                      </span>
                      <span className={styles.email}>{s.email}</span>
                    </span>
                    <span className={styles.role} style={{ background: ROLE_COLORS[s.role][0], color: ROLE_COLORS[s.role][1] }}>
                      {t(ROLE_LABEL[s.role])}
                    </span>
                    {editingId === s.id ? (
                      <WardEditor current={s.ward} busy={busyId === s.id} onSave={(w) => void saveWard(s, w)} onCancel={() => setEditingId(null)} />
                    ) : (
                      <span className={styles.cell}>{s.scope}</span>
                    )}
                    <span className={styles.cell}>{lastLogin(s.last_login_at, t, lang)}</span>
                    <span className={`${styles.status} ${s.status === "active" ? "" : styles.statusOff}`}>{t(STATUS_LABEL[s.status])}</span>
                    <span className={styles.actions}>
                      {(s.status === "active" || s.status === "disabled") && s.id !== me?.id ? (
                        <button type="button" className={page.btn} disabled={busyId === s.id} onClick={() => void toggle(s)}>
                          {s.status === "active" ? t("accounts.disable") : t("accounts.enable")}
                        </button>
                      ) : null}
                      {s.status === "active" ? (
                        <button type="button" className={page.btn} disabled={busyId === s.id} onClick={() => void issueCode(s)}>
                          {t("accounts.issueResetCode")}
                        </button>
                      ) : null}
                      {s.status === "active" && (s.role === "doctor" || s.role === "nurse") && editingId !== s.id ? (
                        <button type="button" className={page.btn} disabled={busyId === s.id} onClick={() => setEditingId(s.id)}>
                          {t("accounts.wardEdit")}
                        </button>
                      ) : null}
                    </span>
                  </div>
                ))}
          </div>
        )}
      </div>

      {open ? (
        <aside id="add-staff" aria-labelledby="add-staff-title" className={styles.panel}>
          <div className={styles.panelHead}>
            <span id="add-staff-title" className={styles.panelTitle}>
              {t("admin.staffAdd")}
            </span>
            <button type="button" aria-label={t("admin.staffClose")} className={styles.close} onClick={close}>
              ×
            </button>
          </div>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("admin.staffFullName")}</span>
            <input
              ref={nameRef}
              className={page.input}
              value={draft.name}
              autoComplete="off"
              aria-invalid={invalid && !draft.name.trim() ? true : undefined}
              onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
            />
          </label>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("admin.staffEmail")}</span>
            <input
              type="email"
              className={page.input}
              value={draft.email}
              autoComplete="off"
              aria-invalid={invalid && !/^[^\s@]+@[^\s@]+$/.test(draft.email.trim()) ? true : undefined}
              onChange={(e) => setDraft((d) => ({ ...d, email: e.target.value }))}
            />
          </label>
          <div className={page.field}>
            <span id="role-label" className={page.fieldLabel}>
              {t("admin.staffRole")}
            </span>
            <div role="radiogroup" aria-labelledby="role-label" className={styles.segment}>
              {(["doctor", "nurse", "admin"] as StaffRole[]).map((r) => (
                <button
                  key={r}
                  type="button"
                  role="radio"
                  aria-checked={draft.role === r}
                  className={`${styles.segBtn} ${draft.role === r ? styles.segOn : ""}`}
                  onClick={() => setDraft((d) => ({ ...d, role: r }))}
                >
                  {t(ROLE_LABEL[r])}
                </button>
              ))}
            </div>
          </div>
          <label className={page.field}>
            <span className={page.fieldLabel}>{t("admin.staffWard")}</span>
            <span className={page.selectWrap}>
              <select
                className={page.select}
                value={draft.scope}
                onChange={(e) => setDraft((d) => ({ ...d, scope: e.target.value }))}
              >
                {WARDS.map((w) => (
                  <option key={w.value} value={w.value}>
                    {t(w.label)}
                  </option>
                ))}
              </select>
            </span>
          </label>
          {help ? <span className={page.help}>{t(help)}</span> : null}
          {invalid ? (
            <span role="alert" className={styles.invalid}>
              {t("admin.staffInvalid")}
            </span>
          ) : null}
          <button type="button" className={styles.send} onClick={sendInvite}>
            {t("admin.staffSend")}
          </button>
        </aside>
      ) : null}

      {code ? (
        <CodeDialog subject={t("accounts.codeFor", { name: code.name })} code={code.code} expiresAt={code.expires_at} onClose={() => setCode(null)} />
      ) : null}

      {toast ? <Toast>{toast}</Toast> : null}
    </div>
  );
}

export default StaffView;
