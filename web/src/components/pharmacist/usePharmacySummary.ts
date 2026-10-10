"use client";

// GET /pharmacy/summary for the sidebar badge and the dashboard tiles. One shared store per tab: every consumer
// (the sidebar and the tiles both mount on /pharmacist) reads the same value, and a burst of refreshes becomes one
// request. It is refreshed on every prescription_status frame, or every 15 s while no socket is open.
// A failed refresh keeps the last value; a reply that arrives after a newer request was sent is ignored.
import { useCallback, useEffect, useSyncExternalStore } from "react";
import { getPharmacySummary } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live";
import type { PharmacySummary } from "@/lib/types";

let current: PharmacySummary | null = null;
let sent = 0;
let scheduled: ReturnType<typeof setTimeout> | null = null;
const subscribers = new Set<() => void>();

function refreshSummary(): void {
  if (scheduled) return; // coalesce refreshes requested in the same tick
  scheduled = setTimeout(() => {
    scheduled = null;
    const id = ++sent;
    getPharmacySummary().then(
      (s) => {
        if (id !== sent) return; // out of order: a newer request is on its way
        current = s;
        subscribers.forEach((fn) => fn());
      },
      () => undefined,
    );
  }, 0);
}

const subscribe = (fn: () => void) => {
  subscribers.add(fn);
  return () => {
    subscribers.delete(fn);
  };
};

export function usePharmacySummary(enabled: boolean): PharmacySummary | null {
  const summary = useSyncExternalStore(
    subscribe,
    () => current,
    () => null,
  );
  const load = useCallback(() => refreshSummary(), []);
  useEffect(() => {
    if (enabled) load();
  }, [enabled, load]);
  useLiveRefresh(load, ["prescription_status"], { enabled });
  return enabled ? summary : null;
}
