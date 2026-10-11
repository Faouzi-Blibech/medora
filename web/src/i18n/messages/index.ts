import type { Lang } from "../config";
import { accounts } from "./accounts";
import { admin } from "./admin";
import { auth } from "./auth";
import { calendar } from "./calendar";
import { common } from "./common";
import { doctor } from "./doctor";
import { nurse } from "./nurse";
import { patient } from "./patient";
import { radiology } from "./radiology";
import { shared } from "./shared";

export const ALL = { common, shared, doctor, nurse, admin, patient, auth, accounts, calendar, radiology };

type All = typeof ALL;
/** Every message key, as `"<namespace>.<key>"`. */
export type Key = { [N in keyof All]: `${N & string}.${keyof All[N]["en"] & string}` }[keyof All];
export type Vars = Record<string, string | number>;
export type TFn = (key: Key, vars?: Vars) => string;

/** The message for `key` in `lang`, then English, then the key itself; `{name}` placeholders filled from `vars`. */
export function translate(lang: Lang, key: Key, vars?: Vars): string {
  const dot = key.indexOf(".");
  const ns = ALL[key.slice(0, dot) as keyof All] as Record<Lang, Record<string, string>>;
  const k = key.slice(dot + 1);
  const raw = ns[lang][k] ?? ns.en[k] ?? key;
  return vars ? raw.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? String(vars[name]) : m)) : raw;
}

/** English `t`, for code that has no language yet (tests, server fallbacks). */
export const tEn: TFn = (key, vars) => translate("en", key, vars);
