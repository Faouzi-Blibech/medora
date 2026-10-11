import { PatientLookup } from "@/components/admin/PatientLookup";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("accounts.lookupTitle")} · Medora` };
}

export default function AdminPatientsPage() {
  return <PatientLookup />;
}
