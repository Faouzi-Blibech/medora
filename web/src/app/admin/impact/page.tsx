import { Suspense } from "react";
import { getT } from "@/i18n/server";
import { ImpactView } from "@/components/admin/ImpactView";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("admin.impTitle")} · Ward` };
}

export default function AdminImpactPage() {
  return (
    <Suspense fallback={null}>
      <ImpactView />
    </Suspense>
  );
}
