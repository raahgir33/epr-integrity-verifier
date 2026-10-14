"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import type { DemoBatchOut } from "@/lib/api";
import { titleCase } from "@/lib/titleCase";

/** "Run live verification" button + batch picker (docs/BUILD_PLAN.md
 * T13). The caller owns the run: this reports the started run id and
 * takes its disabled state back as a prop.
 *
 * T16b: the uncontrolled path — its own run id, the embedded RunProgress
 * stage list and a "Run Another" button — is gone along with the
 * processor page's live-run control, which was its only caller. The
 * landing page's LiveVerificationSection displays progress in a task-row
 * panel beside the card instead. The 429 cooldown / daily-cap detail
 * still surfaces here, in the card, which is where a viewer is looking
 * when a run is refused. */
export function RunLiveVerification({
  batches,
  fill = false,
  isRunning = false,
  busyLabel,
  onRunStart,
}: {
  batches: DemoBatchOut[];
  /** Fill the parent's width instead of the stand-alone `lg:w-1/2`. Set by
   * LiveVerificationSection, whose grid track is already exactly half the
   * container — without this the card would end up a quarter-width. */
  fill?: boolean;
  isRunning: boolean;
  /** Overrides the "Running…" label once a controlled run has settled —
   * the panel keeps its results on screen after the run ends, and a
   * button still claiming to be running would be saying something untrue.
   * The next action lives in the panel's footer, so this stays disabled. */
  busyLabel?: string;
  onRunStart: (runId: string, batchId: string) => void;
}) {
  const [selected, setSelected] = useState(batches[0]?.batch_id ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const running = isRunning;

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
      if (data.run_id) onRunStart(data.run_id, selected);
    } catch {
      setError("Could not reach the API.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className={`px-12 py-10 mx-auto max-w-6xl rounded-lg border border-border bg-surface p-4 text-center ${
        fill ? "lg:w-full" : "lg:w-1/2"
      }`}
    >
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
          {submitting ? "Starting…" : running ? (busyLabel ?? "Running…") : "Run live verification"}
        </Button>
      </div>

      {error ? <p className="mt-2 text-sm text-risk-high">{error}</p> : null}

    </div>
  );
}
