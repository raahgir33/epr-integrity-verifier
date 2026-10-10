"use client";

import { useRef } from "react";
import { TypingAnimation } from "@/components/magicui/typing-animation";
import { MetricTile } from "@/components/ui/MetricTile";
import type { LandingFigures } from "@/lib/landing";
import { formatTonnesValue } from "@/lib/format";
import { titleCase } from "@/lib/titleCase";
import { useIsBreakpointUp } from "@/lib/useIsBreakpointUp";
import type { ParallaxLayerConfig } from "@/lib/useParallaxLayers";
import { useParallaxLayers } from "@/lib/useParallaxLayers";
import { usePrefersReducedMotion } from "@/lib/usePrefersReducedMotion";

const HEADLINE = "Every certified tonne, verified against the paper trail.";
// T13.6 plan, Part B: the typing animation's speed stays, slowed 1.25x
// (was 35ms/char) at the developer's explicit request.
const TYPING_DURATION_MS = Math.round(35 * 1.25);

type Fragment = {
  src: string;
  alt: string;
  widthPx: number; // the 1x on-screen width; -2x.webp is served at 2x via srcSet
  aspect: number; // height / width, so layout doesn't shift before the image decodes
  className: string; // absolute position toward an edge/corner
  mirror?: boolean;
  depth: number;
  floatPeriodMs: number;
  floatAmpPx: number;
  floatPhase: number;
  mobile?: boolean; // one of the <=3 kept below md
};

// Depths roughly follow the brief's table (0.4 mid, 0.7 near). Positions
// keep the centre clear for the headline/CTAs/metrics — fragments sit
// toward the edges and lower corners only. Sizes/positions are hand-
// placed, not derived from the source images' own framing.
const FRAGMENTS: Fragment[] = [
  {
    src: "/hero/soil-moss-a",
    alt: "",
    widthPx: 72,
    aspect: 1388 / 1591,
    className: "left-[1%] top-[6%] sm:left-[3%] sm:top-[8%]",
    depth: 0.4,
    floatPeriodMs: 7400,
    floatAmpPx: 5,
    floatPhase: 0,
    mobile: true,
  },
  {
    src: "/hero/strata-b",
    alt: "",
    widthPx: 76,
    aspect: 1176 / 1347,
    className: "right-[2%] top-[4%] sm:right-[5%] sm:top-[6%]",
    mirror: true,
    depth: 0.4,
    floatPeriodMs: 6600,
    floatAmpPx: 6,
    floatPhase: 1.4,
  },
  {
    src: "/hero/pellets-rock-a",
    alt: "",
    widthPx: 84,
    aspect: 1055 / 1554,
    className: "left-0 top-[42%] hidden sm:block sm:left-[1%]",
    depth: 0.4,
    floatPeriodMs: 8000,
    floatAmpPx: 5,
    floatPhase: 2.6,
  },
  {
    src: "/hero/pebble-a",
    alt: "",
    widthPx: 108,
    aspect: 1031 / 1330,
    className: "left-[2%] bottom-[2%] sm:left-[4%] sm:bottom-[4%]",
    depth: 0.7,
    floatPeriodMs: 7000,
    floatAmpPx: 7,
    floatPhase: 0.8,
    mobile: true,
  },
  {
    src: "/hero/pellets-a",
    alt: "",
    widthPx: 96,
    aspect: 1440 / 1949,
    className: "right-[3%] bottom-[3%] sm:right-[6%] sm:bottom-[5%]",
    depth: 0.7,
    floatPeriodMs: 9000,
    floatAmpPx: 6,
    floatPhase: 3.6,
    mobile: true,
  },
  {
    src: "/hero/pebble-c",
    alt: "",
    widthPx: 90,
    aspect: 933 / 1481,
    className: "right-[1%] top-[48%] hidden sm:block sm:right-[2%]",
    mirror: true,
    depth: 0.7,
    floatPeriodMs: 6400,
    floatAmpPx: 7,
    floatPhase: 5.0,
  },
];

const MIST_LAYERS: ParallaxLayerConfig[] = [
  { depth: 0.25, floatPeriodMs: 11000, floatAmpPx: 8, floatPhase: 0.5 },
  { depth: 0.5, floatPeriodMs: 9500, floatAmpPx: 8, floatPhase: 2.1 },
];

const MOBILE_FRAGMENTS = FRAGMENTS.filter((f) => f.mobile);

function srcSet(base: string) {
  return `${base}-1x.webp 1x, ${base}-2x.webp 2x`;
}

/** The hero's image layer stack (T13.6 plan, Part B). Theme-aware now —
 * `var(--color-page)` + a soft `#90ddf0` radial tint in light mode,
 * following the dark theme tokens in dark mode — a deliberate reversal of
 * this band's previous "theme-invariant" architecture (see git history):
 * that made sense for a flat dark gradient with no imagery; it doesn't
 * for a scene meant to read as a real place in both themes. */
export function HeroScene({ figures }: { figures: LandingFigures | null }) {
  const reducedMotion = usePrefersReducedMotion();
  const isMdUp = useIsBreakpointUp(768);
  const containerRef = useRef<HTMLDivElement>(null);

  const activeFragments = isMdUp ? FRAGMENTS : MOBILE_FRAGMENTS;
  const allLayers: ParallaxLayerConfig[] = [
    { depth: 0.1, floatPeriodMs: 8000, floatAmpPx: 4, floatPhase: 0 }, // sky
    { depth: 0.2, floatPeriodMs: 7200, floatAmpPx: 5, floatPhase: 1.2 }, // distant
    ...activeFragments.map(({ depth, floatPeriodMs, floatAmpPx, floatPhase }) => ({
      depth,
      floatPeriodMs,
      floatAmpPx,
      floatPhase,
    })),
    ...(isMdUp ? MIST_LAYERS : []),
  ];
  const setLayerRef = useParallaxLayers(containerRef, allLayers, !reducedMotion);
  let layerIndex = 0;

  return (
    <div
      ref={containerRef}
      className="relative overflow-hidden rounded-2xl border border-border px-6 py-14 text-ink sm:px-10 sm:py-20"
      style={{
        backgroundColor: "var(--color-page)",
        backgroundImage:
          "radial-gradient(ellipse 65% 55% at 28% 18%, rgb(144 221 240 / 0.38), transparent 70%)",
      }}
    >
      {reducedMotion ? (
        // prefers-reduced-motion: the flattened poster only, no layers,
        // no parallax JS at all — satisfies the brief's "poster only, no
        // motion" rule structurally, not just by freezing a transform.
        <img
          src="/hero/poster.webp"
          alt=""
          aria-hidden
          decoding="async"
          className="absolute inset-0 h-full w-full object-cover opacity-70"
        />
      ) : (
        <div aria-hidden className="absolute inset-0">
          <div
            ref={setLayerRef(layerIndex++)}
            className="absolute inset-0 opacity-50 will-change-transform"
          >
            <img
              src="/hero/sky-1x.webp"
              srcSet={srcSet("/hero/sky")}
              alt=""
              width={900}
              height={473}
              decoding="async"
              loading="lazy"
              className="h-full w-full object-cover"
            />
          </div>
          <div
            ref={setLayerRef(layerIndex++)}
            className="absolute inset-x-0 bottom-0 h-[55%] opacity-40 will-change-transform"
          >
            <img
              src="/hero/distant-1x.webp"
              srcSet={srcSet("/hero/distant")}
              alt=""
              width={900}
              height={473}
              decoding="async"
              loading="lazy"
              className="h-full w-full object-cover object-bottom"
            />
          </div>

          {activeFragments.map((fragment) => {
            const heightPx = Math.round(fragment.widthPx * fragment.aspect);
            return (
              <div
                key={fragment.src}
                ref={setLayerRef(layerIndex++)}
                className={`absolute will-change-transform ${fragment.className}`}
              >
                <img
                  src={`${fragment.src}-1x.webp`}
                  srcSet={srcSet(fragment.src)}
                  alt=""
                  width={fragment.widthPx}
                  height={heightPx}
                  decoding="async"
                  loading="lazy"
                  style={{
                    width: fragment.widthPx,
                    height: heightPx,
                    transform: fragment.mirror ? "scaleX(-1)" : undefined,
                  }}
                  className="drop-shadow-sm"
                />
              </div>
            );
          })}

          {isMdUp
            ? MIST_LAYERS.map((_, i) => (
                <div
                  key={`mist-${i}`}
                  ref={setLayerRef(layerIndex++)}
                  className={`absolute inset-x-0 bottom-0 h-[35%] will-change-transform ${
                    i === 0 ? "opacity-30" : "opacity-20"
                  }`}
                >
                  <img
                    src={`/hero/mist-${i + 1}-1x.webp`}
                    srcSet={srcSet(`/hero/mist-${i + 1}`)}
                    alt=""
                    width={700}
                    height={350}
                    decoding="async"
                    loading="lazy"
                    className="h-full w-full object-cover object-bottom"
                  />
                </div>
              ))
            : null}
        </div>
      )}

      {/* Theme-matched scrim so the headline/body/metrics stay legible
          regardless of what's behind them — a bright sky/mist patch under
          dark-mode text otherwise reads near-invisible (confirmed via a
          real screenshot: text-ink-muted on the unscrimmed sky had nowhere
          near 4.5:1 contrast in dark mode). color-mix blends the current
          theme's own --color-page over the imagery, so light mode (an
          already-light page color) barely changes while dark mode darkens
          enough to restore contrast — no new dark-mode-only token needed. */}
      <div
        aria-hidden
        className="absolute inset-0"
        style={{ backgroundColor: "color-mix(in srgb, var(--color-page) 55%, transparent)" }}
      />

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
            <TypingAnimation
              aria-hidden
              as="span"
              duration={TYPING_DURATION_MS}
              showCursor={false}
            >
              {HEADLINE}
            </TypingAnimation>
          )}
        </h1>
        <p className="mx-auto mt-4 max-w-[60ch] text-pretty text-base text-ink-muted">
          We reconstruct a processor&apos;s material flow from its own paper trail, test it against
          physical and documentary constraints, and report how many certified tonnes are verifiable,
          with evidence for every finding.
        </p>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <a
            href="#live-verification"
            className="rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground outline-none transition-opacity duration-150 hover:opacity-90 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {titleCase("Run live verification")}
          </a>
          <a
            href="#portfolio-preview"
            className="rounded-md border border-border px-4 py-2.5 text-sm font-medium text-ink outline-none transition-colors duration-150 hover:bg-surface-sunk focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {titleCase("Explore processors")}
          </a>
          <a
            href="#how-it-works"
            className="rounded-md border border-border px-4 py-2.5 text-sm font-medium text-ink outline-none transition-colors duration-150 hover:bg-surface-sunk focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {titleCase("How it works")}
          </a>
        </div>

        {/* T13.5b plan, Part 1: equal-width grid — 2 cols on phones (room
            for labels to wrap), up to 5 equal columns from lg up once the
            T13.6 field-read-accuracy tile is present. figures is null
            when GET /stats failed — the whole row hides rather than
            showing a half-populated grid. */}
        {figures ? (
          <div className="space-y-2">
            <div className="mx-auto mt-10 grid max-w-3xl grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
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
            {figures.fyLabel ? <p className="text-center text-xs text-ink-muted">{figures.fyLabel}</p> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
