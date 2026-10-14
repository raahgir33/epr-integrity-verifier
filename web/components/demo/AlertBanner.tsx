import Link from "next/link";
import { ArrowRight, OctagonAlert } from "lucide-react";
import type { AlertOut } from "@/lib/api";

/** Shown on / (every alert) and /processors/[id] (that processor's own
 * alerts only — the caller filters) once a live verification run's
 * risk band rose or surfaced a new finding (docs/BUILD_PLAN.md T13). */
export function AlertBanner({ alerts }: { alerts: AlertOut[] }) {
  if (alerts.length === 0) return null;

  return (
    <div className="space-y-2">
      {alerts.map((alert) => (
        // T13.5b plan, Part 5 replaced the original hard-coded amber-*
        // classes with theme-aware risk tokens. T16b replaces those again,
        // at the developer's request: risk-medium's amber read as a milder
        // signal than the thing it reports (an alert only ever fires
        // because a risk band rose or a new finding surfaced), and the
        // obvious fix of swapping in bg-risk-high/10 was worse, not better
        // -- 10% red over --color-page's light blue composites to
        // rgb(230,226,229), a muddy grey-pink. The alert now uses its own
        // solid surface, --color-alert-* (globals.css), which is the one
        // deliberately theme-independent group in the palette: the banner
        // is the same object in light and dark rather than a tint that
        // depends on what is behind it.
        //
        // Text and icon use --color-alert-ink / --color-alert-accent, not
        // --color-ink / --color-risk-high, because the surface is light in
        // both themes and those two go near-white in dark (1.1:1 and
        // 1.8:1 here). Measured on the real painted pixel: ink 10.8:1,
        // accent 4.2:1, against AA's 4.5:1 text and 3:1 non-text floors.
        // The icon is not decoration -- per RiskBadge's own rule the shape
        // carries the signal in greyscale and for a colour-blind viewer,
        // so colour is never the only cue. The border communicates state,
        // not depth, which is the case surfaces.md's "shadow for
        // elevation" rule exempts, so it stays a border.
        <div
          key={alert.alert_id}
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-alert-accent/40 bg-alert-surface px-4 py-3 text-sm"
        >
          <p className="flex items-start gap-2 text-pretty text-alert-ink">
            <OctagonAlert aria-hidden size={16} className="mt-0.5 shrink-0 text-alert-accent" />
            <span>
              <span className="font-medium">Live Verification Alert:</span> {alert.message}
            </span>
          </p>
          <Link
            href={`/processors/${encodeURIComponent(alert.processor_id)}`}
            className="relative inline-flex items-center gap-1 font-medium text-alert-ink underline decoration-2 underline-offset-4 outline-none after:absolute after:-inset-2 after:content-[''] hover:opacity-80 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            View {alert.processor_id}
            <ArrowRight aria-hidden size={14} />
          </Link>
        </div>
      ))}
    </div>
  );
}
