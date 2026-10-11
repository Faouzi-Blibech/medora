import { getT } from "@/i18n/server";
import { SettingsPage } from "@/components/settings/SettingsPage";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("auth.settingsTitle") };
}

export default function Page() {
  return <SettingsPage role="doctor" />;
}
