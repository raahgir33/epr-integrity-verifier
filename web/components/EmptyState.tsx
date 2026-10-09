export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-surface px-6 py-10 text-center">
      <p className="font-display text-base font-semibold text-ink">{title}</p>
      <p className="mt-2 text-sm text-ink-muted">{message}</p>
    </div>
  );
}
