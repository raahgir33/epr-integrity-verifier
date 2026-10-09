"use client";

import { useTheme } from "next-themes";

/** Recharts takes literal color props, not CSS custom properties, so a
 * chart can't just inherit globals.css's theme tokens the way every other
 * component does (T13.5b plan, Part 2) — this hook is the one place that
 * duplicates the relevant hex values per theme, kept in sync by hand with
 * app/globals.css's `--color-border`/`--color-ink-muted`/`--color-primary`/
 * accent tokens. `resolvedTheme` is undefined before next-themes mounts;
 * the light values are also this hook's SSR-safe default, matching the
 * app's default theme. */
export type ChartColors = {
  grid: string;
  axisText: string;
  certifiedBar: string;
  verifiedLine: string;
};

const LIGHT: ChartColors = {
  grid: "#e3dccb",
  axisText: "#5b5648",
  certifiedBar: "#c9bfa4",
  verifiedLine: "#15301f",
};

const DARK: ChartColors = {
  grid: "#313b32",
  axisText: "#a39b8b",
  certifiedBar: "#3c4a3f",
  verifiedLine: "#6fcf9b",
};

export function useChartColors(): ChartColors {
  const { resolvedTheme } = useTheme();
  return resolvedTheme === "dark" ? DARK : LIGHT;
}
