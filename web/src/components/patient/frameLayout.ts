"use client";

// The frame's layout, shared with the screens (desktop hides the status bar and tab bar) and the switch.
import { createContext, useContext } from "react";
import type { PatientLayout } from "@/lib/patientLayout";

export interface FrameLayout {
  layout: PatientLayout;
  setLayout: (layout: PatientLayout) => void;
}

export const FrameLayoutContext = createContext<FrameLayout>({ layout: "phone", setLayout: () => undefined });

export function useFrameLayout(): FrameLayout {
  return useContext(FrameLayoutContext);
}
