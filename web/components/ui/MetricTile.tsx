import { CountUp } from "@/components/ui/CountUp";

/** Equal-width metric tile (T13.5b plan, Part 1) — value and unit share one
 * baseline, the unit styled smaller/muted rather than concatenated into the
 * same string, label sits below in the existing caption style. Used by
 * HeroScene's hero figures and ProofStrip; `whitespace-nowrap` on the
 * value row keeps it from wrapping once the surrounding grid is forced to
 * stay equal-width at lg and above.
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
    value: "text-[#faf7f1]",
    unit: "text-[#faf7f1]/75",
    label: "text-[#faf7f1]/70",
  },
} as const;

export function MetricTile({
  value,
  formatter = (n) => String(n),
  unit,
  label,
  tone = "default",
  countUp = false,
}: {
  value: number;
  formatter?: (n: number) => string;
  unit?: string;
  label: string;
  tone?: keyof typeof TONE;
  countUp?: boolean;
}) {
  const colors = TONE[tone];
  const valueClassName = `num-cell font-display text-xl font-semibold tabular-nums sm:text-2xl ${colors.value}`;
  return (
    <div className="min-w-0">
      <div className="flex items-baseline gap-1 whitespace-nowrap">
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
