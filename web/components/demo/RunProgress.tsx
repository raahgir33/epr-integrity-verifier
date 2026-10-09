"use client";

import { useEffect, useRef, useState } from "react";
import { ReasoningTimeline } from "@/components/reasoning/ReasoningTimeline";
import { ShimmerText } from "@/components/ui/ShimmerText";
import type { RunStatusOut } from "@/lib/api";

const STAGE_ORDER = ["reading_documents", "checking", "reasoning", "drafting_memo"] as const;
const STAGE_LABEL: Record<string, string> = {
  reading_documents: "Reading documents",
  checking: "Checks",
  reasoning: "Agents reviewing",
  drafting_memo: "Drafting memo",
};
const POLL_INTERVAL_MS = 2500;

type StageState = "done" | "in_progress" | "pending";

function stageState(stage: string, run: RunStatusOut): StageState {
  if (run.stage_timestamps[stage]) return "done";
  if (run.status === stage) return "in_progress";
  if (STAGE_ORDER.indexOf(stage as (typeof STAGE_ORDER)[number]) < STAGE_ORDER.indexOf(run.status as (typeof STAGE_ORDER)[number])) {
    return "done";
  }
  return "pending";
}

function StageRow({ stage, run }: { stage: string; run: RunStatusOut }) {
  const state = stageState(stage, run);
  const timing = run.stage_timestamps[stage];
  const icon =
    state === "done" ? (
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-risk-low/10 text-risk-low">
        ✓
      </span>
    ) : state === "in_progress" ? (
      <span className="flex h-5 w-5 shrink-0 motion-safe:animate-pulse items-center justify-center rounded-full bg-surface-sunk text-ink-muted">
        •
      </span>
    ) : (
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border text-ink-muted" />
    );

  const label = STAGE_LABEL[stage] ?? stage;

  return (
    <li className="flex items-center gap-2 text-sm">
      {icon}
      {state === "in_progress" ? (
        <ShimmerText className="font-medium text-ink">{label}</ShimmerText>
      ) : (
        <span className={state === "pending" ? "text-ink-muted" : "text-ink"}>{label}</span>
      )}
      {timing ? <span className="text-xs text-ink-muted">· {timing.duration_s.toFixed(0)}s</span> : null}
    </li>
  );
}

/** Polls GET /api/runs/{runId} (proxying GET /runs/{run_id}) until the run
 * reaches done/failed — docs/BUILD_PLAN.md T13's live progress view. */
export function RunProgress({ runId, onSettled }: { runId: string; onSettled?: () => void }) {
  const [run, setRun] = useState<RunStatusOut | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const settledRef = useRef(false);

  useEffect(() => {
    settledRef.current = false;
    let cancelled = false;

    async function poll() {
      try {
        const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { cache: "no-store" });
        const data = (await response.json()) as RunStatusOut & { detail?: string };
        if (cancelled) return;
        if (!response.ok) {
          setFetchError(data.detail ?? "Could not load run status.");
          return;
        }
        setFetchError(null);
        setRun(data);
        if ((data.status === "done" || data.status === "failed") && !settledRef.current) {
          settledRef.current = true;
          onSettled?.();
        }
      } catch {
        if (!cancelled) setFetchError("Could not reach the API.");
      }
    }

    poll();
    const interval = setInterval(() => {
      if (!settledRef.current) poll();
    }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [runId, onSettled]);

  if (fetchError && !run) {
    return <p className="text-sm text-risk-high">{fetchError}</p>;
  }
  if (!run) {
    return <p className="text-sm text-ink-muted">Starting…</p>;
  }

  return (
    <div className="space-y-4">
      <ol className="space-y-2">
        {STAGE_ORDER.map((stage) => (
          <StageRow key={stage} stage={stage} run={run} />
        ))}
      </ol>

      {run.status === "failed" ? (
        <p className="text-sm text-risk-high">Run failed: {run.error_message ?? "unknown error"}</p>
      ) : null}

      {run.status === "done" && run.alert ? (
        <p className="glow-pulse rounded-md border border-risk-medium/30 bg-risk-medium/10 px-3 py-2 text-sm text-ink">
          <span className="font-medium text-risk-medium">Alert:</span> {run.alert.message}
        </p>
      ) : null}
      {run.status === "done" && !run.alert ? (
        <p className="text-sm text-ink-muted">Done — no alert (risk band unchanged, no new finding).</p>
      ) : null}

      {run.steps.length > 0 ? (
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Reasoning trail</p>
          <div className="mt-2">
            <ReasoningTimeline
              steps={run.steps}
              knownDocIds={new Set()}
              isLive={run.status !== "done" && run.status !== "failed"}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
