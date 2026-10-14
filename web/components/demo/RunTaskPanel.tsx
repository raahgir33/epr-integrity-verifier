"use client";

import { RunTaskRow } from "@/components/demo/RunTaskRow";
import type { DemoBatchOut, RunStatusOut } from "@/lib/api";
import { buildRunRows } from "@/lib/runRows";

/** The live-run task panel (T16b) — six pill rows beside the card.
 *
 * Height is capped to the card's by the caller, so the landing section is
 * the same height throughout a run. The row list is the scrolling region;
 * it has a definite height to fill via `min-h-0 flex-1` rather than a
 * max-height, which is the shape ReasoningPanel had to be corrected to
 * (see its own note: a column flex container sized only by max-height
 * gives its flex-1 child no definite main size, and the child grows to
 * fit its content instead of scrolling).
 *
 * The panel deliberately has no background of its own. `--color-surface-
 * sunk` is defined identical to `--color-page` in both themes, so a tray
 * drawn with it is invisible; the rows carry the structure instead, on
 * `bg-surface` with the shared resting elevation. */
export function RunTaskPanel({
  run,
  batch,
  error,
}: {
  run: RunStatusOut | null;
  batch: DemoBatchOut | null;
  error: string | null;
}) {
  if (error && !run) {
    return (
      <div className="flex h-full items-center justify-center rounded-xl p-2">
        <p className="text-sm text-risk-high">{error}</p>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="flex h-full items-center justify-center rounded-xl p-2">
        <p className="text-sm text-ink-muted">Starting…</p>
      </div>
    );
  }

  const rows = buildRunRows(run, batch);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl p-2">
      <ol className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-contain">
        {rows.map((row) => (
          <RunTaskRow key={row.id} row={row} />
        ))}
      </ol>
    </div>
  );
}
