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
  // /evaluation's charts (T18), read ONLY by Recharts' own SVG props.
  // Anything a chart renders as ordinary DOM takes its colour from
  // --color-chart-series / --color-chart-baseline instead: this hook
  // cannot know the theme until next-themes mounts, so a server-rendered
  // inline colour hydrates mismatched and React leaves it unpatched.
  // The two values match certifiedBar/verifiedLine rather than
  // introducing new hues, so the evaluation charts and the processor
  // page's flow chart read as one system, and they form a same-hue ramp,
  // which suits what they encode: a baseline (rule checks alone) and the
  // same measurement after agent validation.
  series: string;
  seriesBaseline: string;
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
  series: "#00b7b5", // same value as certifiedBar
  seriesBaseline: "#005461", // same value as verifiedLine
};

const DARK: ChartColors = {
  grid: "#f4f4f41f", // light grey at ~12% alpha — matches dark --color-border
  axisText: "#8991ab",
  certifiedBar: "#2d5a78",
  certifiedLine: "#f87171", // dark --color-risk-high
  verifiedLine: "#00b7b5",
  zeroMarker: "#f87171", // dark --color-risk-high
  // Same two approved hexes as light, assigned by meaning rather than by
  // token name: the agent-validation series stays the brighter of the
  // pair in both themes, so the emphasis does not invert when the theme
  // changes. #00b7b5 is dark --color-primary; #2d5a78 is dark certifiedBar.
  series: "#00b7b5",
  seriesBaseline: "#2d5a78",
};

export function useChartColors(): ChartColors {
  const { resolvedTheme } = useTheme();
  return resolvedTheme === "dark" ? DARK : LIGHT;
}
