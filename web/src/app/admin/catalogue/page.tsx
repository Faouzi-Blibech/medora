import { CatalogueView } from "@/components/pharmacist/CatalogueView";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("pharmacy.catalogueTitle")} · Ward` };
}

export default function AdminCataloguePage() {
  return <CatalogueView />;
}
