import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { AlertOut } from "@/lib/api";

/** Shown on / (every alert) and /processors/[id] (that processor's own
 * alerts only — the caller filters) once a live verification run's
 * risk band rose or surfaced a new finding (docs/BUILD_PLAN.md T13). */
export function AlertBanner({ alerts }: { alerts: AlertOut[] }) {
  if (alerts.length === 0) return null;

  return (
    <div className="space-y-2">
      {alerts.map((alert) => (
        // T13.5b plan, Part 5: risk-medium tokens (theme-aware) replace the
        // old hard-coded amber-* palette classes, which didn't adapt to
        // dark mode; glow-pulse is the one other place (besides a High
        // RiskBadge) the luminous-green accent is used. Readable text
        // stays text-ink, not text-risk-medium — Lighthouse caught
        // text-risk-medium on this tinted background at 4.12:1, short of
        // the 4.5:1 AA floor (risk-medium's own RiskBadge usage elsewhere
        // passes, since that's a small ring-bordered chip, not body text
        // on a wider tint); the risk band name inside alert.message is
        // the real non-colour signal here regardless.
        <div
          key={alert.alert_id}
          className="glow-pulse flex flex-wrap items-center justify-between gap-2 rounded-lg border border-risk-medium/30 bg-risk-medium/10 px-4 py-3 text-sm"
        >
          <p className="text-ink">
            <span className="font-medium">Live verification alert</span> — {alert.message}
          </p>
          <Link
            href={`/processors/${encodeURIComponent(alert.processor_id)}`}
            className="inline-flex items-center gap-1 font-medium text-ink underline decoration-2 underline-offset-4 outline-none hover:opacity-80 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            View {alert.processor_id}
            <ArrowRight aria-hidden size={14} />
          </Link>
        </div>
      ))}
    </div>
  );
}
