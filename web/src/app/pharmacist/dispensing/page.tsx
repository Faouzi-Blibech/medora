import { DispensingView } from "@/components/pharmacist/DispensingView";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("pharmacy.dispTitle")} · Medora` };
}

export default function PharmacistDispensingPage() {
  return <DispensingView />;
}
