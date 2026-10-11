import { StockView } from "@/components/pharmacist/StockView";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("pharmacy.stockTitle")} · Medora` };
}

export default function PharmacistStockPage() {
  return <StockView />;
}
