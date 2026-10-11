import { Suspense } from "react";
import { getT } from "@/i18n/server";
import { Dashboard } from "@/components/admin/Dashboard";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("admin.dashboard")} · Medora` };
}

export default function AdminDashboardPage() {
  return (
    <Suspense fallback={null}>
      <Dashboard />
    </Suspense>
  );
}
