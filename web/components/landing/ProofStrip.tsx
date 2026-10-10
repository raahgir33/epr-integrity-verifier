"use client";
// Required: MetricTile's countUp path renders CountUp (a Client
// Component) and passes it a `formatter` function prop — functions
// can't cross the Server->Client boundary, so a Server Component calling
// MetricTile(countUp) would fail at runtime ("Functions cannot be passed
// directly to Client Components"). Confirmed live while testing this
// task's own build. HeroScene already had to be client for the same
// reason; StickyHeader needs it too.

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
    <div className="grid grid-cols-2 gap-4 text-center sm:grid-cols-4">
      <MetricTile countUp value={figures.processorsVerified} label="Processors verified" />
      <MetricTile
        countUp
        value={figures.certifiedTonnes}
        formatter={formatTonnesValue}
        unit="t"
        label="Certified tonnes reviewed"
      />
      <MetricTile
        countUp
        value={figures.unverifiableTonnes}
        formatter={formatTonnesValue}
        unit="t"
        label="Tonnes unverifiable"
      />
      <MetricTile countUp value={figures.documentsRead} label="Documents read" />
    </div>
  );
}
