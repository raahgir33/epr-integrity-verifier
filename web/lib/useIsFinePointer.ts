"use client";

import { useEffect, useState } from "react";

/** Same defer-to-client-mount pattern as usePrefersReducedMotion/
 * useIsBreakpointUp — matchMedia is unavailable during SSR. Used by
 * HeroScene's parallax layer (T13.6 plan, Part B) to gate pointer
 * tracking: a touch/coarse pointer gets idle float only, never
 * pointer-driven movement. Defaults to false (treat as coarse) until
 * mounted, so a fine-pointer visitor's first paint matches every other
 * visitor's. */
export function useIsFinePointer(): boolean {
  const [isFine, setIsFine] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(pointer: fine)");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsFine(query.matches);
    const onChange = (e: MediaQueryListEvent) => setIsFine(e.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return isFine;
}
