"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { applyReducedMotion, savedReducedMotion } from "@/lib/motion";
import { dirOf, LANG_COOKIE, type Lang } from "./config";
import { translate, type TFn } from "./messages";

interface I18n {
  t: TFn;
  lang: Lang;
  dir: "ltr" | "rtl";
  setLang: (lang: Lang) => void;
}

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({ initialLang, children }: { initialLang: Lang; children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  // The saved "Reduce motion" choice (Settings), applied once per page load.
  useEffect(() => applyReducedMotion(savedReducedMotion()), []);

  const setLang = useCallback((next: Lang) => {
    document.cookie = `${LANG_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
    document.documentElement.lang = next;
    document.documentElement.dir = dirOf(next);
    setLangState(next);
  }, []);

  const value = useMemo<I18n>(
    () => ({ t: (key, vars) => translate(lang, key, vars), lang, dir: dirOf(lang), setLang }),
    [lang, setLang],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** The current language and its `t`. Client components only; server components use `getT()`. */
export function useT(): I18n {
  const v = useContext(Ctx);
  if (!v) throw new Error("useT() outside <I18nProvider>");
  return v;
}
