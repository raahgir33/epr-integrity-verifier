"use client";

import { useEffect, useState } from "react";

/** Shared `prefers-reduced-motion` check (T13.5b plan, Parts 4/5) for the
 * JS-driven animations (motion height transitions, CountUp, the hero
 * spotlight, card glow/tilt effects) that can't rely on globals.css's
 * `@media (prefers-reduced-motion: no-preference)` CSS gating the way the
 * T13.5 Radix transitions do. Defaults to `false` on the server and until
 * mounted — matches-media can only be read client-side — so these effects
 * run their very first client render the same way the server rendered it,
 * then settle to the real preference a tick later. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    // matchMedia is unavailable during SSR, so this must run post-mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setReduced(query.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
