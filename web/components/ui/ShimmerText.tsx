"use client";

import { usePrefersReducedMotion } from "@/lib/usePrefersReducedMotion";

/** Shimmering text (T13.5b plan, Part 4/5) — built from scratch (the
 * Unlumen ban covers this specifically). A `background-clip: text`
 * gradient sweep via one CSS animation; plain static text under reduced
 * motion. Used for the live-run current-stage label and the AI
 * Loading-equivalent stage indicator (Part 5). */
export function ShimmerText({ children, className = "" }: { children: string; className?: string }) {
  const reduced = usePrefersReducedMotion();

  if (reduced) {
    return <span className={className}>{children}</span>;
  }

  return (
    <span
      className={`inline-block bg-clip-text text-transparent ${className}`}
      style={{
        backgroundImage:
          "linear-gradient(90deg, var(--color-ink-muted) 0%, var(--color-ink-muted) 35%, var(--color-ink) 50%, var(--color-ink-muted) 65%, var(--color-ink-muted) 100%)",
        backgroundSize: "200% 100%",
        animation: "shimmer-text 1.8s linear infinite",
      }}
    >
      {children}
    </span>
  );
}
