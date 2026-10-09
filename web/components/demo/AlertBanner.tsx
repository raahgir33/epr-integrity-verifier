import Link from "next/link";
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
        // RiskBadge) the luminous-green accent is used.
        <div
          key={alert.alert_id}
          className="glow-pulse flex flex-wrap items-center justify-between gap-2 rounded-lg border border-risk-medium/30 bg-risk-medium/10 px-4 py-3 text-sm"
        >
          <p className="text-ink">
            <span className="font-medium text-risk-medium">Live verification alert</span> — {alert.message}
          </p>
          <Link
            href={`/processors/${encodeURIComponent(alert.processor_id)}`}
            className="font-medium text-risk-medium underline decoration-2 underline-offset-4 hover:opacity-80"
          >
            View {alert.processor_id} →
          </Link>
        </div>
      ))}
    </div>
  );
}
