"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Tells a capped scroll region whether content continues past its bottom
 * edge (T16b), so it can fade that edge instead of cutting a line in half.
 *
 * The scrollbar alone cannot carry this. On macOS the scrollbar is an
 * overlay: it paints while the viewer is actively scrolling and then
 * disappears, so a region scrolled part-way looks, at rest, exactly like
 * a region whose content simply ends — the half-cut line is the only
 * hint, and that reads as broken rather than as "more below". The fade is
 * a static, always-present cue, which is the rule that a state should
 * never depend on one channel alone.
 *
 * `signal` is anything whose change might alter the answer — content
 * length, open/closed, run status. Re-measuring is cheap; state is set
 * only when the answer actually changes, so scrolling does not re-render
 * on every event. */
export function useScrollFade<T extends HTMLElement = HTMLDivElement>(signal: unknown) {
  const ref = useRef<T>(null);
  const [fade, setFade] = useState(false);

  const measure = useCallback(() => {
    const element = ref.current;
    if (!element) {
      setFade((previous) => (previous ? false : previous));
      return;
    }
    const more = element.scrollHeight - element.scrollTop - element.clientHeight > 4;
    setFade((previous) => (previous === more ? previous : more));
  }, []);

  useEffect(() => {
    measure();
  }, [measure, signal]);

  return { ref, fade, onScroll: measure };
}
