"use client";

import { useRef } from "react";
import { ChevronDown } from "lucide-react";
import { motion, useScroll, useTransform } from "motion/react";
import { TypingAnimation } from "@/components/magicui/typing-animation";
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

type DepthTier = "sky" | "mistBack" | "far" | "mid" | "near" | "earth" | "mistFront";

// T13.6b plan, Part 3's layer & depth table: pointer-parallax depth (fed
// to useParallaxLayers, unchanged engine) and a separate scroll-drift
// multiplier (fed to motion/react's scroll-linked transforms below) per
// tier. A fixed, breakpoint-independent set of tiers — never one entry
// per fragment — so the number of scroll useTransform() calls stays
// constant regardless of how many fragments are active, which the rules
// of hooks require.
const TIERS: Record<DepthTier, { depth: number; scrollMultiplier: number }> = {
  sky: { depth: 0.04, scrollMultiplier: 0.2 },
  mistBack: { depth: 0.12, scrollMultiplier: 0.35 },
  far: { depth: 0.4, scrollMultiplier: 0.5 },
  mid: { depth: 0.55, scrollMultiplier: 0.6 },
  near: { depth: 0.7, scrollMultiplier: 0.7 },
  earth: { depth: 0.06, scrollMultiplier: 0.15 },
  mistFront: { depth: 0.3, scrollMultiplier: 0.8 },
};

type Fragment = {
  src: string;
  alt: string;
  widthPx: number; // the 1x on-screen width; -2x.webp is served at 2x via srcSet
  aspect: number; // height / width, so layout doesn't shift before the image decodes
  className: string; // absolute position toward an edge/corner
  mirror?: boolean;
  tier: DepthTier;
  blurPx?: number;
  opacityPct?: number;
  floatPeriodMs: number;
  floatAmpPx: number;
  floatPhase: number;
  mobile?: boolean; // one of the 2 kept below md
};

// Far-to-near follows the brief's rule directly: far fragments smaller,
// blurred and slightly faded; near fragments larger and sharp. Positions
// scatter toward edges/corners — one or two cropped by the viewport edge
// (soil-moss-a, pellets-b below) — keeping the left column clear for the
// text block and the centre-right clear for the hero-earth + HUD group.
const FRAGMENTS: Fragment[] = [
  {
    src: "/hero/strata-a",
    alt: "",
    widthPx: 92,
    aspect: 1140 / 1554,
    className: "-top-3 left-[6%] sm:left-[9%]",
    tier: "far",
    blurPx: 2,
    opacityPct: 70,
    floatPeriodMs: 7800,
    floatAmpPx: 5,
    floatPhase: 0,
  },
  {
    src: "/hero/soil-moss-b",
    alt: "",
    widthPx: 84,
    aspect: 1727 / 1715,
    className: "bottom-[3%] right-[2%] sm:right-[4%]",
    tier: "far",
    blurPx: 2.5,
    opacityPct: 72,
    floatPeriodMs: 7200,
    floatAmpPx: 6,
    floatPhase: 2.1,
  },
  {
    src: "/hero/soil-moss-a",
    alt: "",
    widthPx: 110,
    aspect: 1383 / 2192,
    className: "top-[40%] -left-7 hidden sm:block",
    mirror: true,
    tier: "mid",
    blurPx: 1.5,
    opacityPct: 85,
    floatPeriodMs: 8200,
    floatAmpPx: 6,
    floatPhase: 1.2,
    mobile: true,
  },
  {
    src: "/hero/pellets-rock-a",
    alt: "",
    widthPx: 118,
    aspect: 1055 / 1554,
    className: "bottom-[4%] left-[16%] hidden sm:block",
    tier: "mid",
    blurPx: 1.5,
    opacityPct: 85,
    floatPeriodMs: 7000,
    floatAmpPx: 5,
    floatPhase: 3.4,
  },
  {
    src: "/hero/pellets-a",
    alt: "",
    widthPx: 96,
    aspect: 1536 / 1560,
    className: "top-[10%] right-[26%] hidden lg:block",
    tier: "mid",
    blurPx: 1.5,
    opacityPct: 82,
    floatPeriodMs: 9000,
    floatAmpPx: 5,
    floatPhase: 4.6,
  },
  {
    src: "/hero/pebble-a",
    alt: "",
    widthPx: 150,
    aspect: 1031 / 1330,
    className: "bottom-[4%] left-[34%] sm:left-[30%]",
    tier: "near",
    floatPeriodMs: 6600,
    floatAmpPx: 7,
    floatPhase: 0.8,
    mobile: true,
  },
  {
    src: "/hero/pellets-b",
    alt: "",
    widthPx: 130,
    aspect: 1536 / 1711,
    className: "top-[52%] -right-6",
    mirror: true,
    tier: "near",
    floatPeriodMs: 7400,
    floatAmpPx: 6,
    floatPhase: 5.2,
  },
];

const MOBILE_FRAGMENTS = FRAGMENTS.filter((f) => f.mobile);

const MIST_LAYERS: { tier: DepthTier; config: ParallaxLayerConfig }[] = [
  { tier: "mistBack", config: { depth: TIERS.mistBack.depth, floatPeriodMs: 11000, floatAmpPx: 8, floatPhase: 0.5 } },
  { tier: "mistFront", config: { depth: TIERS.mistFront.depth, floatPeriodMs: 9500, floatAmpPx: 8, floatPhase: 2.1 } },
];

const SCROLL_DRIFT_PX = 110; // the nearest tier's (mistFront) max upward scroll drift
const SCROLL_FADE_END = 0.75; // hero fully faded by this fraction of scroll past it

function srcSet(base: string) {
  return `${base}-1x.webp 1x, ${base}-2x.webp 2x`;
}

type HudChip = { key: string; label: string; value: string; mobile: boolean };

/** T13.6b plan, Part 3: HUD values come straight from /stats (via the
 * same `figures` prop every other landing figure reads) — "2 Agents ·
 * Both Must Agree" is the orchestrator's actual shape (Hypothesis vs.
 * Critic, docs/ARCHITECTURE.md), static copy, not a number anyone
 * invented. The field-read-accuracy chip hides on its own, same per-
 * field rule the old metric row already used — a null `/stats` sub-
 * field hides only itself, never the other chips. */
function buildHudChips(figures: LandingFigures): HudChip[] {
  const chips: HudChip[] = [
    {
      key: "certified",
      label: figures.fyLabel ? `Certified Tonnes, ${figures.fyLabel}` : "Certified Tonnes",
      value: `${formatTonnesValue(figures.certifiedTonnes)} t`,
      mobile: true,
    },
    {
      key: "unverifiable",
      label: "Tonnes Unverifiable",
      value: `${formatTonnesValue(figures.unverifiableTonnes)} t`,
      mobile: true,
    },
  ];
  if (figures.fieldReadAccuracyPct !== null) {
    chips.push({
      key: "accuracy",
      label: "Key Fields Read Correctly",
      value: figures.fieldReadAccuracyPct,
      mobile: false,
    });
  }
  chips.push({
    key: "agents",
    label: "Hypothesis vs. Critic",
    value: "2 Agents · Both Must Agree",
    mobile: false,
  });
  return chips;
}

/** The hero's image layer stack (T13.6b plan, Part 3): full-bleed 100svh
 * scene — sky, drifting mist front/back, scattered supporting rock
 * fragments (far/mid/near per the depth table), and a large hero-earth
 * centrepiece with an attached HUD. Pointer-parallax (depth) still runs
 * through useParallaxLayers' single shared rAF loop, unchanged; scroll-
 * drift and the whole-hero fade are a second, independent transform
 * layer (motion/react's useScroll/useTransform) wrapping the same ref'd
 * elements, so the two engines compose without either touching the
 * other's code path. Sky/rock imagery stays theme-invariant (a real sky
 * photograph, not a token-driven flat gradient) — same deliberate
 * hard-coded-hex architecture MetricTile's "inverted" tone already uses
 * for this exact kind of image-band content. */
export function HeroScene({ figures }: { figures: LandingFigures | null }) {
  const reducedMotion = usePrefersReducedMotion();
  const isMdUp = useIsBreakpointUp(768);
  const containerRef = useRef<HTMLDivElement>(null);

  const activeFragments = isMdUp ? FRAGMENTS : MOBILE_FRAGMENTS;

  // Pointer/idle-float engine (unchanged): sky, earth, every active
  // fragment, mist (desktop only) — fixed order, indices tracked below.
  const pointerLayers: ParallaxLayerConfig[] = [
    { depth: TIERS.sky.depth, floatPeriodMs: 9000, floatAmpPx: 4, floatPhase: 0 },
    { depth: TIERS.earth.depth, floatPeriodMs: 12000, floatAmpPx: 6, floatPhase: 0.6 }, // slow float, least pointer-parallax — the focal point
    ...activeFragments.map((f) => ({
      depth: TIERS[f.tier].depth,
      floatPeriodMs: f.floatPeriodMs,
      floatAmpPx: f.floatAmpPx,
      floatPhase: f.floatPhase,
    })),
    ...(isMdUp ? MIST_LAYERS.map((m) => m.config) : []),
  ];
  const setLayerRef = useParallaxLayers(containerRef, pointerLayers, !reducedMotion);
  let layerIndex = 0;
  const skyLayerIndex = layerIndex++;
  const earthLayerIndex = layerIndex++;
  const fragmentLayerStart = layerIndex;
  layerIndex += activeFragments.length;
  const mistBackLayerIndex = isMdUp ? layerIndex++ : -1;
  const mistFrontLayerIndex = isMdUp ? layerIndex++ : -1;

  // Scroll-drift + fade engine: a fixed 7 useTransform calls (one per
  // DepthTier) regardless of breakpoint/fragment count, per this file's
  // own TIERS comment — satisfies the rules of hooks even though
  // `activeFragments.length` varies.
  const { scrollYProgress } = useScroll({ target: containerRef, offset: ["start start", "end start"] });
  const heroOpacity = useTransform(scrollYProgress, [0, SCROLL_FADE_END], [1, 0]);
  const driftSky = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.sky.scrollMultiplier]);
  const driftMistBack = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.mistBack.scrollMultiplier]);
  const driftFar = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.far.scrollMultiplier]);
  const driftMid = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.mid.scrollMultiplier]);
  const driftNear = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.near.scrollMultiplier]);
  const driftEarth = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.earth.scrollMultiplier]);
  const driftMistFront = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.mistFront.scrollMultiplier]);
  const driftByTier: Record<DepthTier, typeof driftSky> = {
    sky: driftSky,
    mistBack: driftMistBack,
    far: driftFar,
    mid: driftMid,
    near: driftNear,
    earth: driftEarth,
    mistFront: driftMistFront,
  };

  const hudChips = figures ? buildHudChips(figures) : [];
  const mobileChips = hudChips.filter((c) => c.mobile);

  return (
    <section
      ref={containerRef}
      className="relative h-[100svh] min-h-[560px] w-full overflow-hidden text-ink"
      style={{ backgroundColor: "#061028" }}
    >
      {reducedMotion ? (
        // prefers-reduced-motion: the flattened poster only, no layers,
        // no parallax/scroll JS at all.
        <img
          src="/hero/poster.webp"
          alt=""
          aria-hidden
          decoding="async"
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <div aria-hidden className="absolute inset-0">
          <motion.div style={{ y: driftByTier.sky }} className="absolute inset-0">
            <div ref={setLayerRef(skyLayerIndex)} className="absolute inset-0 will-change-transform">
              <img
                src="/hero/sky-1x.webp"
                srcSet={srcSet("/hero/sky")}
                alt=""
                width={1600}
                height={893}
                decoding="async"
                className="h-full w-full object-cover"
              />
              {/* Blue-family colour grade (T13.6b plan, Part 3) — a soft
                  #90ddf0 tint over the raw photo, not baked into the
                  asset, so a future re-grade is a one-line change. */}
              <div
                className="absolute inset-0"
                style={{ backgroundColor: "rgb(144 221 240 / 0.14)", mixBlendMode: "soft-light" }}
              />
            </div>
          </motion.div>

          {isMdUp ? (
            <motion.div style={{ y: driftByTier.mistBack }} className="absolute inset-0">
              <div
                ref={setLayerRef(mistBackLayerIndex)}
                className="absolute inset-0 opacity-25 will-change-transform"
              >
                <img
                  src="/hero/mist-1-1x.webp"
                  srcSet={srcSet("/hero/mist-1")}
                  alt=""
                  width={700}
                  height={350}
                  decoding="async"
                  className="h-full w-full object-cover"
                />
              </div>
            </motion.div>
          ) : null}

          {activeFragments.map((fragment, i) => {
            const heightPx = Math.round(fragment.widthPx * fragment.aspect);
            return (
              <motion.div
                key={fragment.src}
                style={{ y: driftByTier[fragment.tier] }}
                className={`absolute ${fragment.className}`}
              >
                <div
                  ref={setLayerRef(fragmentLayerStart + i)}
                  className="will-change-transform"
                  style={{
                    opacity: fragment.opacityPct !== undefined ? fragment.opacityPct / 100 : 1,
                    filter: fragment.blurPx ? `blur(${fragment.blurPx}px)` : undefined,
                  }}
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
              </motion.div>
            );
          })}

          {/* Hero-earth + HUD group: one shared parallax layer so the
              chips stay visually attached to the rock regardless of
              pointer or scroll position (T13.6b plan, Part 3). */}
          <motion.div
            style={{ y: driftByTier.earth }}
            className="absolute right-[6%] top-1/2 -translate-y-1/2 sm:right-[8%] md:right-[10%]"
          >
            <div ref={setLayerRef(earthLayerIndex)} className="relative will-change-transform">
              <img
                src="/hero/hero-earth-1x.webp"
                srcSet={srcSet("/hero/hero-earth")}
                alt=""
                width={340}
                height={340}
                decoding="async"
                className="h-[42svh] min-h-[220px] w-auto max-w-[70vw] drop-shadow-xl sm:h-[48svh] md:h-[52svh]"
              />

              {/* Thin corner brackets framing part of the rock. */}
              <div
                aria-hidden
                className="pointer-events-none absolute -left-3 -top-3 h-10 w-10 border-l-2 border-t-2 border-white/70"
              />
              <div
                aria-hidden
                className="pointer-events-none absolute -bottom-3 -right-3 h-10 w-10 border-b-2 border-r-2 border-white/70"
              />

              {hudChips.length > 0 ? (
                <div className="absolute left-full top-1/2 ml-4 hidden w-56 -translate-y-1/2 space-y-2 lg:block">
                  {hudChips.map((chip) => (
                    <div key={chip.key} className="flex items-center gap-2">
                      <span aria-hidden className="h-px w-5 shrink-0 bg-white/50" />
                      <div className="rounded-md border border-[#00b7b5]/40 bg-white/85 px-2.5 py-1.5 text-ink shadow-sm backdrop-blur-sm">
                        <div className="font-mono text-sm font-semibold leading-tight">{chip.value}</div>
                        <div className="text-[10px] font-medium uppercase leading-tight tracking-wide text-ink-muted">
                          {chip.label}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </motion.div>

          {isMdUp ? (
            <motion.div style={{ y: driftByTier.mistFront }} className="absolute inset-0">
              <div
                ref={setLayerRef(mistFrontLayerIndex)}
                className="absolute inset-0 opacity-20 will-change-transform"
              >
                <img
                  src="/hero/mist-2-1x.webp"
                  srcSet={srcSet("/hero/mist-2")}
                  alt=""
                  width={700}
                  height={350}
                  decoding="async"
                  className="h-full w-full object-cover"
                />
              </div>
            </motion.div>
          ) : null}
        </div>
      )}

      {/* Localised scrim behind the text column only — the headline/body
          sit on real sky photography whose luminance varies by position,
          not a flat token-driven background, so a global scrim would
          either wash out the sky or under-protect the text. Verified
          against the actual rendered asset in T13.6b's Part 4 contrast
          pass; adjusted there if short of the AA floor. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-0 w-full sm:w-[65%] lg:w-[55%]"
        style={{ background: "linear-gradient(105deg, rgb(6 16 40 / 0.55), rgb(6 16 40 / 0.15) 70%, transparent)" }}
      />

      <motion.div
        style={reducedMotion ? undefined : { opacity: heroOpacity }}
        className="relative z-10 flex h-full flex-col justify-between px-5 py-6 sm:px-10 sm:py-10"
      >
        <div className="flex flex-1 flex-col justify-center">
          <h1
            className="max-w-xl text-pretty font-display font-semibold tracking-tight text-white"
            style={{ fontSize: "clamp(2.25rem, 1.6rem + 3.2vw, 5rem)", lineHeight: 1.05 }}
          >
            <span className="sr-only">{HEADLINE}</span>
            {reducedMotion ? (
              <span aria-hidden>{HEADLINE}</span>
            ) : (
              <TypingAnimation aria-hidden as="span" duration={TYPING_DURATION_MS} showCursor={false}>
                {HEADLINE}
              </TypingAnimation>
            )}
          </h1>
          <p className="mt-4 max-w-md text-pretty text-sm text-white/85 sm:text-base">
            We reconstruct a processor&apos;s material flow from its own paper trail, test it against
            physical and documentary constraints, and report how many certified tonnes are verifiable,
            with evidence for every finding.
          </p>

          <div className="mt-7 flex flex-wrap items-center gap-3">
            <a
              href="#live-verification"
              className="rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground outline-none transition-opacity duration-150 hover:opacity-90 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              {titleCase("Run live verification")}
            </a>
            <a
              href="#portfolio-preview"
              className="rounded-md border border-white/40 px-4 py-2.5 text-sm font-medium text-white outline-none backdrop-blur-sm transition-colors duration-150 hover:bg-white/10 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            >
              {titleCase("Explore processors")}
            </a>
            <a
              href="#how-it-works"
              className="rounded-md border border-white/40 px-4 py-2.5 text-sm font-medium text-white outline-none backdrop-blur-sm transition-colors duration-150 hover:bg-white/10 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            >
              {titleCase("How it works")}
            </a>
          </div>

          {mobileChips.length > 0 ? (
            <div className="mt-7 grid max-w-xs grid-cols-2 gap-2 lg:hidden">
              {mobileChips.map((chip) => (
                <div
                  key={chip.key}
                  className="rounded-md border border-[#00b7b5]/40 bg-white/85 px-2.5 py-1.5 text-ink shadow-sm backdrop-blur-sm"
                >
                  <div className="font-mono text-sm font-semibold leading-tight">{chip.value}</div>
                  <div className="text-[10px] font-medium uppercase leading-tight tracking-wide text-ink-muted">
                    {chip.label}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>

        <div className="flex items-end justify-between gap-4">
          <p className="max-w-[32ch] text-pretty text-xs text-white/70 sm:text-sm">
            Independent verification for India&apos;s plastic packaging EPR certificates.
          </p>
          <div className="flex shrink-0 flex-col items-center gap-1 text-white/70">
            <span className="text-[10px] font-medium uppercase tracking-widest">Scroll to Discover</span>
            <ChevronDown aria-hidden size={16} className={reducedMotion ? undefined : "motion-safe:animate-bounce"} />
          </div>
        </div>
      </motion.div>
    </section>
  );
}
