import type { ReactNode } from "react";
import { riskBandTone } from "@/lib/format";

/** Status chip (T13.5 plan, Part 2): every risk band carries its own icon
 * shape, not just a hue, so the signal survives for colour-blind viewers
 * and in greyscale print — colour is reinforcement, never the only cue.
 * Icons are small components, not precomputed JSX elements, so each
 * <RiskBadge> render creates its own fresh element rather than every
 * instance on a page sharing one cached object reference (the latter
 * tripped React's key validation once more than one RiskBadge rendered
 * on the same page — confirmed by bisection while testing Part 3). */
const TONE_STYLES: Record<string, { bg: string; text: string; ring: string; Icon: () => ReactNode }> = {
  low: {
    bg: "bg-risk-low/10",
    text: "text-risk-low",
    ring: "ring-risk-low/30",
    Icon: () => (
      <svg viewBox="0 0 16 16" aria-hidden className="h-3.5 w-3.5">
        <path
          d="M3 8.5 6.2 11.5 13 4.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
  medium: {
    bg: "bg-risk-medium/10",
    text: "text-risk-medium",
    ring: "ring-risk-medium/30",
    Icon: () => (
      <svg viewBox="0 0 16 16" aria-hidden className="h-3.5 w-3.5">
        <path
          d="M8 1.5 14.8 13.5H1.2Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <path d="M8 6.2v3.1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="11.3" r="0.9" fill="currentColor" />
      </svg>
    ),
  },
  high: {
    bg: "bg-risk-high/10",
    text: "text-risk-high",
    ring: "ring-risk-high/30",
    Icon: () => (
      <svg viewBox="0 0 16 16" aria-hidden className="h-3.5 w-3.5">
        <path
          d="M5.2 1.5h5.6L14.5 5.2v5.6l-3.7 3.7H5.2l-3.7-3.7V5.2Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <path d="M8 5.2v3.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="11" r="0.9" fill="currentColor" />
      </svg>
    ),
  },
  unknown: {
    bg: "bg-risk-unknown/10",
    text: "text-risk-unknown",
    ring: "ring-risk-unknown/30",
    Icon: () => (
      <svg viewBox="0 0 16 16" aria-hidden className="h-3.5 w-3.5">
        <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path
          d="M6.2 6.3a1.8 1.8 0 1 1 2.9 1.4c-.5.4-.9.7-.9 1.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
        <circle cx="8.1" cy="11.3" r="0.8" fill="currentColor" />
      </svg>
    ),
  },
};

export function RiskBadge({ band }: { band: string }) {
  const tone = TONE_STYLES[riskBandTone(band)];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-medium ring-1 ring-inset ${tone.bg} ${tone.text} ${tone.ring}`}
    >
      <tone.Icon />
      {band}
    </span>
  );
}
