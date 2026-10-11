import type { ReactNode } from "react";
import { RoleShell } from "@/components/RoleShell";

export default function PharmacistLayout({ children }: { children: ReactNode }) {
  return <RoleShell role="pharmacist">{children}</RoleShell>;
}
