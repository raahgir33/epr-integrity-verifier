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
 * a different string shape than what the server rendered. Runs once;
 * does nothing under reduced motion (the static server-rendered value is
 * the only thing reduced-motion viewers ever see). */
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
  const animatedRef = useRef(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || reducedMotion || animatedRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry?.isIntersecting || animatedRef.current) return;
        animatedRef.current = true;
        observer.disconnect();

        const start = performance.now();
        function frame(now: number) {
          const elapsed = now - start;
          const progress = Math.min(1, elapsed / DURATION_MS);
          const current = value * easeOutCubic(progress);
          setDisplay(formatter(progress >= 1 ? value : current));
          if (progress < 1) requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
      },
      { threshold: 0.4 },
    );
    observer.observe(node);
    return () => observer.disconnect();
    // formatter is expected to be a stable (or inline-constant-shaped)
    // function per call site, same pattern as MetricTile's own default.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, reducedMotion]);

  return (
    <span ref={ref} className={`num-cell tabular-nums ${className}`}>
      {display}
    </span>
  );
}
