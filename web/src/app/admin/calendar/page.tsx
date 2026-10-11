import { Suspense } from "react";
import { getT } from "@/i18n/server";
import { HealthCalendar } from "@/components/calendar/HealthCalendar";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: `${t("calendar.title")} · Ward` };
}

export default function AdminCalendarPage() {
  return (
    <Suspense fallback={null}>
      <HealthCalendar role="admin" editable />
    </Suspense>
  );
}
