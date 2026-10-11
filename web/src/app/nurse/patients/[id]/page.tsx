import { Suspense } from "react";
import { getT } from "@/i18n/server";
import { NursePatientDetail } from "@/components/nurse/NursePatientDetail";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("nurse.metaPatient")} · Medora` };
}

export default async function NursePatientPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense fallback={null}>
      <NursePatientDetail id={id} />
    </Suspense>
  );
}
