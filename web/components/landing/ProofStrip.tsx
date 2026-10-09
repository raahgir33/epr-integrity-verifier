import { MetricTile } from "@/components/ui/MetricTile";
import type { LandingFigures } from "@/lib/landing";
import { formatTonnesValue } from "@/lib/format";

/** Live portfolio figures (T13.5 plan, Part 3, section 2; MetricTile swap
 * T13.5b plan, Part 1) — same four figures as HeroScene's small inline
 * row, restated here for emphasis; both read from the same
 * lib/landing.ts figures object, so the two never disagree with each
 * other. */
export function ProofStrip({ figures }: { figures: LandingFigures }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <MetricTile value={figures.processorsVerified} label="Processors verified" />
      <MetricTile
        value={figures.certifiedTonnes}
        formatter={formatTonnesValue}
        unit="t"
        label="Certified tonnes reviewed"
      />
      <MetricTile
        value={figures.unverifiableTonnes}
        formatter={formatTonnesValue}
        unit="t"
        label="Tonnes unverifiable"
      />
      <MetricTile value={figures.documentsRead} label="Documents read" />
    </div>
  );
}
