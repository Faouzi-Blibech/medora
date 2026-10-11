import { getT } from "@/i18n/server";
import { ShiftHandover } from "@/components/nurse/ShiftHandover";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("nurse.metaHandover")} · Medora` };
}

export default function NurseHandoverPage() {
  return <ShiftHandover />;
}
