import { StatTile } from "@/components/ui/StatTile";
import type { LandingFigures } from "@/lib/landing";
import { formatTonnes } from "@/lib/format";

/** Live portfolio figures (T13.5 plan, Part 3, section 2) — same four
 * figures as HeroScene's small inline row, restated here as full stat
 * tiles for emphasis; both read from the same lib/landing.ts figures
 * object, so the two never disagree with each other. */
export function ProofStrip({ figures }: { figures: LandingFigures }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatTile label="Processors verified" value={String(figures.processorsVerified)} />
      <StatTile label="Certified tonnes reviewed" value={formatTonnes(figures.certifiedTonnes)} />
      <StatTile label="Tonnes unverifiable" value={formatTonnes(figures.unverifiableTonnes)} />
      <StatTile label="Documents read" value={String(figures.documentsRead)} />
    </div>
  );
}
