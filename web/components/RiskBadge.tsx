import { CircleCheck, CircleQuestionMark, OctagonAlert, TriangleAlert } from "lucide-react";
import { riskBandTone } from "@/lib/format";

/** Status chip (T13.5 plan, Part 2): every risk band carries its own icon
 * shape, not just a hue, so the signal survives for colour-blind viewers
 * and in greyscale print — colour is reinforcement, never the only cue.
 * Icons (T13.5c plan, Audit Batch 1) are Lucide, one family app-wide,
 * default stroke width (2px) matching the badge's font-medium (500)
 * text per icons.md's stroke-to-text-weight table, size={16} matching
 * the badge's existing h-3.5/w-3.5 footprint. */
const TONE_STYLES: Record<string, { bg: string; text: string; ring: string; Icon: typeof CircleCheck }> = {
  low: { bg: "bg-risk-low/5", text: "text-risk-low", ring: "ring-risk-low/30", Icon: CircleCheck },
  medium: { bg: "bg-risk-medium/5", text: "text-risk-medium", ring: "ring-risk-medium/30", Icon: TriangleAlert },
  high: { bg: "bg-risk-high/5", text: "text-risk-high", ring: "ring-risk-high/30", Icon: OctagonAlert },
  unknown: {
    bg: "bg-risk-unknown/5",
    text: "text-risk-unknown",
    ring: "ring-risk-unknown/30",
    Icon: CircleQuestionMark,
  },
};

export function RiskBadge({ band }: { band: string }) {
  const toneName = riskBandTone(band);
  const tone = TONE_STYLES[toneName];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-medium ring-1 ring-inset ${tone.bg} ${tone.text} ${tone.ring}`}
    >
      <tone.Icon aria-hidden size={16} />
      {band}
    </span>
  );
}
