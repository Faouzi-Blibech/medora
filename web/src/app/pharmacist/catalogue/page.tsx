import { CatalogueView } from "@/components/pharmacist/CatalogueView";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("pharmacy.catalogueTitle")} · Medora` };
}

export default function PharmacistCataloguePage() {
  return <CatalogueView />;
}
