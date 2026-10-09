import { CountUp } from "@/components/ui/CountUp";

/** Equal-width metric tile (T13.5b plan, Part 1) — value and unit share one
 * baseline, the unit styled smaller/muted rather than concatenated into the
 * same string, label sits below in the existing caption style. Used by
 * HeroScene's hero figures, ProofStrip and StickyHeader's compact tiles;
 * `whitespace-nowrap` on the value row keeps it from wrapping once the
 * surrounding grid is forced to stay equal-width at lg and above.
 *
 * `countUp` (Part 5) renders the value through CountUp instead of a plain
 * span, passing `value`/`formatter` straight through so the animation
 * regenerates the exact same formatted string every frame rather than
 * re-parsing a string back into a number. MetricTile itself stays usable
 * from a Server Component either way — CountUp is the only client piece. */
const TONE = {
  default: { value: "text-ink", unit: "text-ink-muted", label: "text-ink-muted" },
  // "inverted" sits on HeroScene's own deliberately theme-invariant dark
  // band (a fixed hex gradient, not --color-primary — see HeroScene's own
  // comment) — hard-coded to match, so it never flips with the viewer's
  // chosen theme the way text-primary-foreground now does.
  inverted: {
    value: "text-[#f4f4f4]",
    unit: "text-[#f4f4f4]/75",
    label: "text-[#f4f4f4]/70",
  },
  // StickyHeader's unverifiable-tonnes tile: red when there's a real
  // unverifiable figure, green when it's zero — same risk-* tokens
  // RiskBadge/StageComparison use elsewhere, never a decorative choice.
  "risk-high": { value: "text-risk-high", unit: "text-ink-muted", label: "text-ink-muted" },
  "risk-low": { value: "text-risk-low", unit: "text-ink-muted", label: "text-ink-muted" },
} as const;

const SIZE = {
  md: "text-xl sm:text-2xl",
  sm: "text-base sm:text-lg",
} as const;

export function MetricTile({
  value,
  // Rounded, not raw String(n): with countUp, CountUp's in-flight frames
  // are genuine floats (value * easeOutCubic(progress)), and for a
  // unit-less integer count (processors verified, documents read)
  // String(n) on those frames showed a long, visually jarring decimal
  // (e.g. "2.999854783280468") that could even overflow its grid cell
  // into a neighbouring tile — confirmed by actually screenshotting the
  // animation mid-flight, not just reading the final frame. Tonnage
  // formatters (formatTonnesValue etc.) already round via Intl.NumberFormat
  // and were never affected; this default-only fix doesn't touch them.
  formatter = (n) => String(Math.round(n)),
  unit,
  label,
  tone = "default",
  size = "md",
  countUp = false,
}: {
  value: number;
  formatter?: (n: number) => string;
  unit?: string;
  label: string;
  tone?: keyof typeof TONE;
  size?: keyof typeof SIZE;
  countUp?: boolean;
}) {
  const colors = TONE[tone];
  const valueClassName = `num-cell font-display font-semibold ${SIZE[size]} ${colors.value}`;
  return (
    <div className="min-w-0">
      <div className="inline-flex items-baseline gap-1 whitespace-nowrap">
        {countUp ? (
          <CountUp value={value} formatter={formatter} className={valueClassName} />
        ) : (
          <span className={valueClassName}>{formatter(value)}</span>
        )}
        {unit ? <span className={`text-sm font-medium ${colors.unit}`}>{unit}</span> : null}
      </div>
      <div className={`mt-0.5 text-xs font-medium uppercase tracking-wide ${colors.label}`}>{label}</div>
    </div>
  );
}
