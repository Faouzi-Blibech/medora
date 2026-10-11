import Link from "next/link";
import { Suspense } from "react";
import { AuthFrame } from "@/components/auth/AuthFrame";
import { LoginForm } from "@/components/LoginForm";
import type { Key } from "@/i18n/messages";
import { getT } from "@/i18n/server";
import { USE_MOCKS } from "@/lib/time";
import authStyles from "@/components/auth/Auth.module.css";
import styles from "./page.module.css";

// Mock mode: a role picker standing in for the login (the design's "Login & components"
// file was not in the handoff bundle). Real mode (NEXT_PUBLIC_USE_MOCKS=0): a sign-in form.
const ROLES = [
  { href: "/doctor", role: "shared.roleDoctor", name: "Dr Trabelsi", sub: "shared.subDoctor", ini: "DT" },
  { href: "/nurse", role: "shared.roleNurse", name: "Nurse Ines", sub: "shared.subNurse", ini: "NI" },
  { href: "/admin", role: "shared.roleAdmin", name: "Mme Gharbi", sub: "shared.subAdmin", ini: "MG" },
  { href: "/patient", role: "shared.rolePatient", name: "Amira", sub: "shared.subPatient", ini: "AB" },
] as const satisfies readonly { href: string; role: Key; name: string; sub: Key; ini: string }[];

export default async function Home() {
  const { t } = await getT();
  return (
    <AuthFrame
      title={USE_MOCKS ? t("shared.pickRoleTitle") : t("shared.signIn")}
      lead={USE_MOCKS ? t("shared.pickRoleLead") : t("shared.signInLead")}
    >
      {USE_MOCKS ? (
        <nav className={styles.grid} aria-label={t("shared.rolesAria")}>
          {ROLES.map((r) => (
            <Link key={r.href} href={r.href} className={`${styles.card} ward-lift`}>
              <span className={styles.avatar}>{r.ini}</span>
              <span className={styles.who}>
                <span className={styles.role}>{t(r.role)}</span>
                <span className={styles.person}>{r.name}</span>
                <span className={styles.sub}>{t(r.sub)}</span>
              </span>
              <span className={styles.chev} aria-hidden="true">
                ›
              </span>
            </Link>
          ))}
        </nav>
      ) : (
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
      )}
      <nav className={authStyles.links} aria-label={t("auth.accountLinks")}>
        <Link href="/register">{t("auth.createAccount")}</Link>
        <Link href="/reset">{t("auth.haveCode")}</Link>
      </nav>
    </AuthFrame>
  );
}
