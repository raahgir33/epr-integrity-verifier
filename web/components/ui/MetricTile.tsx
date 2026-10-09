/** Equal-width metric tile (T13.5b plan, Part 1) — value and unit share one
 * baseline, the unit styled smaller/muted rather than concatenated into the
 * same string, label sits below in the existing caption style. Used by
 * HeroScene's hero figures and ProofStrip; `whitespace-nowrap` on the
 * value row keeps it from wrapping once the surrounding grid is forced to
 * stay equal-width at lg and above.
 *
 * `value`/`formatter` (rather than a pre-formatted string) is the hook
 * T13.5b Part 5's CountUp wires into later — passing a raw number lets the
 * count-up animation regenerate the exact same formatted string every
 * frame instead of re-parsing a string back into a number. */
const TONE = {
  default: { value: "text-ink", unit: "text-ink-muted", label: "text-ink-muted" },
  // "inverted" sits on HeroScene's own primary-colored gradient band,
  // which keeps the same foreground pairing regardless of the active
  // site theme — never swap this for text-ink/text-ink-muted there.
  inverted: {
    value: "text-primary-foreground",
    unit: "text-primary-foreground/75",
    label: "text-primary-foreground/70",
  },
} as const;

export function MetricTile({
  value,
  formatter = (n) => String(n),
  unit,
  label,
  tone = "default",
}: {
  value: number;
  formatter?: (n: number) => string;
  unit?: string;
  label: string;
  tone?: keyof typeof TONE;
}) {
  const colors = TONE[tone];
  return (
    <div className="min-w-0">
      <div className="flex items-baseline gap-1 whitespace-nowrap">
        <span className={`num-cell font-display text-xl font-semibold tabular-nums sm:text-2xl ${colors.value}`}>
          {formatter(value)}
        </span>
        {unit ? <span className={`text-sm font-medium ${colors.unit}`}>{unit}</span> : null}
      </div>
      <div className={`mt-0.5 text-xs font-medium uppercase tracking-wide ${colors.label}`}>{label}</div>
    </div>
  );
}
