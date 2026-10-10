"use client";

import { useEffect, useMemo, useRef } from "react";
import { useIsFinePointer } from "@/lib/useIsFinePointer";

export type ParallaxLayerConfig = {
  /** 0 (background) .. 1 (nearest) — pointer-shift multiplier. */
  depth: number;
  /** Idle sine-drift period, ms. */
  floatPeriodMs: number;
  /** Idle sine-drift amplitude, px. */
  floatAmpPx: number;
  /** Phase offset (radians) so layers don't drift in lockstep. */
  floatPhase: number;
};

const MAX_SHIFT_PX = 18; // nearest layer's max pointer-driven translate
const LERP_FACTOR = 0.08; // per-frame approach toward the pointer target

/** Drives HeroScene's parallax layers (T13.6 plan, Part B) via refs and
 * direct style writes in a single shared requestAnimationFrame loop —
 * never React state, so N layers never trigger N (or even 1) re-render
 * per frame. Returns a `setLayerRef(index)` callback-ref factory; the
 * caller attaches `setLayerRef(i)` to layer `i`'s wrapper element (a
 * single mutable array under the hood, not one useRef per layer, so the
 * number of layers can vary across renders without breaking the rules of
 * hooks).
 *
 * - Pointer position is normalized -1..1 over containerRef's bounding
 *   rect and lerped toward on every frame (never jumps).
 * - A per-layer sine idle-float is always added, pointer tracking or not
 *   — so the scene breathes even when the mouse is still.
 * - Pointer tracking itself is skipped on a coarse/touch pointer
 *   (useIsFinePointer) — idle float only there.
 * - The whole loop pauses when the container scrolls off-screen
 *   (IntersectionObserver) or the tab is hidden (visibilitychange).
 * - `enabled=false` (e.g. prefers-reduced-motion) never starts the loop
 *   at all — callers in that state should render the static poster
 *   instead of mounting layers that would never move. */
export function useParallaxLayers(
  containerRef: React.RefObject<HTMLElement | null>,
  layers: ParallaxLayerConfig[],
  enabled: boolean,
): (index: number) => (el: HTMLDivElement | null) => void {
  const elements = useRef<(HTMLDivElement | null)[]>([]);
  const isFinePointer = useIsFinePointer();

  const pointerTarget = useRef({ x: 0, y: 0 });
  const pointerCurrent = useRef({ x: 0, y: 0 });
  const inView = useRef(false);
  const startTime = useRef<number | null>(null);

  const setLayerRef = useMemo(
    () => (index: number) => (el: HTMLDivElement | null) => {
      elements.current[index] = el;
    },
    [],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !enabled) return;

    const onPointerMove = (e: PointerEvent) => {
      if (!isFinePointer) return;
      const rect = container.getBoundingClientRect();
      const nx = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      const ny = ((e.clientY - rect.top) / rect.height) * 2 - 1;
      pointerTarget.current = {
        x: Math.max(-1, Math.min(1, nx)),
        y: Math.max(-1, Math.min(1, ny)),
      };
    };
    const onPointerLeave = () => {
      pointerTarget.current = { x: 0, y: 0 };
    };

    container.addEventListener("pointermove", onPointerMove);
    container.addEventListener("pointerleave", onPointerLeave);

    const observer = new IntersectionObserver(
      ([entry]) => {
        inView.current = entry.isIntersecting;
      },
      { threshold: 0.01 },
    );
    observer.observe(container);

    let rafId: number | null = null;
    const tick = (now: number) => {
      rafId = requestAnimationFrame(tick);
      if (document.hidden || !inView.current) return;
      if (startTime.current === null) startTime.current = now;
      const elapsed = now - startTime.current;

      pointerCurrent.current.x +=
        (pointerTarget.current.x - pointerCurrent.current.x) * LERP_FACTOR;
      pointerCurrent.current.y +=
        (pointerTarget.current.y - pointerCurrent.current.y) * LERP_FACTOR;

      for (let i = 0; i < layers.length; i++) {
        const el = elements.current[i];
        if (!el) continue;
        const layer = layers[i];
        const shiftX = pointerCurrent.current.x * layer.depth * MAX_SHIFT_PX;
        const shiftY = pointerCurrent.current.y * layer.depth * MAX_SHIFT_PX;
        const floatPhaseRad = (elapsed / layer.floatPeriodMs) * Math.PI * 2 + layer.floatPhase;
        const floatX = Math.sin(floatPhaseRad) * layer.floatAmpPx;
        const floatY = Math.cos(floatPhaseRad * 0.7) * layer.floatAmpPx * 0.6;
        el.style.transform = `translate3d(${(shiftX + floatX).toFixed(2)}px, ${(shiftY + floatY).toFixed(2)}px, 0)`;
      }
    };
    rafId = requestAnimationFrame(tick);

    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      observer.disconnect();
      container.removeEventListener("pointermove", onPointerMove);
      container.removeEventListener("pointerleave", onPointerLeave);
    };
    // layers' identity changes are intentionally not tracked — it's a
    // fixed manifest defined as a module-level/useMemo constant by every
    // caller, and re-subscribing on every render would thrash the
    // IntersectionObserver/listeners for no benefit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerRef, enabled, isFinePointer]);

  return setLayerRef;
}
