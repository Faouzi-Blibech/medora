import { Suspense } from "react";
import { getT } from "@/i18n/server";
import { ExamWorklist } from "@/components/nurse/ExamWorklist";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("nurse.metaExams")} · Medora` };
}

export default function NurseExamsPage() {
  return (
    <Suspense fallback={null}>
      <ExamWorklist />
    </Suspense>
  );
}
