"use client";

import { useEffect, useState } from "react";

/** Shared check for "hover-capable, fine-pointer device" (T13.5b plan,
 * Kokonut addendum) — MouseEffectCard/SpotlightCard attach their pointer-
 * tracking listener only when this is true, on top of the CSS-level
 * `(hover: hover)` gate that keeps the glow itself invisible on touch
 * regardless, so a touch device does no extra work for an effect it can
 * never show. Defaults to `false` (matches most phones/tablets) until
 * mounted, so there's no hydration mismatch. */
export function useIsFinePointer(): boolean {
  const [isFine, setIsFine] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(hover: hover) and (pointer: fine)");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- matchMedia is unavailable during SSR, so this must run post-mount.
    setIsFine(query.matches);
    const onChange = (e: MediaQueryListEvent) => setIsFine(e.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return isFine;
}
