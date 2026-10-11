"use client";

// The health events around today for `role` (two months back, ~13 months ahead), plus the weather-health alerts
// for the next days (GET /health-watch, or /health-watch/me for a patient) as one-day "weather" entries.
// Shared by the calendar page, the patient tab and the upcoming banner. A failed weather call leaves the calendar as is.
import { useCallback, useEffect, useState } from "react";
import { getHealthEvents, getHealthWatch, getMyHealthWatch } from "@/lib/api";
import { addDays, todayIso, weatherEvents } from "@/lib/healthCalendar";
import type { HealthEvent, HealthWatch, Role } from "@/lib/types";

/** The weather-health watch for this role, or null when unavailable (offline, mock mode). */
export function loadHealthWatch(role: Role): Promise<HealthWatch | null> {
  return (role === "patient" ? getMyHealthWatch() : getHealthWatch()).catch(() => null);
}

export function useHealthEvents(role: Role): {
  events: HealthEvent[] | null;
  watch: HealthWatch | null;
  failed: boolean;
  reload: () => void;
} {
  const [state, setState] = useState<{ events: HealthEvent[] | null; watch: HealthWatch | null; failed: boolean }>({
    events: null,
    watch: null,
    failed: false,
  });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    const today = todayIso();
    Promise.all([getHealthEvents({ role, from: addDays(today, -60), to: addDays(today, 400) }), loadHealthWatch(role)]).then(
      ([events, watch]) => alive && setState({ events: [...weatherEvents(watch, role), ...events], watch, failed: false }),
      () => alive && setState((s) => ({ ...s, failed: true })),
    );
    return () => {
      alive = false;
    };
  }, [role, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { events: state.events, watch: state.watch, failed: state.failed, reload };
}

export default useHealthEvents;
