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

      <div className="card mx-auto max-w-full p-4 text-center sm:max-w-[50%]">
        <dl className="mx-auto grid max-w-sm grid-cols-3 gap-3 text-sm">
          <div>
            <dd className="tabular-nums text-center text-ink">{site.building_count}</dd>
            <dt className="mt-0.5 text-xs uppercase tracking-wide text-ink-muted">Buildings</dt>
          </div>
          <div>
            <dd className="tabular-nums text-center text-ink">{formatM2(site.total_footprint_m2)}</dd>
            <dt className="mt-0.5 text-xs uppercase tracking-wide text-ink-muted">Footprint</dt>
          </div>
          <div>
            <dd className="tabular-nums text-center text-ink">{formatCheckValue("C8", site.measured)}</dd>
            <dt className="mt-0.5 text-xs uppercase tracking-wide text-ink-muted">Capacity / m²</dt>
          </div>
        </dl>
        <p className="mt-4 text-sm text-ink">{site.explanation}</p>
        <p className="mt-3 text-xs text-ink-muted">{site.disclaimer}</p>
        <p className="mt-1 text-xs text-ink-muted">
          {site.sentinel_attribution} · {site.open_buildings_attribution}
        </p>
      </div>
    </div>
  );
}
