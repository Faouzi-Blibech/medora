// On a patient page: a link that opens the AI assistant on this patient. Reports are attached from the
// assistant itself, with the + button next to the message box.
import Link from "next/link";
import { useT } from "@/i18n/I18nProvider";
import styles from "./PatientAiCard.module.css";

export function PatientAiCard({ patientId, role }: { patientId: string; role: "doctor" | "nurse" }) {
  const { t } = useT();
  return (
    <section className={styles.card}>
      <Link href={`/${role}/assistant?patient=${encodeURIComponent(patientId)}`} className={styles.ask}>
        {t("shared.asstAskAbout")} <span className="flip">→</span>
      </Link>
    </section>
  );
}

export default PatientAiCard;
