"use client";

import { useState } from "react";
import { RunProgress } from "@/components/demo/RunProgress";
import type { DemoBatchOut } from "@/lib/api";

/** "Run live verification" button + batch picker + progress view
 * (docs/BUILD_PLAN.md T13). batches is pre-filtered by the caller
 * (all batches on /, just this processor's own batch(es) on
 * /processors/[id]). */
export function RunLiveVerification({ batches }: { batches: DemoBatchOut[] }) {
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
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="font-display text-base font-semibold text-slate-900">Run live verification</p>
      <p className="mt-1 text-sm text-slate-600">
        Simulate a new certificate batch arriving for one processor — watch it extracted, checked and
        reviewed by the agent loop end to end.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={running || submitting}
          className="rounded border border-slate-300 px-2 py-1.5 text-sm disabled:opacity-60"
        >
          {batches.map((b) => (
            <option key={b.batch_id} value={b.batch_id}>
              {b.processor_id} — +{b.quantity_t.toFixed(2)}t ({b.period_month})
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={handleRun}
          disabled={running || submitting || !selected}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Starting…" : running ? "Running…" : "Run live verification"}
        </button>
        {running ? (
          <button
            type="button"
            onClick={() => setRunId(null)}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Run another
          </button>
        ) : null}
      </div>

      {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}

      {runId ? (
        <div className="mt-4 border-t border-slate-100 pt-4">
          <RunProgress runId={runId} />
        </div>
      ) : null}
    </div>
  );
}
