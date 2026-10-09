import Link from "next/link";
import { RiskBadge } from "@/components/RiskBadge";
import type { ProcessorProfile, StageAssessment } from "@/lib/api";
import { formatTonnes } from "@/lib/format";

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
          <h1 className="font-display text-lg font-semibold text-ink">{profile.name}</h1>
        </div>
        <div className="flex items-center gap-3">
          <RiskBadge band={stage.risk_band} />
          <div className="hidden items-center gap-2 text-sm sm:flex">
            <Link
              href="?tab=memo"
              className="rounded-md border border-border px-2.5 py-1 font-medium text-ink hover:bg-surface-sunk"
            >
              View memo
            </Link>
            {hasLiveBatches ? (
              <a
                href="#live-verification"
                className="rounded-md bg-primary px-2.5 py-1 font-medium text-primary-foreground hover:opacity-90"
              >
                Run live verification
              </a>
            ) : null}
          </div>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
        <span className="text-ink-muted">
          Certified <span className="num-cell font-medium text-ink">{formatTonnes(certifiedT)}</span>
        </span>
        <span className="text-ink-muted">
          Verifiable <span className="num-cell font-medium text-ink">{formatTonnes(stage.verifiable_t)}</span>
        </span>
        {clean ? (
          <span className="inline-flex items-center gap-1 font-medium text-risk-low">
            <svg viewBox="0 0 16 16" aria-hidden className="h-3.5 w-3.5">
              <path
                d="M3 8.5 6.2 11.5 13 4.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Verified — no unverifiable tonnes
          </span>
        ) : (
          <span className="text-ink-muted">
            Unverifiable{" "}
            <span className="num-cell font-medium text-risk-high">{formatTonnes(stage.unverifiable_t)}</span>
          </span>
        )}
      </div>
    </div>
  );
}
