import { Suspense } from "react";
import { getT } from "@/i18n/server";
import { CalendarView } from "@/components/patient/CalendarView";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("calendar.title")} · Ward` };
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <CalendarView />
    </Suspense>
  );
}
