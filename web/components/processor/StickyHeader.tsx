"use client";
// Required: MetricTile's countUp path passes a `formatter` function prop
// to CountUp (a Client Component) — functions can't cross the Server->
// Client boundary. See ProofStrip.tsx's identical comment for the full
// explanation; confirmed live while testing this task's own build.

import Link from "next/link";
import { RiskBadge } from "@/components/RiskBadge";
import { MetricTile } from "@/components/ui/MetricTile";
import type { ProcessorProfile, StageAssessment } from "@/lib/api";
import { formatTonnes, formatTonnesValue } from "@/lib/format";
import { titleCase } from "@/lib/titleCase";

/** Sticky summary header (T13.5 plan, Part 4) — one line of identity plus
 * one line of tonnes. Always visible; only becomes position:sticky at lg
 * and above (where the tabs/rail layout has room for it) — below lg it's
 * a normal card that scrolls away with the rest of the page. top-16
 * matches the global Nav's own ~64px height, so the two sticky bars
 * stack directly rather than overlapping. Amendment A: certified_t
 * always reads checks_only (the figure is identical across stages);
 * verifiable_t/unverifiable_t/risk_band always prefer the full stage,
 * falling back to checks_only — the same (full ?? checks_only) pattern
 * ProcessorsTable, StageComparison and this same page's own body use, so
 * the headline here is never a different figure from the one below it. */
export function StickyHeader({
  profile,
  certifiedT,
  stage,
  hasLiveBatches,
}: {
  profile: ProcessorProfile;
  certifiedT: number;
  stage: StageAssessment;
  hasLiveBatches: boolean;
}) {
  const clean = stage.unverifiable_t <= 0;

  return (
    <div className="card px-4 py-3 lg:sticky lg:top-16 lg:z-30 lg:bg-surface/95 lg:backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-xs text-ink-muted">{profile.processor_id}</span>
          <h1 className="font-display text-lg font-semibold text-balance text-ink">{profile.name}</h1>
        </div>
        <div className="flex items-center gap-3">
          <RiskBadge band={stage.risk_band} />
          <div className="hidden items-center gap-2 text-sm sm:flex">
            <Link
              href="?tab=memo"
              className="rounded-md border border-border px-2.5 py-2.5 font-medium text-ink outline-none transition-[color,background-color] duration-150 hover:bg-surface-sunk focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              {titleCase("View memo")}
            </Link>
            {hasLiveBatches ? (
              <a
                href="#live-verification"
                className="rounded-md bg-primary px-2.5 py-2.5 font-medium text-primary-foreground outline-none transition-opacity duration-150 hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                {titleCase("Run live verification")}
              </a>
            ) : null}
          </div>
        </div>
      </div>

      {/* Processor metric tiles — plain tiles, no hover/glow effect
          (T13.5c plan, Batch 0.6: card hover/glow/tilt effects removed
          app-wide). rounded-md, not the outer .card's rounded-lg, so the
          nested radius stays concentric (outer radius minus padding). */}
      <div className="mt-3 grid grid-cols-3 gap-3 sm:w-fit">
        <div className="rounded-md px-3 py-2">
          <MetricTile size="sm" countUp value={certifiedT} formatter={formatTonnesValue} unit="t" label="Certified" />
        </div>
        <div className="rounded-md px-3 py-2">
          <MetricTile
            size="sm"
            countUp
            value={stage.verifiable_t}
            formatter={formatTonnesValue}
            unit="t"
            label="Verifiable"
          />
        </div>
        <div className="rounded-md px-3 py-2">
          <MetricTile
            size="sm"
            countUp
            tone={clean ? "risk-low" : "risk-high"}
            value={stage.unverifiable_t}
            formatter={formatTonnesValue}
            unit="t"
            label="Unverifiable"
          />
        </div>
      </div>

      {/* T13.5b plan, Part 4: KeyFactsRail's "Type/Capacity/Consent
          window" block, moved here now that the rail is retired in favor
          of the docked reasoning panel. */}
      <div className="mt-1.5 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-ink-muted">
        <span>
          Type <span className="font-medium text-ink">{profile.type}</span>
        </span>
        <span>
          Capacity <span className="num-cell font-medium text-ink">{formatTonnes(profile.capacity_t_per_year)}/yr</span>
        </span>
        <span>
          Consent{" "}
          <span className="font-medium text-ink">
            {profile.consent_valid_from} – {profile.consent_valid_to}
          </span>
        </span>
      </div>
    </div>
  );
}
