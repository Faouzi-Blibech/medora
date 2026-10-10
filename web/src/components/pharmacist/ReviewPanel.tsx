"use client";

// One prescription under review, using only the minimal patient projection (spec §2: never notes, exams
// or vitals). Allergies come first, then the items, the checks (recomputed now), the doctor's override
// reason, the patient's other running prescriptions, and the history.
// Validate is 1 click with no checks, or tick + click with checks. Request changes and Reject go through
// CommentDialog (open, type, Send).
import { useCallback, useEffect, useRef, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import page from "@/components/admin/AdminPage.module.css";
import { CheckList } from "@/components/shared/CheckList";
import { ErrorCard } from "@/components/shared/ErrorCard";
import { RxStatusBadge } from "@/components/shared/RxStatusBadge";
import { fmtWhen } from "@/lib/accountsUi";
import { ApiError, getReview, rejectPrescription, requestPrescriptionChanges, validatePrescription } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live";
import { DECISION_KEY, decisionProblem } from "@/lib/pharmacy";
import { describePharmacyError } from "@/lib/pharmacyUi";
import type { Prescription, PrescriptionItem, ReviewDecision, ReviewDetail } from "@/lib/types";
import { CommentDialog, type CommentKind } from "./CommentDialog";
import styles from "./Pharmacist.module.css";

export interface ReviewPanelProps {
  id: string;
  /** After a successful decision, with the updated prescription. */
  onDecided: (rx: Prescription, decision: ReviewDecision) => void;
  /** Someone else decided first (409 `bad_status`): the list should reload. */
  onStale: () => void;
}

function ItemLine({ item }: { item: PrescriptionItem }) {
  const { t } = useT();
  const units = item.units_per_intake ?? 1;
  // Doses and times are LTR so they never reorder inside Arabic text.
  const parts = [
    item.dose_mg != null ? <span dir="ltr">{t("pharmacy.itemDoseMg", { mg: item.dose_mg })}</span> : null,
    units !== 1 ? t("pharmacy.itemUnits", { n: units }) : null,
    <span dir="ltr" key="times">
      {item.times.join(" · ")}
    </span>,
    t("pharmacy.itemDays", { n: item.days }),
  ].filter((x) => !!x);
  return (
    <div className={styles.item}>
      <span dir="auto" className={styles.itemMed}>
        {item.med}
        {item.drug_id ? null : <span className={styles.nf}> · {t("pharmacy.nonFormularyTag")}</span>}
      </span>
      <span className={styles.itemMeta}>
        {parts.map((p, i) => (
          <span key={i}>
            {i > 0 ? " · " : null}
            {p}
          </span>
        ))}
      </span>
    </div>
  );
}

export function ReviewPanel({ id, onDecided, onStale }: ReviewPanelProps) {
  const { t, lang } = useT();
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [ack, setAck] = useState(false);
  const [dialog, setDialog] = useState<CommentKind | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false); // the double-click guard must not wait for a re-render
  const checksSig = useRef<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getReview(id).then(
      (d) => {
        // Checks that changed since the tick was given must be looked at again: never validate a warning unseen.
        const sig = d.checks.map((c) => `${c.code}:${c.item_index}:${c.severity}`).join("|");
        if (sig !== checksSig.current) setAck(false);
        checksSig.current = sig;
        setDetail(d);
        setFailed(false);
      },
      () => setFailed(true),
    );
  }, [id]);
  useEffect(load, [load]);
  useLiveRefresh(load, ["prescription_status"]);

  async function run(decision: ReviewDecision, call: () => Promise<Prescription>) {
    if (busyRef.current) return; // a double click sends one request
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      const rx = await call();
      setDialog(null);
      onDecided(rx, decision);
    } catch (err) {
      setError(t(describePharmacyError(err)));
      if (err instanceof ApiError && err.code === "ack_required") setAck(false); // the warnings changed: tick again
      if (err instanceof ApiError && (err.code === "bad_status" || err.code === "ack_required")) {
        setDialog(null);
        load();
        if (err.code === "bad_status") onStale();
      }
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  if (failed && !detail) return <ErrorCard title={t("pharmacy.reviewLoadError")} onRetry={load} secondaryLabel={null} />;
  if (!detail) return <div className="ward-skeleton" style={{ height: 360 }} role="status" aria-busy="true" aria-label={t("pharmacy.loading")} />;

  const { prescription: rx, patient, checks } = detail;
  const hasChecks = checks.length > 0;
  const pending = rx.status === "pending_pharmacy";
  const blocked = decisionProblem({ decision: "validate", acknowledged: ack, comment: "" }, hasChecks) !== null;
  const where = patient.ward && patient.bed ? t("pharmacy.bedWard", { ward: patient.ward, bed: patient.bed }) : (patient.ward ?? patient.bed);
  const meta = [
    patient.age != null
      ? t("pharmacy.patientLine", { age: patient.age, sex: t(patient.sex === "F" ? "pharmacy.sexF" : "pharmacy.sexM") })
      : t(patient.sex === "F" ? "pharmacy.sexF" : "pharmacy.sexM"), // age is null without a date of birth
    patient.weight_kg != null ? t("pharmacy.weight", { kg: patient.weight_kg }) : null,
    where,
    t("pharmacy.byDoctor", { name: detail.doctor_name }),
  ].filter((x): x is string => !!x);

  return (
    <article className={styles.panel} aria-labelledby={`rv-${rx.id}`}>
      <header className={styles.panelHead}>
        <h2 id={`rv-${rx.id}`} dir="auto" className={styles.panelName}>
          {patient.name}
        </h2>
        <RxStatusBadge status={rx.status} urgent={rx.urgent} />
        <span className={styles.panelMeta}>{meta.join(" · ")}</span>
      </header>

      <div className={`${styles.allergy} ${patient.allergies.length ? styles.allergyOn : ""}`}>
        <span className={styles.allergyLabel}>{t("pharmacy.allergiesTitle")}</span>
        <span dir="auto" className={styles.allergyList}>
          {patient.allergies.length ? patient.allergies.join(", ") : t("pharmacy.noAllergies")}
        </span>
      </div>

      <section className={styles.block}>
        <h3 className={styles.blockTitle}>
          {t("pharmacy.itemsTitle")}
          {rx.version > 1 ? <span className={styles.blockSub}> · {t("pharmacy.versionLine", { n: rx.version })}</span> : null}
        </h3>
        {rx.items.map((it, i) => (
          <ItemLine key={i} item={it} />
        ))}
        {rx.care_plan ? (
          <p dir="auto" className={styles.muted}>
            {rx.care_plan}
          </p>
        ) : null}
        {detail.replaces ? (
          <p dir="auto" className={styles.muted}>
            {t("pharmacy.replacesLine", { meds: detail.replaces.items.map((i) => i.med).join(", ") })}
          </p>
        ) : null}
      </section>

      <section className={styles.block}>
        <h3 className={styles.blockTitle}>{t("pharmacy.checksTitle")}</h3>
        <CheckList checks={checks} items={rx.items} emptyText={t("pharmacy.noWarnings")} />
        {rx.override_reason ? (
          <div className={styles.override}>
            <span className={styles.overrideLabel}>{t("pharmacy.overrideTitle")}</span>
            <span dir="auto">{rx.override_reason}</span>
          </div>
        ) : null}
      </section>

      <section className={styles.block}>
        <h3 className={styles.blockTitle}>{t("pharmacy.runningTitle")}</h3>
        {detail.running.length === 0 ? (
          <p className={styles.muted}>{t("pharmacy.runningNone")}</p>
        ) : (
          detail.running.flatMap((r) => r.items.map((it, i) => <ItemLine key={`${r.id}-${i}`} item={it} />))
        )}
      </section>

      <section className={styles.block}>
        <h3 className={styles.blockTitle}>{t("pharmacy.historyTitle")}</h3>
        {detail.history.length === 0 ? (
          <p className={styles.muted}>{t("pharmacy.historyNone")}</p>
        ) : (
          <ul className={styles.history}>
            {detail.history.map((h) => (
              <li key={h.id}>
                <span>
                  {t("pharmacy.historyLine", {
                    decision: t(DECISION_KEY[h.decision]),
                    name: h.pharmacist_name ?? t("pharmacy.rolePharmacist"),
                    when: fmtWhen(h.created_at, lang),
                  })}
                </span>
                {h.comment ? (
                  <span dir="auto" className={styles.muted}>
                    {h.comment}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {pending ? (
        <footer className={styles.actions}>
          {hasChecks ? (
            <label className={styles.ack}>
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              {t("pharmacy.ackLabel")}
            </label>
          ) : null}
          <div className={styles.actionRow}>
            <button
              type="button"
              className={page.btnPrimary}
              disabled={busy || blocked}
              onClick={() => void run("validated", () => validatePrescription(rx.id, { acknowledged: ack }))}
            >
              {t("pharmacy.validate")}
            </button>
            <button type="button" className={page.btn} disabled={busy} onClick={() => setDialog("request_changes")}>
              {t("pharmacy.requestChanges")}
            </button>
            <button type="button" className={`${page.btn} ${styles.danger}`} disabled={busy} onClick={() => setDialog("reject")}>
              {t("pharmacy.reject")}
            </button>
          </div>
        </footer>
      ) : rx.review_comment ? (
        <p dir="auto" className={styles.muted}>
          {t("pharmacy.reviewComment", { comment: rx.review_comment })}
        </p>
      ) : null}
      {/* Outside the pending-only footer: after a 409 `bad_status` the reload makes the prescription read-only. */}
      {error && !dialog ? (
        <span role="alert" className={styles.error}>
          {error}
        </span>
      ) : null}

      {dialog ? (
        <CommentDialog
          kind={dialog}
          busy={busy}
          error={error}
          onClose={() => {
            setDialog(null);
            setError(null);
          }}
          onSubmit={(comment) =>
            void run(dialog === "reject" ? "rejected" : "changes_requested", () =>
              dialog === "reject" ? rejectPrescription(rx.id, comment) : requestPrescriptionChanges(rx.id, comment),
            )
          }
        />
      ) : null}
    </article>
  );
}

export default ReviewPanel;
