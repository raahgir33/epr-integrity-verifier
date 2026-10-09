"use client";

import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "@/lib/usePrefersReducedMotion";

const DURATION_MS = 900;

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/** Count-up (T13.5b plan, Part 5) — built from scratch (the Unlumen ban
 * covers this specifically). Server-renders `formatter(value)` directly
 * (so hydration, no-JS and SEO always show the correct final string);
 * once the element scrolls into view, animates a local number from 0 to
 * `value` via requestAnimationFrame, calling the SAME formatter every
 * frame and snapping to `formatter(value)` exactly on completion — never
 * a different string shape than what the server rendered. The entrance
 * animation runs once; does nothing under reduced motion.
 *
 * `valueRef` is kept current on every render (not just when the entrance
 * effect's dependency array changes) so the animation always targets the
 * actual latest value, even if it changes between mount and the moment
 * the element scrolls into view. Separately, a later change to `value` —
 * a live-run update re-rendering the same mounted instance, rather than a
 * fresh page load — always snaps `display` to the new formatted value
 * immediately, so this never gets stuck showing a stale number after its
 * one entrance animation has already used up its "once". */
export function CountUp({
  value,
  formatter = (n) => String(n),
  className = "",
}: {
  value: number;
  formatter?: (n: number) => string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [display, setDisplay] = useState(() => formatter(value));
  const reducedMotion = usePrefersReducedMotion();
  const enteredRef = useRef(false);
  const lastShownValueRef = useRef(value);
  const valueRef = useRef(value);
  // Kept current via an effect (not a direct render-time write, which
  // react-hooks/refs now disallows) — this still runs well before any
  // later IntersectionObserver callback could read it.
  useEffect(() => {
    valueRef.current = value;
  }, [value]);

  // Entrance animation — plays at most once per mounted instance, the
  // first time it scrolls into view. Reads valueRef (not the `value`
  // closure) so it always targets the latest figure even though this
  // effect itself only runs once (its own deps never change after mount).
  useEffect(() => {
    const node = ref.current;
    if (!node || reducedMotion || enteredRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry?.isIntersecting || enteredRef.current) return;
        enteredRef.current = true;
        observer.disconnect();
        const target = valueRef.current;

        const start = performance.now();
        function frame(now: number) {
          const elapsed = now - start;
          const progress = Math.min(1, elapsed / DURATION_MS);
          const current = target * easeOutCubic(progress);
          setDisplay(formatter(progress >= 1 ? target : current));
          lastShownValueRef.current = target;
          if (progress < 1) requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
      },
      { threshold: 0.4 },
    );
    observer.observe(node);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion]);

  // Keeps `display` correct for the CURRENT value at all times — covers
  // reduced motion (no entrance animation ever runs) and any value change
  // either before the entrance has played (not yet visible) or after it
  // has already used its one play.
  useEffect(() => {
    if (!enteredRef.current || value !== lastShownValueRef.current) {
      setDisplay(formatter(value));
      lastShownValueRef.current = value;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <span ref={ref} className={`num-cell ${className}`}>
      {display}
    </span>
  );
}
