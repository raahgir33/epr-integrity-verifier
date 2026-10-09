export function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="card px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</div>
      <div className="mt-1 font-display text-xl font-semibold tabular-nums text-ink">{value}</div>
      {sub ? <div className="mt-0.5 text-xs text-ink-muted">{sub}</div> : null}
    </div>
  );
}
