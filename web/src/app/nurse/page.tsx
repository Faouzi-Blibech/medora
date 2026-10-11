import { Suspense } from "react";
import { getT } from "@/i18n/server";
import { WardBoard } from "@/components/nurse/WardBoard";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("nurse.metaBoard")} · Medora` };
}

export default function NurseBoardPage() {
  return (
    <Suspense fallback={null}>
      <WardBoard />
    </Suspense>
  );
}
