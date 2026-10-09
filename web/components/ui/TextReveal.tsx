"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { usePrefersReducedMotion } from "@/lib/usePrefersReducedMotion";

/** Text reveal (T13.5b plan, Part 5) — built from scratch: not one of the
 * three pre-approved Magic UI components (Animated List, Typing
 * Animation, Progressive Blur) and not in the from-scratch list either,
 * so it's a small bespoke fade+rise on scroll-into-view. Landing-page
 * section headings only — never audit content, tables or memos. Wraps a
 * heading (e.g. SectionTitle) rather than replacing it, so title-casing
 * stays exactly where Part 2 put it.
 *
 * Uses this app's own usePrefersReducedMotion (useState(false) + an
 * effect), not motion/react's own useReducedMotion — confirmed live
 * (Playwright's reducedMotion:'reduce' context option) that motion's hook
 * reads the real browser preference synchronously on the client's first
 * render, which doesn't match what the server rendered (it has no way to
 * know the client's media query) and threw a real hydration-mismatch
 * error whenever a visitor's OS actually has reduced motion set — this
 * component's branch picks a structurally different tree (plain children
 * vs a wrapping motion.div), so the mismatch was real, not cosmetic. */
export function TextReveal({ children }: { children: ReactNode }) {
  const reducedMotion = usePrefersReducedMotion();

  if (reducedMotion) {
    return <>{children}</>;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.6 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}
