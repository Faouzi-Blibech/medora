"use client";

// GET /pharmacy/summary for the sidebar badge and the dashboard tiles. It is refreshed on every
// prescription_status frame, or every 15 s while no socket is open. A failed refresh keeps the last value.
import { useCallback, useEffect, useState } from "react";
import { getPharmacySummary } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live";
import type { PharmacySummary } from "@/lib/types";

export function usePharmacySummary(enabled: boolean): PharmacySummary | null {
  const [summary, setSummary] = useState<PharmacySummary | null>(null);
  const load = useCallback(() => {
    getPharmacySummary().then(setSummary, () => undefined);
  }, []);
  useEffect(() => {
    if (enabled) load();
  }, [enabled, load]);
  useLiveRefresh(load, ["prescription_status"], { enabled });
  return enabled ? summary : null;
}
