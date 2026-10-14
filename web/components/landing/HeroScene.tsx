"use client";

import { useRef } from "react";
import { ChevronDown } from "lucide-react";
import { motion, useScroll, useTransform } from "motion/react";
import { TypingAnimation } from "@/components/magicui/typing-animation";
import { PageContainer } from "@/components/ui/PageContainer";
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

type DepthTier = "sky" | "distant" | "mistBack" | "far" | "mid" | "near" | "earth" | "mistFront";

// T13.6b plan, Part 3's layer & depth table: pointer-parallax depth (fed
// to useParallaxLayers, unchanged engine) and a separate scroll-drift
// multiplier (fed to motion/react's scroll-linked transforms below) per
// tier. A fixed, breakpoint-independent set of tiers — never one entry
// per fragment — so the number of scroll useTransform() calls stays
// constant regardless of how many fragments are active, which the rules
// of hooks require.
const TIERS: Record<DepthTier, { depth: number; scrollMultiplier: number }> = {
  sky: { depth: 0.04, scrollMultiplier: 0.2 },
  // T16a item 2b: the floating-island band. Still the slowest SOLID
  // layer — well under `far` (0.4) and the fragments above it — but
  // raised from the original 0.08/0.25 at the developer's request: at
  // 0.08 the pointer response was arithmetically present and visually
  // invisible, which read as a static backdrop rather than a distant
  // one. 0.16/0.35 is roughly double, enough to register as movement
  // while staying clearly behind everything else in the stack.
  distant: { depth: 0.16, scrollMultiplier: 0.35 },
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

// T16a items 2a + 3. Far-to-near still follows the brief's rule — far
// fragments smaller, blurred and slightly faded; near fragments larger
// and sharp — and the sizes below stay monotonic by tier (near 150/130 >
// mid 118/110/96 > far 92/84), which is what makes the depth order read
// without any extra cue.
//
// What changed is grouping. The fragments previously scattered toward
// whichever edge was free, which reads as random rather than composed.
// They now sit in three deliberate clusters that frame the content:
//
//   lower-left anchor   pebble-a (near, sharp) + soil-moss-a (mid)
//                       in the gap between the CTA row and the bottom
//                       tagline, closing the composition's bottom-left
//                       corner without touching either.
//   upper-right frame   pellets-a (mid) + soil-moss-b (far, smallest,
//                       most blurred) above and outboard of the globe.
//   right-field accent  pellets-b (near) low on the right, below the
//                       HUD chip stack, as the near-field counterweight.
//
// strata-a and pellets-rock-a leave this scatter entirely and become the
// mirrored pair around the globe (item 3, Composition A): one shared
// right-[30%] offset and symmetric 12% vertical offsets, so they read as
// one vertical axis through the globe. They keep their own tiers and
// sizes (far/92 above, mid/118 below), so the mirror carries a slight,
// deliberate depth tilt rather than being a flat reflection.
//
// Every position below was checked arithmetically at 1280/1440/1663/1920
// against the globe box, the HUD chip column, both corner brackets, the
// text column, the bottom tagline, "Scroll to Discover" — and against
// each OTHER fragment, which caught two collisions in the first pass:
// strata-a overlapped pellets-a in the top right, and pellets-b ran
// straight through the chip stack.
//
// Nothing is cropped by the viewport edge any more. T13.6b deliberately
// bled soil-moss-a and pellets-b off the left and right edges; this task
// reverses that, confirmed by the developer.
const FRAGMENTS: Fragment[] = [
  // --- mirrored pair around the globe (item 3, Composition A) ---
  {
    src: "/hero/strata-a",
    alt: "",
    widthPx: 92,
    aspect: 1140 / 1554,
    // Beside the globe, not above it, with a constant 48px gap. A fixed
    // right-% cannot do this: the globe's left edge is
    // (82vw - its own height), so it slides with BOTH viewport width and
    // height, and a percentage that gapped correctly at 1663 sat on top
    // of the globe at 1280. Deriving the offset from the same geometry
    // the globe uses keeps the gap constant at every size —
    // 92px width + 48px gap = 140px back from the globe's left edge.
    // Vertical centring is done as top: calc(50% - half-height) rather
    // than -translate-y-1/2, because motion/react writes its scroll
    // drift into this element's own transform and a Tailwind translate
    // would be overwritten by it.
    // Below the globe and to its left, both offsets derived from the
    // globe's own geometry (right-[18%], h-46svh) so the relationship
    // holds at any viewport size rather than drifting with a fixed %.
    // 16px under the globe's bottom edge; 80px back from its left edge.
    //
    // Hidden below 2xl, and that is a real constraint rather than a
    // preference: the band under the globe is bounded by the CTA row
    // (ends y707) and pebble-a (starts y774) — 67px, exactly this
    // image's height, so there is zero slack. Below 1536 the CTA row
    // still extends far enough right that this element lands on top of
    // it, and no combination of the two offsets clears both the CTAs and
    // pebble-a at 1280/1440. From 1536 the CTA row no longer reaches
    // that far right and it clears everything with 7px to spare.
    className:
      "hidden 2xl:block 2xl:top-[calc(50%+23svh+16px)] 2xl:left-[calc(82vw-46svh-172px)]",
    // Unblurred and near-opaque at the developer's request — it was
    // blurPx 2 / 70% as a far-tier element. The tier itself is unchanged,
    // so its parallax and scroll speed are exactly what has already been
    // reviewed; only its rendering is sharper.
    tier: "far",
    opacityPct: 95,
    floatPeriodMs: 7800,
    floatAmpPx: 5,
    floatPhase: 0,
  },
  {
    src: "/hero/pellets-rock-a",
    alt: "",
    widthPx: 118,
    aspect: 1055 / 1554,
    // Below the globe, mirroring strata-a: same right offset, same 12%
    // inset from the opposite edge. Clears the globe's bottom by ~61px
    // and the bottom-right corner bracket entirely.
    className: "hidden sm:block sm:bottom-[12%] sm:right-[30%]",
    tier: "mid",
    blurPx: 1.5,
    opacityPct: 85,
    floatPeriodMs: 7000,
    floatAmpPx: 5,
    floatPhase: 3.4,
  },

  // --- upper-right frame ---
  {
    src: "/hero/pellets-a",
    alt: "",
    widthPx: 96,
    aspect: 1536 / 1560,
    // Pushed up and outboard from its old top-[26%]: at that offset it
    // overlapped strata-a's new position in the top right.
    className: "top-[6%] right-[12%] hidden lg:block",
    tier: "mid",
    blurPx: 1.5,
    opacityPct: 82,
    floatPeriodMs: 9000,
    floatAmpPx: 5,
    floatPhase: 4.6,
  },
  {
    src: "/hero/soil-moss-b",
    alt: "",
    widthPx: 84,
    aspect: 1727 / 1715,
    // Outboard of pellets-a and well above the chip stack. Fully inside
    // the viewport at every width.
    className: "hidden sm:block sm:top-[18%] sm:right-[4%]",
    tier: "far",
    blurPx: 2.5,
    opacityPct: 72,
    floatPeriodMs: 7200,
    floatAmpPx: 6,
    floatPhase: 2.1,
  },

  // --- right-field accent ---
  {
    src: "/hero/pellets-b",
    alt: "",
    widthPx: 130,
    aspect: 1536 / 1711,
    // Dropped from top-[52%] to top-[74%], in two moves. 52% ran through
    // the HUD chip stack; 66% cleared it at the time, but O2 then made
    // the chips materially taller — larger figures, wider gaps, and
    // three-line labels now that the live fy_label is "FY 2025-26 to
    // date" — taking the stack from ~200px to ~358px and putting this
    // fragment back inside it by 29px at every width from 1280 to 1920.
    // 74% clears the stack's new lower edge by ~45px, with margin for the
    // label wrapping to vary with the data.
    className: "hidden sm:block sm:top-[74%] sm:right-[2%]",
    mirror: true,
    tier: "near",
    floatPeriodMs: 7400,
    floatAmpPx: 6,
    floatPhase: 5.2,
  },

  // --- lower-left anchor ---
  {
    src: "/hero/soil-moss-a",
    alt: "",
    widthPx: 110,
    aspect: 1383 / 2192,
    // Moved out of the text column: at sm:top-[40%] it sat behind the
    // body paragraph. Now in the clear band between the CTA row and the
    // tagline, and fully on-screen (was -left-7).
    className: "bottom-[3%] left-[2%] sm:bottom-[12%] sm:left-[3%]",
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
    src: "/hero/pebble-a",
    alt: "",
    widthPx: 150,
    aspect: 1031 / 1330,
    // The near-field anchor: largest and the only unblurred fragment.
    // Sits right of the tagline's text box at every width.
    // Base offset is 32% not 30%: at 390px the two mobile fragments
    // touched by ~1px, since soil-moss-a's box ends at x=118 and this
    // one started at x=117. 32% opens a 7px gap.
    className: "bottom-[5%] left-[32%] sm:left-[26%]",
    tier: "near",
    floatPeriodMs: 6600,
    floatAmpPx: 7,
    floatPhase: 0.8,
    mobile: true,
  },
];

const MOBILE_FRAGMENTS = FRAGMENTS.filter((f) => f.mobile);

// Longest period of any layer — a distant object drifts slowly, it does
// not bob like the near fragments. The amplitude is small but no longer
// the smallest: 4px was imperceptible across a band this wide.
const DISTANT_LAYER: ParallaxLayerConfig = {
  depth: TIERS.distant.depth,
  floatPeriodMs: 14000,
  floatAmpPx: 7,
  floatPhase: 1.7,
};

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
  // T16a O2: "2 Agents · Both Must Agree" was one 26-character string in
  // the value slot, which broke across three ragged lines in a 160px
  // column. Every other chip puts the quantity in `value` and the
  // description in `label`; this one now does too.
  chips.push({
    key: "agents",
    label: "Hypothesis vs. Critic · Both Must Agree",
    value: "2 Agents",
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
    ...(isMdUp ? [DISTANT_LAYER, ...MIST_LAYERS.map((m) => m.config)] : []),
  ];
  const setLayerRef = useParallaxLayers(containerRef, pointerLayers, !reducedMotion);
  let layerIndex = 0;
  const skyLayerIndex = layerIndex++;
  const earthLayerIndex = layerIndex++;
  const fragmentLayerStart = layerIndex;
  layerIndex += activeFragments.length;
  const distantLayerIndex = isMdUp ? layerIndex++ : -1;
  const mistBackLayerIndex = isMdUp ? layerIndex++ : -1;
  const mistFrontLayerIndex = isMdUp ? layerIndex++ : -1;

  // Scroll-drift + fade engine: a fixed 7 useTransform calls (one per
  // DepthTier) regardless of breakpoint/fragment count, per this file's
  // own TIERS comment — satisfies the rules of hooks even though
  // `activeFragments.length` varies.
  const { scrollYProgress } = useScroll({ target: containerRef, offset: ["start start", "end start"] });
  const heroOpacity = useTransform(scrollYProgress, [0, SCROLL_FADE_END], [1, 0]);
  const driftSky = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.sky.scrollMultiplier]);
  const driftDistant = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.distant.scrollMultiplier]);
  const driftMistBack = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.mistBack.scrollMultiplier]);
  const driftFar = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.far.scrollMultiplier]);
  const driftMid = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.mid.scrollMultiplier]);
  const driftNear = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.near.scrollMultiplier]);
  const driftEarth = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.earth.scrollMultiplier]);
  const driftMistFront = useTransform(scrollYProgress, [0, 1], [0, -SCROLL_DRIFT_PX * TIERS.mistFront.scrollMultiplier]);
  const driftByTier: Record<DepthTier, typeof driftSky> = {
    sky: driftSky,
    distant: driftDistant,
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
          {/* T16a: the backdrop layers are taller than the hero rather
              than exactly its height. Each one is translated UPWARD by
              its scroll drift, so an inset-0 layer uncovers the section's
              own #061028 background along the bottom as the page scrolls
              — a dark band that grows with scroll position, which is what
              it looked like. Sky drifts at most 110 x 0.2 = 22px (plus
              4px float and 0.7px pointer), so 64px of overhang is the fix
              with room to spare. */}
          <motion.div style={{ y: driftByTier.sky }} className="absolute inset-x-0 top-0 -bottom-16">
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

          {/* T16a item 2b: the distant floating-island band, restoring the
              most-distant layer T13.6b dropped. Sits directly on the sky
              and BEHIND the mist, so the mist softens it the way depth
              should. Full-bleed along the bottom edge, where a horizon
              belongs; hidden below md alongside the mist, because on a
              phone this band and the bottom-anchored hero-earth would
              occupy the same strip. Lazy + async: it must not become the
              LCP element.

              Pushed 14% below the hero's bottom edge at the developer's
              request, so the nearest islands run off the bottom instead
              of all floating clear of it — the section's own
              overflow-hidden does the trimming. It also keeps the band's
              own lower edge safely out of frame: total upward travel is
              ~48px (scroll drift 110 x 0.35 = 38.5, idle float 7, pointer
              0.16 x MAX_SHIFT_PX 18 = 2.9), against a 14% offset that is
              ~131px on a 937px-tall hero. */}
          {isMdUp ? (
            <motion.div style={{ y: driftByTier.distant }} className="absolute inset-x-0 -bottom-[14%]">
              <div
                ref={setLayerRef(distantLayerIndex)}
                className="will-change-transform"
                style={{ opacity: 0.65, filter: "blur(2px)" }}
              >
                <img
                  src="/hero/distant-1-1x.webp"
                  srcSet={srcSet("/hero/distant-1")}
                  alt=""
                  width={1100}
                  height={231}
                  decoding="async"
                  loading="lazy"
                  className="h-auto w-full"
                />
              </div>
            </motion.div>
          ) : null}

          {isMdUp ? (
            <motion.div style={{ y: driftByTier.mistBack }} className="absolute inset-x-0 top-0 -bottom-24">
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
            // Mobile (brief: "text stacked above" the scene, not
            // overlaid): bottom-anchored in the lower band the text
            // column's justify-start flow leaves clear, found overlapping
            // the headline/CTAs when it was unconditionally vertically
            // centered during T13.6b's own verification pass. sm+ restores
            // the desktop vertical-centre overlay.
            className="absolute bottom-[1%] right-[4%] sm:bottom-auto sm:right-[8%] sm:top-1/2 sm:-translate-y-1/2 lg:right-[18%]"
          >
            <div ref={setLayerRef(earthLayerIndex)} className="relative will-change-transform">
              <img
                src="/hero/hero-earth-1x.webp"
                srcSet={srcSet("/hero/hero-earth")}
                alt=""
                width={340}
                height={340}
                decoding="async"
                // lg jumps to a smaller vh% than sm, not a continued
                // increase: the HUD column appears for the first time at
                // lg (below, `lg:block`) and needs real horizontal room
                // between earth's right edge and the viewport edge —
                // measured directly (Playwright + getBoundingClientRect)
                // against 1280/1440/1920 during T13.6b's verification
                // pass after the chip column was found overflowing the
                // viewport by ~100px at the previous, larger sizing. The
                // base (mobile) size is deliberately smaller than sm+ —
                // it shares its band with 2 fragments and the bottom row,
                // not the whole viewport height.
                className="h-[28svh] min-h-[170px] w-auto max-w-[62vw] drop-shadow-xl sm:h-[48svh] sm:max-w-[70vw] lg:h-[38svh] xl:h-[46svh]"
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

              {/* T16a O2: ml-3 -> ml-5. The spacing was already constant
                  (left-full is the globe image's own right edge, so the
                  gap never drifted with breakpoint), just tight. The
                  corner bracket does NOT collide with this column — it
                  sits 88px below the lowest chip — so nothing moved on
                  its account. w-40 stays: w-48 would leave only 14px to
                  the viewport edge at 1280. */}
              {hudChips.length > 0 ? (
                <div className="absolute left-full top-1/2 ml-5 hidden w-40 -translate-y-1/2 space-y-3.5 lg:block">
                  {hudChips.map((chip) => (
                    <div key={chip.key} className="flex items-center gap-2">
                      <span aria-hidden className="h-px w-4 shrink-0 bg-white/50" />
                      {/* Fixed navy/grey, not text-ink/-muted: this chip's
                          own surface is deliberately theme-invariant
                          (always a light card over the photo), so the
                          theme token would flip to near-white text in
                          dark mode — confirmed illegible (~1:1) in
                          T13.6b's own dark-mode verification pass. Same
                          hardcoded-hex architecture as MetricTile's
                          "inverted" tone for this exact kind of
                          image-band content. */}
                      {/* T16a O2 readability. Contrast was never the
                          problem here — the label measured 5.53:1 at its
                          worst even on the darkest sky — the problem was
                          size: a 9px label is below what anyone should be
                          asked to read, whatever its ratio. Label 9->10px
                          with a heavier weight and navy/80 instead of /70
                          (8.6:1), value 12->13px, and the surface from
                          white/85 to /92 so it stops shifting with
                          whatever sky is behind it. tabular-nums keeps the
                          figures aligned down the column, and text-balance
                          stops the long labels (the live fy_label is
                          "FY 2025-26 to date") leaving an orphan word. */}
                      <div className="rounded-md border border-[#00b7b5]/40 bg-white/92 px-2.5 py-2 text-[#071952] shadow-sm backdrop-blur-sm">
                        <div className="font-ui text-[15px] font-semibold leading-tight tabular-nums">
                          {chip.value}
                        </div>
                        <div className="mt-0.5 text-balance text-[10px] font-semibold uppercase leading-snug tracking-wider text-[#071952]/80">
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
            <motion.div style={{ y: driftByTier.mistFront }} className="absolute inset-x-0 top-0 -bottom-32">
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
          either wash out the sky or under-protect the text.

          T16a item 1, below sm: unchanged from T13.6b. The mobile layout
          stacks text at the top and bottom-anchors hero-earth, so the
          desktop band's geometry doesn't apply; its own contrast is
          tracked separately. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-0 w-full sm:hidden"
        style={{ background: "linear-gradient(105deg, rgb(6 16 40 / 0.55), rgb(6 16 40 / 0.15) 70%, transparent)" }}
      />

      {/* T16a item 1, sm and up: the scrim is sized to the TEXT COLUMN
          rather than to a share of the viewport. Its right edge is derived
          from the same PageContainer padding + max-width scale O1 put the
          text on — px-6/8/12/16 with the 1440/1600 caps — so it lands a
          constant 64px past the headline's own max-w-xl (36rem) at every
          width. The old `lg:w-[55%]` was 914.7px on a 1663px viewport,
          which is exactly where the reported hard vertical line fell: the
          gradient was still at ~0.19 alpha when the element ended, and a
          gradient that is still visibly dark at its own edge reads as a
          seam, not a fade.

          Horizontal: a flat alpha across the whole column, fading out
          only across that 64px margin. A diagonal or radial falloff was
          measured first and rejected — it decays in both axes at once, so
          it is weakest exactly at the body paragraph's right edge, which
          is the pixel most in need of cover (a radial feather never got
          body text above 2.44:1 without driving the left edge to near
          opaque).

          Alpha is 0.25 by explicit decision: this task asked for the
          overlay to get NARROWER, not darker, and 0.25 is the value the
          developer settled on after seeing it rendered. It is well under
          the 0.55 the old diagonal gradient started at, so the band is
          substantially lighter than before across its whole width.

          Contrast consequence, recorded so it is not rediscovered later:
          the body paragraph and the bottom tagline do not meet WCAG AA
          over the brightest cloud at this alpha (~1.9:1 against a 4.5
          floor), and the headline sits near its own 3.0 large-text
          floor. Text alpha cannot recover it — the copy is already
          white-ish and the cloud behind it is near-white, so white is
          the ceiling. Only a darker band (~0.62) or a text shadow would,
          and both were declined. Deliberate, not an oversight.

          Vertical: feathered toward the top via mask-image, so the sky
          under the nav opens up instead of carrying a full-height slab.
          Every HERO text element sits below 26%, so the feather is free
          for them — measured identical ratios at 22/26/30%. It is not
          free for the NAV BRAND, which sits at ~3-5% of the hero: fading
          the mask to 0 there dropped it from 5.65:1 to 2.78:1, under its
          3.0 large-text floor. So the mask starts at 0.5 rather than 0 —
          the top keeps half the band's alpha (0.64 x 0.5 = 0.32 effective,
          against 0.55 before this change), which still visibly opens the
          sky while keeping the brand legible. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-0 hidden sm:block sm:w-[min(100%,664px)] lg:w-[min(100%,672px)] xl:w-[calc(max(0px,(100vw-1440px)/2)+688px)] 2xl:w-[calc(max(0px,(100vw-1600px)/2)+704px)]"
        style={{
          background:
            "linear-gradient(to right, rgb(6 16 40 / 0.25) 0, rgb(6 16 40 / 0.25) calc(100% - 64px), rgb(6 16 40 / 0) 100%)",
          maskImage: "linear-gradient(to bottom, rgb(0 0 0 / 0.5) 0, #000 26%, #000 100%)",
          WebkitMaskImage: "linear-gradient(to bottom, rgb(0 0 0 / 0.5) 0, #000 26%, #000 100%)",
        }}
      />

      {/* T16a O1: the hero's content column now runs through the same
          PageContainer every other page/Nav/Footer uses, instead of its
          own px-5/sm:px-10 — the hero was the one surface whose left
          edge didn't track the nav brand's. Measured before the change:
          brand 48/48/95.5/224px against hero text flat at 40px for
          1280/1440/1663/1920, so the gap grew from 8px to 184px as the
          viewport widened past PageContainer's max-width cap, where the
          brand starts centering and the hero kept hugging the edge.
          Only horizontal padding moves here; the vertical py-6/sm:py-10
          and the h-full justify-between flow stay on this element,
          since the two PageContainers below are its flex children. */}
      {/* T16a: bottom fade into the page, so the hero hands off to the
          section below instead of ending on a hard horizontal cut
          between sky photography and the page colour. Uses
          var(--color-page) rather than a literal, so it lands on the
          right colour in both themes.

          Painted LAST of the decorative layers — after the scrims, not
          before them. The text-column scrim is inset-y-0 at 0.25 navy,
          so with the fade underneath it the left side kept a navy cast
          all the way to the hero's edge and never reached the page
          colour: the fade worked on the right of the hero and visibly
          failed on the left. Ordering it above both scrims makes the
          hand-off uniform across the full width. Still before the
          content layer (relative z-10), so the tagline and scroll
          indicator stay crisp on top of it.

          The ramp deliberately stays transparent through the first 45%:
          the bottom tagline's baseline sits ~40px above the hero's lower
          edge, inside this band, and a fade that started at its top edge
          would put near-page-colour behind white text. Holding it clear
          until 45% keeps the colour in the strip below the text. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-24"
        style={{
          background:
            "linear-gradient(to bottom, transparent 0%, transparent 45%, var(--color-page) 100%)",
        }}
      />

      <motion.div
        style={reducedMotion ? undefined : { opacity: heroOpacity }}
        className="relative z-10 flex h-full flex-col justify-between py-6 sm:py-10"
      >
        {/* Mobile: text starts at the top and flows down ("stacked
            above" the scene, per the brief) rather than vertically
            centering into the same band hero-earth occupies — found
            overlapping the headline/CTAs when both were centered during
            T13.6b's own verification pass. sm+ restores the centred
            overlay look. */}
        <PageContainer className="flex flex-1 flex-col justify-start pt-2 sm:justify-center sm:pt-0">
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
          {/* T16a: semibold, matching the bottom tagline. With the scrim
              at 0.25 this is the only lever left that lifts the body's
              legibility without darkening the band — text alpha is
              already near its ceiling against the bright cloud behind
              it. */}
          <p className="mt-4 max-w-md text-pretty text-sm font-semibold text-white/85 sm:text-base">
            We reconstruct a processor&apos;s material flow from its own paper trail, test it against
            physical and documentary constraints, and report how many certified tonnes are verifiable,
            with evidence for every finding.
          </p>

          <div className="mt-7 flex flex-wrap items-center gap-3">
            {/* T16a item D, then revised: the fill is a literal #00b7b5
                rather than a token, because the two themes need the SAME
                colour here and no single token provides it —
                --color-primary is #005461 in light and #00b7b5 in dark,
                --color-glow is #00b7b5 in light and #90ddf0 in dark. A
                literal pins both to #00b7b5, which is what was asked for:
                light changes, dark is left exactly as it was. The
                foreground stays tokenised, so it still flips white/navy
                per theme. Hardcoded hex is this file's existing
                convention for theme-invariant surfaces (see the HUD
                chips).

                Contrast, recorded so it is not rediscovered as a
                surprise: light is white on #00b7b5 = 2.49:1, under the
                4.5 floor, and axe reports it as a serious violation on
                `/` at 1440 and 390. This is a deliberate choice by the
                developer, who saw the 8.60:1 alternative (#005461) and
                preferred this colour. Dark is unchanged at navy #071952
                on #00b7b5 = 6.65:1. */}
            <a
              href="#live-verification"
              className="rounded-md bg-[#00b7b5] px-4 py-2.5 text-sm font-medium text-primary-foreground outline-none transition-opacity duration-150 hover:opacity-90 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
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
            <div className="mt-7 grid max-w-xs grid-cols-2 gap-3 lg:hidden">
              {mobileChips.map((chip) => (
                <div
                  key={chip.key}
                  // Fixed navy, not text-ink — see the desktop HUD
                  // column's identical comment; this surface is always
                  // light, regardless of site theme.
                  className="rounded-md border border-[#00b7b5]/40 bg-white/92 px-2.5 py-2 text-[#071952] shadow-sm backdrop-blur-sm"
                >
                  <div className="font-ui text-base font-semibold leading-tight tabular-nums">
                    {chip.value}
                  </div>
                  <div className="mt-0.5 text-balance text-[10px] font-semibold uppercase leading-snug tracking-wider text-[#071952]/80">
                    {chip.label}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </PageContainer>

        <PageContainer className="flex items-end justify-between gap-4">
          {/* T16a: white/70 -> /85 (item 1, to claw back contrast under a
              lighter scrim) -> fully opaque white at the developer's
              request. This is the most legible this line can be made
              without touching the scrim: white is the ceiling against the
              bright cloud behind it. */}
          <p className="max-w-[32ch] text-pretty text-xs font-semibold text-white sm:text-sm">
            Independent verification for India&apos;s plastic packaging EPR certificates.
          </p>
          {/* T16a: white/70 -> /90, in two steps at the developer's
              request. Raised on the wrapper, not the span, so the chevron
              keeps pace with the label — splitting them would leave the
              icon visibly faded against its own text. */}
          <div className="flex shrink-0 flex-col items-center gap-1 text-white/90">
            {/* T16a: 10px/medium -> 11px/semibold at the developer's
                request (12px first, then back 1px). Same weight the HUD
                chip labels now use, so the two smallest pieces of type in
                the hero read as one system. */}
            <span className="text-[11px] font-semibold uppercase tracking-widest">Scroll to Discover</span>
            <ChevronDown aria-hidden size={16} className={reducedMotion ? undefined : "motion-safe:animate-bounce"} />
          </div>
        </PageContainer>
      </motion.div>
    </section>
  );
}
