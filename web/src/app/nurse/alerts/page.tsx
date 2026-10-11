import { Suspense } from "react";
import { getT } from "@/i18n/server";
import { AlertsView } from "@/components/nurse/AlertsView";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("nurse.metaAlerts")} · Medora` };
}

export default function NurseAlertsPage() {
  return (
    <Suspense fallback={null}>
      <AlertsView />
    </Suspense>
  );
}
