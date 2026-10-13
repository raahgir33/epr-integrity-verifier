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
  certifiedLine: string;
  verifiedLine: string;
  zeroMarker: string;
};

// T13.5c plan, Batch 0.8/0.10: hex values kept in sync by hand with the
// new palette's --color-border/--color-ink-muted/--color-primary tokens
// (app/globals.css), plus --color-risk-high for certifiedLine/zeroMarker
// (the certified series reads as the claim being tested, and the marker
// flags a month with no inbound material at all).
// certifiedBar is a deliberate exception, not derived
// from a theme token: the developer's own review note (2026-10-10, round
// 6) asked for the teal highlight (#00b7b5) in place of the dark-navy
// bar it read as before (it was #1A3D64, close enough to --color-ink's
// #071952 to look like the ink colour in a bar chart).
const LIGHT: ChartColors = {
  grid: "#0719521f", // navy at ~12% alpha (8-digit hex) — matches --color-border's own construction
  axisText: "#5a668b",
  certifiedBar: "#00b7b5",
  certifiedLine: "#b91c1c", // --color-risk-high
  verifiedLine: "#005461",
  zeroMarker: "#b91c1c", // --color-risk-high
};

const DARK: ChartColors = {
  grid: "#f4f4f41f", // light grey at ~12% alpha — matches dark --color-border
  axisText: "#8991ab",
  certifiedBar: "#2d5a78",
  certifiedLine: "#f87171", // dark --color-risk-high
  verifiedLine: "#00b7b5",
  zeroMarker: "#f87171", // dark --color-risk-high
};

export function useChartColors(): ChartColors {
  const { resolvedTheme } = useTheme();
  return resolvedTheme === "dark" ? DARK : LIGHT;
}
