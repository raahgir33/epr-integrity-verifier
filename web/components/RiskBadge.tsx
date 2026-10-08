import { riskBandTone } from "@/lib/format";

const TONE_STYLES: Record<string, { dot: string; text: string }> = {
  low: { dot: "bg-risk-low", text: "text-risk-low" },
  medium: { dot: "bg-risk-medium", text: "text-risk-medium" },
  high: { dot: "bg-risk-high", text: "text-risk-high" },
  unknown: { dot: "bg-risk-unknown", text: "text-risk-unknown" },
};

export function RiskBadge({ band }: { band: string }) {
  const tone = TONE_STYLES[riskBandTone(band)];
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${tone.text}`}>
      <span aria-hidden className={`inline-block h-2 w-2 rounded-full ${tone.dot}`} />
      {band}
    </span>
  );
}
