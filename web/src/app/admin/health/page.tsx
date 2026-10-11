import { redirect } from "next/navigation";

// Health watch is part of the health calendar now (weather-health alerts are entries in it).
export default function AdminHealthWatchRedirect() {
  redirect("/admin/calendar");
}
