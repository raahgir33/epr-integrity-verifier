"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

/** Text reveal (T13.5b plan, Part 5) — built from scratch: not one of the
 * three pre-approved Magic UI components (Animated List, Typing
 * Animation, Progressive Blur) and not in the from-scratch list either,
 * so it's a small bespoke fade+rise on scroll-into-view. Landing-page
 * section headings only — never audit content, tables or memos. Wraps a
 * heading (e.g. SectionTitle) rather than replacing it, so title-casing
 * stays exactly where Part 2 put it. */
export function TextReveal({ children }: { children: ReactNode }) {
  const reducedMotion = useReducedMotion();

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
