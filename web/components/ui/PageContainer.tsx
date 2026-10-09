import type { ReactNode } from "react";

/** The one shared page container (T13.5 plan, Part 1; widened in T13.5b
 * Part 1): mobile-first side padding 16 -> 24 -> 32 -> 48 -> 64px, max
 * width ~1440px at xl and ~1600px at 2xl, full-bleed (no cap) below that.
 * Every page/Nav/Footer uses this instead of its own max-width and
 * padding utility classes, so the numbers only ever live in one place. */
export function PageContainer({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`mx-auto w-full px-4 sm:px-6 lg:px-8 xl:px-12 2xl:px-16 xl:max-w-[1440px] 2xl:max-w-[1600px] ${className}`}
    >
      {children}
    </div>
  );
}
