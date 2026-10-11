import { Suspense } from "react";
import { PharmacistHome } from "@/components/pharmacist/PharmacistHome";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("pharmacy.navWorklist")} · Medora` };
}

export default function PharmacistPage() {
  return (
    <Suspense fallback={null}>
      <PharmacistHome />
    </Suspense>
  );
}
