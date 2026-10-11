"use client";

// Real-mode sign-in (NEXT_PUBLIC_USE_MOCKS=0): POST /auth/login, keep the token, open the role's view.
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useT } from "@/i18n/I18nProvider";
import { describeError } from "@/lib/accountsUi";
import { login } from "@/lib/api";
import type { Role } from "@/lib/types";
import auth from "@/components/auth/Auth.module.css";
import styles from "@/app/page.module.css";

const HOME: Record<Role, string> = { doctor: "/doctor", nurse: "/nurse", admin: "/admin", patient: "/patient", pharmacist: "/pharmacist" };

export function LoginForm() {
  const router = useRouter();
  const { t } = useT();
  const expired = useSearchParams().get("expired") === "1";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await login(email.trim(), password);
      router.push(HOME[res.user.role] ?? "/");
    } catch (err) {
      setError(t(describeError(err, "login").key));
      setBusy(false);
    }
  }

  return (
    <form className={styles.login} onSubmit={submit} aria-label={t("shared.signIn")}>
      {expired ? (
        <span role="status" className={auth.notice}>
          {t("auth.errSessionExpired")}
        </span>
      ) : null}
      <label className={styles.field}>
        <span className={styles.fieldLabel}>{t("shared.loginEmail")}</span>
        <input
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={styles.input}
        />
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>{t("shared.loginPassword")}</span>
        <input
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={styles.input}
        />
      </label>
      {error ? (
        <span role="alert" className={styles.loginError}>
          {error}
        </span>
      ) : null}
      <button type="submit" className={styles.submit} disabled={busy}>
        {busy ? t("shared.loginSigningIn") : t("shared.signIn")}
      </button>
    </form>
  );
}

export default LoginForm;
