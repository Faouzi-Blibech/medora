"use client";

// Comment dialog for "Request changes" and "Reject": the comment is required (1–500 characters).
// It opens with the text box focused; Escape or Cancel closes it; Send stays disabled until the comment is valid.
// Steps: open (1), type, Send (2): within the spec's 3-step limit.
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import page from "@/components/admin/AdminPage.module.css";
import { COMMENT_MAX, decisionProblem } from "@/lib/pharmacy";
import styles from "./Pharmacist.module.css";

export type CommentKind = "request_changes" | "reject";

export interface CommentDialogProps {
  kind: CommentKind;
  busy: boolean;
  /** A failed send (already localized). */
  error: string | null;
  onSubmit: (comment: string) => void;
  onClose: () => void;
}

export function CommentDialog({ kind, busy, error, onSubmit, onClose }: CommentDialogProps) {
  const { t } = useT();
  const [comment, setComment] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  const close = useRef(onClose);
  const busyRef = useRef(busy);
  const form = useRef<HTMLFormElement>(null);
  const id = useId();
  const problem = decisionProblem({ decision: kind, acknowledged: false, comment }, false);
  const length = [...comment.trim()].length;

  useEffect(() => {
    close.current = onClose;
    busyRef.current = busy;
  });
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    box.current?.focus();
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape" && !busyRef.current) close.current(); // not while a send is in flight
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (opener?.isConnected) opener.focus(); // back to the button that opened the dialog
    };
  }, []);

  /** Tab stays inside the dialog: it wraps from the last control to the first and back. */
  function trap(e: KeyboardEvent<HTMLFormElement>) {
    if (e.key !== "Tab") return;
    const els = [...(form.current?.querySelectorAll<HTMLElement>("textarea, button") ?? [])].filter((x) => !(x as HTMLButtonElement).disabled);
    if (!els.length) return;
    const first = els[0];
    const last = els[els.length - 1];
    const here = document.activeElement;
    const inside = !!form.current?.contains(here);
    if (e.shiftKey && (here === first || !inside)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (here === last || !inside)) {
      e.preventDefault();
      first.focus();
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (problem || busy) return;
    onSubmit(comment.trim());
  }

  return (
    <div className={styles.overlay}>
      <form ref={form} role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} className={styles.dialog} onSubmit={submit} onKeyDown={trap}>
        <h2 id={`${id}-title`} className={styles.dialogTitle}>
          {t(kind === "reject" ? "pharmacy.reject" : "pharmacy.requestChanges")}
        </h2>
        <label className={page.field}>
          <span className={page.fieldLabel}>{t(kind === "reject" ? "pharmacy.commentLabelReject" : "pharmacy.commentLabelChanges")}</span>
          <textarea
            ref={box}
            dir="auto"
            rows={4}
            maxLength={COMMENT_MAX}
            className={styles.textarea}
            value={comment}
            aria-describedby={`${id}-count`}
            onChange={(e) => setComment(e.target.value)}
          />
        </label>
        <span id={`${id}-count`} className={styles.count}>
          {t("pharmacy.commentCount", { n: length, max: COMMENT_MAX })}
        </span>
        {problem === "comment_too_long" ? (
          <span role="alert" className={styles.error}>
            {t("pharmacy.commentTooLong")}
          </span>
        ) : null}
        {error ? (
          <span role="alert" className={styles.error}>
            {error}
          </span>
        ) : null}
        <div className={styles.dialogActions}>
          <button type="button" className={page.btn} disabled={busy} onClick={onClose}>
            {t("pharmacy.cancel")}
          </button>
          <button type="submit" className={`${page.btnPrimary} ${kind === "reject" ? styles.dangerPrimary : ""}`} disabled={busy || problem !== null}>
            {t("pharmacy.send")}
          </button>
        </div>
      </form>
    </div>
  );
}

export default CommentDialog;
