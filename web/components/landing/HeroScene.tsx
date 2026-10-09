"use client";

import { TypingAnimation } from "@/components/magicui/typing-animation";
import { MetricTile } from "@/components/ui/MetricTile";
import type { LandingFigures } from "@/lib/landing";
import { formatTonnesValue } from "@/lib/format";
import { titleCase } from "@/lib/titleCase";
import { usePrefersReducedMotion } from "@/lib/usePrefersReducedMotion";

const HEADLINE = "Every certified tonne, verified against the paper trail.";

/** A single parallax image layer for the future hero (T13.5 plan: "Build
 * a HeroScene component now with a static fallback ... and props that
 * will accept 3-5 image layers later. Do not add images."). Not used by
 * anything yet — this shape is a placeholder contract for that later
 * task, not a feature this task implements. */
export type HeroImageLayer = {
  src: string;
  depth: number; // 0 (background) .. 1 (foreground) — scroll/parallax speed multiplier
  alt: string;
};

export function HeroScene({
  figures,
  layers = [],
}: {
  figures: LandingFigures;
  layers?: HeroImageLayer[];
}) {
  // Static fallback only — no image layers exist yet (layers is always
  // empty today); this div is where they'll be absolutely positioned,
  // depth-sorted, once that follow-up task adds real assets.
  const hasLayers = layers.length > 0;
  const reducedMotion = usePrefersReducedMotion();

  return (
    // T13.5b plan, Part 5: this band is deliberately theme-invariant — a
    // fixed dark gradient with a fixed light-grey foreground, the same in
    // both site themes (like a photograph would be), rather than reading
    // --color-primary/-foreground, which flip between themes for buttons
    // and text elsewhere. Every child element below hard-codes the
    // matching fixed hex pair instead of those theme tokens — MetricTile's
    // "inverted" tone does the same, for the same reason. T13.5c plan,
    // Batch 0.8: the fixed pair itself updated from the old forest-green/
    // off-white combination to the new palette's navy→deep-teal gradient
    // and light-grey foreground, keeping this same "theme-invariant
    // hard-coded" architecture with the new brand colours.
    <div className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-[#071952] via-[#071952] to-[#005461] px-6 py-14 text-[#f4f4f4] sm:px-10 sm:py-20">
      {hasLayers ? (
        <div aria-hidden className="absolute inset-0">
          {/* Reserved for future parallax image layers — intentionally empty today. */}
        </div>
      ) : null}

      <div className="relative mx-auto max-w-3xl text-center">
        {/* T13.5b plan, Part 5: the real headline always stays in the DOM,
            visually hidden, for screen readers/SEO/no-JS; the visible
            TypingAnimation beside it is aria-hidden and decorative only,
            and is skipped entirely under reduced motion in favor of just
            showing the real heading plainly and instantly. */}
        <h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
          <span className="sr-only">{HEADLINE}</span>
          {reducedMotion ? (
            <span aria-hidden>{HEADLINE}</span>
          ) : (
            <TypingAnimation aria-hidden as="span" duration={35} showCursor={false}>
              {HEADLINE}
            </TypingAnimation>
          )}
        </h1>
        <p className="mx-auto mt-4 max-w-[60ch] text-pretty text-base text-[#f4f4f4]/85">
          We reconstruct a processor&apos;s material flow from its own paper trail, test it against
          physical and documentary constraints, and report how many certified tonnes are verifiable —
          with evidence for every finding.
        </p>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          {/* Focus rings here use a hard-coded light colour, not
              --color-primary — this band is deliberately theme-invariant
              (see the comment above), so its focus ring needs to contrast
              reliably against the same fixed dark background in both
              site themes, not a token that flips. */}
          <a
            href="#live-verification"
            className="rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground outline-none transition-opacity duration-150 hover:opacity-90 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#f4f4f4]"
          >
            {titleCase("Run live verification")}
          </a>
          <a
            href="#portfolio-preview"
            className="rounded-md border border-[#f4f4f4]/40 px-4 py-2.5 text-sm font-medium text-[#f4f4f4] outline-none transition-colors duration-150 hover:bg-[#f4f4f4]/10 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#f4f4f4]"
          >
            {titleCase("Explore processors")}
          </a>
          <a
            href="#how-it-works"
            className="rounded-md border border-[#f4f4f4]/40 px-4 py-2.5 text-sm font-medium text-[#f4f4f4] outline-none transition-colors duration-150 hover:bg-[#f4f4f4]/10 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#f4f4f4]"
          >
            {titleCase("How it works")}
          </a>
        </div>

        {/* T13.5b plan, Part 1: equal-width grid — 2 cols on phones (room
            for labels to wrap), 4 equal columns from sm (640px) up, well
            before the "no wrapping at >=1024px" floor; MetricTile keeps
            value+unit on one shared baseline with the unit styled
            separately. */}
        <div className="mx-auto mt-10 grid max-w-2xl grid-cols-2 gap-4 sm:grid-cols-4">
          <MetricTile
            tone="inverted"
            countUp
            value={figures.processorsVerified}
            label="Processors verified"
          />
          <MetricTile
            tone="inverted"
            countUp
            value={figures.certifiedTonnes}
            formatter={formatTonnesValue}
            unit="t"
            label="Certified tonnes reviewed"
          />
          <MetricTile
            tone="inverted"
            countUp
            value={figures.unverifiableTonnes}
            formatter={formatTonnesValue}
            unit="t"
            label="Tonnes unverifiable"
          />
          <MetricTile tone="inverted" countUp value={figures.documentsRead} label="Documents read" />
        </div>
      </div>
    </div>
  );
}
