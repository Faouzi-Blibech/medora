import { ResetForm } from "@/components/auth/ResetForm";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("auth.resetTitle")} · Medora` };
}

export default function ResetPage() {
  return <ResetForm />;
}
