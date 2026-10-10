"use client";

// The doctor's live check panel: POST /prescriptions/check 400 ms after the last change (spec §6).
// Only the newest draft may update the panel: a slow reply to an older draft is dropped.
// While a new check runs, the previous result stays on screen with `checking` set.
import { useEffect, useState } from "react";
import { checkPrescription } from "@/lib/api";
import type { Check, CheckRequest } from "@/lib/types";

export const CHECK_DEBOUNCE_MS = 400;

export interface CheckState {
  /** null until the first result (or after a failure). */
  checks: Check[] | null;
  checking: boolean;
  failed: boolean;
  /** The draft key (JSON of the request) that `checks` was computed for; "" before any result. */
  checkedKey: string;
}

const IDLE: CheckState = { checks: null, checking: false, failed: false, checkedKey: "" };

/** The content key of a check request: compare it with `CheckState.checkedKey` to know a result is current. */
export const checkKeyOf = (req: CheckRequest | null): string => (req ? JSON.stringify(req) : "");

export function usePrescriptionCheck(req: CheckRequest | null, delayMs = CHECK_DEBOUNCE_MS): CheckState {
  // A content key: a new object with the same content must not restart the timer.
  const key = checkKeyOf(req);
  const [state, setState] = useState<CheckState>(IDLE);

  useEffect(() => {
    if (!key) {
      setState(IDLE);
      return;
    }
    let alive = true; // false once a newer draft (or unmount) supersedes this one
    setState((s) => ({ ...s, checking: true }));
    const timer = setTimeout(() => {
      checkPrescription(JSON.parse(key) as CheckRequest).then(
        (r) => {
          if (alive) setState({ checks: r.checks, checking: false, failed: false, checkedKey: key });
        },
        () => {
          if (alive) setState({ checks: null, checking: false, failed: true, checkedKey: key });
        },
      );
    }, delayMs);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [key, delayMs]);

  return state;
}
