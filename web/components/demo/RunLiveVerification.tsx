"use client";

import { useState } from "react";
import { RunProgress } from "@/components/demo/RunProgress";
import { Button } from "@/components/ui/Button";
import type { DemoBatchOut, RunStatusOut } from "@/lib/api";

/** "Run live verification" button + batch picker + progress view
 * (docs/BUILD_PLAN.md T13). batches is pre-filtered by the caller
 * (all batches on /, just this processor's own batch(es) on
 * /processors/[id]).
 *
 * `onRunUpdate` (T13.5b plan, Part 4) is forwarded straight to RunProgress
 * — see that component's own doc comment for what it's for. */
export function RunLiveVerification({
  batches,
  onRunUpdate,
}: {
  batches: DemoBatchOut[];
  onRunUpdate?: (run: RunStatusOut | null) => void;
}) {
  const [selected, setSelected] = useState(batches[0]?.batch_id ?? "");
  const [runId, setRunId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const running = runId !== null;

  if (batches.length === 0) return null;

  async function handleRun() {
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/demo-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ batch_id: selected }),
      });
      const data = (await response.json()) as { run_id?: string; detail?: string };
      if (!response.ok) {
        setError(data.detail ?? "Could not start the run.");
        return;
      }
      if (data.run_id) setRunId(data.run_id);
    } catch {
      setError("Could not reach the API.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="font-display text-base font-semibold text-ink">Run live verification</p>
      <p className="mt-1 text-sm text-ink-muted">
        Simulate a new certificate batch arriving for one processor — watch it extracted, checked and
        reviewed by the agent loop end to end.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={running || submitting}
          className="rounded border border-border px-2 py-1.5 text-sm disabled:opacity-60"
        >
          {batches.map((b) => (
            <option key={b.batch_id} value={b.batch_id}>
              {b.processor_id} — +{b.quantity_t.toFixed(2)}t ({b.period_month})
            </option>
          ))}
        </select>
        <Button variant="primary" onClick={handleRun} disabled={running || submitting || !selected}>
          {submitting ? "Starting…" : running ? "Running…" : "Run live verification"}
        </Button>
        {running ? (
          <Button
            variant="secondary"
            onClick={() => {
              setRunId(null);
              onRunUpdate?.(null);
            }}
          >
            Run another
          </Button>
        ) : null}
      </div>

      {error ? <p className="mt-2 text-sm text-risk-high">{error}</p> : null}

      {runId ? (
        <div className="mt-4 border-t border-border pt-4">
          <RunProgress runId={runId} onRunUpdate={onRunUpdate} />
        </div>
      ) : null}
    </div>
  );
}
