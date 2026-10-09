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

// T13.5c plan, Batch 0.8/0.10: hex values kept in sync by hand with the
// new palette's --color-border/--color-ink-muted/--color-primary tokens
// (app/globals.css). certifiedBar is the one deliberate exception — the
// developer's own note names #1A3D64 specifically for "wherever light
// brown is used now", so it isn't derived from a theme token.
const LIGHT: ChartColors = {
  grid: "#0719521f", // navy at ~12% alpha (8-digit hex) — matches --color-border's own construction
  axisText: "#5a668b",
  certifiedBar: "#1A3D64",
  verifiedLine: "#005461",
};

const DARK: ChartColors = {
  grid: "#f4f4f41f", // light grey at ~12% alpha — matches dark --color-border
  axisText: "#8991ab",
  certifiedBar: "#2d5a78",
  verifiedLine: "#00b7b5",
};

export function useChartColors(): ChartColors {
  const { resolvedTheme } = useTheme();
  return resolvedTheme === "dark" ? DARK : LIGHT;
}
