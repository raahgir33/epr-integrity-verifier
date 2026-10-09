/** Compact stat tile (T13.5 plan, Part 2) — a denser variant of StatCard,
 * for contexts with little vertical room (sticky headers, side rails). */
export function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</div>
      <div className="mt-0.5 truncate font-display text-lg font-semibold tabular-nums text-ink">{value}</div>
      {sub ? <div className="text-xs text-ink-muted">{sub}</div> : null}
    </div>
  );
}
