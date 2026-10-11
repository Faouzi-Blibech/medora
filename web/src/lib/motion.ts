// "Reduce motion" preference: `<html data-motion="reduced">`, saved per browser in localStorage.
// CSS animations opt out with `[data-motion="reduced"]`.
const KEY = "ward_motion";

export function savedReducedMotion(): boolean {
  try {
    return localStorage.getItem(KEY) === "reduced";
  } catch {
    return false;
  }
}

export function applyReducedMotion(reduced: boolean): void {
  if (reduced) document.documentElement.dataset.motion = "reduced";
  else delete document.documentElement.dataset.motion;
}

export function setReducedMotion(reduced: boolean): void {
  applyReducedMotion(reduced);
  try {
    if (reduced) localStorage.setItem(KEY, "reduced");
    else localStorage.removeItem(KEY);
  } catch {
    // Storage blocked: the choice holds for this page only.
  }
}
