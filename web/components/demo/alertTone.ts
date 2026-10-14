import { CircleCheck, CircleQuestionMark, OctagonAlert, TriangleAlert } from "lucide-react";
import type { AlertOut } from "@/lib/api";
import { riskBandTone } from "@/lib/format";

/** Per-band styling for a live-verification alert (T16b), shared by the
 * live-run panel's footer, the only place an alert is shown.
 *
 * An alert fires whenever a run moved a processor's risk band or surfaced
 * a new finding — which is not always bad news — so the banner takes the
 * colour of the band the processor *landed on*: green for Low, amber for
 * Medium, red for High. Band → tone comes from `riskBandTone`, and the
 * icons are exactly RiskBadge's own per-band shapes, so a band looks the
 * same wherever it appears and the signal survives in greyscale and for a
 * colour-blind viewer.
 *
 * A null band (the API models `risk_band_after` as optional) falls to the
 * neutral "unknown" tone rather than being guessed as high — an alert
 * with no band recorded is not evidence of the worst case. */
const TONE = {
  low: {
    surface: "bg-alert-low-surface",
    border: "border-alert-low-accent/40",
    accent: "text-alert-low-accent",
    Icon: CircleCheck,
  },
  medium: {
    surface: "bg-alert-medium-surface",
    border: "border-alert-medium-accent/40",
    accent: "text-alert-medium-accent",
    Icon: TriangleAlert,
  },
  high: {
    surface: "bg-alert-high-surface",
    border: "border-alert-high-accent/40",
    accent: "text-alert-high-accent",
    Icon: OctagonAlert,
  },
  unknown: {
    surface: "bg-alert-unknown-surface",
    border: "border-alert-unknown-accent/40",
    accent: "text-alert-unknown-accent",
    Icon: CircleQuestionMark,
  },
} as const;

export function alertTone(alert: Pick<AlertOut, "risk_band_after">) {
  return TONE[riskBandTone(alert.risk_band_after ?? "")];
}
