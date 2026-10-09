import type { ReactNode } from "react";

/** The one shared page container (T13.5 plan, Part 1): mobile-first side
 * padding 16 -> 24 -> 32 -> 48px, max width ~1280px at xl and ~1440px at
 * 2xl, full-bleed (no cap) below that. Every page/Nav/Footer uses this
 * instead of its own max-width and padding utility classes, so the three
 * numbers only ever live in one place. */
export function PageContainer({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`mx-auto w-full px-4 sm:px-6 lg:px-8 2xl:px-12 xl:max-w-[1280px] 2xl:max-w-[90rem] ${className}`}>
      {children}
    </div>
  );
}
