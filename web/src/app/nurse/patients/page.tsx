import { Suspense } from "react";
import { getT } from "@/i18n/server";
import { PatientsView } from "@/components/nurse/PatientsView";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("nurse.metaPatients")} · Medora` };
}

export default function NursePatientsPage() {
  return (
    <Suspense fallback={null}>
      <PatientsView />
    </Suspense>
  );
}
