"use client";

import { useState } from "react";
import { useScrollFade } from "@/lib/useScrollFade";
import { RunPanelFooter } from "@/components/demo/RunPanelFooter";
import { RunTaskRow } from "@/components/demo/RunTaskRow";
import type { DemoBatchOut, RunStatusOut } from "@/lib/api";
import { buildRunRows, describeRun, type RunRow, type RunRowId } from "@/lib/runRows";

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
 * `bg-surface` with the shared resting elevation.
 *
 * **Which rows are open is derived, not stored.** A row is open if the
 * viewer has toggled it, and otherwise if it is the stage currently
 * running. That single expression gives the whole specified behaviour for
 * free — rows start collapsed (nothing is running yet), the active stage
 * opens as it starts and closes as it finishes, and a row the viewer has
 * touched stops following the run and stays where they put it. Holding
 * open/closed in state and syncing it to the run in an effect would need
 * a setState inside an effect on every stage transition, which is both
 * the pattern this project's lint rule forbids and a source of one-frame
 * flicker. */
export function RunTaskPanel({
  run,
  batch,
  error,
  onViewProcessor,
  onTryAgain,
}: {
  run: RunStatusOut | null;
  batch: DemoBatchOut | null;
  error: string | null;
  onViewProcessor: (processorId: string) => void;
  onTryAgain: () => void;
}) {
  // Only rows the viewer has actually clicked appear here; everything
  // else follows the run.
  const [toggled, setToggled] = useState<Partial<Record<RunRowId, boolean>>>({});
  // Declared before the early returns below: hook order must not depend
  // on whether a run has arrived yet.
  const {
    ref: listRef,
    fade: listFade,
    onScroll: onListScroll,
  } = useScrollFade<HTMLOListElement>(`${run?.status}:${run?.steps.length}:${Object.values(toggled).join(",")}`);

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
  const isOpen = (row: RunRow) => toggled[row.id] ?? row.state === "in_progress";

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl p-2">
      {/* Announced only when the text changes — see describeRun. */}
      <p aria-live="polite" className="sr-only">
        {describeRun(rows, run)}
      </p>

      <ol
        ref={listRef}
        aria-label="Verification stages"
        onScroll={onListScroll}
        className={`scrollbar-subtle flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-contain ${
          listFade ? "fade-bottom" : ""
        }`}
      >
        {rows.map((row) => (
          <RunTaskRow
            key={row.id}
            row={row}
            open={isOpen(row)}
            onToggle={() =>
              setToggled((previous) => ({ ...previous, [row.id]: !(previous[row.id] ?? row.state === "in_progress") }))
            }
          />
        ))}
      </ol>

      <RunPanelFooter run={run} onViewProcessor={onViewProcessor} onTryAgain={onTryAgain} />
    </div>
  );
}
