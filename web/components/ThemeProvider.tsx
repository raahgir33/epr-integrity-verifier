"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ReactNode } from "react";

/** T13.5b plan, Part 2: thin client wrapper — layout.tsx (a server
 * component) can't use next-themes' provider directly. `attribute=
 * "data-theme"` matches globals.css's `:root[data-theme="dark"]` block;
 * default is light, enableSystem is off (the task asked for "default
 * light", not "default to the visitor's OS setting"), so there's never a
 * "system" state and no prefers-color-scheme media query is needed in
 * CSS. next-themes' own injected script sets the attribute before first
 * paint, so there's no flash regardless. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <NextThemesProvider attribute="data-theme" defaultTheme="light" enableSystem={false}>
      {children}
    </NextThemesProvider>
  );
}
