import { TeamView } from "@/components/doctor/TeamView";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("accounts.teamTitle")} · Medora` };
}

export default function DoctorTeamPage() {
  return <TeamView />;
}
