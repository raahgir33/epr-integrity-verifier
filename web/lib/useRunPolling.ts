"use client";

import { useEffect, useState } from "react";
import type { RunStatusOut } from "@/lib/api";

const POLL_INTERVAL_MS = 2500;

/** A single failed poll is not worth showing. The live API hands back a
 * run_id as soon as the batch is accepted, but the run row is not
 * queryable for a moment after that, so the very first poll can
 * legitimately 404 — and any poll can blip. Only a second consecutive
 * failure means something is actually wrong. */
const FAILURES_BEFORE_SURFACING = 2;

type PollState = { runId: string; run: RunStatusOut | null; error: string | null };

/** Polls GET /api/runs/{runId} until the run goes terminal (T16b).
 *
 * Lifted out of RunProgress, which owned this loop when progress rendered
 * inside the card; that component has since gone with the processor
 * page's live-run control, so this is now the only poller.
 *
 * The stored state carries the run id it belongs to, and the hook returns
 * nothing unless that id still matches the one being asked for. Two things
 * fall out of that: passing null (the card's reset between runs) reports
 * an empty run without the effect having to clear state on its way in —
 * which would be a synchronous setState inside an effect — and the
 * previous run's rows can never flash in the panel for the moment between
 * a new run starting and its first response arriving.
 *
 * **A failed poll never discards the run it already has.** It used to,
 * and on a real run against the deployed API that blanked the whole panel
 * for one tick — the rows vanished, a 404 flashed in their place, and the
 * next poll put them back. The last good snapshot is kept and the error
 * is reported alongside it, so the panel can stay up and say something is
 * wrong rather than replacing itself. */
export function useRunPolling(runId: string | null): {
  run: RunStatusOut | null;
  error: string | null;
} {
  const [state, setState] = useState<PollState | null>(null);

  useEffect(() => {
    if (!runId) return;

    let cancelled = false;
    let settled = false;
    let consecutiveFailures = 0;

    function recordFailure(id: string, message: string) {
      consecutiveFailures += 1;
      const surface = consecutiveFailures >= FAILURES_BEFORE_SURFACING;
      setState((previous) => {
        const keptRun = previous && previous.runId === id ? previous.run : null;
        if (!surface && !keptRun) return previous;
        return { runId: id, run: keptRun, error: surface ? message : null };
      });
    }

    async function poll(id: string) {
      try {
        const response = await fetch(`/api/runs/${encodeURIComponent(id)}`, { cache: "no-store" });
        const data = (await response.json()) as RunStatusOut & { detail?: string };
        if (cancelled) return;
        if (!response.ok) {
          recordFailure(id, data.detail ?? "Could not load run status.");
          return;
        }
        consecutiveFailures = 0;
        setState({ runId: id, run: data, error: null });
        if (data.status === "done" || data.status === "failed") settled = true;
      } catch {
        if (!cancelled) recordFailure(id, "Could not reach the API.");
      }
    }

    void poll(runId);
    const interval = setInterval(() => {
      if (!settled) void poll(runId);
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [runId]);

  const current = state && state.runId === runId ? state : null;
  return { run: current?.run ?? null, error: current?.error ?? null };
}
