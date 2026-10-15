import type { SiteResponse } from "@/lib/api";
import { formatCheckValue } from "@/lib/checks";
import { formatM2 } from "@/lib/format";

/** T13.5c plan, Batch 0.11 — per the developer's deployed-site review:
 * the satellite image sits in its own card with minimal padding; a
 * separate, centered, max-50%-width card below it holds the metrics and
 * the description, full width on mobile. Metrics are number-above-label
 * (matching this app's own MetricTile/StatTile convention elsewhere),
 * not the earlier label-above-value order. */
export function SitePanel({ site, processorId }: { site: SiteResponse; processorId: string }) {
  return (
    <div id="site" className="scroll-mt-20 space-y-4">
      <div className="card p-2">
        {/* eslint-disable-next-line @next/next/no-img-element -- proxied, dynamically-sized Cloud Run image, not a build-time asset */}
        <img
          src={`/site-images/${encodeURIComponent(processorId)}`}
          alt={`Satellite imagery of ${processorId}'s registered site, with Open Buildings footprints and the detection radius painted in`}
          className="w-full rounded border border-border"
        />
      </div>

      <div className="card mx-auto max-w-full p-4 text-center">
        {/* T16c F14: term-then-description order in the DOM (a <dd> may
            not precede its own <dt>); the number-above-label look is done
            visually with flex-col-reverse, so screen readers announce the
            name before the value while the layout is unchanged.
            T16c F13: all three labels share one weight, and the third is
            "Capacity / m²" rather than "Capacity per m²" — the longer
            wording wrapped and stranded "m²" alone on a second line. */}
        <dl className="mx-auto grid max-w-sm grid-cols-3 gap-3 text-sm">
          <div className="flex flex-col-reverse">
            <dt className="mt-2 text-balance text-sm font-medium uppercase tracking-wide text-ink-muted">Buildings</dt>
            <dd className="text-center tabular-nums text-lg font-semibold text-ink">{site.building_count}</dd>
          </div>
          <div className="flex flex-col-reverse">
            <dt className="mt-2 text-balance text-sm font-medium uppercase tracking-wide text-ink-muted">Footprint</dt>
            <dd className="text-center tabular-nums text-lg font-semibold text-ink">{formatM2(site.total_footprint_m2)}</dd>
          </div>
          <div className="flex flex-col-reverse">
            <dt className="mt-2 text-balance text-sm font-medium uppercase tracking-wide text-ink-muted">Capacity / m²</dt>
            <dd className="text-center tabular-nums text-lg font-semibold text-ink">{formatCheckValue("C8", site.measured)}</dd>
          </div>
        </dl>
        <p className="mt-4 text-lg text-ink">{site.explanation}</p>
        <p className="mt-3 text-sm text-ink-muted">{site.disclaimer}</p>
        <p className="mt-1 text-sm text-ink-muted">
          {site.sentinel_attribution} · {site.open_buildings_attribution}
        </p>
      </div>
    </div>
  );
}
