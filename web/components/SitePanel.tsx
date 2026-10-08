import type { SiteResponse } from "@/lib/api";
import { formatCheckValue } from "@/lib/checks";
import { formatM2 } from "@/lib/format";

export function SitePanel({ site, processorId }: { site: SiteResponse; processorId: string }) {
  return (
    <div id="site" className="scroll-mt-20 rounded-lg border border-slate-200 bg-white p-4">
      {/* eslint-disable-next-line @next/next/no-img-element -- proxied, dynamically-sized Cloud Run image, not a build-time asset */}
      <img
        src={`/site-images/${encodeURIComponent(processorId)}`}
        alt={`Satellite imagery of ${processorId}'s registered site, with Open Buildings footprints and the detection radius painted in`}
        className="w-full max-w-md rounded border border-slate-200"
      />
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Buildings</dt>
          <dd className="num-cell tabular-nums text-slate-900">{site.building_count}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Footprint</dt>
          <dd className="num-cell tabular-nums text-slate-900">{formatM2(site.total_footprint_m2)}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Capacity / m²</dt>
          <dd className="num-cell tabular-nums text-slate-900">
            {formatCheckValue("C8", site.measured)}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-sm text-slate-700">{site.explanation}</p>
      <p className="mt-3 text-xs text-slate-500">{site.disclaimer}</p>
      <p className="mt-1 text-xs text-slate-400">
        {site.sentinel_attribution} · {site.open_buildings_attribution}
      </p>
    </div>
  );
}
