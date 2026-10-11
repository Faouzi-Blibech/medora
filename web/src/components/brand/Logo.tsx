// The Medora logo: a heartbeat line that draws the "M", then "edora" ("ed" bold).
// `tone="dark"` is for dark backgrounds (white letters, mint line); "light" for light ones (ink letters, teal line).
import { useId } from "react";
import styles from "./Logo.module.css";

export function Logo({ tone = "dark", size = 30 }: { tone?: "dark" | "light"; size?: number }) {
  const grad = useId();
  const [from, to] = tone === "dark" ? ["#3ddcb4", "#9af3d8"] : ["#0b8a96", "#2fbfa3"];
  return (
    <span className={`${styles.logo} ${tone === "dark" ? styles.dark : styles.light}`} style={{ fontSize: size }}>
      <svg className={styles.mark} viewBox="0 0 46 40" aria-hidden="true">
        <defs>
          <linearGradient id={grad} x1="0" y1="1" x2="1" y2="0">
            <stop offset="0" stopColor={from} />
            <stop offset="1" stopColor={to} />
          </linearGradient>
        </defs>
        <path
          d="M3 33 H13 L17.5 21 L22 30 L28 4 L32.5 35 H44"
          fill="none"
          stroke={`url(#${grad})`}
          strokeWidth="4.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className={styles.word} aria-hidden="true">
        <b>ed</b>ora
      </span>
      <span className={styles.sr}>Medora</span>
    </span>
  );
}

export default Logo;
