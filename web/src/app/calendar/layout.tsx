import type { ReactNode } from "react";

/** Full-width calendar (/calendar): no sidebar, no phone frame, just the canvas. */
export default function CalendarLayout({ children }: { children: ReactNode }) {
  return <div style={{ minHeight: "100vh", background: "var(--canvas)" }}>{children}</div>;
}
