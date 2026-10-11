"use client";

// Which patient interface to show: the phone PWA (patient@ward.tn, Amira) or the desktop
// platform (every other patient account). A per-user choice is kept in localStorage.
import { useCallback, useEffect, useReducer } from "react";
import { USE_MOCKS } from "./time";
import { useMeState } from "./useMe";
import type { Me } from "./types";

export type PatientLayout = "phone" | "desktop";

const storageKey = (userId: string) => `ward_patient_layout:${userId}`;

/** The phone stays the demo's first patient (Amira); every other patient account gets the desktop. */
export function defaultLayoutFor(me: Me | null): PatientLayout {
  if (USE_MOCKS || !me) return "phone";
  return me.email === "patient@ward.tn" || me.id === "u-0005" ? "phone" : "desktop";
}

// This tab's choices, so a switch still works when storage is blocked.
const chosen = new Map<string, PatientLayout>();

function readOverride(userId: string): PatientLayout | null {
  const mine = chosen.get(userId);
  if (mine) return mine;
  try {
    const v = window.localStorage.getItem(storageKey(userId));
    return v === "phone" || v === "desktop" ? v : null;
  } catch {
    return null;
  }
}

// Every caller re-reads after a switch, so the frame and the toggle stay in step.
const listeners = new Set<() => void>();

export function usePatientLayout(): {
  layout: PatientLayout;
  setLayout: (layout: PatientLayout) => void;
  /** False until the signed-in user is known (render nothing yet, to avoid a phone/desktop flash). */
  ready: boolean;
} {
  const { me, failed } = useMeState("patient");
  const [, bump] = useReducer((n: number) => n + 1, 0);
  useEffect(() => {
    listeners.add(bump);
    return () => {
      listeners.delete(bump);
    };
  }, []);
  // `me` is only set in the browser (after an effect), so reading storage here never runs on the server.
  const layout = (me ? readOverride(me.id) : null) ?? defaultLayoutFor(me);
  const setLayout = useCallback(
    (next: PatientLayout) => {
      if (me) {
        chosen.set(me.id, next);
        try {
          window.localStorage.setItem(storageKey(me.id), next);
        } catch {
          // Storage blocked: the choice lasts for this tab only.
        }
      }
      listeners.forEach((f) => f());
    },
    [me],
  );
  return { layout, setLayout, ready: !!me || failed };
}
