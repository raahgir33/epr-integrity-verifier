"use client";

import { useState } from "react";
import { RunProgress } from "@/components/demo/RunProgress";
import { Button } from "@/components/ui/Button";
import type { DemoBatchOut, RunStatusOut } from "@/lib/api";
import { titleCase } from "@/lib/titleCase";

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
    <div className="px-12 py-10 mx-auto max-w-6xl rounded-lg border border-border bg-surface p-4 text-center lg:w-1/2">
      <p className="mt-4 mb-4 font-display text-xl font-semibold text-ink">{titleCase("Agentic verification - Live!")}</p>
      <p className="mt-1 mb-8 leading-relaxed tracking-wide text-sm text-ink-muted">
        Simulate a New Certificate Batch Arriving for Any One Processor <br/> 
        Watch It Get <b>Extracted, Checked and Reviewed</b> by the Agent Loop End-to-End.
      </p>

      <div className="mt-3 flex flex-col items-center gap-3">
        <select
          aria-label="Certificate batch to simulate"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={running || submitting}
          className="w-full rounded border border-border px-5 py-5 text-lg outline-none focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-60"
        >
          {batches.map((b) => (
            <option key={b.batch_id} value={b.batch_id}>
              {b.processor_id} · +{b.quantity_t.toFixed(2)}t ({b.period_month})
            </option>
          ))}
        </select>
        <Button
          variant="glow"
          size="xl"
          className="w-full mt-5 mb-4"
          onClick={handleRun}
          disabled={running || submitting || !selected}
        >
          {submitting ? "Starting…" : running ? "Running…" : "Run live verification"}
        </Button>
        {running ? (
          <Button
            variant="secondary"
            className="w-full"
            onClick={() => {
              setRunId(null);
              onRunUpdate?.(null);
            }}
          >
            Run Another
          </Button>
        ) : null}
      </div>

      {error ? <p className="mt-2 text-sm text-risk-high">{error}</p> : null}

      {runId ? (
        <div className="mt-4 border-t border-border pt-4 text-center">
          <RunProgress runId={runId} onRunUpdate={onRunUpdate} />
        </div>
      ) : null}
    </div>
  );
}
