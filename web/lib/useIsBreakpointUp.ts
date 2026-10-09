"use client";

import { useEffect, useState } from "react";

/** Tracks a `min-width` breakpoint client-side (T13.5b plan, Part 4;
 * generalized from a fixed `xl`-only hook in T13.5c plan, Batch 0.9, when
 * the processor page's reasoning-dock breakpoint moved from `xl` (1280px)
 * to `lg` (1024px)) — the processor page needs this in JS, not just CSS,
 * to decide whether the reasoning log is a docked panel or a tab *item*
 * (removing a Tabs entry can't be done with a CSS display:none trick).
 * Defaults to `false` (the narrower, tab-based layout) on the server and
 * on first client render, so hydration never mismatches; a wide-viewport
 * visitor sees one layout swap right after mount, which is the standard
 * tradeoff for any viewport-dependent layout fork like this. */
export function useIsBreakpointUp(minWidthPx: number): boolean {
  const [isUp, setIsUp] = useState(false);

  useEffect(() => {
    const query = window.matchMedia(`(min-width: ${minWidthPx}px)`);
    // matchMedia is unavailable during SSR, so this must run post-mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsUp(query.matches);
    const onChange = (e: MediaQueryListEvent) => setIsUp(e.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [minWidthPx]);

  return isUp;
}
