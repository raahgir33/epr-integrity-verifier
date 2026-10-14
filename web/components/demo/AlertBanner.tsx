import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { alertTone } from "@/components/demo/alertTone";
import type { AlertOut } from "@/lib/api";

/** Shown on / (every alert) and /processors/[id] (that processor's own
 * alerts only — the caller filters) once a live verification run's
 * risk band rose or surfaced a new finding (docs/BUILD_PLAN.md T13). */
export function AlertBanner({ alerts }: { alerts: AlertOut[] }) {
  if (alerts.length === 0) return null;

  return (
    <div className="space-y-2">
      {alerts.map((alert) => {
        const tone = alertTone(alert);
        return (
        // T13.5b plan, Part 5 replaced the original hard-coded amber-*
        // classes with theme-aware risk tokens. T16b replaces those again,
        // at the developer's request, and makes them follow the band: an
        // alert fires whenever a run moved a processor's risk band or
        // surfaced a new finding, which is not always bad news, so a
        // single red for every alert overstated the Low and Medium cases.
        // The banner now takes the colour of the band the processor
        // landed on — see components/demo/alertTone.ts, which both this
        // and the live-run panel's footer line share.
        //
        // The surfaces are solid, not the usual `/10` tint: 10% red over
        // --color-page's light blue composites to rgb(230,226,229), a
        // muddy grey-pink with no red left in it. They are also the one
        // theme-independent group in the palette, so the banner is the
        // same object in light and dark.
        //
        // Text stays --color-alert-ink rather than the band colour.
        // Lighthouse previously caught coloured text on a tint like this
        // at 4.12:1, under AA's 4.5:1 floor. Measured on the real painted
        // pixel, the ink clears every band comfortably — Low 14.6:1,
        // Medium 14.1:1, High 10.8:1, Unknown 13.6:1 — and each accent
        // clears the 3:1 non-text floor (4.2-6.2:1). Identical in both
        // themes, since these surfaces do not flip. The border communicates state,
        // not depth, which is the case surfaces.md's "shadow for
        // elevation" rule exempts, so it stays a border.
        <div
          key={alert.alert_id}
          className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border px-4 py-3 text-sm ${tone.border} ${tone.surface}`}
        >
          <p className="flex items-start gap-2 text-pretty text-alert-ink">
            <tone.Icon aria-hidden size={16} className={`mt-0.5 shrink-0 ${tone.accent}`} />
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
        );
      })}
    </div>
  );
}
