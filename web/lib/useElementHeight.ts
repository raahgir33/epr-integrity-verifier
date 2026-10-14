"use client";

import { useEffect, useState, type RefObject } from "react";

/** Tracks an element's rendered border-box height (T16b). The live-run
 * task panel is capped to the Run Live Verification card's own height so
 * the landing section is exactly as tall during a run as it is before and
 * after one — the whole point of the task, since the old in-card progress
 * view grew the card and pushed the page down.
 *
 * Reads `getBoundingClientRect().height`, not the entry's `contentRect` and
 * not `offsetHeight`. `contentRect` is the *content* box, so it excludes the
 * card's padding and border and would cap the panel short by exactly the
 * card's vertical padding. `offsetHeight` is the right box but is rounded to
 * a whole number: measured at 1440px the card is 424.56px tall, which
 * `offsetHeight` reports as 425, and that 0.44px made the panel the tallest
 * thing in the grid row and grew the section — the precise regression this
 * task exists to remove. `getBoundingClientRect()` is fractional and
 * border-box; it is also transform-aware, which is harmless here because the
 * card's only transform is the horizontal slide (no scale).
 *
 * Returns null until first measurement so a caller can render uncapped for
 * the one frame before the observer fires. */
export function useElementHeight(ref: RefObject<HTMLElement | null>): number | null {
  const [height, setHeight] = useState<number | null>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const measure = () => setHeight(element.getBoundingClientRect().height);
    measure();

    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);

  return height;
}
