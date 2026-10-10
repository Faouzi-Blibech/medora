"use client";

import { useEffect, useState } from "react";

/** `value`, updated only once it has stayed the same for `ms` (search boxes). */
export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}
