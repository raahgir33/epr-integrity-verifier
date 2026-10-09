import type { SiteResponse } from "@/lib/api";
import { formatCheckValue } from "@/lib/checks";
import { formatM2 } from "@/lib/format";

export function SitePanel({ site, processorId }: { site: SiteResponse; processorId: string }) {
  return (
    <div id="site" className="card scroll-mt-20 p-4">
      {/* T13.5b plan, Part 5: image centred, metrics in an aligned grid
          beneath it — both wrapped in the same max-w-md block so the
          3-column grid lines up under the image instead of spanning the
          full card width. */}
      <div className="mx-auto max-w-md">
        {/* eslint-disable-next-line @next/next/no-img-element -- proxied, dynamically-sized Cloud Run image, not a build-time asset */}
        <img
          src={`/site-images/${encodeURIComponent(processorId)}`}
          alt={`Satellite imagery of ${processorId}'s registered site, with Open Buildings footprints and the detection radius painted in`}
          className="w-full rounded border border-border"
        />
        <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-muted">Buildings</dt>
            <dd className="num-cell tabular-nums text-ink">{site.building_count}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-muted">Footprint</dt>
            <dd className="num-cell tabular-nums text-ink">{formatM2(site.total_footprint_m2)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-muted">Capacity / m²</dt>
            <dd className="num-cell tabular-nums text-ink">
              {formatCheckValue("C8", site.measured)}
            </dd>
          </div>
        </dl>
      </div>
      <p className="mt-3 text-sm text-ink">{site.explanation}</p>
      <p className="mt-3 text-xs text-ink-muted">{site.disclaimer}</p>
      <p className="mt-1 text-xs text-ink-muted">
        {site.sentinel_attribution} · {site.open_buildings_attribution}
      </p>
    </div>
  );
}
