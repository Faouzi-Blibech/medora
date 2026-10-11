import { PendingView } from "@/components/admin/PendingView";
import { getT } from "@/i18n/server";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("accounts.pendingTitle")} · Medora` };
}

export default function AdminPendingPage() {
  return <PendingView />;
}
