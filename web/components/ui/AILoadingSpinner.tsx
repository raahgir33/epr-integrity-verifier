"use client";

import { usePrefersReducedMotion } from "@/lib/usePrefersReducedMotion";

/** Compact multi-ring progress spinner (T13.5b plan, Kokonut addendum) —
 * built from scratch, not Kokonut's "AI Loading" component: that one's
 * `TASK_SEQUENCES` is self-timed, invented log lines ("Scanning web
 * pages...", "Visiting 5 websites...") with no connection to any real
 * data — exactly the "fake progress" the brief rules out, and not
 * something that can be fixed by re-skinning it, since the fabricated
 * content is the component's entire design. This is purely a decorative
 * spinner (no text of its own); callers pair it with a real stage label
 * (STAGE_LABEL from lib/runStages.ts) via ShimmerText. A single static
 * ring under reduced motion, rather than the rotating rings. */
export function AILoadingSpinner({ className = "h-5 w-5" }: { className?: string }) {
  const reducedMotion = usePrefersReducedMotion();

  return (
    <svg viewBox="0 0 48 48" aria-hidden className={className}>
      {reducedMotion ? (
        <circle cx="24" cy="24" r="18" fill="none" stroke="var(--color-primary)" strokeWidth="4" strokeDasharray="70 40" />
      ) : (
        <g>
          <circle
            cx="24"
            cy="24"
            r="20"
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth="3"
            strokeDasharray="60 66"
            opacity="0.9"
            style={{ transformOrigin: "24px 24px", animation: "ai-spin-cw 1.6s linear infinite" }}
          />
          <circle
            cx="24"
            cy="24"
            r="14"
            fill="none"
            stroke="var(--color-glow)"
            strokeWidth="3"
            strokeDasharray="44 44"
            opacity="0.9"
            style={{ transformOrigin: "24px 24px", animation: "ai-spin-ccw 1.3s linear infinite" }}
          />
          <circle
            cx="24"
            cy="24"
            r="8"
            fill="none"
            stroke="var(--color-primary)"
            strokeWidth="3"
            strokeDasharray="25 25"
            opacity="0.9"
            style={{ transformOrigin: "24px 24px", animation: "ai-spin-cw 1s linear infinite" }}
          />
        </g>
      )}
    </svg>
  );
}
