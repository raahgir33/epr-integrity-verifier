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
        <div
          key={alert.alert_id}
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm"
        >
          <p className="text-amber-900">
            <span className="font-medium">Live verification alert</span> — {alert.message}
          </p>
          <Link
            href={`/processors/${encodeURIComponent(alert.processor_id)}`}
            className="font-medium text-amber-900 underline decoration-2 underline-offset-4 hover:text-amber-700"
          >
            View {alert.processor_id} →
          </Link>
        </div>
      ))}
    </div>
  );
}
