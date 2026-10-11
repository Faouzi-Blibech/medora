"use client";

// The only place a one-time code is shown. The code is a prop from the caller's state:
// it is never written to storage, URL or logs, and leaving the page asks for confirmation.
import { useEffect, useRef, useState } from "react";
import { useT } from "@/i18n/I18nProvider";
import { fmtWhen } from "@/lib/accountsUi";
import styles from "./CodeDialog.module.css";

export interface CodeDialogProps {
  subject: string;
  code: string;
  expiresAt: string;
  onClose: () => void;
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    /* no clipboard API on plain-HTTP LAN installs, or permission denied: fall back below */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    ta.remove();
  }
}

export function CodeDialog({ subject, code, expiresAt, onClose }: CodeDialogProps) {
  const { t, lang } = useT();
  const [copy, setCopy] = useState<"idle" | "ok" | "failed">("idle");
  const copyRef = useRef<HTMLButtonElement>(null);
  const when = fmtWhen(expiresAt, lang);

  useEffect(() => {
    copyRef.current?.focus();
    const guard = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);

  function print() {
    document.body.dataset.printing = "code";
    window.addEventListener("afterprint", () => delete document.body.dataset.printing, { once: true });
    window.print();
  }

  return (
    <div className={styles.overlay}>
      <div role="dialog" aria-modal="true" aria-labelledby="code-subject" className={styles.dialog}>
        <p id="code-subject" dir="auto" className={styles.subject}>
          {subject}
        </p>
        <p className={styles.warn}>{t("accounts.codeOnce")}</p>
        <div dir="ltr" className={styles.code}>
          {code}
        </div>
        <p className={styles.valid}>{t("accounts.codeValid", { when })}</p>
        {copy === "failed" ? (
          <p role="alert" className={styles.feedback}>
            {t("accounts.codeCopyFailed")}
          </p>
        ) : null}
        <div className={styles.actions}>
          <button ref={copyRef} type="button" className={styles.btn} onClick={async () => setCopy((await copyText(code)) ? "ok" : "failed")}>
            {copy === "ok" ? t("accounts.codeCopied") : t("accounts.codeCopy")}
          </button>
          <button type="button" className={styles.btn} onClick={print}>
            {t("accounts.codePrint")}
          </button>
          <button type="button" className={styles.btnPrimary} onClick={onClose}>
            {t("accounts.codeDone")}
          </button>
        </div>
      </div>

      <div data-print-sheet>
        <span className={styles.sheetBrand}>Medora</span>
        <span dir="auto">{subject}</span>
        <span dir="ltr" className={styles.sheetCode}>
          {code}
        </span>
        <span>{t("accounts.codeValid", { when })}</span>
        <span>{t("accounts.printInstruction")}</span>
      </div>
    </div>
  );
}

export default CodeDialog;
