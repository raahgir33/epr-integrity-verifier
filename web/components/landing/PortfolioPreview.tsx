import Link from "next/link";
import { RiskBadge } from "@/components/RiskBadge";
import type { ProcessorDetailResponse } from "@/lib/api";
import { formatTonnes } from "@/lib/format";
import { topFindingHeadline } from "@/lib/landing";

/** Processor cards (T13.5 plan, Part 3, section 5) — risk-band chip,
 * tonnes and a top-finding headline, each linking to /processors/[id].
 * Amendment F: a clean processor's headline reads "Verified — no
 * unverifiable tonnes" (via topFindingHeadline) rather than a blank
 * findings area. */
export function PortfolioPreview({ details }: { details: ProcessorDetailResponse[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {details.map((detail) => {
        const stage = detail.full ?? detail.checks_only;
        const clean = stage.unverifiable_t <= 0;
        return (
          <div
            key={detail.profile.processor_id}
            className="card transition-colors duration-150 hover:border-primary"
          >
            <Link href={`/processors/${encodeURIComponent(detail.profile.processor_id)}`} className="block p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-mono text-xs text-ink-muted">{detail.profile.processor_id}</p>
                  <p className="font-display text-base font-semibold text-ink">{detail.profile.name}</p>
                </div>
                <RiskBadge band={stage.risk_band} />
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                <dt className="text-ink-muted">Certified</dt>
                <dd className="num-cell text-ink">{formatTonnes(detail.checks_only.certified_t)}</dd>
                <dt className="text-ink-muted">Verifiable</dt>
                <dd className="num-cell text-ink">{formatTonnes(stage.verifiable_t)}</dd>
              </dl>
              <p className={`mt-3 text-sm ${clean ? "font-medium text-risk-low" : "text-ink-muted"}`}>
                {topFindingHeadline(detail)}
              </p>
            </Link>
          </div>
        );
      })}
    </div>
  );
}
