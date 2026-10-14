"use client";

import { useEffect, useState } from "react";
import type { AlertOut, AlertsResponse, RunStatusOut } from "@/lib/api";

/** Retries at ~2s, then ~5s after the run settles. */
const RETRY_DELAYS_MS = [2000, 5000];

/** The alert a finished run produced (T16b).
 *
 * `GET /runs/{run_id}` usually carries it, but not always: the endpoint
 * resolves `alert_id` against the alerts table and silently reports no
 * alert when that row is not readable yet (app/main.py's get_run_status).
 * On a real run the developer saw the panel say "no alert", then found
 * the alert on the landing page moments later — the run had flipped to
 * done just before its own alert became queryable.
 *
 * So when a settled run reports no alert, this asks `/api/alerts` and
 * matches on `run_id`, which is exact — never "the most recent alert",
 * which would attribute someone else's run to this one. It gives up after
 * two tries, because a run genuinely producing no alert is the normal
 * case and must not spin.
 *
 * Returns null until a run has settled, so nothing renders mid-run. */
export function useRunAlert(run: RunStatusOut | null): AlertOut | null {
  const [found, setFound] = useState<{ runId: string; alert: AlertOut } | null>(null);

  const settled = run?.status === "done" || run?.status === "failed";
  const runId = run?.run_id ?? null;
  const needsLookup = settled && !!runId && !run?.alert;

  useEffect(() => {
    if (!needsLookup || !runId) return;
    let cancelled = false;
    const timers: ReturnType<typeof setTimeout>[] = [];

    async function lookup() {
      try {
        const response = await fetch("/api/alerts", { cache: "no-store" });
        if (!response.ok || cancelled) return false;
        const data = (await response.json()) as AlertsResponse;
        const match = data.alerts.find((a) => a.run_id === runId);
        if (match && !cancelled) {
          setFound({ runId: runId!, alert: match });
          return true;
        }
      } catch {
        // A failed lookup just means no alert is shown; the run's own
        // outcome is already on screen.
      }
      return false;
    }

    void (async () => {
      for (const delay of RETRY_DELAYS_MS) {
        timers.push(setTimeout(() => void lookup(), delay));
      }
      await lookup();
    })();

    return () => {
      cancelled = true;
      for (const t of timers) clearTimeout(t);
    };
  }, [needsLookup, runId]);

  if (!settled || !runId) return null;
  if (run?.alert) return run.alert;
  return found && found.runId === runId ? found.alert : null;
}
