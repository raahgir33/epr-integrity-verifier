"use client";

import { useEffect, useState } from "react";

/** Tracks Tailwind's `xl` breakpoint (1280px) client-side (T13.5b plan,
 * Part 4) — the processor page needs this in JS, not just CSS, to decide
 * whether the reasoning log is a docked panel or a tab *item* (removing a
 * Tabs entry can't be done with a CSS display:none trick). Defaults to
 * `false` (the narrower, tab-based layout) on the server and on first
 * client render, so hydration never mismatches; a wide-viewport visitor
 * sees one layout swap right after mount, which is the standard tradeoff
 * for any viewport-dependent layout fork like this. */
export function useIsXlUp(): boolean {
  const [isXlUp, setIsXlUp] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(min-width: 1280px)");
    // matchMedia is unavailable during SSR, so this must run post-mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsXlUp(query.matches);
    const onChange = (e: MediaQueryListEvent) => setIsXlUp(e.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return isXlUp;
}
