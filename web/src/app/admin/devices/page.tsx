import { Suspense } from "react";
import { getT } from "@/i18n/server";
import { DevicesView } from "@/components/admin/DevicesView";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("admin.bedsDevices")} · Medora` };
}

export default function AdminDevicesPage() {
  return (
    <Suspense fallback={null}>
      <DevicesView />
    </Suspense>
  );
}
