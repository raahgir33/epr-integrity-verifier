"use client";

import { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import { ReasoningTimeline } from "@/components/reasoning/ReasoningTimeline";
import { AILoadingSpinner } from "@/components/ui/AILoadingSpinner";
import { ShimmerText } from "@/components/ui/ShimmerText";
import type { RunStatusOut } from "@/lib/api";
import { STAGE_LABEL, STAGE_ORDER } from "@/lib/runStages";

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
        <Check aria-hidden size={14} />
      </span>
    ) : state === "in_progress" ? (
      <AILoadingSpinner className="h-5 w-5 shrink-0" />
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
      {timing ? <span className="text-xs tabular-nums text-ink-muted">· {timing.duration_s.toFixed(0)}s</span> : null}
    </li>
  );
}

/** Polls GET /api/runs/{runId} (proxying GET /runs/{run_id}) until the run
 * reaches done/failed — docs/BUILD_PLAN.md T13's live progress view.
 *
 * `onRunUpdate` (T13.5b plan, Part 4/Kokonut addendum) lets a processor-
 * page caller mirror the live run's steps into the docked reasoning panel
 * (ProcessorLiveRun/ProcessorTabs) instead of this component's own
 * embedded trail below — when a caller passes it, this component assumes
 * something else is now displaying the trail and skips rendering its own
 * copy, so the same steps are never shown twice in two different styles.
 * The landing page's global "Run live verification" has no per-processor
 * panel to feed, so it omits the prop and keeps the embedded trail. */
export function RunProgress({
  runId,
  onSettled,
  onRunUpdate,
}: {
  runId: string;
  onSettled?: () => void;
  onRunUpdate?: (run: RunStatusOut | null) => void;
}) {
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
        onRunUpdate?.(data);
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
      onRunUpdate?.(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onRunUpdate is a setState setter (RunLiveVerification/ProcessorLiveRun), stable by identity; adding it would re-subscribe on every parent render for no reason.
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
          {/* text-ink, not text-risk-medium — see AlertBanner.tsx's identical
              comment: Lighthouse caught that pairing at 4.12:1, short of
              AA's 4.5:1 floor on this tinted background. */}
          <span className="font-medium">Alert:</span> {run.alert.message}
        </p>
      ) : null}
      {run.status === "done" && !run.alert ? (
        <p className="text-sm text-ink-muted">Done. No alert (risk band unchanged, no new finding).</p>
      ) : null}

      {!onRunUpdate && run.steps.length > 0 ? (
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
