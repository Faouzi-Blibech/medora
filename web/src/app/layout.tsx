import type { Metadata } from "next";
import { Fraunces, Noto_Sans_Arabic, Public_Sans } from "next/font/google";
import type { ReactNode } from "react";
import { dirOf } from "@/i18n/config";
import { I18nProvider } from "@/i18n/I18nProvider";
import { getLang } from "@/i18n/server";
import "./globals.css";

// Fraunces is a variable font: leaving `weight` unset loads the variable axis
// (covers 400/500/600) and lets us add the optical-size axis.
const fraunces = Fraunces({
  subsets: ["latin"],
  axes: ["opsz"],
  display: "swap",
  variable: "--font-fraunces",
});

const publicSans = Public_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-public-sans",
});

// Arabic glyphs for every view (the end of the --sans and --serif stacks).
const notoArabic = Noto_Sans_Arabic({
  subsets: ["arabic"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-noto-arabic",
});

export const metadata: Metadata = {
  title: "Medora",
  description: "Medora — the connected patient process",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const lang = await getLang();
  return (
    <html
      lang={lang}
      dir={dirOf(lang)}
      className={`${fraunces.variable} ${publicSans.variable} ${notoArabic.variable}`}
    >
      <body>
        <I18nProvider initialLang={lang}>{children}</I18nProvider>
      </body>
    </html>
  );
}
