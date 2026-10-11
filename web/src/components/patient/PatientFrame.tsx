"use client";

// The patient app frame, in one of two layouts (lib/patientLayout):
// - phone: a 390 × 844 phone (radius 46, ink bezel) on the backdrop. At phone width (≤ 480 px) the app
//   fills the screen and the fake status bar is hidden.
// - desktop: the patient platform, a left sidebar like the staff one and a wide main area.
// Nothing renders until the signed-in user (and so the layout) is known, so neither flashes.
import type { ReactNode } from "react";
import { usePatientLayout } from "@/lib/patientLayout";
import { FrameLayoutContext } from "./frameLayout";
import { PatientSidebar } from "./PatientSidebar";
import styles from "./Patient.module.css";

export function PatientFrame({ children }: { children: ReactNode }) {
  const { layout, setLayout, ready } = usePatientLayout();
  if (!ready) return <div className={styles.blank} aria-busy="true" />;
  return (
    <FrameLayoutContext.Provider value={{ layout, setLayout }}>
      {layout === "desktop" ? (
        <div className={styles.desk}>
          <aside className={styles.deskAside}>
            <div className={styles.deskAsideInner}>
              <PatientSidebar />
            </div>
          </aside>
          {/* `patient-desk`: a global hook for other modules' desktop rules (Assistant.module.css). */}
          <main className={`${styles.deskMain} patient-desk`}>{children}</main>
        </div>
      ) : (
        <div className={styles.stage}>
          <div className={styles.phone}>{children}</div>
        </div>
      )}
    </FrameLayoutContext.Provider>
  );
}

export default PatientFrame;
