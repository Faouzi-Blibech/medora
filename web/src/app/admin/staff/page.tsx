import { Suspense } from "react";
import { getT } from "@/i18n/server";
import { StaffView } from "@/components/admin/StaffView";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("admin.staff")} · Medora` };
}

export default function AdminStaffPage() {
  return (
    <Suspense fallback={null}>
      <StaffView />
    </Suspense>
  );
}
