"use client";

import { useEffect, useState } from "react";
import type { RunStatusOut } from "@/lib/api";

const POLL_INTERVAL_MS = 2500;

type PollState = { runId: string; run: RunStatusOut | null; error: string | null };

/** Polls GET /api/runs/{runId} until the run goes terminal (T16b).
 *
 * Lifted out of RunProgress, which owned this loop when progress rendered
 * inside the card. The landing page's task panel needs the same run data
 * without that component's markup, and RunProgress still serves the
 * processor page unchanged, so the loop lives here and both can use it.
 *
 * The stored state carries the run id it belongs to, and the hook returns
 * nothing unless that id still matches the one being asked for. Two things
 * fall out of that: passing null (the card's reset between runs) reports
 * an empty run without the effect having to clear state on its way in —
 * which would be a synchronous setState inside an effect — and the
 * previous run's rows can never flash in the panel for the moment between
 * a new run starting and its first response arriving.
 *
 * The interval stops once status is done or failed: a settled run is never
 * re-fetched. */
export function useRunPolling(runId: string | null): {
  run: RunStatusOut | null;
  error: string | null;
} {
  const [state, setState] = useState<PollState | null>(null);

  useEffect(() => {
    if (!runId) return;

    let cancelled = false;
    let settled = false;

    async function poll(id: string) {
      try {
        const response = await fetch(`/api/runs/${encodeURIComponent(id)}`, { cache: "no-store" });
        const data = (await response.json()) as RunStatusOut & { detail?: string };
        if (cancelled) return;
        if (!response.ok) {
          setState({ runId: id, run: null, error: data.detail ?? "Could not load run status." });
          return;
        }
        setState({ runId: id, run: data, error: null });
        if (data.status === "done" || data.status === "failed") settled = true;
      } catch {
        if (!cancelled) setState({ runId: id, run: null, error: "Could not reach the API." });
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
