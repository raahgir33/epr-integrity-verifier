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
 * T13.5b plan, Part 1; /stats-sourced T13.6 plan) — same figures as
 * HeroScene's small inline row, restated here for emphasis; both read
 * from the same lib/landing.ts getLandingFigures() (GET /stats under the
 * hood), so the two never disagree with each other. `figures` is null
 * when /stats failed — renders nothing rather than a half-populated
 * strip, per the T13.6 brief ("labels hide gracefully; nothing on the
 * page breaks"). */
export function ProofStrip({ figures }: { figures: LandingFigures | null }) {
  if (!figures) return null;

  return (
    <div className="space-y-2">
      <div className="mx-auto grid max-w-full grid-cols-2 gap-4 text-center sm:grid-cols-3 lg:grid-cols-5">
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
        {/* "ingested", not "read": GET /stats counts every registered
            document row (app/store/cache.py's documents_read), which
            includes the six demo-batch files staged for the live run.
            Those are ingested and served, but only extracted once a run
            reads them, so 720 rows cover 714 actually read. Counting rows
            is the right figure to show; this label is what makes it a
            true statement. */}
        <MetricTile countUp value={figures.documentsRead} label="Documents ingested" />
        {figures.fieldReadAccuracyValue !== null ? (
          <MetricTile
            countUp
            value={figures.fieldReadAccuracyValue}
            formatter={(n) => n.toFixed(2)}
            unit="%"
            label="Of key document fields read correctly"
          />
        ) : null}
      </div>
      {figures.fyLabel ? (
        <p className="text-center text-xs text-ink-muted">{figures.fyLabel}</p>
      ) : null}
    </div>
  );
}
