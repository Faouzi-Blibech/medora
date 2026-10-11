import { getT } from "@/i18n/server";
import { PatientScreen } from "@/components/patient/PatientScreen";
import { SettingsPage } from "@/components/settings/SettingsPage";
import styles from "@/components/patient/Patient.module.css";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("auth.settingsTitle") };
}

export default function Page() {
  return (
    <PatientScreen>
      <div className={styles.scroll}>
        <SettingsPage role="patient" compact />
      </div>
    </PatientScreen>
  );
}
