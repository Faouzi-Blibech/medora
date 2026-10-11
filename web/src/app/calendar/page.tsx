import { Suspense } from "react";
import { getT } from "@/i18n/server";
import { FullCalendarPage } from "@/components/calendar/FullCalendarPage";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("calendar.title")} · Ward` };
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <FullCalendarPage />
    </Suspense>
  );
}
